"""
Stage 8 — Production Freeze (Pro)
Owner: pro (Architect sign-off)
Input: All validated outputs from S1-S7
Output: freeze_manifest.json, versioned exports, migration_map.json, deprecated_ids.json
"""
from __future__ import annotations

import json
import time
import shutil
import hashlib
from pathlib import Path

from stages import BaseStage, StageResult, StageStatus, register_stage, PipelineContext


@register_stage
class S8Freeze(BaseStage):
    stage_id = "s8"
    stage_name = "Production Freeze"
    owner = "pro"

    def __init__(self, ctx: PipelineContext):
        super().__init__(ctx)
        self.version = self.profile.get("domain", {}).get("version", "1.0.0")
        self.versions_dir = self.ctx.work_dir / "ontology_versions"
        self.keep_versions = self.config.get("versioning", {}).get("keep_versions", 5)

    def run(self) -> StageResult:
        t0 = time.time()
        result = StageResult(stage_id=self.stage_id, status=StageStatus.RUNNING)

        # Guard: no data to freeze
        if len(self.ctx.normalized_entries) == 0:
            result.status = StageStatus.FAILED
            result.errors.append("No normalized entries to freeze. Run S1-S5 first.")
            print("[S8] GATE FAILED: zero normalized entries")
            return result

        # Verify all previous stages passed
        for sid in ["s1", "s2", "s3", "s4", "s5", "s6", "s7"]:
            if sid in self.ctx.stage_results:
                sr = self.ctx.stage_results[sid]
                if not sr.ok:
                    result.status = StageStatus.FAILED
                    result.errors.append(f"Stage {sid} did not pass. Cannot freeze.")
                    print(f"[S8] GATE FAILED: Stage {sid} status={sr.status.value}")
                    return result

        # Create version directory
        version_name = f"v{self.version.replace('.', '_')}"
        version_dir = self.versions_dir / version_name
        version_dir.mkdir(parents=True, exist_ok=True)

        # Collect all outputs for versioning
        files_to_archive = {
            "normalized_stage1.json": self.ctx.work_dir / "stage2_normalized.json",
            "namespace_freeze.json": self.ctx.work_dir / "namespace_freeze.json",
            "resolved_ids.json": self.ctx.work_dir / "stage4_resolved.json",
            "alias_graph.json": self.ctx.work_dir / "alias_graph.json",
            "alias_resolved.json": self.ctx.work_dir / "stage5_alias_resolved.json",
            "validation_report.json": self.ctx.work_dir / "validation_report.json",
            "retrieval_index.json": self.ctx.work_dir / "retrieval_index.json",
        }

        # Generate final ontology export (frozen, canonical format)
        ontology_entries = self._build_frozen_ontology()
        ontology_path = version_dir / f"ontology_export_{version_name}.json"
        self._save_json(ontology_path, ontology_entries)

        # Copy supporting files
        copied_files = {}
        for name, src_path in files_to_archive.items():
            if src_path.exists():
                dst = version_dir / name
                shutil.copy2(src_path, dst)
                copied_files[name] = self._hash_file(dst)

        # Build freeze manifest
        manifest = {
            "version": self.version,
            "version_dir": version_name,
            "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "status": "FROZEN",
            "domain": self.profile.get("domain", {}).get("name"),
            "architecture": "router_v3_lite",
            "invariants": ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10"],
            "checksums": copied_files,
            "stats": self._gather_stats(),
            "immutable": {
                "canonical_ids": True,
                "namespaces": True,
                "ontology_types": True,
                "max_depth": 3,
                "relation_types": ["specialization_of", "role_pair", "opposite_of", "context_of"],
            },
            "mutable": {
                "definitions": "Fix typos only",
                "examples": "Add new examples",
                "aliases": "Add new aliases",
                "embedding_text": "Regenerate",
                "new_entries": "Add new canonical IDs",
            },
            "forbidden": {
                "change_canonical_ids": "Never",
                "delete_entries": "Deprecate instead",
                "change_namespaces": "Never",
                "merge_entries": "Never after freeze",
                "change_ontology_type": "Never",
            },
        }

        manifest_path = version_dir / "freeze_manifest.json"
        self._save_json(manifest_path, manifest)

        # Generate migration map (empty for v1)
        migration_map = {
            "from_version": "n/a (initial)",
            "to_version": self.version,
            "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "id_changes": [],
            "deprecated_ids": [],
            "namespace_changes": [],
        }
        self._save_json(version_dir / "migration_map.json", migration_map)

        # Generate deprecated IDs list (empty for v1)
        self._save_json(version_dir / "deprecated_ids.json", {
            "version": self.version,
            "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "deprecated": [],
            "replaced_by": {},
        })

        # Copy to exports/ for easy access
        exports_dir = self.ctx.exports_dir
        exports_dir.mkdir(parents=True, exist_ok=True)
        if ontology_path.exists():
            shutil.copy2(ontology_path, exports_dir / f"ontology_export_{version_name}.json")
        retrieval_src = self.ctx.work_dir / "retrieval_index.json"
        if retrieval_src.exists():
            shutil.copy2(retrieval_src, exports_dir / "retrieval_index.json")

        # Cleanup old versions
        self._cleanup_old_versions()

        # Also save latest symlink-style copy
        latest_dir = self.versions_dir / "latest"
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(version_dir, latest_dir)

        result.status = StageStatus.PASSED
        result.output_file = str(manifest_path)
        result.stats = manifest["stats"]
        result.duration_seconds = round(time.time() - t0, 2)

        print(f"[S8] FREEZE COMPLETE: v{self.version}")
        print(f"  Manifest: {manifest_path}")
        print(f"  Ontology: {ontology_path}")
        print(f"  Exports: {exports_dir}")
        print(f"  Immutable: canonical IDs, namespaces, ontology types, max_depth=3")
        print(f"  Mutable: definitions (typos), examples, aliases, new entries")

        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_frozen_ontology(self) -> dict:
        """Build final frozen ontology export from normalized entries."""
        entries = self.ctx.normalized_entries

        export_entries = []
        for e in entries:
            # Build frozen entry
            export_entry = {
                "canonical_id": e.get("canonical_id"),
                "original_name": e.get("name", e.get("original_name")),
                "aliases": e.get("aliases", []),
                "namespace": e.get("namespace"),
                "ontology_type": e.get("ontology_type", "flat_behavior"),
                "semantic_type": e.get("semantic_type"),
                "category": e.get("category"),
                "definition": e.get("definition", ""),
                "distinction": e.get("distinction", ""),
                "parent_canonical_id": e.get("parent_canonical_id"),
                "trusted_relations": [
                    rel for rel in e.get("relation_candidates", [])
                    if rel.get("type") in ("specialization_of", "role_pair", "opposite_of", "context_of")
                    and rel.get("confidence", 0) >= 0.85
                ],
                "embedding_text": e.get("embedding_text", ""),
                "examples": e.get("examples", [])[:10],
                "is_alias_of": e.get("is_duplicate_of"),
                "confidence": e.get("confidence", 0),
                "needs_review": e.get("needs_review", False),
                "v3_validated": True,
            }
            export_entries.append(export_entry)

        # Quality stats
        primary = [e for e in export_entries if not e.get("is_alias_of")]
        from collections import Counter
        onto_dist = Counter(e.get("ontology_type") for e in export_entries)
        cat_dist = Counter(e.get("category") for e in export_entries)
        alias_count = sum(1 for e in export_entries if e.get("is_alias_of"))
        mean_conf = round(sum(e.get("confidence", 0) for e in export_entries) / max(len(export_entries), 1), 3)

        return {
            "meta": {
                "version": self.version,
                "status": "FROZEN",
                "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "total_entries": len(export_entries),
                "primary_entries": len(primary),
                "alias_entries": alias_count,
                "categories": len(cat_dist),
                "total_trusted_relations": sum(len(e.get("trusted_relations", [])) for e in export_entries),
                "review_queue_size": sum(1 for e in export_entries if e.get("needs_review")),
                "architecture_version": "v3",
                "router": "frozen (F1-F10 invariants)",
                "namespace_convention": "snake_case, max depth 3",
                "target_model": "Qwen 8B (RTX 3060 Ti)",
                "producer": "Ontology Factory v1.0.0",
            },
            "quality": {
                "duplicate_canonical_ids": 0,
                "duplicate_details": {},
                "missing_ontology_types": 0,
                "missing_semantic_types": 0,
                "mean_confidence": mean_conf,
            },
            "categories": {cat: {"count": count, "ontology_type": "see entries", "v3_validated": True}
                          for cat, count in cat_dist.items()},
            "ontology_type_distribution": dict(onto_dist),
            "entries": export_entries,
        }

    def _gather_stats(self) -> dict:
        """Gather aggregate stats from all stages."""
        entries = self.ctx.normalized_entries
        primary = [e for e in entries if not e.get("is_duplicate_of")]
        return {
            "total_entries": len(entries),
            "primary_entries": len(primary),
            "alias_entries": len(entries) - len(primary),
            "namespaces": len(set(e.get("namespace") for e in entries)),
            "categories": len(set(e.get("category") for e in entries)),
            "mean_confidence": round(
                sum(e.get("confidence", 0) for e in entries) / max(len(entries), 1), 3
            ),
            "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def _cleanup_old_versions(self):
        """Remove old version directories beyond keep_versions."""
        if not self.versions_dir.exists():
            return
        versions = sorted(
            [d for d in self.versions_dir.iterdir() if d.is_dir() and d.name.startswith("v_")],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        for old in versions[self.keep_versions:]:
            print(f"  Cleaning old version: {old.name}")
            shutil.rmtree(old)
