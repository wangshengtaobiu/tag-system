#!/usr/bin/env python3
"""Build the FAISS retrieval index from exports/retrieval_index.json.

The original build script was never committed, so this reproduces the artifact
the tagger expects: an inner-product index over L2-normalized embeddings, plus
the canonical_id list whose row order matches the index rows.

Usage:
    python build_faiss_index.py \
        --retrieval-index exports/retrieval_index.json \
        --model D:/model/bge-m3/BAAI/bge-m3 \
        --out-dir exports

Writes retrieval_faiss.index and retrieval_ids.json into --out-dir.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer


def main():
    ap = argparse.ArgumentParser(description="Build FAISS index for the tag retriever")
    ap.add_argument("--retrieval-index", default="exports/retrieval_index.json")
    ap.add_argument("--model", default="D:/model/bge-m3/BAAI/bge-m3")
    ap.add_argument("--out-dir", default="exports")
    ap.add_argument("--batch-size", type=int, default=64)
    args = ap.parse_args()

    data = json.loads(Path(args.retrieval_index).read_text(encoding="utf-8"))
    entries = [e for e in data["entries"] if e.get("canonical_id")]
    skipped = len(data["entries"]) - len(entries)
    ids = [e["canonical_id"] for e in entries]
    texts = [e.get("embedding_text") or e.get("original_name", "") for e in entries]
    print(f"[FAISS] {len(entries)} entries ({skipped} without canonical_id skipped), model={args.model}")

    model = SentenceTransformer(args.model)
    emb = model.encode(
        texts,
        batch_size=args.batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    emb = np.asarray(emb, dtype="float32")
    print(f"[FAISS] embedding matrix: {emb.shape}")

    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(emb)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(out / "retrieval_faiss.index"))
    (out / "retrieval_ids.json").write_text(
        json.dumps(ids, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[FAISS] wrote {out / 'retrieval_faiss.index'} "
          f"({index.ntotal} vectors, dim {emb.shape[1]})")
    print(f"[FAISS] wrote {out / 'retrieval_ids.json'} ({len(ids)} ids)")


if __name__ == "__main__":
    main()
