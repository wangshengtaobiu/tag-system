#!/usr/bin/env python3
"""
Tagger — Local Tagging Pipeline (Standalone)

Usage:
    python run_tagger.py --index retrieval_index.json --input novels/
    python run_tagger.py --index retrieval_index.json --text "some text to tag"
    python run_tagger.py --index retrieval_index.json --input novels/ --rerank

Pipeline:
    text → chunk → BGE embedding → FAISS top-50 → (Qwen 8B rerank) → top-K tags

Hardware: RTX 3060 Ti (8GB VRAM) or CPU.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict, Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from retrieval import RetrievalConfig, RetrievalResult, TaggingResult
from retrieval.embedder import Embedder
from retrieval.indexer import Indexer
from retrieval.retriever import Retriever
from retrieval.reranker import Reranker


# ============================================================
# Ontology export → retrieval index 转换（不依赖 ontology_factory）
# ============================================================

CANONICAL_ID_PATTERN = r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?$"


def _build_semantic_summary(entry: dict) -> str:
    definition = (entry.get("definition") or "")[:100]
    distinction = (entry.get("distinction") or "")[:60]
    if distinction:
        return f"{definition} [{distinction}]"
    return definition


def build_retrieval_entries(entries: list[dict]) -> list[dict]:
    """将冻结本体条目转为检索用条目。"""
    retrieval_entries = []
    for e in entries:
        if e.get("is_alias_of") or e.get("is_duplicate_of"):
            continue

        name = e.get("original_name") or e.get("name") or ""
        aliases = (e.get("aliases") or [])[:5]
        definition = (e.get("definition") or "")[:200]
        distinction = (e.get("distinction") or "")[:150]
        examples = (e.get("examples") or [])[:5]

        emb_parts = [name]
        if aliases:
            emb_parts.append(" | ".join(aliases))
        if definition:
            emb_parts.append(definition)
        if distinction:
            emb_parts.append(f"区别于: {distinction}")
        if examples:
            emb_parts.append("示例: " + "、".join(examples))

        embedding_text = " | ".join(p for p in emb_parts if p)
        semantic_summary = _build_semantic_summary(e)

        expansion_terms = [
            f"ns:{e.get('namespace', '')}",
            f"type:{e.get('semantic_type', '')}",
            f"cat:{e.get('category', '')}",
        ] + examples[:3]
        for axis in (e.get("semantic_axes") or []):
            expansion_terms.append(f"axis:{axis}")

        retrieval_entries.append({
            "canonical_id": e.get("canonical_id"),
            "original_name": name,
            "namespace": e.get("namespace"),
            "semantic_type": e.get("semantic_type"),
            "category": e.get("category"),
            "ontology_type": e.get("ontology_type"),
            "embedding_text": embedding_text,
            "semantic_summary": semantic_summary,
            "retrieval_aliases": [name] + aliases[:10],
            "candidate_expansion_terms": expansion_terms[:15],
            "parent_canonical_id": e.get("parent_canonical_id"),
            "trusted_relations": e.get("trusted_relations") or [],
            "confidence": e.get("confidence") or 0,
            "v3_validated": e.get("v3_validated") or False,
        })

    return retrieval_entries


def convert_ontology_to_retrieval(ontology_data: dict) -> dict:
    """将 ontology_export_v1.json 转为 retrieval_index 格式。"""
    entries = ontology_data.get("entries") or []
    retrieval_entries = build_retrieval_entries(entries)

    by_ns = defaultdict(list)
    by_cat = defaultdict(list)
    by_st = defaultdict(list)
    for re_entry in retrieval_entries:
        cid = re_entry["canonical_id"]
        if re_entry.get("namespace"):
            by_ns[re_entry["namespace"]].append(cid)
        if re_entry.get("category"):
            by_cat[re_entry["category"]].append(cid)
        if re_entry.get("semantic_type"):
            by_st[re_entry["semantic_type"]].append(cid)

    return {
        "meta": {"total_entries": len(retrieval_entries)},
        "entries": retrieval_entries,
        "indices": {
            "by_namespace": dict(by_ns),
            "by_category": dict(by_cat),
            "by_semantic_type": dict(by_st),
        },
    }


# ============================================================
# Input loading
# ============================================================

def load_input_texts(input_path: str) -> list[dict]:
    path = Path(input_path)
    texts = []

    if path.is_file():
        if path.suffix == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                texts = data
            elif isinstance(data, dict):
                texts = data.get("texts") or data.get("entries") or data.get("data") or []
        elif path.suffix == ".txt":
            content = path.read_text(encoding="utf-8")
            texts = [{"id": path.stem, "text": content}]
        elif path.suffix in (".jsonl", ".ndjson"):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        texts.append(json.loads(line))
    elif path.is_dir():
        for txt_file in sorted(path.glob("*.txt")):
            texts.append({"id": txt_file.stem, "text": txt_file.read_text(encoding="utf-8")})
        for json_file in sorted(path.glob("*.json")):
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "text" in data:
                texts.append(data)

    return texts


def format_tagging_result(result: TaggingResult) -> dict:
    return {
        "text_id": result.text_id,
        "tags": [
            {
                "canonical_id": t.canonical_id,
                "name": t.original_name,
                "namespace": t.namespace,
                "semantic_type": t.semantic_type,
                "score": round(t.score, 4),
                "confidence": t.confidence,
            }
            for t in result.tags
        ],
        "rejected": [
            {
                "canonical_id": t.canonical_id,
                "name": t.original_name,
                "score": round(t.score, 4),
            }
            for t in result.rejected_tags[:5]
        ],
        "total_candidates": result.total_candidates,
        "duration_seconds": result.duration_seconds,
    }


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Tagger — Local Tagging Pipeline (Standalone)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_tagger.py --index retrieval_index.json --input novels/
  python run_tagger.py --index retrieval_index.json --input novels/ --rerank
  python run_tagger.py --index retrieval_index.json --text "the novel passage..."
  python run_tagger.py --index ontology_export_v1.json --input novels/
        """,
    )
    parser.add_argument("--index", "-i", required=True,
                        help="Path to retrieval_index.json or ontology_export_v1.json")
    parser.add_argument("--input", default=None,
                        help="Path to text file / JSON / directory")
    parser.add_argument("--text", "-t", default=None,
                        help="Direct text to tag")
    parser.add_argument("--output", "-o", default="tagging_results.json",
                        help="Output file (default: tagging_results.json)")
    parser.add_argument("--rerank", action="store_true",
                        help="Enable Qwen 8B reranking (needs ~5.5GB VRAM)")
    parser.add_argument("--namespace", "-n", default=None,
                        help="Filter candidates by namespace")
    parser.add_argument("--category", default=None,
                        help="Filter candidates by category")
    parser.add_argument("--semantic-type", default=None,
                        help="Filter candidates by semantic type")
    parser.add_argument("--min-confidence", type=float, default=0.70,
                        help="Min confidence threshold (default: 0.70)")
    parser.add_argument("--top-k", type=int, default=10,
                        help="Max tags per text (default: 10)")
    parser.add_argument("--chunk-size", type=int, default=512,
                        help="Text chunk size (default: 512)")
    parser.add_argument("--chunk-overlap", type=int, default=50,
                        help="Chunk overlap (default: 50)")
    parser.add_argument("--no-chunk", action="store_true",
                        help="Disable text chunking")
    parser.add_argument("--device", default="cuda",
                        help="Device: cuda / cpu (default: cuda)")
    parser.add_argument("--quantization", default="4bit",
                        help="Qwen quantization: 4bit / none (default: 4bit)")

    args = parser.parse_args()

    if not args.input and not args.text:
        print("ERROR: --input or --text is required")
        sys.exit(1)

    print("=" * 60)
    print("TAGGER — Local Inference Pipeline (Standalone)")
    print("=" * 60)

    # ---- Load index ----
    print(f"\n[LOAD] Index: {args.index}")
    index_path = Path(args.index)
    if not index_path.exists():
        print(f"ERROR: File not found: {args.index}")
        sys.exit(1)

    with open(index_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    if "indices" in raw_data:
        retrieval_index = raw_data
        print(f"  Type: retrieval_index ({retrieval_index['meta']['total_entries']} entries)")
    else:
        print("  Type: ontology_export (converting to retrieval format)")
        retrieval_index = convert_ontology_to_retrieval(raw_data)
        print(f"  Converted: {retrieval_index['meta']['total_entries']} entries")

    # ---- Config ----
    config = RetrievalConfig(
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        top_k_candidates=50,
        top_k_final=args.top_k,
        device=args.device,
        quantization=args.quantization,
    )

    # ---- Embedder ----
    print(f"\n[LOAD] Embedder: {config.embedding_model}")
    embedder = Embedder(config.embedding_model, config.device)
    embedder.load()

    # ---- Index ----
    print(f"\n[BUILD] FAISS index")
    indexer = Indexer(config.embedding_dim, index_type="flat")
    indexer.build(retrieval_index)

    print(f"[EMBED] Encoding {len(retrieval_index['entries'])} entries...")
    t0 = time.time()
    embedding_texts = [e["embedding_text"] for e in retrieval_index["entries"]]
    embeddings = embedder.encode(embedding_texts, batch_size=32)
    print(f"[EMBED] Done in {time.time() - t0:.1f}s  shape={embeddings.shape}")
    indexer._build_faiss_index(embeddings)

    # ---- Retriever ----
    retriever = Retriever(config, indexer, embedder)

    # ---- Reranker (optional) ----
    reranker = None
    if args.rerank:
        print(f"\n[LOAD] Reranker: {config.reranker_model} ({config.quantization})")
        reranker = Reranker(config.reranker_model, config.device, config.quantization)
        reranker.load()
        print(f"  VRAM: embedder ~{config.embedding_model_mb}MB + reranker ~{config.reranker_model_mb}MB "
              f"= ~{config.embedding_model_mb + config.reranker_model_mb}MB "
              f"(budget: {config.vram_budget_mb}MB)")

    # ---- Input ----
    if args.text:
        texts = [{"id": "direct_input", "text": args.text}]
    else:
        texts = load_input_texts(args.input)
    print(f"\n[INPUT] {len(texts)} text(s)")

    # ---- Tagging ----
    print(f"\n[TAG] chunk_size={config.chunk_size} overlap={config.chunk_overlap} "
          f"namespace={args.namespace or 'all'} min_conf={args.min_confidence}")
    t0 = time.time()
    results = []
    for i, item in enumerate(texts):
        text = item.get("text") or item.get("content") or ""
        text_id = item.get("id") or f"text_{i}"
        result = retriever.tag_text(
            text, text_id=text_id, reranker=reranker,
            min_confidence=args.min_confidence, chunk=not args.no_chunk,
        )
        results.append(result)
        print(f"  [{i+1}/{len(texts)}] {text_id}: {len(result.tags)} tags ({result.duration_seconds}s)")

    total_time = round(time.time() - t0, 2)
    print(f"\n[DONE] {len(texts)} texts in {total_time}s")

    # ---- Save ----
    output_data = {
        "meta": {
            "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total_texts": len(texts),
            "total_time_seconds": total_time,
            "config": {
                "chunk_size": config.chunk_size,
                "min_confidence": args.min_confidence,
                "reranking": args.rerank,
            },
        },
        "results": [format_tagging_result(r) for r in results],
    }
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"[SAVE] {output_path}")

    # ---- Cleanup ----
    embedder.unload()
    if reranker:
        reranker.unload()


if __name__ == "__main__":
    main()
