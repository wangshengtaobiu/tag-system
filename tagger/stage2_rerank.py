"""Stage 2: candidate rerank.

Primary path: a multilingual cross-encoder (bge-reranker-v2-m3) scoring
(book chunk, tag description) pairs. Each candidate is scored against the chunk
that actually recalled it — scoring everything against the book head would
penalise exactly the tags chunk-level recall was added to find.

Fallback path: character-level TF-IDF fused with the dense ranking (RRF), used
only when the reranker model is not available locally. No LLM calls.
"""

import json
import os
import re
import time
from collections import Counter
from pathlib import Path

from .chunking import chunk_text
from .config import PipelineConfig

# cross-encoder singleton (loaded once per process)
_ce = None
_batch_size = 32
RRF_K = 60


def init_reranker(config: PipelineConfig) -> bool:
    """Try to load the cross-encoder. Returns True when usable."""
    global _ce, _batch_size
    if _ce is not None:
        return True
    if not config.use_reranker:
        return False
    model_dir = Path(config.reranker_model)
    if not model_dir.exists():
        print(f"[Stage2] reranker model not found at {config.reranker_model}; "
              f"falling back to TF-IDF")
        return False
    try:
        from sentence_transformers import CrossEncoder
        max_len = getattr(config, "reranker_max_length", 512)
        _ce = CrossEncoder(str(model_dir), max_length=max_len)
        _batch_size = getattr(config, "reranker_batch_size", 32)
        # The checkpoint ships as F32; fp16 is ~3.4x faster on consumer GPUs.
        if getattr(config, "reranker_fp16", True):
            params = next(_ce.model.parameters(), None)
            if params is not None and params.device.type == "cuda":
                _ce.model.half()
                print(f"[Stage2] loaded reranker: {config.reranker_model} "
                      f"(fp16, max_length={max_len})")
            else:
                print(f"[Stage2] loaded reranker: {config.reranker_model} "
                      f"(fp32 — no CUDA device, fp16 skipped, max_length={max_len})")
        else:
            print(f"[Stage2] loaded reranker: {config.reranker_model} "
                  f"(fp32, max_length={max_len})")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[Stage2] failed to load reranker ({e}); falling back to TF-IDF")
        _ce = None
        return False


def _candidate_passage(c: dict) -> str:
    """Text that represents a tag to the reranker.

    Kept short on purpose: the pair must fit reranker_max_length together with
    the chunk, otherwise truncation silently eats the definition.
    """
    parts = [c.get("original_name", "")]
    aliases = c.get("retrieval_aliases", [])[1:] if c.get("retrieval_aliases") else []
    if aliases:
        parts.append("、".join(aliases[:5]))
    summary = c.get("semantic_summary") or c.get("embedding_text", "")
    if summary:
        parts.append(summary[:140])
    return " | ".join(p for p in parts if p)


def _query_for(c: dict, chunks: list[str], query_chars: int, title: str = "") -> str:
    """The chunk that recalled this candidate, truncated to the token budget.

    best_chunk == -1 means only the book title matched, so the title is the
    honest query for it; falling back to chunk 0 would score it against text
    that has nothing to do with it.
    """
    ci = c.get("best_chunk", 0)
    if isinstance(ci, int) and ci < 0:
        return title[:query_chars]
    if not isinstance(ci, int) or not (0 <= ci < len(chunks)):
        ci = 0
    return chunks[ci][:query_chars] if chunks else ""


def rerank(chunks: list[str], candidates: list[dict], top_k: int = 40,
           query_chars: int = 500, title: str = "") -> list[dict]:
    """Re-score candidates, each against its own best chunk, keep top_k."""
    if len(candidates) <= top_k:
        return candidates
    if not chunks:
        return candidates[:top_k]

    if _ce is not None:
        pairs = [(_query_for(c, chunks, query_chars, title), _candidate_passage(c))
                 for c in candidates]
        scores = _ce.predict(pairs, batch_size=_batch_size)
        scored = sorted(zip(scores, candidates), key=lambda x: -float(x[0]))
        return [c for _, c in scored[:top_k]]

    # ---- TF-IDF + dense rank fusion (no reranker available) ----
    cand_tokens = []
    for c in candidates:
        cand_tokens.append(_tokenize((c.get("embedding_text", "") + " "
                                      + " ".join(c.get("retrieval_aliases", [])))))
    idf = _compute_idf(cand_tokens)

    qcache: dict[int, dict] = {}
    scores = []
    for c, ct in zip(candidates, cand_tokens):
        ci = c.get("best_chunk", 0)
        if not isinstance(ci, int) or not (0 <= ci < len(chunks)):
            ci = 0
        if ci not in qcache:
            qcache[ci] = _tfidf_vector(_tokenize(_query_for(c, chunks, query_chars, title)), idf)
        scores.append(_cosine(qcache[ci], _tfidf_vector(ct, idf)))

    lexical = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)
    fused: dict[int, float] = {}
    for rank, i in enumerate(lexical):
        fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)
    for rank, i in enumerate(range(len(candidates))):   # dense order as second channel
        fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + rank + 1)

    order = sorted(fused, key=lambda i: fused[i], reverse=True)
    return [candidates[i] for i in order[:top_k]]


def _tokenize(text: str) -> list[str]:
    """Character-level tokenizer for Chinese + word-level for English."""
    tokens = []
    for chunk in re.split(r'([a-zA-Z0-9_]+)', text.lower()):
        chunk = chunk.strip()
        if not chunk:
            continue
        if re.match(r'^[a-zA-Z0-9_]+$', chunk):
            tokens.append(chunk)
        else:
            for ch in chunk:
                if ord(ch) > 127:
                    tokens.append(ch)
    return tokens


def _compute_idf(documents: list[list[str]]) -> dict[str, float]:
    N = len(documents)
    df = Counter()
    for doc in documents:
        for term in set(doc):
            df[term] += 1
    return {t: N / (df[t] + 1) for t in df}


def _tfidf_vector(tokens: list[str], idf: dict) -> dict[str, float]:
    tf = Counter(tokens)
    vec = {t: freq * idf.get(t, 0) for t, freq in tf.items()}
    norm = sum(v * v for v in vec.values()) ** 0.5
    if norm > 0:
        vec = {k: v / norm for k, v in vec.items()}
    return vec


def _cosine(v1: dict, v2: dict) -> float:
    if not v1 or not v2:
        return 0.0
    keys = set(v1) & set(v2)
    return sum(v1[k] * v2[k] for k in keys)


def run_stage2(input_path: str, output_path: str, config: PipelineConfig):
    """Read stage1 cache, rerank candidates per book, write stage2 cache.

    Resumable: books already present in the output are skipped, so a long run
    that hits the Windows allocator cliff (no expandable_segments support, so
    fragmentation is permanent once it starts) can be restarted in a fresh
    process and continue rather than redo everything.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    t0 = time.time()
    processed = 0

    using_ce = init_reranker(config)
    backend = "cross-encoder" if using_ce else "tfidf+rrf"

    done = set()
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    done.add(json.loads(line)["book"])
        if done:
            print(f"[Stage2] resuming: {len(done)} books already done")

    top_k = config.stage2_top_k
    print(f"[Stage2] rerank per-book candidate union → {top_k} (backend={backend})")

    with open(input_path, "r", encoding="utf-8") as inf, \
         open(output_path, "a" if done else "w", encoding="utf-8") as outf:
        for line in inf:
            if not line.strip():
                continue
            record = json.loads(line.strip())
            if record.get("book") in done:
                continue
            candidates = record.get("candidates", [])
            original_count = len(candidates)
            title = Path(record.get("book", "")).stem
            chunks = chunk_text(record.get("text", ""), config.chunk_chars)

            t1 = time.time()
            record["candidates"] = rerank(chunks, candidates, top_k=top_k,
                                          query_chars=config.rerank_query_chars,
                                          title=title)
            dt = time.time() - t1
            record["candidates_before_rerank"] = original_count
            outf.write(json.dumps(record, ensure_ascii=False) + "\n")
            outf.flush()
            processed += 1
            flag = "  <-- SLOW" if dt > 60 else ""
            print(f"  [{processed}] {title[:30]:30s} {original_count:4d} → "
                  f"{len(record['candidates']):2d} in {dt:.1f}s{flag}")

    elapsed = time.time() - t0
    print(f"[Stage2] Done: {processed} books in {elapsed:.1f}s "
          f"({elapsed / max(processed, 1):.1f}s/book)")
    print(f"         Output: {output_path}")
