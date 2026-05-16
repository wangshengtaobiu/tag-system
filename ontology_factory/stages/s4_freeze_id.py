"""
Stage 4 — Canonical ID Freeze (Flash+Pro)
Owner: flash+pro (Flash proposes, Pro resolves duplicates)
Input: stage2_normalized.json + namespace_freeze.json
Output: stage4_resolved.json
"""
from __future__ import annotations

import time
from pathlib import Path
from collections import Counter

from stages import (
    BaseStage, StageResult, StageStatus, register_stage, PipelineContext,
    validate_canonical_id, count_duplicate_cids,
)


@register_stage
class S4FreezeID(BaseStage):
    stage_id = "s4"
    stage_name = "Canonical ID Freeze"
    owner = "flash+pro"

    def __init__(self, ctx: PipelineContext):
        super().__init__(ctx)
        self.architect_fixes: dict[str, dict] = {}  # tag_name → fix dict
        self.true_aliases: dict[str, str] = {}       # alias_name → primary_name
        self._load_fixes()
        self._load_aliases()

    def _load_fixes(self):
        """Load architect fixes from work_dir/architect_fixes.json if exists."""
        path = self.ctx.work_dir / "architect_fixes.json"
        if path.exists():
            try:
                data = self._load_json(path)
                self.architect_fixes = data if isinstance(data, dict) else {}
                print(f"[S4] Loaded {len(self.architect_fixes)} architect fixes from {path}")
            except Exception as e:
                print(f"[S4] WARN: Failed to load architect fixes: {e}")

    def _load_aliases(self):
        """Load confirmed aliases from work_dir/confirmed_aliases.json if exists."""
        path = self.ctx.work_dir / "confirmed_aliases.json"
        if path.exists():
            try:
                data = self._load_json(path)
                # Expect dict format: alias_name → primary_name
                if isinstance(data, dict):
                    self.true_aliases = data
                elif isinstance(data, list):
                    # Support list of {alias, primary} objects
                    for item in data:
                        if isinstance(item, dict):
                            alias = item.get("alias") or item.get("name")
                            primary = item.get("primary") or item.get("target")
                            if alias and primary:
                                self.true_aliases[alias] = primary
                print(f"[S4] Loaded {len(self.true_aliases)} confirmed aliases from {path}")
            except Exception as e:
                print(f"[S4] WARN: Failed to load confirmed aliases: {e}")

    def register_fix(self, tag_name: str, fix: dict):
        """Register an architect fix for a specific tag."""
        self.architect_fixes[tag_name] = fix

    def register_alias(self, alias_name: str, primary_name: str):
        """Register a confirmed alias."""
        self.true_aliases[alias_name] = primary_name

    def run(self) -> StageResult:
        t0 = time.time()
        result = StageResult(stage_id=self.stage_id, status=StageStatus.RUNNING)
        entries = self.ctx.normalized_entries

        # Fallback: load from S2 output if normalized_entries is empty
        if not entries:
            s2_path = self.ctx.work_dir / "stage2_normalized.json"
            if s2_path.exists():
                print(f"[S4] Loading normalized entries from {s2_path}")
                with open(s2_path, "r", encoding="utf-8") as f:
                    s2_data = self._load_json(s2_path)
                entries = s2_data.get("entries", [])
                self.ctx.normalized_entries = entries
            else:
                result.status = StageStatus.FAILED
                result.errors.append("No normalized entries. Run S1-S2 first.")
                return result

        fixes_applied = 0
        aliases_marked = 0
        depth_truncations = 0

        for entry in entries:
            name = entry.get("name", entry.get("original_name", ""))

            # 1. Apply architect fixes
            if name in self.architect_fixes:
                fix = self.architect_fixes[name]
                for key, value in fix.items():
                    if key != "reason":
                        entry[key] = value
                fixes_applied += 1

            # 2. Mark confirmed aliases
            if name in self.true_aliases:
                entry["is_duplicate_of"] = self.true_aliases[name]
                aliases_marked += 1

            # 3. Truncate depth-4+ IDs
            cid = entry.get("canonical_id", "")
            if cid:
                segments = cid.split(".")
                if len(segments) > 3:
                    entry["canonical_id"] = ".".join(segments[:3])
                    depth_truncations += 1

            # 4. Validate format
            if cid and not validate_canonical_id(entry.get("canonical_id", cid)):
                result.warnings.append(f"Invalid ID format after fixes: {name} → {entry.get('canonical_id')}")

        # 5. Auto-deduplicate: keep highest confidence entry, mark others as duplicates
        cid_groups = {}
        for entry in entries:
            cid = entry.get("canonical_id", "")
            if cid:
                cid_groups.setdefault(cid, []).append(entry)

        deduped = 0
        for cid, group in cid_groups.items():
            if len(group) > 1:
                # Sort by confidence descending, keep first
                group.sort(key=lambda e: e.get("confidence", 0), reverse=True)
                primary = group[0]
                for dup in group[1:]:
                    dup["is_duplicate_of"] = primary.get("name", "")
                    dup["canonical_id"] = ""  # Clear duplicate ID
                    deduped += 1

        if deduped:
            print(f"[S4] Auto-deduplicated: {deduped} entries marked as duplicates")

        # 6. Check for remaining duplicate IDs
        dups = count_duplicate_cids(entries)
        if dups:
            result.errors.append(f"DUPLICATE CANONICAL IDs after fixes: {dups}")
            result.status = StageStatus.FAILED
            result.stats = {
                "total": len(entries),
                "fixes_applied": fixes_applied,
                "aliases_marked": aliases_marked,
                "depth_truncations": depth_truncations,
                "duplicate_ids": len(dups),
                "duplicate_details": dups,
            }
            print(f"[S4] GATE FAILED: {len(dups)} duplicate ID groups remaining")
            for cid, count in list(dups.items())[:5]:
                print(f"  - {cid}: {count} entries")
            return result

        # 6. Compute confidence distribution
        conf_bins = {"0.95+": 0, "0.85-0.94": 0, "0.70-0.84": 0, "<0.70": 0}
        for e in entries:
            c = e.get("confidence", 0)
            if c >= 0.95:
                conf_bins["0.95+"] += 1
            elif c >= 0.85:
                conf_bins["0.85-0.94"] += 1
            elif c >= 0.70:
                conf_bins["0.70-0.84"] += 1
            else:
                conf_bins["<0.70"] += 1

        mean_conf = round(sum(e.get("confidence", 0) for e in entries) / max(len(entries), 1), 3)

        # Save
        output_data = {
            "meta": {
                "stage": "4",
                "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "total_entries": len(entries),
                "fixes_applied": fixes_applied,
                "aliases_confirmed": aliases_marked,
                "remaining_duplicates": 0,
                "architecture": "FROZEN v3",
            },
            "confidence_distribution": conf_bins,
            "mean_confidence": mean_conf,
            "entries": entries,
        }

        output_path = self.ctx.work_dir / "stage4_resolved.json"
        self._save_json(output_path, output_data)

        self.ctx.normalized_entries = entries
        self.ctx.alias_graph = {k: v for k, v in self.true_aliases.items()}

        result.status = StageStatus.PASSED
        result.output_file = str(output_path)
        result.stats = {
            "total": len(entries),
            "fixes_applied": fixes_applied,
            "aliases_confirmed": aliases_marked,
            "depth_truncations": depth_truncations,
            "duplicate_ids": 0,
            "mean_confidence": mean_conf,
        }
        result.duration_seconds = round(time.time() - t0, 2)

        print(f"[S4] GATE PASSED: 0 duplicate IDs, {fixes_applied} fixes, {aliases_marked} aliases, mean_confidence={mean_conf}")
        return result
