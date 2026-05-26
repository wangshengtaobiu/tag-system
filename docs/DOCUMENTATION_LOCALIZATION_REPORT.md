# Documentation Localization Report

**Date:** 2026-05-26
**Scope:** README files + docs/specs only. No code, config, or test changes.

---

## 已双语化的文档

| 文件 | 状态 | 说明 |
|------|------|------|
| `README.md` (root) | 已完成 | 中文主简介 + English Summary + 双语标题 |
| `tag_acquisition/README.md` | 已完成 | 中文主文档 + English Summary + pipeline/Config/Schema 中文解释 |
| `ontology_factory/README.md` | 已完成 | 中文主文档 + English Summary + S0 Contract + Review Queue + 9 阶段表 |
| `docs/specs/tag-system-design.md` | 已是中文 | 无需变更，工程接口/字段名保持英文 |

---

## 保持英文的内容（未翻译）

以下类别严格保持英文，未做任何翻译：

| 类别 | 示例 |
|------|------|
| 文件名 | `run_factory.py`, `factory_config.yaml`, `adult_profile.json` |
| class/function 名 | `BaseStage`, `PipelineContext`, `S0Enrich` |
| schema field | `label`, `count`, `canonical_id`, `namespace`, `confidence` |
| stage 名 | `s0`, `s1`, `s2`, `s3`, `s4`, `s5`, `s6`, `s7`, `s8` |
| config key | `batch_size`, `min_batch`, `max_retries`, `auto_accept` |
| JSON key | `enrichment_confidence`, `needs_review`, `review_reason` |
| CLI 参数 | `--stage`, `--end-stage`, `--dry-run`, `--skip-flash`, `--profile`, `--input` |
| git 命令 | `git clone`, `git push`, `git tag` |

---

## 保留英文的工程术语

以下术语在中文正文中保持英文，不做翻译：

pipeline, retrieval, ontology, schema, snapshot, review queue, stage, normalization, alias, namespace, canonical ID, embedding, surface form, delimiter policy, enrichment, triage, freeze, dedup, corpus

---

## 仍需人工润色的地方

| 位置 | 说明 |
|------|------|
| `ontology_factory/docs/操作手册.md` | 文件名仍为中文，如需 GitHub 可读性可改为 `MANUAL.md`（已有一个 MANUAL.md 在 ontology_factory 根目录，需确认是否重复） |
| `ontology_factory/README.md` 第 116 行 | MANUAL.md 链接指向根目录下的文件，`docs/ontology_factory_design.md` 也在 docs 目录下，路径需确认 |
| S0 prompt 细节 | README 中只概括了 S0 做什么，具体的 system prompt 内容在代码中，文档未展开 |
| confidence 阈值分布 | 中文描述已覆盖，但具体 tier 百分比（60-80%, 15-30% 等）未放入 README，在 `factory_config.yaml` 中 |

---

## 文档风格检查

- 无 "AI revolution" / "next-generation" / "powerful" / "state-of-the-art" 等空话
- 无全文双语重复
- 无机器翻译痕迹
- 风格：中文技术博客 + 工程文档，清晰克制

---

## 禁止项确认

- 未修改任何代码
- 未修改任何配置
- 未修改任何测试
