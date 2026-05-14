"""
Stage 7 — Retrieval Export (Script)
Owner: script (pure transformation)
Input: stage5_alias_resolved.json (frozen ontology entries)
Output: retrieval_index.json
"""
from __future__ import annotations

import time
from pathlib import Path
from collections import defaultdict

from stages import (
    BaseStage, StageResult, StageStatus, register_stage, PipelineContext,
    build_retrieval_embeddings,
)


@register_stage
class S7RetrievalExport(BaseStage):
    stage_id = "s7"
    stage_name = "Retrieval Export"
    owner = "script"

    def run(self) -> StageResult:
        t0 = time.time()
        result = StageResult(stage_id=self.stage_id, status=StageStatus.RUNNING)
        entries = self.ctx.normalized_entries

        retrieval_entries = build_retrieval_embeddings(entries)

        # Build facet indices
        by_namespace = defaultdict(list)
        by_category = defaultdict(list)
        by_semantic_type = defaultdict(list)

        for re in retrieval_entries:
            cid = re["canonical_id"]
            if re.get("namespace"):
                by_namespace[re["namespace"]].append(cid)
            if re.get("category"):
                by_category[re["category"]].append(cid)
            if re.get("semantic_type"):
                by_semantic_type[re["semantic_type"]].append(cid)

        avg_chars = round(
            sum(len(re.get("embedding_text", "")) for re in retrieval_entries) / max(len(retrieval_entries), 1)
        )

        output_data = {
            "meta": {
                "version": "1.0.0",
                "stage": "7",
                "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "total_entries": len(retrieval_entries),
                "embedding_model": self.profile.get("retrieval_facets", {}).get("embedding_model", "bge-large-zh-v1.5"),
                "reranker": "Qwen 8B (local, RTX 3060 Ti)",
                "avg_embedding_chars": avg_chars,
                "namespaces": len(by_namespace),
                "categories": len(by_category),
                "semantic_types": len(by_semantic_type),
            },
            "entries": retrieval_entries,
            "indices": {
                "by_namespace": {ns: sorted(ids) for ns, ids in sorted(by_namespace.items())},
                "by_category": {cat: sorted(ids) for cat, ids in sorted(by_category.items())},
                "by_semantic_type": {st: sorted(ids) for st, ids in sorted(by_semantic_type.items())},
            },
        }

        output_path = self.ctx.work_dir / "retrieval_index.json"
        self._save_json(output_path, output_data)

        result.status = StageStatus.PASSED
        result.output_file = str(output_path)
        result.stats = {
            "total_entries": len(retrieval_entries),
            "avg_embedding_chars": avg_chars,
            "namespaces": len(by_namespace),
            "categories": len(by_category),
            "semantic_types": len(by_semantic_type),
        }
        result.duration_seconds = round(time.time() - t0, 2)

        print(f"[S7] GATE PASSED: {len(retrieval_entries)} entries, {avg_chars} avg chars, "
              f"{len(by_namespace)} namespaces, {len(by_category)} categories, {len(by_semantic_type)} semantic_types")
        return result
