# Tag System 完整设计文档

> **版本 1.1.0**
> 范围：tag_acquisition + tag_enrichment + ontology_factory + tagger 全链路

---

## 一、系统概览

Tag System 是一个完整的标签生产与消费系统，从原始数据采集到语义丰富化，再到冻结本体生成，最后到自动打标。

```
tag_acquisition          tag_enrichment           ontology_factory              tagger
(数据采集+清洗)    →     (AI 语义丰富化)    →     (标准化+冻结本体)      →     (BGE+FAISS+Qwen 打标)

Pixiv/外部 API           DeepSeek Flash LLM       Flash LLM（仅 S0、S2）       BGE-large-zh-v1.5
确定性规则清洗            批量生成语义字段          脚本验证                    FAISS 向量检索
                                                  S1/S3-S8 纯脚本             Qwen 8B 重排
```

### 四阶段说明

系统分为四个独立的**生产阶段**，每阶段产出不同格式的数据，可独立运行和审核：

| 阶段 | 模块 | 输入 | 输出 | 是否需要 AI |
|------|------|------|------|------------|
| 1. 采集 | tag_acquisition | Pixiv API | `collected_tags.json` — `[{label, count}]` | **否**（纯规则） |
| 2. 丰富化 | tag_enrichment | `collected_tags.json` | `enriched_tags.json` — `[{标签名, 分类建议, 定义说明, 上位tag, 区别, 文学示例词}]` | **是**（Flash LLM） |
| 3. 本体构建 | ontology_factory | `enriched_tags.json` | `ontology_export_v*.json`（冻结本体） | **是**（S0+S2 用 Flash） |
| 4. 打标 | tagger | 冻结本体 + 检索索引 + 待打标文本 | `[{canonical_id, confidence, aliases_matched}]` | **是**（Qwen 8B 重排） |

**关键设计原则：tag_acquisition 是纯规则处理。** tag_enrichment、ontology_factory 的 S0/S2、以及 tagger 的重排环节需要 AI。ontology_factory 的 S1/S3-S8 全是纯脚本。

### 全链路流程

```
原始标签 → 采集清洗 → 语义丰富化 → 目录分拣 → 语义标准化 → 命名空间 → ID冻结 → 别名 → 验证 → 导出 → 冻结本体 → 向量索引 → 自动打标
   ↑          ↑           ↑           ↑           ↑           ↑        ↑       ↑      ↑      ↑        ↑          ↑          ↑
 tag_acq   tag_acq   tag_enrich   S1(脚本)    S2(Flash)   S3(脚本)  S4(脚本) S5(脚本) S6(脚本) S7(脚本)  S8(脚本)   tagger    tagger
 (采集)    (规则)     (AI)
```

### 模块关系

| 模块 | 职责 | 依赖 |
|------|------|------|
| tag_acquisition | 从外部 API 采集标签，规则清洗 | 无 |
| tag_enrichment | 用 AI 为原始标签生成语义字段（分类、定义、上位关系、示例） | tag_acquisition 输出 |
| ontology_factory | 将 enriched 标签转化为冻结本体 | tag_enrichment 输出 |
| tagger | 利用冻结本体对内容自动打标 | ontology_factory 输出 |

---

## 二、tag_acquisition 模块

### 2.1 功能

从外部 API（Pixiv 等）采集标签数据，执行去噪清洗，输出干净的标签列表。

### 2.2 文件结构

```
tag_acquisition/
├── __init__.py
├── schema.py          # 数据模型定义
├── collector.py       # 核心采集器
├── run.py             # 入口脚本
├── analyze_noise.py   # 去噪分析工具
└── config.yaml        # 采集配置
```

### 2.3 采集流程

```
1. 从 Pixiv 搜索 API 获取原始标签
2. 拆分复合标签（按 /／,，|｜._#＃- 分隔符）
3. 规则过滤：
   - 黑名单排除（语言标记、格式标记、R18 等元数据标签）
   - 汉字 ≥ 2 个字符
   - 无 emoji
   - 假名占比 ≤ 20%
4. 统计频率，取 top N（默认 3000）
5. 输出 collected_tags.json
```

### 2.4 输出格式

输出为 JSON 数组，每条只包含标签名和出现次数：

```json
[
  {"label": "腿控", "count": 42},
  {"label": "性奴", "count": 38},
  ...
]
```

**注意：此格式是中间产物，供 tag_enrichment 读取。不直接供 ontology_factory 使用。**

### 2.5 已知问题与待修复项

1. `config.yaml` 中 `min_tag_length: 2` 残留，代码已移除该参数 → **删除残留配置**
2. `analyze_noise.py` 硬编码代理地址，不使用 config.yaml → **改用 config.yaml 代理配置**
3. `CleanedTagEntry.to_dict()` 输出中文键名 — 此 dataclass 从未被实例化，**应移至 tag_enrichment 或确认用途后清理**
4. `--resume` 逻辑只检查输出文件存在，不检查数据完整性 → **增强 resume 检查**
5. Pixiv API URL 需验证可用性 → **实际运行测试**

---

## 三、tag_enrichment 模块

### 3.1 功能

用 AI（DeepSeek Flash）为 tag_acquisition 产出的原始标签（`{label, count}`）生成语义字段，产出 ontology_factory 可消费的富格式数据。

**这是整个系统中真正需要 AI 介入的核心环节。** tag_acquisition 只做规则清洗，不知道标签的语义含义。tag_enrichment 需要理解每个标签在成人内容语境下的分类、定义、上下位关系、相似标签区别、以及文学使用示例。

### 3.2 文件结构

```
ontology_factory/
├── stages/
│   ├── s0_enrich.py         # S0: 标签语义丰富化（Flash LLM，批量处理）
│   └── ...                  # S1-S8（现有）
```

tag_enrichment 作为 ontology_factory 的 **S0 阶段** 集成，复用 BaseStage、PipelineContext、review queue、配置系统。

### 3.3 输入格式

```json
[
  {"label": "腿控", "count": 42},
  {"label": "性奴", "count": 38},
  ...
]
```

### 3.4 输出格式

```json
{
  "meta": {
    "stage": "0",
    "date": "2026-05-24T...",
    "total_entries": 3000,
    "batches": 100,
    "model": "deepseek-v4-flash"
  },
  "quality": {
    "mean_confidence": 0.89,
    "needs_review": 42
  },
  "entries": [
    {
      "标签名": "腿控",
      "分类建议": "恋物偏好",
      "定义说明": "对女性腿部（大腿、小腿）线条与触感的性偏好...",
      "上位tag": "恋物",
      "区别": "与足控的区别：足控聚焦脚部，腿控关注腿部整体。",
      "文学示例词": "丝滑腿控, 修长玉腿, 大腿夹击, 美腿",
      "enrichment_confidence": 0.92,
      "needs_review": false,
      "review_reason": ""
    },
    ...
  ]
}
```

此格式与 ontology_factory S1 的字段查找完全兼容（S1 支持 `标签名`/`分类建议`/`上位tag`/`文学示例词` 等中文键名）。

### 3.5 处理流程

```
1. 读取 collected_tags.json（[{label, count}]）
2. 从领域 profile 提取有效分类列表（namespace_map[*].categories 去重）
3. 分批（默认 30 条/批）发送给 Flash LLM
4. LLM 为每条标签生成：分类建议、定义说明、上位tag、区别、文学示例词、置信度
5. 解析 LLM 返回的 JSON，验证必填字段
6. 低置信度条目（confidence < 0.85）生成 review 队列项
7. 输出 enriched_tags.json 到 work/ 目录
8. 设置 ctx.raw_tags 供 S1 消费
```

### 3.6 LLM Prompt 设计

- **语言**：中文（与标签内容一致，DeepSeek 在中文语义任务上表现更好）
- **系统 prompt**：列出 profile 中的所有有效分类，要求 LLM 从中选择
- **用户 prompt**：批量发送 `[{label, count}]` JSON
- **输出要求**：纯 JSON 数组，不包含 markdown 代码块
- **批大小**：30（比 S2 的 50 小，因为每条需要生成更多 token）

### 3.7 成本估算

3000 标签 / 30 每批 = 100 次 API 调用。
每批 ~500 输入 token + ~150 输出 token。
DeepSeek Flash 定价下约 $0.01-0.03，可忽略。

### 3.8 运行方式

```bash
# 从 raw 数据开始（S0 → S1 → ... → S8）
python run_factory.py --profile profiles/adult_profile.json --input collected_tags.json --stage s0

# 跳过 S0，使用已丰富过的数据（S1 → ... → S8）
python run_factory.py --profile profiles/adult_profile.json --input enriched_tags.json --stage s1

# 仅运行 S0 做丰富化，审核后再跑后续阶段
python run_factory.py --profile profiles/adult_profile.json --input collected_tags.json --stage s0 --end-stage s0
```

### 3.9 错误处理

| 场景 | 行为 |
|------|------|
| 无 API key | `SKIPPED`，流水线继续（用户需提供预丰富数据） |
| 输入文件不存在 | `FAILED`，流水线停止 |
| LLM API 错误 | 重试 3 次，间隔 5s |
| JSON 解析失败 | 批大小减半（最小 10），重试 |
| 验证错误 | 打印前 5 条错误，仍使用数据（S1 会清理） |
| 低置信度 | 生成 ReviewItem 到 review 队列 |
| 已丰富过的输入 | 检测 `分类建议` 字段，跳过 S0（幂等） |

---

## 四、ontology_factory 模块

### 4.1 功能

将原始的、非结构化的标签目录转换为冻结的、机器可读的规范本体。

### 4.2 文件结构

```
ontology_factory/
├── run_factory.py          # 入口脚本
├── stages/
│   ├── __init__.py         # BaseStage, PipelineContext, StageResult, 工具函数
│   ├── s0_enrich.py        # 语义丰富化（Flash LLM，批量）
│   ├── s1_triage.py        # 目录分拣（脚本）
│   ├── s2_normalize.py     # 语义标准化（Flash LLM）
│   ├── s3_namespace.py     # 命名空间架构（脚本）
│   ├── s4_freeze_id.py     # ID 冻结（脚本）
│   ├── s5_alias.py         # 别名折叠（脚本）
│   ├── s6_validate.py      # 验证审计（脚本）
│   ├── s7_retrieval.py     # 检索导出（脚本）
│   └── s8_freeze.py        # 生产冻结（脚本）
├── validators/
│   ├── __init__.py
│   └── validator.py        # 验证器
├── review_queue/
│   ├── __init__.py
│   ├── schema.py           # Review 队列 schema
│   └── reviewer.py         # Review CLI
├── profiles/
│   └── adult_profile.json  # 领域 Profile
├── config/
│   └── factory_config.yaml # 运行时配置
├── docs/
│   └── ontology_factory_design.md
└── 操作手册.md
```

### 4.3 9 阶段流水线

```
S0 丰富化 → S1 分拣 → S2 标准化 → S3 命名空间 → S4 ID冻结 → S5 别名 → S6 验证 → S7 导出 → S8 冻结
```

| 阶段 | 执行者 | 是否需要 API | Token 消耗 |
|------|--------|-------------|-----------|
| S0 语义丰富化 | Flash | **是** | **是** |
| S1 目录分拣 | 脚本 | 否 | 否 |
| S2 语义标准化 | Flash | **是** | **是** |
| S3 命名空间架构 | 脚本（原设计 Pro） | 否 | 否 |
| S4 ID 冻结 | 脚本（原设计 Flash+Pro） | 否 | 否 |
| S5 别名折叠 | 脚本（原设计 Flash+Pro） | 否 | 否 |
| S6 验证审计 | 脚本 | 否 | 否 |
| S7 检索导出 | 脚本 | 否 | 否 |
| S8 生产冻结 | 脚本（原设计 Pro） | 否 | 否 |

**Token 消耗总结：仅 S0 和 S2 消耗 token。S1/S3-S8 均为纯脚本，不调用任何 API。**

S4 和 S5 各自独立运行，不合并。

### 4.4 核心设计原则

#### 渐进冻结

```
命名空间规则 → 先冻结 (S3，脚本)
规范 ID      → 其次冻结 (S4，脚本)
别名图       → 再次冻结 (S5，脚本)
完整本体     → 最后冻结 (S8，脚本)
```

#### 保守合并

**错误合并是灾难性的。重复存留是可以接受的。** 默认不合并，仅在 95%+ 确定时才合并。

#### 浅且宽

max_depth = 3（硬限制）。

#### 尽可能确定性

S0 和 S2 之外全是纯脚本，零 LLM 调用。

#### 关系类型白名单

只允许 4 种可信关系类型：`specialization_of`、`role_pair`、`opposite_of`、`context_of`。

### 4.5 已知问题与待修复项

1. **配置分散** — 配置在 3 个文件（factory_config.yaml, adult_profile.json, domain_profile.schema.json），需合并为单一 config.yaml
2. **STAGE_REGISTRY 死代码** — `run_factory.py` 硬编码阶段，装饰器未使用
3. **ReviewItem 数据类** — 定义但从未实例化，实际用 dict
4. **review_queue 未集成到流水线** — S2 产生 review 条目，但流水线未暂停等待审查
5. **字段名不一致** — `name`/`original_name`、`is_alias_of`/`is_duplicate_of` 混用
6. **无 circuit breaker** — API 失败时浪费时间重试
7. **无结构化日志** — 全部用 print()
8. **S0 输入兼容性** — 需要确认能正确读取 `[{label, count}]` 格式（来自 tag_acquisition）

---

## 五、tagger 模块（新增）

### 5.1 目标

利用冻结本体对本地模型生成内容进行自动打标。

### 5.2 技术栈

| 组件 | 方案 |
|------|------|
| 文本编码 | BGE-large-zh-v1.5 |
| 向量检索 | FAISS（扁平索引或 IVF） |
| 重排序 | Qwen-8B |
| 推理环境 | 本地 GPU |

### 5.3 流程

```
输入文本 → 分段 → BGE 编码 → FAISS Top-K → Qwen 8B 重排 → 输出标签+置信度
```

### 5.4 输出格式

```json
{
  "text_segment": "...",
  "tags": [
    {"canonical_id": "play.bondage", "confidence": 0.92, "aliases_matched": ["捆绑"]},
    {"canonical_id": "mental.humiliation", "confidence": 0.78}
  ]
}
```

### 5.5 依赖

- ontology_factory 输出的冻结本体（`ontology_export_v*.json`）
- 检索索引（`retrieval_index.json`）

---

## 六、配置统一（待实施）

### 6.1 ontology_factory 配置合并

合并为单一 `ontology_factory/config.yaml`：

```yaml
# ===== 领域配置 =====
namespaces:
  play: { description: "玩法/行为", categories: ["玩法", "行为"] }

semantic_types:
  - behavior
  - mental_state

forbidden_merges:
  - [足控, 腿控]
  - [男同, 男男]

# ===== 运行时配置 =====
pipeline:
  stages: [s0, s1, s2, s3, s4, s5, s6, s7, s8]
  batch_size: 50

models:
  flash: { provider: deepseek, model: deepseek-v4-flash }
  pro:   { provider: deepseek, model: deepseek-v4 }

thresholds:
  confidence_auto_accept: 0.85
  confidence_needs_review: 0.70
  confidence_reject: 0.60

alias_policy:
  conservative_merge: true
  max_aliases_per_entry: 10

id_convention:
  format: "namespace.descriptor[.detail]"
  max_depth: 3
  case: snake_case
```

**删除文件：**
- `config/factory_config.yaml`
- `profiles/adult_profile.json`
- `profiles/domain_profile.schema.json`

---

## 七、review_queue 集成（待实施）

### 7.1 方案

1. S2 产生的低置信度条目（confidence < threshold_needs_review）进入 review_queue
2. S2 完成后、S3 之前插入 review 步骤：
   - 如有未解决条目，流水线暂停，调用 reviewer CLI
   - 用户审查通过后继续
3. S6（Validate）增加检查：review_queue 中无未解决条目
4. 统一用 dict 表示 review 条目（与现有代码一致）

---

## 八、错误处理增强（待实施）

1. **Circuit Breaker**: API 连续 N 次失败后跳过剩余批次，输出警告
2. **结构化日志**: 关键阶段输出到 `work/pipeline.log`
3. **幂等性**: `item_id` 生成不用 `time.time()`，改用确定性 hash

---

## 九、冻结后治理

**允许的操作：**
- 修正定义中的拼写错误
- 更新示例列表
- 为已有条目添加新别名
- 添加新条目（使用新的 canonical ID）
- 弃用条目（标记 deprecated=true）

**需要新版本的操作：**
- 更改 canonical ID
- 删除条目
- 更改命名空间
- 合并两个主条目
- 添加新命名空间

**永久禁止：**
- 不提升版本号就更改 canonical ID
- 未经弃用期就删除条目
- 将已弃用的 canonical ID 用于新概念

---

*Tag System 完整设计文档 v1.1.0*
