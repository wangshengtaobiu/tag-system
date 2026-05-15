"""
Stage 1 — Inventory Triage
Owner: script (fully automated)
Input: raw_tags.json
Output: inventory_clean.json + s1_stats.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from collections import Counter

from stages import BaseStage, StageResult, StageStatus, register_stage, PipelineContext


@register_stage
class S1Triage(BaseStage):
    stage_id = "s1"
    stage_name = "Inventory Triage"
    owner = "script"

    def run(self) -> StageResult:
        t0 = time.time()
        result = StageResult(stage_id=self.stage_id, status=StageStatus.RUNNING)
        raw = self.ctx.raw_tags

        stats = {
            "input_count": len(raw),
            "duplicates_removed": 0,
            "empty_names_removed": 0,
            "short_names_flagged": 0,
            "language_distribution": {},
        }

        cleaned = []
        seen_names = set()

        for tag in raw:
            name = (tag.get("name") or tag.get("标签名") or tag.get("original_name") or "").strip()

            # 1. Skip empty names
            if not name or len(name) < 1:
                stats["empty_names_removed"] += 1
                continue

            # 2. Skip exact name duplicates
            if name in seen_names:
                stats["duplicates_removed"] += 1
                continue
            seen_names.add(name)

            # 3. Flag short names
            if len(name) < 2:
                stats["short_names_flagged"] += 1

            # 4. Build clean entry
            entry = {
                "name": name,
                "category": tag.get("category") or tag.get("分类建议") or tag.get("分类") or "",
                "definition": tag.get("definition") or tag.get("定义说明") or tag.get("描述") or "",
                "distinction": tag.get("distinction") or tag.get("区别") or "",
                "parent_name": tag.get("parent_name") or tag.get("上位tag") or "",
                "examples": self._extract_examples(tag),
            }
            cleaned.append(entry)

        stats["output_count"] = len(cleaned)
        stats["language_distribution"] = self._detect_language_mix(cleaned)

        # Save
        output_path = self.ctx.work_dir / "inventory_clean.json"
        self._save_json(output_path, {
            "meta": {
                "stage": "1",
                "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "input_count": stats["input_count"],
                "output_count": stats["output_count"],
            },
            "stats": stats,
            "entries": cleaned,
        })

        # Save stats
        self._save_json(self.ctx.work_dir / "s1_stats.json", stats)

        self.ctx.raw_tags = cleaned  # Update context

        result.status = StageStatus.PASSED
        result.output_file = str(output_path)
        result.stats = stats
        result.duration_seconds = round(time.time() - t0, 2)

        gate_msg = (
            f"All tags accounted for. {stats['output_count']} clean, "
            f"{stats['duplicates_removed']} duplicates removed, "
            f"{stats['empty_names_removed']} empty names removed."
        )
        print(f"[S1] GATE PASSED: {gate_msg}")
        return result

    @staticmethod
    def _extract_examples(tag: dict) -> list[str]:
        """Extract examples from various field names."""
        for key in ("examples", "示例词", "文学示例词", "示例"):
            val = tag.get(key, "")
            if isinstance(val, list):
                return val[:10]
            if isinstance(val, str) and val.strip():
                return [x.strip() for x in val.replace("、", ",").replace("，", ",").split(",") if x.strip()][:10]
        return []

    @staticmethod
    def _detect_language_mix(entries: list[dict]) -> dict[str, int]:
        """Count language categories."""
        zh = en = jp = mixed = 0
        for e in entries:
            name = e["name"]
            has_cjk = any("\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u30ff" for c in name)
            has_latin = any(c.isascii() and c.isalpha() for c in name)
            if has_cjk and has_latin:
                mixed += 1
            elif has_cjk:
                if any("\u3040" <= c <= "\u30ff" for c in name):
                    jp += 1
                else:
                    zh += 1
            elif has_latin:
                en += 1
            else:
                zh += 1  # default
        return {"zh": zh, "en": en, "jp": jp, "mixed": mixed}
