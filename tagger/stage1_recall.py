"""Stage 1: BGE-M3 + FAISS chunk-level recall.

Each book is split into chunks; every chunk queries the index separately and the
per-book candidate list is the UNION of those hits, annotated with how many
chunks recalled each tag and which chunk matched best. A single query built from
the book head was measured to miss ~40% of this union.

Saves per-book cache as JSONL:
  {book, text, slice_text, n_chunks, candidates: [...]}
"""

import json
import os
import time
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from .chunking import chunk_text
from .config import PipelineConfig

_cfg: PipelineConfig = None
_model = None
_index = None
_ids = None
_entries = None


def init(config: PipelineConfig):
    global _cfg, _model, _index, _ids, _entries
    _cfg = config
    kwargs = {}
    if getattr(config, "bge_fp16", True):
        try:
            import torch
            if torch.cuda.is_available():
                kwargs["model_kwargs"] = {"torch_dtype": torch.float16}
        except ImportError:
            pass
    _model = SentenceTransformer(config.bge_model, **kwargs)
    if kwargs:
        print("[Stage1] bge-m3 loaded in fp16")
    _index = faiss.read_index(str(Path(config.faiss_index)))
    with open(Path(config.faiss_ids), "r", encoding="utf-8") as f:
        _ids = json.load(f)
    with open(Path(config.ontology_path), "r", encoding="utf-8") as f:
        data = json.load(f)
    _entries = {e["canonical_id"]: e for e in data["entries"]}


def recall(query_text: str, k: int = None) -> list[dict]:
    """Single-query recall (kept for ad-hoc use and tests)."""
    k = k or _cfg.stage1_top_k
    vec = _model.encode([query_text], normalize_embeddings=True)
    _, indices = _index.search(vec.astype("float32"), k)
    return [_entries[_ids[i]] for i in indices[0]]


def recall_batch(texts: list[str], k: int) -> list[tuple[list[str], list[float]]]:
    """Encode and search many queries in one forward pass.

    Returns [(canonical_ids, cosine_scores)] aligned with `texts`. Batching is
    what makes chunk-level recall affordable: a 90-chunk book costs one or two
    forward passes instead of 90 separate encodes.
    """
    if not texts:
        return []
    vecs = _model.encode(texts, normalize_embeddings=True, batch_size=len(texts))
    scores, indices = _index.search(np.asarray(vecs, dtype="float32"), k)
    return [([_ids[i] for i in row], [float(s) for s in srow])
            for row, srow in zip(indices, scores)]


def get_id_to_name() -> dict:
    return {cid: e.get("original_name", cid) for cid, e in _entries.items()}


def release():
    """Drop the embedding model and index so stage 2's reranker gets the VRAM.

    On an 8GB card bge-m3 plus the cross-encoder do not comfortably coexist.
    """
    global _model, _index, _ids, _entries
    _model = _index = _ids = _entries = None
    import gc
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def recall_book(text: str, title: str, config: PipelineConfig) -> tuple[list[dict], int]:
    """Chunk a book, recall per chunk, return (union candidates, n_chunks).

    The title is queried on its own, not merged into chunk 0. A candidate that
    only the title matched gets best_chunk = -1: it has no chunk to show the
    judge, and it must not vote in chunk selection. Merging the title into
    chunk 0 instead poisoned that chunk's embedding and made the judge read the
    book's opening for books whose title is descriptive of their content.
    """
    chunks = chunk_text(text, config.chunk_chars)
    if not chunks:
        return [], 0

    meta: dict[str, dict] = {}
    bs = max(1, config.chunk_batch_size)
    k = config.stage1_top_k
    for start in range(0, len(chunks), bs):
        batch = chunks[start:start + bs]
        for j, (ids, scores) in enumerate(recall_batch(batch, k)):
            cidx = start + j
            for cid, sc in zip(ids, scores):
                m = meta.get(cid)
                if m is None:
                    meta[cid] = {"best_chunk": cidx, "best_score": sc, "chunk_hits": 1}
                else:
                    m["chunk_hits"] += 1
                    if sc > m["best_score"]:
                        m["best_score"], m["best_chunk"] = sc, cidx

    # title-only hits: real evidence for a title like "24小时捆绑", but there is
    # no chunk to point the judge at, so best_chunk stays -1
    if title:
        title_scores: dict[str, float] = {}
        for ids, scores in recall_batch([title], k):
            for cid, sc in zip(ids, scores):
                title_scores[cid] = sc
        for cid, sc in title_scores.items():
            m = meta.get(cid)
            if m is None:
                meta[cid] = {"best_chunk": -1, "best_score": sc, "chunk_hits": 1}
            else:
                m["chunk_hits"] += 1

    ordered = sorted(meta.items(),
                     key=lambda kv: (-kv[1]["best_score"], -kv[1]["chunk_hits"]))
    if config.max_candidates:
        ordered = ordered[:config.max_candidates]

    candidates = []
    for cid, m in ordered:
        e = _entries.get(cid)
        if e is None:
            continue
        candidates.append({
            "canonical_id": cid,
            "original_name": e.get("original_name", ""),
            "retrieval_aliases": e.get("retrieval_aliases", []),
            "semantic_summary": e.get("semantic_summary", ""),
            "embedding_text": e.get("embedding_text", ""),
            "namespace": e.get("namespace", ""),
            "category": e.get("category", ""),
            "chunk_hits": m["chunk_hits"],
            "best_chunk": m["best_chunk"],
            "best_score": round(m["best_score"], 4),
        })
    return candidates, len(chunks)


def run_stage1(books: list[dict], config: PipelineConfig,
               output_path: str, ckpt_path: str = None):
    """Process all books: chunk → batched BGE recall → union → cache JSONL.

    books: list of {name, path, text} or {name, text}
    """
    init(config)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    sc = config.slice

    done = set()
    if ckpt_path and os.path.exists(ckpt_path):
        with open(ckpt_path, "r", encoding="utf-8") as f:
            done = set(json.load(f).get("completed", []))
    # Also skip books already in the output, so a run interrupted by the Windows
    # allocator cliff can simply be restarted without duplicating records.
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        done.add(json.loads(line)["book"])
                    except (json.JSONDecodeError, KeyError):
                        pass
        if done:
            print(f"[Stage1] resuming: {len(done)} books already cached")

    t0 = time.time()
    processed = 0
    total = len(books)
    print(f"[Stage1] {total} books | chunk={config.chunk_chars} chars, "
          f"top_k={config.stage1_top_k}/chunk, cap={config.max_candidates}")

    with open(output_path, "a", encoding="utf-8") as out:
        for b in books:
            name = b["name"]
            if name in done:
                continue

            text = b.get("text", "")
            if not text or len(text.strip()) < 50:
                continue

            title = Path(name).stem
            t1 = time.time()
            candidates, n_chunks = recall_book(text, title, config)
            dt = time.time() - t1

            record = {
                "book": name,
                "text": text,
                "slice_text": (f"{text[:sc.head_chars]}\n\n...\n\n{text[-sc.tail_chars:]}"
                               if sc.tail_chars else text[:sc.head_chars]),
                "n_chunks": n_chunks,
                "candidates": candidates,
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            processed += 1

            multi = sum(1 for c in candidates if c["chunk_hits"] > 1)
            print(f"  [{processed}/{total}] {title[:30]:30s} {n_chunks:4d} chunks -> "
                  f"{len(candidates):4d} cands ({multi} multi-chunk) {dt:.1f}s")

            if ckpt_path and processed % 50 == 0:
                done.add(name)
                with open(ckpt_path, "w", encoding="utf-8") as cf:
                    json.dump({"completed": sorted(done)}, cf, ensure_ascii=False)

        if ckpt_path and processed:
            done.add(name)
            with open(ckpt_path, "w", encoding="utf-8") as cf:
                json.dump({"completed": sorted(done)}, cf, ensure_ascii=False)

    elapsed = time.time() - t0
    print(f"[Stage1] Done: {processed} books in {elapsed:.1f}s "
          f"({elapsed / max(processed, 1):.1f}s/book)")
    print(f"         Output: {output_path}")
