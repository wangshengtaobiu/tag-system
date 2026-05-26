# Release Notes — v0.1-stable

**Date**: 2026-05-26
**License**: MIT

---

## English Summary

First stable release of tag-system — a pipeline system for acquiring, enriching, and freezing domain-specific content tags into a structured ontology. 0 data loss across all test runs (30/50/200 tags). Architecture frozen (S1–S8).

---

## 本次发布 What's New

### tag_acquisition

- 重写 tag 采集 pipeline
- Surface 归一化（全角 → 半角、空白整理）
- 保护短语拆分 + delimiter policy
- 质量过滤（长度、噪声模式、黑名单）
- 语言检测（zh / jp / en / mixed）
- 追加式 corpus snapshot

### ontology_factory

- 新增 S0 Tag Enrichment 阶段（LLM 语义字段生成）
- S1–S8 pipeline 稳定（triage → normalization → namespace → ID freeze → alias → validation → retrieval → freeze）
- Conservative normalization 模式（不翻译、不扩展、稳定性优先）
- Cardinality validator（检测并恢复 LLM 丢弃的 tag）
- Alias 后处理过滤器（移除英文翻译，保留 CJK/缩写）
- 低置信度条目的 review queue
- 版本化 ontology 导出 + freeze manifest

### Infrastructure

- 测试数据组织到 `tests/data/`（30/50/200 条样本）
- Observation 框架（`collect_observation.py`、`metrics/failed_cases/`）
- 完整 README 文档（根目录 + 各模块）
- MIT License

---

## 观测数据 Observation Metrics

| 指标 Metric | 值 Value |
|-------------|----------|
| 测试运行 | 30 / 50 / 200 条 |
| 数据丢失 | 0（所有运行） |
| Review 率 | ~18% |
| 平均置信度 | ~0.89 |
| Placeholder | 0.5%（LLM 丢弃的 tag 已恢复） |
| Alias 合并 | 0（保守策略） |

---

## 已知限制 Known Limitations

1. **LLM 依赖** — S0 和 S2 需要 DeepSeek API 访问。无本地模型 fallback。
2. **日语 tag 处理** — LLM 偶尔丢弃纯日语 tag（cardinality validator 以 placeholder 形式恢复）。
3. **仅小规模** — 已验证到 200 条。1000+ 条运行尚未测试。
4. **无 alias 自动合并** — 保守策略下所有潜在 alias 需人工 review。
5. **单一 domain** — 仅包含 `adult_content_tags` profile。pipeline 是领域无关的，但其他 domain 的 profile 需手动创建。
6. **无 Web UI** — 全部通过 CLI 交互。

---

## 路线图 Roadmap（未承诺）

- 更大规模验证（1000+ 条）
- 额外 domain profile
- S0/S2 本地模型 fallback
- Alias 自动合并 + confidence 阈值调优
- review queue 的 Web UI

---

## 安装 Installation

```bash
git clone <repo-url>
cd tag-system
pip install -r requirements.txt
export DEEPSEEK_API_KEY=YOUR_KEY
```

## 快速开始 Quick Start

```bash
# 完整 pipeline（30 条，约 5 分钟）
python3 ontology_factory/run_factory.py \
  --profile ontology_factory/profiles/adult_profile.json \
  --input tests/data/acquisition/raw_30.json \
  --stage s0 --end-stage s8
```

完整文档见 [README.md](../README.md)。
