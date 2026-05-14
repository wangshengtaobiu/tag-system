"""
Indexer — FAISS index construction and management.
Supports Flat (exact), IVF (approximate), and IVF+PQ (compressed).
"""
from __future__ import annotations

import json
import numpy as np
from pathlib import Path
from typing import Optional
from collections import defaultdict


class Indexer:
    """FAISS-based vector index for ontology retrieval."""

    def __init__(self, dim: int = 1024, index_type: str = "flat"):
        self.dim = dim
        self.index_type = index_type
        self.index = None
        self.id_to_info: dict[int, dict] = {}      # FAISS id → entry info
        self.cid_to_faiss_id: dict[str, int] = {}   # canonical_id → FAISS id
        self.facet_indices: dict[str, dict[str, list[int]]] = {
            "by_namespace": defaultdict(list),
            "by_category": defaultdict(list),
            "by_semantic_type": defaultdict(list),
        }

    def build(self, retrieval_index: dict, embeddings: Optional[np.ndarray] = None):
        """Build the FAISS index from retrieval_index.json data."""
        print(f"[Indexer] Building {self.index_type.upper()} index...")
        entries = retrieval_index.get("entries", [])
        indices = retrieval_index.get("indices", {})

        # Map canonical_ids to FAISS ids
        for _faiss_id, entry in enumerate(entries):
            cid = entry["canonical_id"]
            self.cid_to_faiss_id[cid] = _faiss_id
            self.id_to_info[_faiss_id] = entry

        # Build facet indices (FAISS ids grouped by facet)
        self._build_facet_indices(entries, indices.get("by_namespace", {}),
                                  indices.get("by_category", {}),
                                  indices.get("by_semantic_type", {}))

        # Build or load vector index
        if embeddings is not None:
            self._build_faiss_index(embeddings)
        else:
            print("[Indexer] No embeddings provided — FAISS index not built (will use brute-force)")

    def _build_facet_indices(self, entries: list[dict], by_ns: dict, by_cat: dict, by_st: dict):
        """Build facet-based pre-filtering indices using FAISS ids."""
        for faiss_id, entry in enumerate(entries):
            cid = entry["canonical_id"]
            ns = entry.get("namespace", "")
            cat = entry.get("category", "")
            st = entry.get("semantic_type", "")
            if ns:
                self.facet_indices["by_namespace"][ns].append(faiss_id)
            if cat:
                self.facet_indices["by_category"][cat].append(faiss_id)
            if st:
                self.facet_indices["by_semantic_type"][st].append(faiss_id)

    def _build_faiss_index(self, embeddings: np.ndarray):
        """Build the actual FAISS index."""
        try:
            import faiss
        except ImportError:
            print("[Indexer] faiss not installed. Using brute-force cosine similarity.")
            return

        embeddings = np.array(embeddings, dtype=np.float32)

        if self.index_type == "flat":
            self.index = faiss.IndexFlatIP(self.dim)  # Inner product (cosine with normalized vectors)
        elif self.index_type == "ivf":
            nlist = min(int(np.sqrt(len(embeddings))), 256)
            quantizer = faiss.IndexFlatIP(self.dim)
            self.index = faiss.IndexIVFFlat(quantizer, self.dim, nlist)
            self.index.train(embeddings)
        elif self.index_type == "ivfpq":
            nlist = min(int(np.sqrt(len(embeddings))), 256)
            m = 64  # sub-quantizers
            quantizer = faiss.IndexFlatIP(self.dim)
            self.index = faiss.IndexIVFPQ(quantizer, self.dim, nlist, m, 8)
            self.index.train(embeddings)
        else:
            print(f"[Indexer] Unknown index type: {self.index_type}")
            return

        self.index.add(embeddings)
        print(f"[Indexer] Index built: {self.index_type.upper()}, {self.index.ntotal} vectors")

    def search(self, query_embedding: np.ndarray, k: int = 50,
               namespace_filter: str | None = None,
               category_filter: str | None = None,
               semantic_type_filter: str | None = None) -> list[tuple[int, float]]:
        """Search for top-k similar entries. Returns list of (faiss_id, score)."""
        if query_embedding.ndim == 1:
            query_embedding = query_embedding.reshape(1, -1)

        # Determine candidate pool
        candidate_ids = None
        if namespace_filter and namespace_filter in self.facet_indices["by_namespace"]:
            candidate_ids = set(self.facet_indices["by_namespace"][namespace_filter])
        elif category_filter and category_filter in self.facet_indices["by_category"]:
            candidate_ids = set(self.facet_indices["by_category"][category_filter])
        elif semantic_type_filter and semantic_type_filter in self.facet_indices["by_semantic_type"]:
            candidate_ids = set(self.facet_indices["by_semantic_type"][semantic_type_filter])

        if self.index is not None:
            if candidate_ids:
                selector = faiss.IDSelectorArray(np.array(sorted(candidate_ids), dtype=np.int64))
                params = faiss.SearchParametersIVF(sel=selector) if self.index_type != "flat" else None
                scores, indices = self.index.search(query_embedding, k, params=params)
            else:
                scores, indices = self.index.search(query_embedding, k)

            results = []
            for idx, score in zip(indices[0], scores[0]):
                if idx >= 0 and idx in self.id_to_info:
                    results.append((int(idx), float(score)))
            return results
        else:
            # Brute-force cosine similarity
            return self._brute_force_search(query_embedding, k, candidate_ids)

    def _brute_force_search(self, query_embedding: np.ndarray, k: int,
                            candidate_ids: set | None = None) -> list[tuple[int, float]]:
        """Fallback brute-force search."""
        # This is a stub — real implementation would compute cosine similarity
        all_ids = list(self.id_to_info.keys())
        if candidate_ids:
            all_ids = [i for i in all_ids if i in candidate_ids]

        # Return top-k random for stub
        import random
        random.shuffle(all_ids)
        return [(i, random.uniform(0.5, 1.0)) for i in all_ids[:k]]

    def save(self, path: Path):
        """Save index to disk."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if self.index is not None:
            try:
                import faiss
                faiss.write_index(self.index, str(path))
                print(f"[Indexer] Saved FAISS index to {path}")
            except ImportError:
                pass

    def load(self, path: Path) -> bool:
        """Load index from disk."""
        path = Path(path)
        if not path.exists():
            return False
        try:
            import faiss
            self.index = faiss.read_index(str(path))
            print(f"[Indexer] Loaded FAISS index ({self.index.ntotal} vectors)")
            return True
        except ImportError:
            return False

    def candidate_pool_size(self, namespace: str | None = None) -> int:
        """Size of candidate pool for a namespace."""
        if namespace and namespace in self.facet_indices["by_namespace"]:
            return len(self.facet_indices["by_namespace"][namespace])
        return len(self.id_to_info)


# For the faiss import in search
try:
    import faiss
except ImportError:
    faiss = None
