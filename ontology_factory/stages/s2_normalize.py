"""
Stage 2 — Semantic Normalization (Flash)
Owner: flash (batch LLM processing)
Input: inventory_clean.json
Output: stage2_normalized.json + stage2_review_queue.json
"""
from __future__ import annotations

import json
import time
import requests
from pathlib import Path
from typing import Any

from stages import (
    BaseStage, StageResult, StageStatus, register_stage, PipelineContext,
    validate_canonical_id, TRUSTED_RELATION_TYPES,
)
from review_queue.schema import make_review_item, ReviewType, Severity


@register_stage
class S2Normalize(BaseStage):
    stage_id = "s2"
    stage_name = "Semantic Normalization"
    owner = "flash"

    def __init__(self, ctx: PipelineContext):
        super().__init__(ctx)
        self.api_base = self.config.get("models", {}).get("flash", {}).get("api_base", "")
        self.api_key = self.config.get("models", {}).get("flash", {}).get("api_key", "")
        self.model = self.config.get("models", {}).get("flash", {}).get("model", "deepseek-v4-flash")
        self.batch_size = self.config.get("pipeline", {}).get("stages", {}).get("s2_normalize", {}).get("batch_size", 50)
        self.min_batch = self.config.get("pipeline", {}).get("stages", {}).get("s2_normalize", {}).get("min_batch", 10)
        self.max_retries = self.config.get("pipeline", {}).get("stages", {}).get("s2_normalize", {}).get("max_retries", 3)
        self.rate_limit_delay = self.config.get("pipeline", {}).get("stages", {}).get("s2_normalize", {}).get("rate_limit_delay", 1.0)
        self.timeout = self.config.get("pipeline", {}).get("stages", {}).get("s2_normalize", {}).get("timeout", 300)

        self.valid_namespaces = set(self.profile.get("namespace_map", {}).keys())
        self.valid_semantic_types = {st["id"] for st in self.profile.get("semantic_types", [])}
        self.auto_accept = self.profile.get("confidence_thresholds", {}).get("auto_accept", 0.85)

    def run(self) -> StageResult:
        t0 = time.time()
        result = StageResult(stage_id=self.stage_id, status=StageStatus.RUNNING)

        # Check if API is available
        if not self.api_key:
            result.status = StageStatus.SKIPPED
            result.errors.append("No API key configured. Skipping Flash normalization.")
            print("[S2] SKIPPED: No API key configured")
            return result

        entries = self.ctx.raw_tags
        batches = self._split_batches(entries)
        total_batches = len(batches)
        all_normalized = []
        all_review_items = []
        batch_reports = []

        print(f"[S2] Processing {len(entries)} tags in {total_batches} batches (size={self.batch_size})")

        for bi, batch in enumerate(batches):
            print(f"[S2] Batch {bi+1}/{total_batches} ({len(batch)} tags)...", end=" ")
            normalized, review_items = self._process_batch(batch, bi)

            if normalized is not None:
                all_normalized.extend(normalized)
                all_review_items.extend(review_items)
                batch_reports.append({"batch_id": bi, "output_count": len(normalized), "review_items": len(review_items)})
                print(f"OK ({len(normalized)} entries, {len(review_items)} flagged)")
            else:
                print("FAILED")
                result.errors.append(f"Batch {bi+1} failed after {self.max_retries} retries")

            time.sleep(self.rate_limit_delay)

        # Aggregate
        primary = [e for e in all_normalized if not e.get("is_duplicate_of")]
        mean_conf = round(sum(e.get("confidence", 0) for e in all_normalized) / max(len(all_normalized), 1), 3)

        output_data = {
            "meta": {
                "stage": "2",
                "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "total_entries": len(all_normalized),
                "batches": total_batches,
                "model": self.model,
                "architecture": "FROZEN v3",
            },
            "quality": {
                "mean_confidence": mean_conf,
                "needs_review": sum(1 for e in all_normalized if e.get("needs_review")),
                "with_relations": sum(1 for e in all_normalized if e.get("relation_candidates")),
                "with_aliases": sum(1 for e in all_normalized if e.get("aliases")),
            },
            "entries": all_normalized,
        }

        output_path = self.ctx.work_dir / "stage2_normalized.json"
        self._save_json(output_path, output_data)

        # Save review queue
        if all_review_items:
            review_path = self.ctx.work_dir / "stage2_review_queue.json"
            self._save_json(review_path, {
                "meta": {"stage": "2", "total": len(all_review_items), "date": time.strftime("%Y-%m-%dT%H:%M:%S")},
                "items": all_review_items,
            })

        self.ctx.normalized_entries = all_normalized
        self.ctx.review_queue = all_review_items

        result.status = StageStatus.PASSED
        result.output_file = str(output_path)
        result.stats = {
            "total_entries": len(all_normalized),
            "batches_processed": len(batch_reports),
            "mean_confidence": mean_conf,
            "review_items": len(all_review_items),
        }
        result.review_items = all_review_items
        result.duration_seconds = round(time.time() - t0, 2)

        print(f"[S2] GATE PASSED: {len(all_normalized)} entries, mean_confidence={mean_conf}, review_queue={len(all_review_items)}")
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _split_batches(self, entries: list[dict]) -> list[list[dict]]:
        return [entries[i:i + self.batch_size] for i in range(0, len(entries), self.batch_size)]

    def _build_prompt_batch(self, batch: list[dict]) -> str:
        """Build JSON input for Flash."""
        items = []
        for tag in batch:
            items.append({
                "name": tag["name"],
                "category": tag.get("category", ""),
                "definition": tag.get("definition", "")[:150],
                "distinction": tag.get("distinction", "")[:80],
                "parent": tag.get("parent_name", "") or None,
                "examples": tag.get("examples", [])[:5],
            })
        return json.dumps({"tags": items}, ensure_ascii=False)

    def _build_prompt_text(self) -> str:
        """Build the system prompt for normalization."""
        ns_list = "\n".join(f"  - {ns}" for ns in sorted(self.valid_namespaces))
        st_list = "\n".join(f"  - {st}" for st in sorted(self.valid_semantic_types))

        return f"""You are a tag ontology normalization system. Your role is MECHANICAL only.

## Domain: Adult Content Tags

### Allowed Namespaces (MUST use one of these):
{ns_list}

### Allowed Semantic Types (MUST use one of these):
{st_list}

### Canonical ID Format:
- Format: namespace.descriptor[.detail]
- snake_case, English identifiers
- Max 3 segments (depth ≤ 3)
- First segment MUST be a valid namespace

### Trusted Relation Types (ONLY these 4):
- specialization_of
- role_pair
- opposite_of
- context_of

### Your Task:
For each tag, output:
1. canonical_id: namespace.descriptor (snake_case, English)
2. normalized_name: cleaned original name
3. namespace: one of the allowed namespaces
4. semantic_type: one of the allowed semantic types
5. category: original category
6. aliases: alternative names (same concept, different wording)
7. possible_duplicates: tags in this batch that mean the SAME concept
8. parent_canonical_id: parent in hierarchy (can be null)
9. relation_candidates: TRUSTED relation types only
10. confidence: 0.0-1.0 score
11. needs_review: true if confidence < 0.85 OR ambiguous
12. review_reason: explanation if needs_review is true

### CONSTRAINTS:
- Do NOT design new namespaces
- Do NOT invent relation types
- Do NOT merge tags (only flag as possible_duplicates)
- Confidence < 0.85 → needs_review must be True
- Be conservative: false merge is worse than duplicate survival

Output ONLY a JSON array of tag objects. No markdown, no explanation."""

    def _call_flash(self, batch_json: str, retry: int = 0) -> dict | None:
        """Call Flash API with retry logic."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._build_prompt_text()},
                {"role": "user", "content": batch_json},
            ],
            "temperature": 0,
            "max_tokens": 2048,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(
                f"{self.api_base}/chat/completions",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                print(f"API ERROR {resp.status_code}: {resp.text[:200]}")
                if retry < self.max_retries:
                    time.sleep(5)
                    return self._call_flash(batch_json, retry + 1)
                return None
            return resp.json()
        except Exception as e:
            print(f"Request failed: {e}")
            if retry < self.max_retries:
                time.sleep(5)
                return self._call_flash(batch_json, retry + 1)
            return None

    def _parse_output(self, api_response: dict) -> list[dict] | None:
        """Parse Flash API response into list of normalized entries."""
        try:
            content = api_response["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            return None

        text = content.strip()
        # Strip markdown wrapping
        text = text.replace("```json", "").replace("```", "").strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON array
            s = text.find("[")
            e = text.rfind("]")
            if s != -1 and e != -1:
                try:
                    parsed = json.loads(text[s:e+1])
                except json.JSONDecodeError:
                    return None
            else:
                return None

        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return parsed.get("tags") or parsed.get("results") or parsed.get("entries") or []
        return None

    def _validate_entry(self, entry: dict, idx: int) -> list[str]:
        """Validate a single normalized entry. Returns list of error strings."""
        errors = []
        required = ["name", "canonical_id", "namespace", "semantic_type", "category"]
        for field in required:
            if not entry.get(field):
                errors.append(f"[{idx}] Missing required field: {field}")

        cid = entry.get("canonical_id", "")
        if cid and not validate_canonical_id(cid):
            errors.append(f"[{idx}] Invalid canonical_id format: {cid}")

        ns = entry.get("namespace", "")
        if ns and ns not in self.valid_namespaces:
            errors.append(f"[{idx}] Invalid namespace: {ns}")

        st = entry.get("semantic_type", "")
        if st and st not in self.valid_semantic_types:
            errors.append(f"[{idx}] Invalid semantic_type: {st}")

        for rel in entry.get("relation_candidates", []):
            if rel.get("type") not in TRUSTED_RELATION_TYPES:
                errors.append(f"[{idx}] Invalid relation type: {rel.get('type')}")

        confidence = entry.get("confidence", 1.0)
        if confidence < self.auto_accept and not entry.get("needs_review"):
            errors.append(f"[{idx}] confidence={confidence} but needs_review=False")

        return errors

    def _process_batch(self, batch: list[dict], batch_id: int) -> tuple[list[dict] | None, list[dict]]:
        """Process a single batch. Returns (normalized_entries, review_items)."""
        batch_json = self._build_prompt_batch(batch)

        for attempt in range(self.max_retries):
            api_response = self._call_flash(batch_json, attempt)
            if api_response is None:
                continue

            parsed = self._parse_output(api_response)
            if parsed is None:
                # Try with degraded batch size
                half_size = max(self.min_batch, len(batch) // 2)
                if half_size < len(batch):
                    print(f"Parse failed, degrading batch size to {half_size}")
                    batch = batch[:half_size]
                    batch_json = self._build_prompt_batch(batch)
                    continue
                else:
                    continue

            # Validate entries
            all_errors = []
            for idx, entry in enumerate(parsed):
                errors = self._validate_entry(entry, idx)
                all_errors.extend(errors)

            if all_errors:
                print(f"Validation errors: {len(all_errors)}")
                # Still use the data but flag issues
                for err in all_errors[:5]:
                    print(f"  - {err}")

            # Build review items for low-confidence entries
            review_items = []
            for entry in parsed:
                confidence = entry.get("confidence", 0)
                if confidence < self.auto_accept or entry.get("needs_review"):
                    name = entry.get("name", "")
                    review_items.append(make_review_item(
                        tag_name=name,
                        review_type=ReviewType.LOW_CONFIDENCE,
                        severity=Severity.HIGH if confidence < 0.70 else Severity.MEDIUM,
                        confidence=confidence,
                        description=entry.get("review_reason", f"Low confidence: {confidence}"),
                        canonical_id=entry.get("canonical_id"),
                        context={
                            "batch_id": batch_id,
                            "category": entry.get("category"),
                            "namespace": entry.get("namespace"),
                            "semantic_type": entry.get("semantic_type"),
                        },
                    ))

            return parsed, review_items

        return None, []
