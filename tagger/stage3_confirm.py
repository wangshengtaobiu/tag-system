"""Stage 3: LLM confirmation.

Given the reranked candidate list and a slice of the book, the model must
return, for every tag it claims applies, a VERBATIM evidence quote. The quote is
then machine-verified against the source text; unverified tags are dropped.
Tags outside the candidate list are dropped. Tags that are mutually confusable
according to their `distinction` line are resolved by one extra pairwise call.

Voting: vote_passes=1 (default) does a single deterministic pass. With
vote_passes>1 the prompt is sampled at vote_temperature and a tag must appear in
>= ceil(N/2) passes (majority) to survive. At temperature 0 the passes are
identical, so voting is a no-op — never combine vote_passes>1 with
vote_temperature=0.
"""

import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .chunking import chunk_text
from .config import PipelineConfig

SYSTEM_PROMPT = (
    "你是成人小说标签专家。根据给定的小说内容，从候选标签列表中选出真正匹配的标签。"
    "严格规则：\n"
    "1. evidence 必须是【小说正文中逐字出现的原文片段】，不得改写、不得概括、"
    "不得引用候选标签的描述文字。引用不到原文的标签请直接不要输出。\n"
    "2. confidence: 0.9=文中有明确描写; 0.7=强烈暗示; <0.6 不输出。\n"
    "3. 只能从候选列表里选，禁止输出列表之外的 canonical_id。\n"
    "4. 有多少匹配就输出多少，不凑数；宁缺勿滥。\n"
    "5. 若两个候选是近似/易混概念，只选更准确的那一个。\n"
    "6. 只输出 JSON，不要任何解释文字。"
)

MAX_EVIDENCE_CHARS = 120

# Token accounting, so the real cache-hit rate and cost are visible instead of
# assumed. Guarded because stage 3 may run several calls concurrently.
_USAGE = Counter()
_USAGE_LOCK = threading.Lock()


def _record_usage(u: dict):
    if not u:
        return
    with _USAGE_LOCK:
        _USAGE["calls"] += 1
        _USAGE["prompt"] += u.get("prompt_tokens", 0) or 0
        _USAGE["cache_hit"] += u.get("prompt_cache_hit_tokens", 0) or 0
        _USAGE["cache_miss"] += u.get("prompt_cache_miss_tokens", 0) or 0
        _USAGE["completion"] += u.get("completion_tokens", 0) or 0


def usage_snapshot() -> Counter:
    with _USAGE_LOCK:
        return Counter(_USAGE)


def reset_usage():
    with _USAGE_LOCK:
        _USAGE.clear()


def _norm_for_match(s: str) -> str:
    """Normalise for substring matching: width, quotes/dashes, all whitespace."""
    s = unicodedata.normalize("NFKC", str(s))
    s = (s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
          .replace("—", "-").replace("–", "-").replace("　", ""))
    return re.sub(r"\s+", "", s)


def _source_text(record: dict, config: PipelineConfig) -> str:
    if config.evidence_against_full_text and record.get("text"):
        return record["text"]
    return record.get("slice_text", "")


def _verify_evidence(evidence: str, source_norm: str, config: PipelineConfig) -> bool:
    ev = _norm_for_match(evidence or "")
    if len(ev) < config.min_evidence_chars:
        return False
    return ev in source_norm


def _context_budget(record: dict, config: PipelineConfig) -> int:
    """How much of the book the judge may read.

    A flat budget is what capped long books: a 300k-character novel got the same
    12k as a 20k one, so with ~6 of 1325 chunks in view the judge was asked
    about 120 candidates drawn from the whole book, 41% of them with no sight of
    their own best chunk. Scale with length, with a floor and a cap.
    """
    n = len(record.get("text", "") or "")
    base = getattr(config, "context_budget_chars", 12000)
    scaled = int(n * getattr(config, "context_ratio", 0.08))
    cap = getattr(config, "context_budget_max", 100000)
    return min(max(base, scaled), cap)


def _select_chunks(record: dict, config: PipelineConfig) -> tuple[list[int], list[str]]:
    """Pick the chunks worth showing the judge.

    Every candidate remembers the chunk that recalled it, so the chunks that
    recalled the most candidates are the ones most likely to hold the evidence.
    Candidates with best_chunk == -1 matched on the title alone: they have no
    chunk to point at, so they neither vote nor drag the judge anywhere.
    """
    chunks = chunk_text(record.get("text", ""), config.chunk_chars)
    if not chunks:
        return [], []

    votes: Counter = Counter()
    for c in record.get("candidates", []):
        bc = c.get("best_chunk")
        if isinstance(bc, int) and 0 <= bc < len(chunks):   # -1 = title only
            votes[bc] += max(1, int(c.get("chunk_hits", 1)))

    budget = _context_budget(record, config)
    picked, used = [], 0
    for ci, _ in votes.most_common():
        if picked and used + len(chunks[ci]) > budget:
            continue
        picked.append(ci)
        used += len(chunks[ci])
        if used >= budget:
            break
    return sorted(picked), chunks


def _hit_label(c: dict) -> str:
    """What a candidate line reports about where the tag was found."""
    bc = c.get("best_chunk")
    if isinstance(bc, int) and bc < 0:
        return "仅书名命中"
    return f"命中{int(c.get('chunk_hits', 1))}块"


def build_prompt(record: dict, config: PipelineConfig) -> str:
    cand_lines = []
    for c in record["candidates"]:
        aliases = c.get("retrieval_aliases", [])
        alias_str = f"({','.join(aliases[1:6])})" if len(aliases) > 1 else ""
        summary = (c.get("semantic_summary") or "")[:80]
        cand_lines.append(
            f"{c['canonical_id']} | {c.get('original_name', '')} {alias_str} "
            f"| {_hit_label(c)} | {summary}"
        )

    title = Path(record["book"]).stem
    picked, chunks = _select_chunks(record, config)
    if picked:
        context = "\n\n".join(f"【第{i + 1}块 / 共{len(chunks)}块】\n{chunks[i]}"
                              for i in picked)
        ctx_note = (f"（下附 {len(picked)} 个片段，是全书 {len(chunks)} 个片段中"
                    f"最可能出现相关内容的；证据必须逐字取自这些片段）")
    else:  # no chunk metadata: fall back to the head+tail slice
        context = record.get("slice_text", "")
        if config.prompt_context_chars and len(context) > config.prompt_context_chars:
            context = context[: config.prompt_context_chars]
        ctx_note = ""

    return f"""{SYSTEM_PROMPT}

书名: {title}
小说内容 {ctx_note}:
{context}

候选标签({len(cand_lines)}个，"命中N块"表示该标签在多少个片段中被检索命中，命中越多通常越核心):
{chr(10).join(cand_lines)}

输出JSON: {{"tags": [{{"canonical_id": "...", "confidence": 0.9, "evidence": "原文逐字片段"}}]}}"""


def _retry_after(headers, body: str) -> float | None:
    """Seconds to wait, from a Retry-After header or the gateway's JSON body."""
    v = headers.get("Retry-After") if headers else None
    if v:
        try:
            return float(v)
        except ValueError:
            pass
    m = re.search(r'"retryAfterSeconds"\s*:\s*(\d+)', body or "")
    return float(m.group(1)) if m else None


def _key_pool(config: PipelineConfig) -> list[str]:
    """Priority-ordered keys. The per-process key (a shard's own account) first,
    then any others, so a shard spends its own key before touching the rest."""
    pool = [config.api_key] if config.api_key else []
    for k in getattr(config, "api_keys", None) or []:
        if k and k not in pool:
            pool.append(k)
    return pool


_KEY_STATE = {"i": 0}
_KEY_LOCK = threading.Lock()
_DEAD_KEYS: set[str] = set()          # confirmed INSUFFICIENT_BALANCE, never retried


def _key_pool(config: PipelineConfig) -> list[str]:
    """Priority-ordered keys, minus any already confirmed out of balance.

    Without the dead-key filter a shard retries a spent key on every rotation:
    observed cycling 1->2->3->4->1 for 30+ rounds, each round an HTTP 402.
    """
    pool = [config.api_key] if config.api_key else []
    for k in getattr(config, "api_keys", None) or []:
        if k and k not in pool:
            pool.append(k)
    live = [k for k in pool if k not in _DEAD_KEYS]
    return live or pool                  # all dead: keep the pool so we can report


def _current_key(config: PipelineConfig) -> str:
    pool = _key_pool(config)
    if not pool:
        return ""
    with _KEY_LOCK:
        return pool[_KEY_STATE["i"] % len(pool)]


def _rotate_key(config: PipelineConfig, why: str) -> str:
    pool = _key_pool(config)
    if len(pool) < 2:
        return ""
    with _KEY_LOCK:
        _KEY_STATE["i"] = (_KEY_STATE["i"] + 1) % len(pool)
        nxt = pool[_KEY_STATE["i"]]
    print(f"    [key] {why} -> 切换到第 {_KEY_STATE['i'] + 1}/{len(pool)} 个 key "
          f"...{nxt[-6:]}")
    return nxt


def _is_quota_error(code: int, detail: str) -> bool:
    """Only a genuine balance/auth failure may rotate the key.

    Rotating on a bare HTTP status is wrong: a 402 that is really a throttle
    pushes the shard onto another shard's account, so two shards then share one
    rate limit and both crawl. Require the body to confirm it.
    """
    d = detail or ""
    if "INSUFFICIENT_BALANCE" in d or "余额不足" in d:
        return True
    if code in (401, 403) and ("UNAUTHORIZED" in d or "未认证" in d or "过期" in d):
        return True
    if code == 402:                      # 402 without a recognisable code is still
        return True                      # payment-related; no other meaning seen
    return False


def _chat(prompt: str, config: PipelineConfig, temperature: float = 0.0,
          max_retries: int = 3, max_tokens: int | None = None) -> tuple[str, str]:
    """Return (text, status). status is "ok", "truncated", "rate_limited",
    "blocked", "http_<code>" or "error".

    "truncated" is a real failure, not a success: the reply was cut off by
    max_tokens, the JSON is incomplete, and the fallback parser then yields tags
    with no evidence — which every downstream check drops. Left unreported it
    looks exactly like "the book has no tags".
    """
    body = {
        "model": config.opencode_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens or getattr(config, "max_output_tokens", 4000),
        "stream": False,
    }
    if not getattr(config, "thinking_enabled", False):
        body["thinking"] = {"type": "disabled"}
    body.update(getattr(config, "extra_payload", None) or {})
    payload = json.dumps(body).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {_current_key(config) or config.api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    for attempt in range(max_retries):
        last = attempt == max_retries - 1
        headers["Authorization"] = f"Bearer {_current_key(config) or config.api_key}"
        try:
            req = urllib.request.Request(config.api_url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=config.opencode_timeout) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            choice = d["choices"][0]
            text = choice["message"].get("content") or ""
            _record_usage(d.get("usage") or {})
            if choice.get("finish_reason") == "length":
                print(f"    [truncated] hit max_tokens={body['max_tokens']}")
                return text, "truncated"
            return text, "ok"
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            # A rejected/ exhausted key: rotate and retry immediately, without
            # burning an attempt. Without this a shard dies the moment its own
            # sub-key runs out, mid-corpus.
            if _is_quota_error(e.code, detail):
                if "INSUFFICIENT_BALANCE" in detail or "余额不足" in detail:
                    with _KEY_LOCK:
                        _DEAD_KEYS.add(_current_key(config) or config.api_key)
                if _rotate_key(config, f"HTTP {e.code}"):
                    continue
            if e.code == 400:                      # moderation block / param rejection
                print(f"    [blocked] HTTP 400 {detail[:110]}")
                return "", "blocked"
            if e.code == 429:
                wait = _retry_after(e.headers, detail) or (attempt + 1) * 10
                if last:
                    return "", "rate_limited"
                print(f"    [429] waiting {wait:.0f}s")
                time.sleep(wait)
                continue
            if last:
                return "", f"http_{e.code}"
            time.sleep((attempt + 1) * 5)
        except (urllib.error.URLError, json.JSONDecodeError, KeyError,
                ConnectionError, TimeoutError):
            if last:
                return "", "error"
            time.sleep((attempt + 1) * 5)
    return "", "error"


def call_api(prompt: str, config: PipelineConfig, temperature: float = 0.0,
             max_retries: int = 3, max_tokens: int | None = None
             ) -> tuple[list[dict], str]:
    text, status = _chat(prompt, config, temperature, max_retries, max_tokens)
    return _parse_response(text), status


def _to_float(v, default: float = 0.0) -> float:
    """Models sometimes emit numbers as strings ("0.9") or with annotations."""
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"\d+(?:\.\d+)?", str(v or ""))
    return float(m.group(0)) if m else default


def _coerce_tag(t: dict) -> dict | None:
    """Normalise one model-emitted tag, or None if it is unusable.

    Everything downstream compares/floats these fields, so a single quoted
    number used to abort a whole run.
    """
    if not isinstance(t, dict):
        return None
    cid = str(t.get("canonical_id") or "").strip()
    if not cid:
        return None
    ev = t.get("evidence", "")
    if isinstance(ev, (list, tuple)):
        ev = " ".join(str(x) for x in ev)
    return {"canonical_id": cid,
            "confidence": _to_float(t.get("confidence"), 0.0),
            "evidence": str(ev or "")}


def _parse_response(content: str) -> list[dict]:
    """Parse the reply, tolerating a fenced/chatty wrapper or a cut-off tail.

    The degraded path keeps evidence: dropping it would make every recovered
    tag fail evidence verification, turning a partial answer into zero tags.
    """
    content = (content or "").strip()
    m = re.search(r'\{[\s\S]*"tags"[\s\S]*\}', content)
    if m:
        content = m.group(0)
    if "```" in content:
        content = re.sub(r'```\w*', '', content).strip()
    raw = None
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            raw = parsed.get("tags", []) or []
        elif isinstance(parsed, list):
            raw = parsed
    except json.JSONDecodeError:
        pass

    if raw is None:
        # object-by-object salvage (e.g. the array was truncated mid-way)
        raw = []
        for obj in re.findall(r'\{[^{}]*"canonical_id"[^{}]*\}', content):
            cid = re.search(r'"canonical_id":\s*"([^"]+)"', obj)
            if not cid:
                continue
            conf = re.search(r'"confidence":\s*"?([\d.]+)', obj)
            ev = re.search(r'"evidence":\s*"([^"]*)"', obj)
            raw.append({"canonical_id": cid.group(1),
                        "confidence": conf.group(1) if conf else 0.7,
                        "evidence": ev.group(1) if ev else ""})

    out = []
    for t in raw:
        c = _coerce_tag(t)
        if c is not None:
            out.append(c)
    return out


def _sample_tags(prompt: str, config: PipelineConfig,
                 max_tokens: int | None = None) -> tuple[list[dict], str]:
    """Single pass, or N sampled passes reduced by MAJORITY (never union).

    Returns (tags, status). "empty" means the call succeeded but the model
    produced no tags — on adult content that is usually a soft refusal, and it
    must stay distinguishable from "the book genuinely has no tags".
    "truncated" gets one retry at double the token budget, because a cut-off
    reply would otherwise look like a successful empty answer.
    """
    n = max(1, config.vote_passes)
    if n == 1:
        tags, status = call_api(prompt, config, temperature=0.0, max_tokens=max_tokens)
        if status == "truncated":
            bigger = (max_tokens or getattr(config, "max_output_tokens", 4000)) * 2
            print(f"    retrying truncated reply with max_tokens={bigger}")
            tags2, status2 = call_api(prompt, config, temperature=0.0, max_tokens=bigger)
            if status2 != "truncated" or len(tags2) > len(tags):
                tags, status = tags2, status2
        if status == "ok" and not tags:
            status = "empty"
        return tags, status

    votes: dict[str, int] = Counter()
    best: dict[str, dict] = {}
    last = "error"
    for _ in range(n):
        tags, status = call_api(prompt, config, temperature=config.vote_temperature,
                                max_tokens=max_tokens)
        if status == "ok":
            last = "ok"
        elif status != "empty":
            last = status
        for t in tags:
            cid = t.get("canonical_id", "")
            if not cid:
                continue
            votes[cid] += 1
            prev = best.get(cid)
            if prev is None or t.get("confidence", 0) > prev.get("confidence", 0):
                best[cid] = t
    need = (n + 1) // 2  # ceil(n/2)
    kept = [best[cid] for cid, v in votes.items() if v >= need]
    if not kept and last == "ok":
        last = "empty"
    return kept, last


def _conflict_pairs(tags: list[dict], cand_by_cid: dict) -> list[tuple[dict, dict]]:
    """Pairs (a, b) where a's `distinction` names b (parsed from semantic_summary)."""
    name_index = {t.get("tag_name", ""): t for t in tags}
    pairs, seen = [], set()
    for a in tags:
        summary = (cand_by_cid.get(a["canonical_id"], {}) or {}).get("semantic_summary", "")
        for m in re.finditer(r"与(.{1,14}?)的?区别", summary or ""):
            other = name_index.get(m.group(1).strip())
            if other and other is not a:
                key = tuple(sorted([a["canonical_id"], other["canonical_id"]]))
                if key not in seen:
                    seen.add(key)
                    pairs.append((a, other))
    return pairs


def _resolve_conflicts(pairs, cand_by_cid, config) -> dict:
    """One extra batched call asking which side of each confusable pair applies.

    The pairs come from the ontology's own `distinction` text ("与X的区别：…"),
    so the model is shown that rule alongside the two evidence quotes. Returns
    {canonical_id: keep_bool}; anything undecided keeps both.
    """
    blocks = []
    for i, (a, b) in enumerate(pairs, 1):
        ca = cand_by_cid.get(a["canonical_id"], {})
        cb = cand_by_cid.get(b["canonical_id"], {})
        blocks.append(
            f"[{i}] 甲 {a['canonical_id']}（{a.get('tag_name', '')}）\n"
            f"    定义:{(ca.get('semantic_summary') or '')[:70]}\n"
            f"    证据:{(a.get('evidence') or '')[:50]}\n"
            f"    乙 {b['canonical_id']}（{b.get('tag_name', '')}）\n"
            f"    定义:{(cb.get('semantic_summary') or '')[:70]}\n"
            f"    证据:{(b.get('evidence') or '')[:50]}"
        )
    prompt = (
        "下面每组两个标签是易混概念。请判断该小说真正适用的是哪一个：\n"
        "只能回答 甲、乙 或 both（两者确实都成立时才用 both）。\n"
        "宁可判给更具体、更贴合证据的那一个。只输出 JSON。\n\n"
        + "\n".join(blocks)
        + '\n\n输出JSON: {"resolutions":[{"pair":1,"keep":"甲"}]}'
    )

    decisions = {}
    for a, b in pairs:
        decisions[a["canonical_id"]] = True   # default: keep both
        decisions[b["canonical_id"]] = True

    content, _ = _chat(prompt, config, temperature=0.0)
    for m in re.finditer(r'"pair"\s*:\s*(\d+)[^}]*?"keep"\s*:\s*"(甲|乙|both)"', content):
        idx, keep = int(m.group(1)), m.group(2)
        if not 1 <= idx <= len(pairs) or keep == "both":
            continue
        a, b = pairs[idx - 1]
        loser = b if keep == "甲" else a
        decisions[loser["canonical_id"]] = False
    return decisions


def _judge_forced(record: dict, config: PipelineConfig,
                  stats: Counter) -> tuple[list[dict], str]:
    """Ask for a verdict on every candidate, in batches.

    Unlike the select framing there is no way to answer proportionally: each
    candidate gets an explicit y/n, so the reply's length is determined by the
    batch size rather than by how generous the model feels.
    """
    from .prompt_modes import build_forced_prompt, parse_forced

    cands = record["candidates"]
    cap = getattr(config, "judged_candidates", 0)
    if cap:
        record = dict(record, candidates=cands[:cap])
        cands = record["candidates"]
    bs = max(1, getattr(config, "forced_batch_size", 30))
    # reasoning tokens are billed as output and share this budget
    budget = 20000 if getattr(config, "thinking_enabled", False) else 8000
    tags: list[dict] = []
    status = "ok"
    for start in range(0, len(cands), bs):
        prompt, batch = build_forced_prompt(record, config, start=start, count=bs)
        text, st = _chat(prompt, config, max_tokens=budget)
        if st == "truncated":
            text, st = _chat(prompt, config, max_tokens=budget * 2)
        if st != "ok":
            stats[f"batch_{st}"] += 1
            if status == "ok":
                status = st
            continue
        got, seen = parse_forced(text, batch)
        stats["forced_items"] += seen
        tags += got
    if status == "ok" and not tags and cands:
        status = "empty"
    return tags, status


def _process_book(record: dict, config: PipelineConfig, id_to_name: dict,
                  local_stats: Counter) -> tuple[dict, float, bool]:
    """Judge one book and apply every filter. Returns (result, elapsed, failed).

    Safe to run in a worker thread: it only touches its own `local_stats`, and
    the caller merges and writes under a lock.
    """
    book_name = record.get("book", "?")
    cands = record.get("candidates", [])
    cand_by_cid = {c["canonical_id"]: c for c in cands}
    source_norm = _norm_for_match(_source_text(record, config))

    t0 = time.time()
    if getattr(config, "judge_mode", "select") == "forced":
        raw_tags, call_status = _judge_forced(record, config, local_stats)
    else:
        # budget scales with the candidate list: a 40-candidate reply is
        # ~2k tokens, a 120-candidate one is well past 2500 and would be cut
        budget = min(16000, 500 + 160 * len(cands))
        raw_tags, call_status = _sample_tags(build_prompt(record, config), config,
                                             max_tokens=budget)
    elapsed = time.time() - t0
    local_stats["llm_raw"] += len(raw_tags)
    local_stats[f"call_{call_status}"] += 1

    def result(tags, status, raw_n):
        return {"book": book_name, "tags": tags, "status": status,
                "elapsed_s": round(elapsed, 1), "candidates_used": len(cands),
                "llm_raw": raw_n}

    # Anything that is not "ok" is a failure unless we still got usable tags out
    # of a partially-succeeded book. Treating a connection error as "empty" would
    # record a network hiccup as "this book genuinely has no tags" — over a
    # multi-hour corpus run that silently deletes books.
    out_status = call_status
    if call_status != "ok":
        if raw_tags:
            out_status = f"partial_{call_status}"
        else:
            return result([], call_status, 0), elapsed, True

    if not raw_tags:
        # model answered but selected nothing: keep the book, flag it
        return result([], "empty", 0), elapsed, False

    kept = []
    for t in raw_tags:
        cid = t.get("canonical_id", "")
        if cid not in cand_by_cid:              # outside candidate list
            local_stats["drop_not_candidate"] += 1
            continue
        if (t.get("confidence", 0) or 0) < config.confidence_threshold:
            local_stats["drop_low_conf"] += 1
            continue
        if config.verify_evidence and not _verify_evidence(
                t.get("evidence", ""), source_norm, config):
            local_stats["drop_unverified_evidence"] += 1
            continue
        t["tag_name"] = id_to_name.get(cid, cid)
        t["evidence"] = (t.get("evidence") or "")[:MAX_EVIDENCE_CHARS]
        kept.append(t)

    # pairwise resolution of mutually confusable tags
    if config.disambiguate_confusions and len(kept) > 1:
        pairs = _conflict_pairs(kept, cand_by_cid)
        if pairs:
            decisions = _resolve_conflicts(pairs, cand_by_cid, config)
            before = len(kept)
            kept = [t for t in kept if decisions.get(t["canonical_id"], True)]
            local_stats["drop_conflict"] += before - len(kept)

    # dedupe: same canonical_id, or an identical quote reused twice.
    # The model can name one tag twice with different passages, which
    # evidence-only dedup misses, so key on canonical_id as well.
    seen_cid: dict[str, dict] = {}
    seen_ev: set[str] = set()
    final: list[dict] = []
    for t in kept:
        cid = t["canonical_id"]
        ev = _norm_for_match(t.get("evidence", ""))
        prev = seen_cid.get(cid)
        if prev is not None:
            local_stats["drop_dup_cid"] += 1
            if len(t.get("evidence", "")) > len(prev.get("evidence", "")):
                final[final.index(prev)] = t      # keep the fuller quote
                seen_cid[cid] = t
            continue
        if ev and ev in seen_ev:
            local_stats["drop_dup_evidence"] += 1
            continue
        seen_cid[cid] = t
        seen_ev.add(ev)
        final.append(t)

    # A reply whose tags were all rejected is not a clean "ok": the model did
    # answer, yet the book silently ends up with zero tags while the status
    # claims success. Report that case distinctly.
    if not final:
        return result([], "all_filtered", len(raw_tags)), elapsed, False

    return result(final, out_status, len(raw_tags)), elapsed, False


def run_stage3(input_path: str, output_path: str, config: PipelineConfig):
    """Read stage2 cache, confirm each book, write final results."""
    local = re.search(r"(localhost|127\.0\.0\.1|0\.0\.0\.0)", config.api_url)
    if not config.api_key and not local:
        raise SystemExit(
            "[Stage3] no API key. Set OPENCODE_API_KEY, or use a local server "
            "(--config local).")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    onto_path = Path(config.ontology_path)
    if not onto_path.is_absolute():
        onto_path = Path(__file__).resolve().parent.parent / onto_path
    with open(onto_path, "r", encoding="utf-8") as f:
        onto = json.load(f)
    id_to_name = {e["canonical_id"]: e.get("original_name", e["canonical_id"])
                  for e in onto["entries"]}

    records = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line.strip()))

    # Resumable: API calls are the expensive part of this pipeline, so a crash
    # (or a gateway outage) must not force a full re-run.
    done = set()
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        done.add(json.loads(line)["book"])
                    except (json.JSONDecodeError, KeyError):
                        pass
        if done:
            print(f"[Stage3] resuming: {len(done)} books already done")
    records = [r for r in records if r.get("book") not in done]

    total = len(records)
    print(f"[Stage3] {total} books | model={config.opencode_model} | "
          f"vote={config.vote_passes}@{config.vote_temperature} | "
          f"threshold≥{config.confidence_threshold} | "
          f"verify_evidence={config.verify_evidence} | "
          f"disambiguate={config.disambiguate_confusions}")

    processed = failed = 0
    stats = Counter()
    times = []
    workers = max(1, int(getattr(config, "stage3_workers", 1)))
    if workers > 1:
        print(f"[Stage3] {workers} concurrent calls per process "
              f"(separate keys = separate accounts, so this is where throughput comes from)")
    lock = threading.Lock()
    counts = {"ok": 0, "fail": 0}

    def handle(record):
        local = Counter()
        rec_out, elapsed, was_fail = _process_book(record, config, id_to_name, local)
        with lock:
            out.write(json.dumps(rec_out, ensure_ascii=False) + "\n")
            out.flush()
            stats.update(local)
            stats["final_tags"] += len(rec_out["tags"])
            counts["fail" if was_fail else "ok"] += 1
            times.append(elapsed)
            n = counts["ok"] + counts["fail"]
            names = [t.get("tag_name", t.get("canonical_id", "?"))
                     for t in rec_out["tags"][:4]]
            print(f"  [{n}/{total}] {Path(rec_out['book']).name[:30]:30s} "
                  f"{rec_out['status']:9s} {len(rec_out['tags']):2d}tags "
                  f"{elapsed:.0f}s {names}", flush=True)

    with open(output_path, "a" if done else "w", encoding="utf-8") as out:
        if workers == 1:
            for r in records:
                handle(r)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for _ in pool.map(handle, records):
                    pass
    processed, failed = counts["ok"], counts["fail"]

    avg_t = sum(times) / len(times) if times else 0
    print(f"\n[Stage3] Done: {processed} ok, {failed} fail | avg {avg_t:.1f}s/book")
    print(f"  llm_raw={stats['llm_raw']} final={stats['final_tags']}")
    for k in sorted(x for x in stats if x.startswith("call_")):
        print(f"  {k}={stats[k]}")
    n_empty = stats.get("call_empty", 0)
    if n_empty:
        print(f"  !! {n_empty}/{total} books returned ZERO tags — check whether these "
              f"are genuine or model refusals before trusting recall")
    for k in ("drop_not_candidate", "drop_low_conf", "drop_unverified_evidence",
              "drop_conflict", "drop_dup_cid", "drop_dup_evidence"):
        print(f"  {k}={stats[k]}")

    # Real token usage, so cost and cache-hit rate are measured, not estimated.
    u = usage_snapshot()
    if u["prompt"]:
        hit = u["cache_hit"] / max(u["prompt"], 1)
        print(f"\n[Stage3] 用量: {u['calls']} 次调用  "
              f"输入 {u['prompt']:,} (缓存命中 {u['cache_hit']:,} = {hit:.0%})  "
              f"输出 {u['completion']:,}")
        per_book_prompt = u["prompt"] / max(processed + failed, 1)
        per_book_out = u["completion"] / max(processed + failed, 1)
        print(f"         每本: 输入 {per_book_prompt:,.0f}  输出 {per_book_out:,.0f}")
        for model, (pin, pout, pcache) in (
                ("deepseek-flash", (2.0, 8.0, 0.04)),
                ("deepseek-v4-pro-0813", (9.0, 27.0, 0.3)),
                ("seed-2.1-pro", (6.0, 30.0, 1.2))):
            if model != config.opencode_model:
                continue
            c = (u["cache_miss"] * pin + u["cache_hit"] * pcache + u["completion"] * pout) / 1e6
            print(f"         本次成本 ¥{c:.4f}   "
                  f"全库 4342 本外推 ¥{c / max(processed + failed, 1) * 4342:,.0f}")
    print(f"  Output: {output_path}")
