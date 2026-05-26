# Ontology Factory — 标签本体标准化系统

将原始、杂乱的标签目录，转化为**冻结的、机器可读的标准化本体**。

```
原始标签（混乱、不一致）  →  标准化本体（唯一 ID、命名空间、层级）  →  检索索引（向量搜索就绪）
"足控"                      fetish.foot_fetish                        bge 向量 → top-k 匹配
"恋足"                      (上面的别名)
```

## English Summary

Transforms raw, inconsistent tag inventories into a frozen, machine-readable standardized ontology. Each tag gets a unique canonical ID, belongs to a clear namespace, carries a definition, aliases, and hierarchical relationships. The 9-stage pipeline (S0–S8) runs automatically: enrichment → triage → normalization → namespace → ID freeze → alias → validation → retrieval export → production freeze.

---

## 核心概念 Core Concepts

| 概念 Concept | 说明 |
|-------------|------|
| **本体 Ontology** | 标签的"身份证系统"。每个标签获得唯一的 canonical_id，归属到明确的 namespace，带上定义、别名、层级关系。 |
| **流水线 Pipeline** | 9 个阶段自动处理：S0 语义化 → S1 分拣 → S2 标准化 → S3 namespace → S4 ID 冻结 → S5 别名折叠 → S6 验证 → S7 导出 → S8 冻结。 |
| **冻结 Freeze** | 完成后产出一份"不可变"的标准化数据，下游系统可以永远依赖这些 ID，不会突然改变。 |

---

## 快速开始 Quick Start

### 系统要求

| 要求 | 说明 |
|------|------|
| Python | 3.10+ |
| 网络 | 能访问 `api.deepseek.com` |
| 依赖 | `pip install requests pyyaml` |
| API Key | DeepSeek API Key（通过环境变量 `DEEPSEEK_API_KEY` 配置） |

**不需要 GPU、不需要本地模型。** 全部走 DeepSeek 云端 API。

### 常用命令

| 场景 | 命令 |
|------|------|
| 完整流水线 | `python run_factory.py --profile profiles/adult_profile.json --input ../tag.json` |
| 只校验输入不执行 | 加 `--dry-run` |
| 跳过 AI 阶段（纯脚本） | 加 `--skip-flash` |
| 从指定阶段开始 | 加 `--stage s4`（从 S4 开始） |
| 到指定阶段结束 | 加 `--end-stage s6`（S6 后停止） |

---

## 9 阶段流水线 Pipeline Stages

```
S0 语义化(Flash) → S1 分拣(脚本) → S2 标准化(Flash) → S3 命名空间(Pro)
→ S4 ID冻结(Flash+Pro) → S5 别名(Flash+Pro) → S6 验证(脚本)
→ S7 导出(脚本) → S8 冻结(脚本)
```

| 阶段 Stage | 干什么 | 需要 API？ |
|-----------|--------|-----------|
| S0 语义化 | 调 Flash API 为每个原始 tag 生成分类建议、定义说明、上位 tag | **是** |
| S1 分拣 | 去重、清理空名、统一字段名 | 否 |
| S2 标准化 | 调 Flash API 给每个标签分配 canonical_id、namespace、语义类型 | **是** |
| S3 命名空间架构 | 检查命名空间分配是否合理 | 否（纯校验） |
| S4 ID 冻结 | 截断过深 ID、应用人工修正、检查重复 ID | 否 |
| S5 别名折叠 | 合并同义词、构建别名图 | 否 |
| S6 验证审计 | 9 项确定性检查（重复 ID、循环、深度等） | 否 |
| S7 检索导出 | 生成向量检索就绪的索引 | 否 |
| S8 生产冻结 | 打包版本化输出、生成冻结清单 | 否 |

---

## 运行结果 Outputs

```
ontology_factory/
├── exports/                          # ← 最终产物
│   ├── ontology_export_v1_0_0.json   # 冻结的标准化本体（主文件）
│   └── retrieval_index.json          # 检索索引（给下游系统用）
└── work/                             # ← 中间产物（调试用）
    ├── enriched_tags.json            # S0 语义化结果
    ├── inventory_clean.json          # S1 清理后
    ├── stage2_normalized.json        # S2 AI 标准化结果
    ├── namespace_freeze.json         # S3 命名空间冻结
    ├── stage4_resolved.json          # S4 ID 冻结后
    ├── validation_report.json        # S6 验证报告
    └── retrieval_index.json          # S7 检索索引
```

- **`ontology_export_v1_0_0.json`**：每个标签的完整身份证——canonical_id、namespace、定义、别名、层级关系、置信度。是"权威数据源"。
- **`retrieval_index.json`**：把标签转成适合向量检索的格式（embedding_text、分面索引）。给下游"用这些 tag 给小说打标"的系统使用。

---

## 目录结构 Directory Structure

```
ontology_factory/
├── run_factory.py              # 主入口
├── config/factory_config.yaml  # 运行时配置（API、模型、阈值）
├── profiles/
│   └── adult_profile.json      # 成人标签领域的"地图"（namespace、语义类型）
├── stages/                     # 9 个阶段的代码
├── validators/                 # 9 项验证检查
├── review_queue/              # 人工审核队列工具
├── docs/
│   └── ontology_factory_design.md  # Domain Profile 编写指南
├── exports/                   # 输出目录
├── work/                      # 中间产物目录
└── README.md
```

---

**完整操作手册见 [docs/操作手册.md](docs/操作手册.md)**
