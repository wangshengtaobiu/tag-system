"""
Stage 0 — Tag Enrichment (Flash)
Owner: flash (batch LLM processing)
Input: acquisition export snapshot (SurfaceCorpusEntry JSONL)
Output: enriched entries with Chinese keys compatible with S1 triage

Generates semantic fields (category, definition, parent, distinction, examples)
for surface tags. Does NOT modify acquisition fields.
"""
from __future__ import annotations

import json
import time
import requests
from typing import Any

from stages import BaseStage, StageResult, StageStatus, register_stage, PipelineContext
from review_queue.schema import make_review_item, ReviewType, Severity


@register_stage
class S0Enrich(BaseStage):
    stage_id = "s0"
    stage_name = "Tag Enrichment"
    owner = "flash"

    def __init__(self, ctx: PipelineContext):
        super().__init__(ctx)
        stage_cfg = self.config.get("pipeline", {}).get("stages", {}).get("s0_enrich", {})
        flash_cfg = self.config.get("models", {}).get("flash", {})
        self.api_base = flash_cfg.get("api_base", "")
        self.api_key = flash_cfg.get("api_key", "")
        self.model = flash_cfg.get("model", "deepseek-v4-flash")
        self.batch_size = stage_cfg.get("batch_size", 5)
        self.min_batch = stage_cfg.get("min_batch", 3)
        self.max_retries = stage_cfg.get("max_retries", 3)
        self.rate_limit_delay = stage_cfg.get("rate_limit_delay", 1.0)
        self.timeout = stage_cfg.get("timeout", 300)
        self.auto_accept = self.profile.get("confidence_thresholds", {}).get("auto_accept", 0.85)
        self.valid_categories = self._extract_profile_categories()

    def run(self) -> StageResult:
        t0 = time.time()
        result = StageResult(stage_id=self.stage_id, status=StageStatus.RUNNING)

        if not self.api_key:
            result.status = StageStatus.SKIPPED
            result.errors.append("No API key configured. Skipping Flash enrichment.")
            print("[S0] SKIPPED: No API key configured.")
            return result

        entries = self._resolve_input()
        if entries is None:
            result.status = StageStatus.FAILED
            result.errors.append("No input found. Provide acquisition export via --input.")
            return result

        # Already enriched — pass through
        if entries and ("分类建议" in entries[0] or "category" in entries[0]):
            print("[S0] Input already enriched, skipping.")
            self.ctx.raw_tags = entries
            result.status = StageStatus.PASSED
            result.stats = {"total_entries": len(entries), "pass_through": True}
            result.duration_seconds = round(time.time() - t0, 2)
            return result

        batches = [entries[i:i + self.batch_size] for i in range(0, len(entries), self.batch_size)]
        total_batches = len(batches)
        all_enriched: list[dict] = []
        all_review_items: list[dict] = []

        print(f"[S0] Enriching {len(entries)} tags in {total_batches} batches (size={self.batch_size})")

        for bi, batch in enumerate(batches):
            print(f"[S0] Batch {bi + 1}/{total_batches} ({len(batch)} tags)...", end=" ", flush=True)
            enriched, review_items = self._process_batch(batch, bi)

            if enriched is not None:
                all_enriched.extend(enriched)
                all_review_items.extend(review_items)
                print(f"OK ({len(enriched)} entries, {len(review_items)} flagged)")
            else:
                print("FAILED")
                result.errors.append(f"Batch {bi + 1} failed after {self.max_retries} retries")

            if bi < total_batches - 1:
                time.sleep(self.rate_limit_delay)

        # CARDINALITY VALIDATOR: detect dropped entries
        input_labels = {e.get("label") or e.get("surface") or e.get("标签名") or e.get("name", "") for e in entries}
        output_labels = {e.get("标签名") or e.get("label") or e.get("name", "") for e in all_enriched}
        missing_labels = input_labels - output_labels

        if missing_labels:
            print(f"[S0] CARDINALITY WARNING: {len(missing_labels)} input tags missing after enrichment: {sorted(missing_labels)[:10]}")
            # Create placeholder entries for missing tags
            for label in sorted(missing_labels):
                orig = next((e for e in entries if (e.get("label") or e.get("name", "")) == label), {})
                placeholder = {
                    "标签名": label,
                    "分类建议": "",
                    "定义说明": "",
                    "上位tag": "无",
                    "区别": "",
                    "文学示例词": "",
                    "enrichment_confidence": 0.0,
                    "needs_review": True,
                    "review_reason": f"LLM dropped tag '{label}' during enrichment batch. Manual enrichment required.",
                }
                all_enriched.append(placeholder)
                all_review_items.append(make_review_item(
                    tag_name=label,
                    review_type=ReviewType.LOW_CONFIDENCE,
                    severity=Severity.HIGH,
                    confidence=0.0,
                    description=f"LLM dropped '{label}' during enrichment.",
                ))

        mean_conf = round(
            sum(e.get("enrichment_confidence", 0) for e in all_enriched) / max(len(all_enriched), 1), 3
        )

        # Save enriched output
        output_path = self.ctx.work_dir / "enriched_tags.json"
        output_data = {
            "meta": {
                "stage": "0",
                "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "total_entries": len(all_enriched),
                "batches": total_batches,
                "model": self.model,
            },
            "quality": {
                "mean_confidence": mean_conf,
                "needs_review": sum(1 for e in all_enriched if e.get("needs_review")),
            },
            "entries": all_enriched,
        }
        self._save_json(output_path, output_data)

        # Save review queue
        if all_review_items:
            review_path = self.ctx.work_dir / "stage0_review_queue.json"
            self._save_json(review_path, {
                "meta": {"stage": "0", "total": len(all_review_items), "date": time.strftime("%Y-%m-%dT%H:%M:%S")},
                "items": all_review_items,
            })

        self.ctx.raw_tags = all_enriched

        result.status = StageStatus.PASSED
        result.output_file = str(output_path)
        result.stats = {
            "total_entries": len(all_enriched),
            "batches_processed": total_batches,
            "mean_confidence": mean_conf,
            "review_items": len(all_review_items),
        }
        result.review_items = all_review_items
        result.duration_seconds = round(time.time() - t0, 2)

        print(
            f"[S0] GATE PASSED: {len(all_enriched)} enriched, "
            f"mean_conf={mean_conf}, review={len(all_review_items)}"
        )
        return result

    def _resolve_input(self) -> list[dict] | None:
        """Resolve input from ctx.raw_tags."""
        raw = self.ctx.raw_tags
        if not raw:
            return None
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return raw.get("tags") or raw.get("entries") or raw.get("data") or None
        return None

    def _extract_profile_categories(self) -> list[str]:
        categories: set[str] = set()
        for ns_def in self.profile.get("namespace_map", {}).values():
            for cat in ns_def.get("categories", []):
                categories.add(cat)
            label = ns_def.get("label", "")
            if label:
                categories.add(label)
        categories.discard("")
        return sorted(categories)

    def _build_system_prompt(self) -> str:
        cat_list = "\n".join(f"  - {c}" for c in self.valid_categories)
        return f"""你是一个中文成人内容标签语义分析专家。你的任务是为每个原始标签生成结构化的语义信息。

### 可用分类（从以下分类中选择最匹配的一个）：
{cat_list}

### 输出要求（对每个标签生成以下字段）：
- 标签名: 原始标签名，保持不变
- 分类建议: 从上述分类列表中选择一个最匹配的分类
- 定义说明: 用1-2句话简明描述该标签在成人内容中的含义和典型使用场景（不超过150字）
- 上位tag: 该标签的更上位/更通用的概念。如果没有明确上位，填"无"
- 区别: 简要说明与最相似标签的区别（不超过80字）。如果无明显相似标签，填"无明显混淆"
- 文学示例词: 3-8个在文学/小说中可能的组合词或短语，用逗号分隔
- enrichment_confidence: 0.0-1.0，你对本次分类和定义的置信度
- needs_review: true/false，如果enrichment_confidence < 0.85则为true
- review_reason: 需要审核的原因（仅在needs_review=true时提供）

### 规则：
- 定义说明应准确反映该标签在成人/色情内容语境下的含义
- 分类建议必须从上述列表中选择，不要自创分类
- 上位tag应该是该标签的直接父概念
- 如果某个标签含义模糊或可能有多重含义，降低enrichment_confidence并设置needs_review=true

### 输出格式：
返回纯JSON数组，不要包含markdown代码块、解释文字或其他包装。"""

    def _build_batch_input(self, batch: list[dict]) -> str:
        items = []
        for tag in batch:
            label = tag.get("label") or tag.get("surface") or tag.get("标签名") or tag.get("name") or tag.get("normalized", "")
            items.append({"label": label})
        return json.dumps({"tags": items}, ensure_ascii=False)

    def _call_flash(self, batch_json: str) -> dict | None:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": batch_json},
            ],
            "temperature": 0,
            "max_tokens": 8192,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        for attempt in range(self.max_retries):
            try:
                resp = requests.post(
                    f"{self.api_base}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    return resp.json()
                print(f"  API ERROR {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                print(f"  Request failed: {e}")
            if attempt < self.max_retries - 1:
                time.sleep(5)
        return None

    def _parse_output(self, api_response: dict) -> list[dict] | None:
        try:
            content = api_response["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            return None

        text = content.strip().replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            s = text.find("[")
            e = text.rfind("]")
            if s != -1 and e != -1:
                try:
                    parsed = json.loads(text[s:e + 1])
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
        errors = []
        for field_name in ("标签名", "分类建议", "定义说明"):
            if not entry.get(field_name):
                errors.append(f"[{idx}] Missing required field: {field_name}")

        confidence = entry.get("enrichment_confidence", 1.0)
        if confidence < self.auto_accept and not entry.get("needs_review"):
            errors.append(f"[{idx}] confidence={confidence} but needs_review=False")
        return errors

    def _process_batch(self, batch: list[dict], batch_id: int) -> tuple[list[dict] | None, list[dict]]:
        batch_json = self._build_batch_input(batch)

        for attempt in range(self.max_retries):
            api_response = self._call_flash(batch_json)
            if api_response is None:
                continue

            parsed = self._parse_output(api_response)
            if parsed is None:
                half_size = max(self.min_batch, len(batch) // 2)
                if half_size < len(batch):
                    batch = batch[:half_size]
                    batch_json = self._build_batch_input(batch)
                    continue
                continue

            # Normalize LLM output: ensure Chinese key names for S1 compatibility
            for entry in parsed:
                if "label" in entry and "标签名" not in entry:
                    entry["标签名"] = entry.pop("label")
                # Also normalize other possible English key variants
                if "category" in entry and "分类建议" not in entry:
                    entry["分类建议"] = entry.pop("category")
                if "definition" in entry and "定义说明" not in entry:
                    entry["定义说明"] = entry.pop("definition")
                if "parent" in entry and "上位tag" not in entry:
                    entry["上位tag"] = entry.pop("parent")
                if "distinction" in entry and "区别" not in entry:
                    entry["区别"] = entry.pop("distinction")
                if "examples" in entry and "文学示例词" not in entry:
                    entry["文学示例词"] = entry.pop("examples")

            for idx, entry in enumerate(parsed):
                errs = self._validate_entry(entry, idx)
                for err in errs[:3]:
                    print(f"  Validation: {err}")

            review_items = []
            for entry in parsed:
                confidence = entry.get("enrichment_confidence", 0)
                if confidence < self.auto_accept or entry.get("needs_review"):
                    tag_name = entry.get("标签名", "")
                    review_items.append(make_review_item(
                        tag_name=tag_name,
                        review_type=ReviewType.LOW_CONFIDENCE,
                        severity=Severity.HIGH if confidence < 0.70 else Severity.MEDIUM,
                        confidence=confidence,
                        description=entry.get("review_reason", f"Enrichment low confidence: {confidence}"),
                        context={
                            "batch_id": batch_id,
                            "category": entry.get("分类建议"),
                            "definition": (entry.get("定义说明", "") or "")[:100],
                            "parent_name": entry.get("上位tag"),
                        },
                    ))

            return parsed, review_items

        return None, []
