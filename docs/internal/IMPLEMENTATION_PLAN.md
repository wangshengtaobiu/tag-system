# 标签体系 — 实现方案

## 项目现状

| 模块 | 状态 | 说明 |
|------|------|------|
| `tag_acquisition/` | ✅ 已完成 | Pixiv 采集 + 规则去噪，输出 `raw_tags.json` |
| `ontology_factory/` | ✅ v1.0.0 已冻结 | 8 阶段流水线，1145 条本体 + 33 条别名，25 个命名空间 |
| `tagger/` | ❌ 未创建 | 计划：BGE embedding + FAISS 检索 + Qwen 8B 重排 |

---

## 整体架构

```
Pixiv 搜索 API
  ↓ 按关键词搜索小说，提取 tags
tag_acquisition/                    ontology_factory/
┌──────────────────────┐            ┌────────────────────────────┐
│  collector.py        │            │  S1  Inventory Triage       │
│  复合标签拆分         │───▶ work/  │  S2  LLM 语义标准化 (flash)  │
│  规则级去噪           │  JSON      │  S3  Namespace 校验冻结     │
│  无 AI、无登录        │            │  S4  ID 冻结 + 人工修复     │
└──────────────────────┘            │  S5  别名折叠               │
                                    │  S6  校验审计 (9 项)        │
                                    │  S7  检索索引               │
                                    │  S8  版本冻结               │
                                    └────────────────────────────┘
                                           ↓
                                    exports/
                                    ontology_export_v1_0_0.json
```

**责任边界**：
- `tag_acquisition`：采集原始标签，规则级去噪，输出干净标签列表
- `ontology_factory`：AI 本体化（分类/定义/层级/去重/别名/冻结），输出结构化本体
- `tagger`（规划中）：利用本体对本地模型生成内容进行自动打标

---

## Part 1: tag_acquisition

### 目标
从 Pixiv 采集中文成人内容标签，经规则级去噪后输出 `raw_tags.json`。

### 原则
1. 给下游的数据是干净的（规则能清的必须清掉）
2. 规则筛不干净的（角色名、语义噪音）不硬筛，交给 ontology_factory 的 LLM 处理
3. 保留热度（count）字段，供下游参考
4. 无 AI、无登录

### 文件结构

```
tag_acquisition/
├── __init__.py          # 包标识
├── schema.py            # RawTagEntry(label, count)、CleanedTagEntry
├── config.yaml          # 搜索关键词、页数、代理、阈值
├── collector.py         # 核心：API 采集 + 复合标签拆分 + 规则去噪
├── run.py               # 入口：--config / --resume / --output-dir
└── analyze_noise.py     # 噪音分析工具（调试用）
```

### 处理流程

```
Pixiv 搜索 API
  ↓ 按关键词搜索小说，提取 tags 字段
复合标签拆分（分隔符: /／,，|｜._#＃-）
  ↓
规则级去噪
  ├─ 黑名单过滤（25+ 非内容元数据标签）
  ├─ 必须含汉字
  ├─ 汉字数量 >= 2 个
  ├─ 假名占比 ≤ 20%
  └─ 过滤 emoji / 纯英文 / 纯数字 / 纯日文
  ↓
频率统计 + 去重
  ↓
输出 raw_tags.json（按 count 降序）
```

### 使用方式

```bash
# 完整采集
python3 -m tag_acquisition.run

# 断点续采
python3 -m tag_acquisition.run --resume

# 指定输出目录
python3 -m tag_acquisition.run -o ./output
```

---

## Part 2: ontology_factory

### 目标
将 `raw_tags.json` 转化为结构化的、带版本控制的标签本体。

### 原则
1. 所有语义理解工作集中在本模块（LLM 调用）
2. 利用上游传入的 `count` 字段辅助决策
3. 8 阶段流水线，可按阶段启停
4. 输出带版本号的冻结本体 + 检索索引

### 文件结构

```
ontology_factory/
├── run_factory.py               # 入口：--profile / --input / --stage / --skip-flash
├── config/factory_config.yaml   # 工厂配置：模型路由、阶段参数、阈值
├── profiles/adult_profile.json  # 领域画像：25 个 namespace、16 种语义类型
│
├── stages/                      # 8 个流水线阶段
│   ├── __init__.py              #   BaseStage、PipelineContext、StageResult
│   ├── s1_triage.py             #   S1: 字段统一、去重、去空、语言检测
│   ├── s2_normalize.py          #   S2: LLM 语义标准化（flash 模型）
│   ├── s3_namespace.py          #   S3: 命名空间校验与冻结
│   ├── s4_freeze_id.py          #   S4: 规范 ID 冻结 + 人工修复应用
│   ├── s5_alias.py              #   S5: 别名折叠 + 去重合并
│   ├── s6_validate.py           #   S6: 9 项校验审计
│   ├── s7_retrieval.py          #   S7: 生成检索索引
│   └── s8_freeze.py             #   S8: 版本冻结（快照 + manifest + 迁移映射）
│
├── validators/validator.py      # 9 项确定性校验（无 LLM）
├── review_queue/                # 人工审查队列
│   ├── schema.py                #   ReviewItem、ReviewType、Severity
│   └── reviewer.py              #   CLI 交互式审查工具
│
├── work/                        # 中间产物目录
└── exports/                     # 最终输出目录
```

### 流水线阶段

| 阶段 | 所有者 | 做什么 | 输出 |
|------|--------|--------|------|
| **S1 Triage** | 脚本 | 字段名统一、去重、去空、语言检测 | `inventory_clean.json` |
| **S2 Normalize** | LLM (flash) | 分配 namespace、semantic_type、canonical_id、confidence | `stage2_normalized.json` |
| **S3 Namespace** | 脚本 | 验证 namespace 合法性，检查分布平衡 | `namespace_freeze.json` |
| **S4 Freeze ID** | LLM + 脚本 | 应用人工修复，截断超长 ID，去重复 canonical_id | `stage4_resolved.json` |
| **S5 Alias** | LLM + 脚本 | 别名合并，尊重 forbidden_merges | `stage5_alias_resolved.json` |
| **S6 Validate** | 脚本 | 9 项校验（重复 ID、命名空间、关系合法性等） | `validation_report.json` |
| **S7 Retrieval** | 脚本 | 生成 embedding_text、semantic_summary、面索引 | `retrieval_index.json` |
| **S8 Freeze** | 脚本 | 版本号快照、freeze_manifest、migration_map | `exports/` + `ontology_versions/` |

### 热度字段使用场景

| 场景 | 用法 |
|------|------|
| S2 Normalize | 高频标签优先处理，低频标签作为 LLM 判断辅助信号 |
| S5 Alias | 合并别名时保留高热度的标签名作为主名 |
| S7 Retrieval | 检索结果可按热度排序 |
| 通用 | 作为元数据保留在最终本体中，供 tagger 使用 |

**注意：热度不用于过滤。小众性癖标签可能热度低但有价值。**

### 使用方式

```bash
cd ontology_factory

# 完整流水线
python3 run_factory.py --profile profiles/adult_profile.json --input ../raw_tags.json

# 从指定阶段开始
python3 run_factory.py --profile profiles/adult_profile.json --input ../raw_tags.json --stage s4

# 跳过 LLM 依赖阶段（纯脚本模式）
python3 run_factory.py --profile profiles/adult_profile.json --input ../raw_tags.json --skip-flash
```

---

## Part 3: tagger（规划中）

### 目标
利用已冻结的标签本体，对本地模型生成的内容（小说/文本）进行自动打标。

### 计划技术栈

| 组件 | 方案 |
|------|------|
| 文本编码 | BGE-large-zh-v1.5（与本体 embedding 一致） |
| 向量检索 | FAISS（扁平索引或 IVF） |
| 重排序 | Qwen-8B 或同等规模的本地模型 |
| 推理环境 | 本地 GPU |

### 计划流程

```
输入文本
  ↓ 分段/分句
  ↓ BGE 编码为向量
FAISS 检索 Top-K 候选标签
  ↓
Qwen 8B 重排（上下文感知）
  ↓
输出匹配标签 + 置信度
  ↓
与本体对齐（验证 namespace/关系合法性）
```

### 输出格式（待设计）

```json
{
  "text_segment": "...",
  "tags": [
    {"canonical_id": "play.bondage", "confidence": 0.92, "aliases_matched": ["捆绑"]},
    {"canonical_id": "mental.humiliation", "confidence": 0.78}
  ]
}
```

---

## 数据流总览

```
Pixiv API
  ↓ (采集 + 规则去噪)
tag_acquisition/collector.py
  ↓ raw_tags.json  [{label, count}, ...]
ontology_factory/run_factory.py
  ↓ S1 → S2 → S3 → S4 → S5 → S6 → S7 → S8
exports/ontology_export_v1_0_0.json
  ↓
tagger/ (规划中)
  ↓ 使用本体对本地模型生成内容进行自动打标
打标结果 JSON
```

---

## 已产出数据

| 文件 | 说明 |
|------|------|
| `collected_tags.json` | 当前采集的原始标签（label + count） |
| `ontology_factory/exports/ontology_export_v1_0_0.json` | v1.0.0 冻结本体（1145 条本体 + 33 条别名） |
| `ontology_factory/exports/retrieval_index.json` | v1.0.0 检索索引 |
| `ontology_factory/work/ontology_versions/v1_0_0/` | 完整版本快照（含 manifest + migration_map） |
