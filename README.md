# tag-system

一套基于 pipeline 的标签本体系统，用于从原始 tag 语料中采集、清洗、语义化、冻结为结构化 ontology。

本项目聚焦成人内容标签（如 Pixiv 小说标签），但 pipeline 是领域无关的 —— 任何 tag 语料都可以通过替换 domain profile 进行处理。

**包含内容：**
- 标签采集与本体 pipeline 的完整源码
- 领域 profile 配置（adult_content_tags）
- 小型测试数据集（30–200 条）

**不包含：**
- 生产环境数据集
- 模型权重或本地 AI 模型
- API 凭证
- 预计算的 embedding 或索引

---

## English Summary

A pipeline system for acquiring, enriching, and freezing domain-specific content tags into a structured ontology. Includes source code for tag acquisition and ontology pipeline (S0–S8), domain profile configuration, and small test datasets. Production data, API keys, and model weights are intentionally excluded.

---

## 系统架构 Architecture

```
Pixiv / API
    ↓
tag_acquisition (normalize, split, filter, dedup)
    ↓
Surface Corpus (raw tags → clean tags)
    ↓
ontology_factory S0 (LLM enrichment)
    ↓
ontology_factory S1–S8 (ontology pipeline)
    ↓
Frozen Ontology + Retrieval Export
```

数据单向流动。每个 stage 读取上一 stage 的输出，写入自己的文件，不修改上游数据。

---

## 模块说明 Modules

### tag_acquisition

从外部源采集原始 tag，进行 surface form 归一化、复合 tag 拆分、噪声过滤，导出干净的语料库。

**职责：**
- Surface 归一化（全角 → 半角、空白清理）
- 保护短语拆分（如 "足控・M属性" → 两条）
- 分隔符策略执行
- 语言检测
- 质量过滤（长度、频率、噪声模式）
- 去重
- 追加式语料快照

**不做：** 语义化、ontology 构建、翻译、别名合并。

### ontology_factory

将干净 tag 输入 9 阶段 pipeline（S0–S8），产出冻结的、带版本号的 ontology，包含 canonical ID、namespace、校验、retrieval 导出。

**职责：**
- S0: LLM 语义化（分类、定义、上位 tag）
- S1–S8: ontology pipeline（分拣、归一化、namespace 分配、ID 冻结、别名折叠、校验、retrieval 导出、生产冻结）
- 低置信度条目的 review queue
- 版本化 ontology 导出与冻结清单

**不做：** 原始爬虫、源数据修改、外部 API 调用（除 S0/S2 LLM  enrichment 外）。

---

## 快速开始 Quick Start

### 环境要求

- Python 3.10+
- DeepSeek API key（用于 S0 和 S2 阶段）

### 1. 安装

```bash
# 无需安装 package，克隆后直接运行
git clone <repo-url>
cd tag-system
```

### 2. 配置 API Key

```bash
export DEEPSEEK_API_KEY=YOUR_KEY
```

Key 通过环境变量 `DEEPSEEK_API_KEY` 读取。不要硬编码在配置文件中。

### 3. 运行 ontology_factory（完整 pipeline，需 API key）

```bash
export DEEPSEEK_API_KEY=YOUR_KEY
python3 ontology_factory/run_factory.py \
  --profile ontology_factory/profiles/adult_profile.json \
  --input tests/data/acquisition/raw_30.json \
  --stage s0 --end-stage s8
```

30 条 tag 走完 9 个 stage → 产出 frozen ontology + retrieval index。

### 4. 运行 ontology_factory（不调 LLM）

```bash
# 跳过 LLM stages，从 S3 开始（需要之前运行产生的 work/stage2_normalized.json）
python3 ontology_factory/run_factory.py \
  --profile ontology_factory/profiles/adult_profile.json \
  --input tests/data/ontology/smoke_20.json \
  --stage s3 --end-stage s6
```

运行 S3–S6（纯脚本阶段）。验证 namespace、ID 冻结、别名、pipeline 逻辑，无需 API 调用。

### 5. 运行 ontology_factory（跳过 S0，用已语义化的数据）

```bash
export DEEPSEEK_API_KEY=YOUR_KEY
python3 ontology_factory/run_factory.py \
  --profile ontology_factory/profiles/adult_profile.json \
  --input tests/data/acquisition/small_50.json \
  --stage s1 --end-stage s8
```

50 条已语义化 tag 走 S1–S8。无需 S0 阶段。

---

## 仓库结构 Repository Structure

```
tag-system/
├── tag_acquisition/          # 标签采集与清洗
│   ├── collector.py          # Pixiv API 采集器
│   ├── normalize.py          # Surface 归一化
│   ├── split.py              # 复合 tag 拆分
│   ├── filter.py             # 质量过滤
│   └── run.py                # 入口
│
├── ontology_factory/         # Ontology pipeline (S0–S8)
│   ├── run_factory.py        # Pipeline 入口
│   ├── stages/               # S0–S8 stage 实现
│   ├── config/               # Pipeline 配置
│   ├── profiles/             # 领域 profile（adult_content_tags）
│   ├── validators/           # 确定性校验
│   └── review_queue/         # 人工 review 工具
│
├── tests/data/               # 测试数据集
│   ├── acquisition/          # 原始与对抗测试集
│   └── ontology/             # 已语义化的冒烟测试集
│
└── docs/                     # 设计文档
```

运行时产物（`work/`、`exports/`、`metrics/`）已排除在版本控制外。

---

## 当前状态 Current Status

**版本：** v0.1-stable

| 指标 Metric | 值 Value |
|-------------|----------|
| Pipeline stages | S0–S8（9 个阶段） |
| 测试通过 | 30 / 50 / 200 条 |
| 数据丢失 | 0（所有运行） |
| Review 率 | ~18%（保守策略） |
| 平均置信度 | ~0.89 |
| 架构 | Frozen（S1–S8 不再变更） |

系统在小规模场景（数百条 tag）下运行稳定。大规模生产运行（1000+ 条）尚未验证。

---

## 不包含的内容 What Is NOT Included

本仓库有意排除：

- **生产数据集** — 真实语料与领域相关，可能包含敏感内容
- **完整 Pixiv 导出** — 仅包含小型测试样本
- **Embedding 文件** — retrieval 索引在运行时生成，不持久化
- **缓存 / 中间产物** — 所有中间输出均可从源码 + 配置重现
- **API 凭证** — key 必须通过环境变量提供

---

## 许可证 License

MIT License。详见 [LICENSE](LICENSE)。
