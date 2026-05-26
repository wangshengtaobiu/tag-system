# Documentation Localization Report

**Date**: 2026-05-26
**Scope**: 全部 markdown 文档。不修改代码、配置、测试。

---

## 已本地化的文档 Localized

| 文件 | 状态 | 说明 |
|------|------|------|
| `README.md` (根) | 已本地化 | 中文主简介 + English Summary + 双语标题 |
| `tag_acquisition/README.md` | 已本地化 | 中文主 + pipeline/Config/Schema 中文解释 |
| `ontology_factory/README.md` | 已本地化 | 中文主 + S0 Contract + Review Queue + 9 阶段表 |
| `tests/README.md` | 已本地化 | 中文主 + 测试文件表 + 使用方法 + 指标 |
| `docs/RELEASE_NOTES_v0.1.md` | 已本地化 | 中文主 + English Summary + 观测数据 + 已知限制 |
| `ontology_factory/metrics/observation_report_20260524.md` | 已本地化 | 中文主 + 双语表头 |
| `ontology_factory/metrics/v0.1-stable_STATUS.md` | 已本地化 | 中文主 + 双语表头 |
| `docs/specs/tag-system-design.md` | 已是中文 | 无需变更 |
| `ontology_factory/MANUAL.md` | 已是中文 | 无需变更 |
| `ontology_factory/docs/ontology_factory_design.md` | 已是中文 | 无需变更 |

---

## 移到 internal 的文档 Moved to Internal

以下是一次性 release audit 产物，已移入 `docs/internal/`：

- `AUDIT_REPORT.md`
- `FINAL_RELEASE_SUMMARY.md`
- `GITHUB_VISIBILITY.md`
- `LICENSE_RECOMMENDATION.md`
- `README_AUDIT.md`
- `RELEASE_BLOCKING_CHECK.md`
- `RELEASE_GIT_AUDIT.md`
- `RELEASE_PRECHECK.md`
- `TEST_LAYOUT_PLAN.md`

---

## 保持英文的内容（未翻译）

以下类别严格保持英文：

| 类别 Category | 示例 Example |
|---------------|--------------|
| 文件名 | `run_factory.py`, `factory_config.yaml`, `adult_profile.json` |
| class/function | `BaseStage`, `PipelineContext`, `S0Enrich` |
| schema field | `label`, `count`, `canonical_id`, `namespace`, `confidence` |
| stage 名 | `s0`, `s1`, `s2`, ..., `s8` |
| config key | `batch_size`, `min_batch`, `max_retries`, `auto_accept` |
| JSON key | `enrichment_confidence`, `needs_review`, `review_reason` |
| CLI 参数 | `--stage`, `--end-stage`, `--dry-run`, `--skip-flash` |
| git 命令 | `git clone`, `git push`, `git tag` |

---

## 保留英文的工程术语

以下术语在中文正文中保持英文：

pipeline, retrieval, ontology, schema, snapshot, review queue, stage, normalization, alias, namespace, canonical ID, embedding, surface form, delimiter policy, enrichment, triage, freeze, dedup, corpus, placeholder, cardinality validator, conservative policy, auto-accept, fallback

---

## 文档风格

- 无 "AI revolution" / "next-generation" / "powerful" / "state-of-the-art" 等空话
- 无全文双语重复
- 无机器翻译痕迹
- 风格：中文技术博客 + 工程文档，清晰克制

---

## 仍需人工润色的地方

| 位置 | 说明 |
|------|------|
| metrics 报告中的专业术语 | 已双语化表头，但部分分析性文字仍需领域专家审阅 |
| MANUAL.md (605 行) | 已是中文，但内容较长，未做精简 |

---

## 禁止项确认

- 未修改任何代码
- 未修改任何配置
- 未修改任何测试数据
