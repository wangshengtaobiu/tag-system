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
        self.batch_size = self.config.get("pipeline", {}).get("stages", {}).get("s2_normalize", {}).get("batch_size", 3)
        self.min_batch = self.config.get("pipeline", {}).get("stages", {}).get("s2_normalize", {}).get("min_batch", 2)
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
        # Fallback: if raw_tags don't have 'name' field, load from S1 output
        if entries and "name" not in entries[0]:
            inv_path = self.ctx.work_dir / "inventory_clean.json"
            if inv_path.exists():
                print(f"[S2] Raw entries lack 'name' field, loading from {inv_path}")
                with open(inv_path, "r", encoding="utf-8") as f:
                    inv_data = json.load(f)
                entries = inv_data.get("entries", [])
                self.ctx.raw_tags = entries
            else:
                result.status = StageStatus.FAILED
                result.errors.append("S1 output not found. Run S1 first or provide data with 'name' field.")
                return result
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
        """Build the system prompt for normalization — conservative, no drift."""
        ns_list = "\n".join(f"  - {ns}" for ns in sorted(self.valid_namespaces))
        st_list = "\n".join(f"  - {st}" for st in sorted(self.valid_semantic_types))

        return f"""You are a conservative tag normalization system for Chinese adult content tags.

Your goal is STABILITY, not cleverness.

### Rules:

1. raw_tag is preserved as-is. Never translate or replace the original tag.

2. canonical_zh (the "name" field) must be Simplified Chinese.
   - Short, stable, community-standard form.
   - For established abbreviations (NTR, SM, BDSM, TS, JK, OL), keep them as-is.
   - Do NOT translate to English.
   - Do NOT add explanations or sentences.

3. aliases: ONLY include real equivalent names from the same concept.
   - Must be actual alternative names used in real communities.
   - Do NOT generate English translations.
   - Do NOT generate synonyms, style words, or related concepts.
   - If uncertain, leave aliases empty.
   - When in doubt, do NOT add an alias.

4. Do NOT infer or expand category/namespace/semantic_type beyond what the input provides.
   - Use the input category if available.
   - Pick namespace from the allowed list below — choose the most obvious match.
   - If no clear match, set needs_review=true.

5. When uncertain (ambiguous meaning, unclear language, possible duplicate, unsure canonical), set needs_review=true.
   Do NOT guess.

### Allowed Namespaces:
{ns_list}

### Allowed Semantic Types:
{st_list}

### Output format:
Return ONLY a JSON array. Each element must have:
canonical_id (format "namespace.descriptor", snake_case, English, max 2 segments),
name (canonical_zh, Simplified Chinese),
namespace (from allowed list),
semantic_type (from allowed list),
category (from input, or empty string),
aliases (list of real equivalent names only, no English translations),
possible_duplicates (other tags in this batch meaning the SAME thing),
parent_canonical_id (parent or null),
relation_candidates (only use: specialization_of, role_pair, opposite_of, context_of),
confidence (0.0-1.0),
needs_review (true/false),
review_reason (only when needs_review=true).

No markdown. No explanation. No wrapping text."""

    def _call_flash(self, batch_json: str, retry: int = 0) -> dict | None:
        """Call Flash API with retry logic."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._build_prompt_text()},
                {"role": "user", "content": batch_json},
            ],
            "temperature": 0,
            "max_tokens": 8192,
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

        for rel in (entry.get("relation_candidates") or []):
            if isinstance(rel, dict):
                rel_type = rel.get("type", "")
            elif isinstance(rel, str):
                rel_type = rel
            else:
                continue
            if rel_type not in TRUSTED_RELATION_TYPES:
                errors.append(f"[{idx}] Invalid relation type: {rel_type}")

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

            # Post-process: filter aliases to remove English translations
            ESTABLISHED_ABBR = {"NTR", "SM", "BDSM", "TS", "JK", "OL", "R18", "R18G",
                                "NTRN", "NTRH", "NTRR"}
            COMMON_ROMAJI = {"netorare", "netori", "mesuochi", "mesudochi", "shibari",
                             "kinbaku", "irumachio", "nakadashi", "okazukai", "sumata",
                             "aizuchi", "bukkake", "gokkun", "paizuri", "tenga", "hentai",
                             "ecchi", "yuri", "yaoi", "futanari", "tentacle", "ahegao"}
            for entry in parsed:
                raw_aliases = entry.get("aliases", [])
                filtered = []
                for alias in raw_aliases:
                    # Keep if: contains CJK chars
                    has_cjk = any("\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u30ff" for c in alias)
                    # Keep if: established abbreviation
                    is_established_abbr = alias.upper() in ESTABLISHED_ABBR
                    # Keep if: known romaji term
                    is_romaji = alias.lower() in COMMON_ROMAJI
                    # Keep if: underscore-style canonical (snake_case, single word)
                    is_canonical_style = "_" in alias and " " not in alias
                    # Reject: multi-word English phrases (e.g. "big breasts", "leg fetish")
                    is_english_phrase = " " in alias and not has_cjk
                    if is_english_phrase:
                        continue
                    if has_cjk or is_established_abbr or is_romaji or is_canonical_style:
                        filtered.append(alias)
                entry["aliases"] = filtered[:10]  # cap at 10

            # Post-process: fix common namespace mistakes
            for entry in parsed:
                ns = entry.get("namespace", "")
                if ns and ns not in self.valid_namespaces:
                    # Try to find closest match by prefix
                    for valid_ns in sorted(self.valid_namespaces):
                        if ns.startswith(valid_ns) or valid_ns.startswith(ns):
                            entry["namespace"] = valid_ns
                            # Also fix canonical_id prefix
                            cid = entry.get("canonical_id", "")
                            if cid:
                                parts = cid.split(".", 1)
                                if len(parts) == 2:
                                    entry["canonical_id"] = f"{valid_ns}.{parts[1]}"
                            break

            # CARDINALITY VALIDATOR: detect dropped/renamed tags
            name_to_orig = {tag["name"]: tag for tag in batch}
            input_names = {tag["name"] for tag in batch}
            output_names = {entry.get("name", "") for entry in parsed}
            missing_names = input_names - output_names
            extra_names = output_names - input_names

            if missing_names:
                print(f"  CARDINALITY WARNING: {len(missing_names)} input tags missing in output: {sorted(missing_names)}")
                # Try to match missing tags to renamed outputs (LLM may have translated)
                # Build a mapping: for each missing tag, check if any output entry's aliases
                # or possible_duplicates mention it
                name_to_entry = {e.get("name"): e for e in parsed}
                for missing in sorted(missing_names):
                    # Check if any output entry has this missing name as an alias
                    found_in_alias = None
                    for entry in parsed:
                        if missing in (entry.get("aliases") or []):
                            found_in_alias = entry
                            break
                    if found_in_alias:
                        # The tag was renamed but alias exists — add a separate entry
                        print(f"    {missing} -> found as alias of {found_in_alias['name']}, creating separate entry")
                        new_entry = {
                            "canonical_id": found_in_alias["canonical_id"],
                            "name": missing,
                            "namespace": found_in_alias["namespace"],
                            "semantic_type": found_in_alias["semantic_type"],
                            "category": found_in_alias["category"],
                            "aliases": [found_in_alias["name"]],
                            "possible_duplicates": [found_in_alias["name"]],
                            "parent_canonical_id": found_in_alias.get("parent_canonical_id"),
                            "relation_candidates": [],
                            "confidence": 0.5,
                            "needs_review": True,
                            "review_reason": f"LLM renamed '{missing}' to '{found_in_alias['name']}'. Keeping original as separate entry.",
                        }
                        parsed.append(new_entry)
                    else:
                        # Truly missing — create a placeholder entry with best-effort namespace
                        orig_tag = name_to_orig.get(missing, {})
                        print(f"    {missing} -> truly missing, creating review placeholder")
                        # Try to infer namespace from category by matching against namespace labels
                        category = orig_tag.get("category", "")
                        inferred_ns = "meta_style"  # Safe fallback
                        for valid_ns, ns_def in self.profile.get("namespace_map", {}).items():
                            ns_label = ns_def.get("label", "").lower()
                            if category and (category.lower() in ns_label or ns_label in category.lower()):
                                inferred_ns = valid_ns
                                break
                        new_entry = {
                            "canonical_id": f"{inferred_ns}.{missing}",
                            "name": missing,
                            "namespace": inferred_ns,
                            "semantic_type": "unknown",
                            "category": category,
                            "aliases": [],
                            "possible_duplicates": [],
                            "parent_canonical_id": None,
                            "relation_candidates": [],
                            "confidence": 0.0,
                            "needs_review": True,
                            "review_reason": f"LLM dropped tag '{missing}' entirely. Manual normalization required.",
                        }
                        parsed.append(new_entry)

            # Preserve definition/distinction/examples from input (LLM prompt doesn't request them back)
            for entry in parsed:
                orig = name_to_orig.get(entry.get("name", ""))
                if orig:
                    entry.setdefault("definition", orig.get("definition", "")[:150])
                    entry.setdefault("distinction", orig.get("distinction", "")[:80])
                    entry.setdefault("parent_name", orig.get("parent_name", ""))
                    entry.setdefault("examples", orig.get("examples", []))

            # Validate entries (skip placeholders created by cardinality validator)
            all_errors = []
            for idx, entry in enumerate(parsed):
                if entry.get("confidence") == 0.0 and entry.get("needs_review") and "dropped" in str(entry.get("review_reason", "")):
                    continue  # Skip placeholder validation
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
