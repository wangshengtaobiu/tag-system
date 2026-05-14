"""
Retriever — Main retrieval pipeline: embedding → candidate retrieval → reranking.
Orchestrates Embedder + Indexer + Reranker.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import numpy as np

from retrieval import RetrievalConfig, RetrievalResult, TaggingResult
from retrieval.embedder import Embedder
from retrieval.indexer import Indexer


class Retriever:
    """Main retrieval pipeline for tag matching."""

    def __init__(self, config: RetrievalConfig, indexer: Indexer, embedder: Embedder):
        self.config = config
        self.indexer = indexer
        self.embedder = embedder

    def retrieve(self, query_text: str,
                 namespace_filter: str | None = None,
                 category_filter: str | None = None,
                 semantic_type_filter: str | None = None) -> list[RetrievalResult]:
        """Retrieve top-k candidates for a query text."""
        # 1. Embed query
        query_emb = self.embedder.encode_single(query_text)

        # 2. Search index
        faiss_results = self.indexer.search(
            query_emb,
            k=self.config.top_k_candidates,
            namespace_filter=namespace_filter,
            category_filter=category_filter,
            semantic_type_filter=semantic_type_filter,
        )

        # 3. Map to RetrievalResult
        results = []
        for faiss_id, score in faiss_results:
            entry = self.indexer.id_to_info.get(faiss_id)
            if entry:
                results.append(RetrievalResult(
                    canonical_id=entry["canonical_id"],
                    original_name=entry["original_name"],
                    namespace=entry.get("namespace", ""),
                    semantic_type=entry.get("semantic_type", ""),
                    score=float(score),
                    confidence=entry.get("confidence", 0.85),
                    matched_text=query_text[:100],
                    expansion_path="direct",
                ))

        return results[:self.config.top_k_candidates]

    def retrieve_with_reranking(self, query_text: str,
                                reranker,  # Reranker instance
                                namespace_filter: str | None = None,
                                min_confidence: float = 0.70) -> list[RetrievalResult]:
        """Full pipeline: retrieve candidates → Qwen reranking → filter."""
        # 1. Retrieve candidates
        candidates = self.retrieve(query_text, namespace_filter=namespace_filter)

        if not candidates:
            return []

        # 2. Rerank with Qwen
        reranked = reranker.rerank(query_text, candidates)

        # 3. Filter by confidence
        filtered = [r for r in reranked if r.confidence >= min_confidence]

        return filtered[:self.config.top_k_final]

    def tag_text(self, text: str, text_id: str = "",
                 reranker=None,
                 min_confidence: float = 0.70,
                 chunk: bool = True) -> TaggingResult:
        """Tag a full text (novel passage)."""
        t0 = time.time()
        all_tags: list[RetrievalResult] = []
        rejected: list[RetrievalResult] = []

        # 1. Chunk text if needed
        chunks = self._chunk_text(text) if chunk else [text]

        # 2. Retrieve for each chunk
        for chunk_text in chunks:
            if reranker:
                chunk_tags = self.retrieve_with_reranking(
                    chunk_text, reranker, min_confidence=min_confidence
                )
            else:
                chunk_tags = self.retrieve(chunk_text)

            for tag in chunk_tags:
                tag.matched_text = chunk_text[:80]
                # Avoid duplicates
                if not any(t.canonical_id == tag.canonical_id for t in all_tags):
                    if tag.score >= 0.5 or (reranker and tag.score >= 0.3):
                        all_tags.append(tag)
                    else:
                        rejected.append(tag)

        # 3. Sort by score
        all_tags.sort(key=lambda t: t.score, reverse=True)

        duration = round(time.time() - t0, 2)
        return TaggingResult(
            text_id=text_id,
            tags=all_tags[:self.config.top_k_final],
            rejected_tags=rejected[:10],
            total_candidates=len(all_tags) + len(rejected),
            duration_seconds=duration,
        )

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks."""
        if len(text) <= self.config.chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.config.chunk_size, len(text))
            chunks.append(text[start:end])
            start += self.config.chunk_size - self.config.chunk_overlap
        return chunks

    def batch_tag(self, texts: list[dict], reranker=None,
                  min_confidence: float = 0.70) -> list[TaggingResult]:
        """Tag a batch of texts."""
        results = []
        for i, item in enumerate(texts):
            text = item.get("text") or item.get("content") or ""
            text_id = item.get("id") or str(i)
            result = self.tag_text(text, text_id=text_id, reranker=reranker,
                                   min_confidence=min_confidence)
            results.append(result)
        return results
