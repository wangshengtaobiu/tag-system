"""Two ways to ask the judge, and the reason the second one exists.

select mode (current): "here is a list, pick the matching ones". Measured to be
unstable — the same book with the same candidate pool produced 5, 17 or 76 tags
depending only on how many candidates were shown, and two books accepted 100% of
what was offered. A selection framing invites a proportional answer instead of a
per-tag judgement.

forced mode: every candidate gets its own verdict in a fixed schema, so the reply
has one entry per candidate, its length is predictable, and there is no way to
"accept everything" without saying yes 120 times explicitly. Batched so a single
reply stays small.

Used by tagger/exp_forced.py to compare the two on identical inputs.
"""

import json
import re

from .config import PipelineConfig

FORCED_SYSTEM = (
    "你是成人小说标签判定员。下面列出候选标签，每个都有编号、名称和定义。\n"
    "你必须对【每一个编号】独立给出判定，不得跳过、不得只挑一部分：\n"
    "  y = 这段小说里确实出现了该标签所描述的内容（必须能在原文里逐字找到证据）\n"
    "  n = 没有出现，或只是勉强沾边\n"
    "判定标准：以【该标签自己的定义】为准，不要因为题材相近就判 y。\n"
    "证据必须是原文逐字片段；判 n 时证据留空。只输出 JSON。"
)


def _cand_line(i: int, c: dict) -> str:
    aliases = c.get("retrieval_aliases", [])
    alias_str = f"（{','.join(aliases[1:5])}）" if len(aliases) > 1 else ""
    summary = (c.get("semantic_summary") or "")[:150]
    bc = c.get("best_chunk")
    where = "仅书名命中" if isinstance(bc, int) and bc < 0 else f"命中{int(c.get('chunk_hits', 1))}块"
    return f"[{i}] {c.get('original_name', '')}{alias_str} | {where} | {summary}"


def build_forced_prompt(record: dict, config: PipelineConfig,
                        start: int = 0, count: int | None = None) -> tuple[str, list[dict]]:
    """Prompt asking for a verdict on each of `count` candidates from `start`.

    Returns (prompt, batch) where batch[i] is the candidate for reply index i+1.
    """
    from .stage3_confirm import _select_chunks          # avoid a circular import
    from pathlib import Path

    cands = record["candidates"]
    batch = cands[start:start + count] if count else cands[start:]
    picked, chunks = _select_chunks(record, config)
    if picked:
        context = "\n\n".join(f"【第{i + 1}块/共{len(chunks)}块】\n{chunks[i]}" for i in picked)
    else:
        context = record.get("slice_text", "")

    lines = "\n".join(_cand_line(i + 1, c) for i, c in enumerate(batch))
    prompt = f"""{FORCED_SYSTEM}

书名: {Path(record['book']).stem}
小说内容:
{context}

候选标签（共 {len(batch)} 个，每一个都要给出 y 或 n）:
{lines}

输出JSON: {{"decisions": [{{"i": 1, "v": "y", "e": "原文逐字片段"}}, {{"i": 2, "v": "n", "e": ""}}]}}"""
    return prompt, batch


def parse_forced(text: str, batch: list[dict]) -> list[dict]:
    """Turn a decisions reply into the same shape select mode produces."""
    text = (text or "").strip()
    m = re.search(r'\{[\s\S]*"decisions"[\s\S]*\}', text)
    if m:
        text = m.group(0)
    if "```" in text:
        text = re.sub(r"```\w*", "", text).strip()

    decisions = []
    try:
        decisions = json.loads(text).get("decisions", []) or []
    except (json.JSONDecodeError, AttributeError):
        for obj in re.findall(r'\{[^{}]*"i"\s*:\s*\d+[^{}]*\}', text):
            i = re.search(r'"i"\s*:\s*(\d+)', obj)
            v = re.search(r'"v"\s*:\s*"([yn])"', obj, re.I)
            e = re.search(r'"e"\s*:\s*"([^"]*)"', obj)
            if i and v:
                decisions.append({"i": int(i.group(1)), "v": v.group(1).lower(),
                                  "e": e.group(1) if e else ""})

    out, seen = [], set()
    for d in decisions:
        try:
            idx = int(d.get("i", 0))
        except (TypeError, ValueError):
            continue
        if not (1 <= idx <= len(batch)) or idx in seen:
            continue
        seen.add(idx)
        if str(d.get("v", "")).strip().lower() not in ("y", "yes", "1", "true", "是"):
            continue
        c = batch[idx - 1]
        ev = d.get("e", "")
        if isinstance(ev, (list, tuple)):
            ev = " ".join(str(x) for x in ev)
        out.append({"canonical_id": c["canonical_id"],
                    "confidence": 0.9,
                    "evidence": str(ev or "")})
    return out, len(seen)
