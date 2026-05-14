"""
Stage 5 — Alias Collapse (Flash+Pro)
Owner: flash+pro (Flash proposes alias merges, Pro confirms)
Input: stage4_resolved.json
Output: stage5_alias_resolved.json + alias_graph.json
"""
from __future__ import annotations

import time
from pathlib import Path

from stages import BaseStage, StageResult, StageStatus, register_stage, PipelineContext
from review_queue.schema import make_review_item, ReviewType, Severity


@register_stage
class S5Alias(BaseStage):
    stage_id = "s5"
    stage_name = "Alias Collapse"
    owner = "flash+pro"

    def __init__(self, ctx: PipelineContext):
        super().__init__(ctx)
        self.merge_threshold = self.profile.get("alias_policy", {}).get("merge_threshold", 0.90)
        self.auto_accept = self.profile.get("alias_policy", {}).get("auto_accept_threshold", 0.85)
        self.max_aliases = self.profile.get("alias_policy", {}).get("max_aliases_per_entry", 10)
        self.forbidden_merges = self.profile.get("alias_policy", {}).get("forbidden_merges", [])
        self.conservative = self.profile.get("alias_policy", {}).get("conservative_merges", True)

    def run(self) -> StageResult:
        t0 = time.time()
        result = StageResult(stage_id=self.stage_id, status=StageStatus.RUNNING)
        entries = self.ctx.normalized_entries

        # Already-processed aliases from S4
        existing_aliases = self.ctx.alias_graph
        alias_graph = dict(existing_aliases)
        forbidden_set = set()
        for pair in self.forbidden_merges:
            a, b = pair
            forbidden_set.add((a, b))
            forbidden_set.add((b, a))

        auto_merged = 0
        review_flagged = 0
        rejected = 0

        for entry in entries:
            name = entry.get("name", entry.get("original_name", ""))
            if entry.get("is_duplicate_of"):
                continue  # Already an alias

            possible_dupes = entry.get("possible_duplicates", [])
            if not possible_dupes:
                continue

            for dupe in possible_dupes:
                dupe_name = dupe.get("name", "") if isinstance(dupe, dict) else str(dupe)
                dupe_conf = dupe.get("confidence", 0.5) if isinstance(dupe, dict) else 0.5

                if (name, dupe_name) in forbidden_set:
                    rejected += 1
                    continue

                if self.conservative and dupe_conf < self.merge_threshold:
                    rejected += 1
                    continue

                if dupe_conf >= self.merge_threshold:
                    alias_graph[dupe_name] = name
                    # Mark dupe entry as alias
                    for e2 in entries:
                        if e2.get("name") == dupe_name or e2.get("original_name") == dupe_name:
                            e2["is_duplicate_of"] = name
                            break
                    auto_merged += 1
                elif dupe_conf >= self.auto_accept:
                    review_flagged += 1
                    result.review_items.append(make_review_item(
                        tag_name=dupe_name,
                        review_type=ReviewType.ALIAS_RISK,
                        severity=Severity.MEDIUM,
                        confidence=dupe_conf,
                        description=f"Possible alias of '{name}' (confidence={dupe_conf})",
                        canonical_id=entry.get("canonical_id"),
                        suggested_fix={
                            "action": "merge_alias",
                            "target": name,
                            "reason": f"Same concept, confidence={dupe_conf}",
                        },
                        context={
                            "primary_name": name,
                            "primary_canonical_id": entry.get("canonical_id"),
                        },
                    ))
                else:
                    rejected += 1

        # Save alias graph
        alias_data = {
            "meta": {
                "stage": "5",
                "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "total_aliases": len(alias_graph),
                "auto_merged": auto_merged,
                "review_flagged": review_flagged,
                "rejected": rejected,
                "merge_threshold": self.merge_threshold,
            },
            "alias_graph": alias_graph,
            "forbidden_merges": list(forbidden_set),
        }

        alias_path = self.ctx.work_dir / "alias_graph.json"
        self._save_json(alias_path, alias_data)

        # Save resolved entries
        output_data = {
            "meta": {
                "stage": "5",
                "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "total_entries": len(entries),
                "auto_merged": auto_merged,
                "review_flagged": review_flagged,
                "rejected": rejected,
            },
            "entries": entries,
        }

        output_path = self.ctx.work_dir / "stage5_alias_resolved.json"
        self._save_json(output_path, output_data)

        self.ctx.normalized_entries = entries
        self.ctx.alias_graph = alias_graph

        result.status = StageStatus.PASSED
        result.output_file = str(output_path)
        result.stats = {
            "total_aliases": len(alias_graph),
            "auto_merged": auto_merged,
            "review_flagged": review_flagged,
            "rejected": rejected,
            "alias_rate": round(len(alias_graph) / max(len(entries), 1) * 100, 1),
        }
        result.duration_seconds = round(time.time() - t0, 2)

        alias_rate = round(len(alias_graph) / max(len(entries), 1) * 100, 1)
        gate_msg = (
            f"{len(alias_graph)} aliases ({alias_rate}%), "
            f"{auto_merged} auto-merged, {review_flagged} flagged, {rejected} rejected."
        )
        print(f"[S5] GATE PASSED: {gate_msg}")
        if review_flagged > 0:
            print(f"  ⚠ {review_flagged} alias candidates need Pro review")

        return result
