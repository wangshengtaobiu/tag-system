"""
Stage 3 — Namespace Architecture (Pro)
Owner: pro (Architect model — semantic judgment)
Input: stage2_normalized.json + domain_profile.json
Output: namespace_freeze.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from collections import Counter

from stages import BaseStage, StageResult, StageStatus, register_stage, PipelineContext


@register_stage
class S3Namespace(BaseStage):
    stage_id = "s3"
    stage_name = "Namespace Architecture"
    owner = "pro"

    def run(self) -> StageResult:
        t0 = time.time()
        result = StageResult(stage_id=self.stage_id, status=StageStatus.RUNNING)

        entries = self.ctx.normalized_entries
        # Fallback: load from S2 output if normalized_entries is empty
        if not entries:
            s2_path = self.ctx.work_dir / "stage2_normalized.json"
            if s2_path.exists():
                print(f"[S3] Loading normalized entries from {s2_path}")
                with open(s2_path, "r", encoding="utf-8") as f:
                    s2_data = json.load(f)
                entries = s2_data.get("entries", [])
                self.ctx.normalized_entries = entries
            else:
                result.status = StageStatus.FAILED
                result.errors.append("S2 output not found. Run S2 first.")
                return result

        profile_namespaces = self.profile.get("namespace_map", {})

        # Report current namespace distribution
        ns_counts = Counter(e.get("namespace", "unknown") for e in entries)
        stats = {
            "total_entries": len(entries),
            "namespaces_used": len(ns_counts),
            "namespaces_defined": len(profile_namespaces),
            "distribution": dict(ns_counts.most_common()),
        }

        # Check for invalid namespaces
        invalid_ns = [ns for ns in ns_counts if ns not in profile_namespaces and ns != "unknown"]
        if invalid_ns:
            result.errors.append(f"Invalid namespaces found: {invalid_ns}")
            result.status = StageStatus.FAILED
            result.stats = stats
            print(f"[S3] GATE FAILED: Invalid namespaces: {invalid_ns}")
            return result

        # Check namespace size balance
        warnings = []
        for ns, count in ns_counts.items():
            if ns == "unknown":
                continue
            if count > 200:
                warnings.append(f"Namespace '{ns}' is large ({count} tags). Consider splitting.")
            elif count < 5 and ns not in ("meta_style", "style"):
                warnings.append(f"Namespace '{ns}' is small ({count} tags). Consider merging.")

        result.warnings = warnings

        # Freeze namespace design
        frozen_ns = {}
        for ns_id, ns_def in profile_namespaces.items():
            frozen_ns[ns_id] = {
                "label": ns_def.get("label", ns_id),
                "description": ns_def.get("description", ""),
                "axes": ns_def.get("axes", []),
                "categories": ns_def.get("categories", []),
                "tag_count": ns_counts.get(ns_id, 0),
                "max_depth": ns_def.get("max_depth", 3),
                "ontology_type_hint": ns_def.get("ontology_type_hint", "any"),
                "frozen": True,
                "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }

        output_data = {
            "meta": {
                "stage": "3",
                "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "status": "FROZEN",
                "total_namespaces": len(frozen_ns),
                "architecture": "router_v3_lite",
            },
            "namespaces": frozen_ns,
            "stats": stats,
            "warnings": warnings,
        }

        output_path = self.ctx.work_dir / "namespace_freeze.json"
        self._save_json(output_path, output_data)
        self.ctx.frozen_namespaces = frozen_ns

        result.status = StageStatus.PASSED
        result.output_file = str(output_path)
        result.stats = stats
        result.duration_seconds = round(time.time() - t0, 2)

        gate_msg = (
            f"{len(frozen_ns)} namespaces frozen. "
            f"{stats['namespaces_used']}/{stats['namespaces_defined']} active. "
            f"{len(invalid_ns)} invalid."
        )
        print(f"[S3] GATE PASSED: {gate_msg}")
        if warnings:
            for w in warnings:
                print(f"  ⚠ {w}")

        return result
