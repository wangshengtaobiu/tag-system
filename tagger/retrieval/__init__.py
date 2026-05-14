"""
Retrieval module — Local inference pipeline for tag matching.
Uses BGE embeddings + FAISS for candidate retrieval, Qwen 8B for reranking.
Hardware target: RTX 3060 Ti (8GB VRAM).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class RetrievalConfig:
    """Configuration for the local retrieval pipeline."""
    embedding_model: str = "bge-large-zh-v1.5"
    embedding_dim: int = 1024
    reranker_model: str = "qwen-2.5-8b-instruct"
    device: str = "cuda"
    quantization: str = "4bit"         # For Qwen 8B
    max_seq_length: int = 512          # For BGE
    chunk_size: int = 512              # Text chunking for novels
    chunk_overlap: int = 50
    top_k_candidates: int = 50         # Pre-filter candidates
    top_k_final: int = 10              # After reranking
    max_context_chunks: int = 3        # Top chunks for reranking
    vram_budget_mb: int = 8000
    embedding_model_mb: int = 1300
    reranker_model_mb: int = 5500


@dataclass
class RetrievalResult:
    """A single retrieval match."""
    canonical_id: str
    original_name: str
    namespace: str
    semantic_type: str
    score: float                     # Similarity/reranking score
    confidence: float                # Ontology confidence
    matched_text: str = ""           # The text chunk that matched
    expansion_path: str = ""         # How we got here (direct/alias/expansion)


@dataclass
class TaggingResult:
    """Result of tagging a text."""
    text_id: str
    tags: list[RetrievalResult]
    rejected_tags: list[RetrievalResult]
    total_candidates: int
    duration_seconds: float
