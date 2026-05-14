"""
Embedder — BGE embedding generation for retrieval.
Model: bge-large-zh-v1.5 (1024-dim, max 512 tokens).
VRAM: ~1.3 GB.
"""
from __future__ import annotations

import numpy as np
from pathlib import Path
from typing import Optional


class Embedder:
    """BGE-large-zh-v1.5 embedding generator."""

    def __init__(self, model_name: str = "bge-large-zh-v1.5", device: str = "cuda"):
        self.model_name = model_name
        self.device = device
        self.model = None
        self.tokenizer = None
        self._loaded = False

    def load(self):
        """Lazy-load the BGE model."""
        if self._loaded:
            return
        print(f"[Embedder] Loading {self.model_name} on {self.device}...")
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name, device=self.device)
            self._loaded = True
            print(f"[Embedder] Loaded. Dim={self.model.get_sentence_embedding_dimension()}")
        except ImportError:
            print("[Embedder] sentence_transformers not installed. Using stub.")
            self.model = None
            self._loaded = True
        except (OSError, Exception) as e:
            print(f"[Embedder] Failed to load model: {e}")
            print("[Embedder] Using stub mode. Set HF_TOKEN or download model locally.")
            self.model = None
            self._loaded = True

    def unload(self):
        """Free VRAM."""
        if self.model:
            del self.model
        self.model = None
        self.tokenizer = None
        self._loaded = False

    def encode(self, texts: list[str], batch_size: int = 32, show_progress: bool = True) -> np.ndarray:
        """Encode texts to embeddings. Returns (N, dim) array."""
        self.load()
        if self.model is None:
            return np.random.randn(len(texts), 1024).astype(np.float32)

        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=True,
        )
        return np.array(embeddings, dtype=np.float32)

    def encode_single(self, text: str) -> np.ndarray:
        """Encode a single text."""
        return self.encode([text], batch_size=1, show_progress=False)[0]

    @property
    def loaded(self) -> bool:
        return self._loaded
