# Ontology Factory 设计文档

> **版本 1.0.0 — 生产版**
> 摘录自成人标签本体项目（1178 个标签，冻结 v3，6 阶段流水线）。
> 目标读者：在新领域运营 Factory 的本体架构师。
> 阅读时间：约 45 分钟。执行时间：2 小时（1K 标签）到 2 天（100K 标签）。

---

# 第一部分 — 系统概览

## 1.1 什么是 Ontology Factory？

Ontology Factory 是一个**半自动化生产系统**，用于将原始的、非结构化的标签目录转换为冻结的、机器可读的规范本体。

```
RAW FOLKSONOMY              CANONICAL ONTOLOGY            RETRIEVAL SYSTEM
(chaotic, human labels)  →  (structured, frozen IDs)  →  (embedding-ready index)

"足控"                        fetish.foot_fetish            bge vector → top-k match
"恋足"                        (alias of above)              Qwen 8B reranking
"腿控"                        fetish.leg_fetish             candidate selection
```

## 1.2 它解决的问题

| Factory 之前 | Factory 之后 |
|---------------|---------------|
| 标签临时随意、不一致 | 每个标签都有一个冻结的规范 ID |
| 同一概念有 3 个以上名称 | 所有别名都解析到一个主 ID |
| 没有机器可读的结构 | 命名空间层级 + 分面索引 |
| 搜索仅支持关键字 | 向量检索 + Qwen 重排序 |
| 添加新标签会导致问题 | ID 稳定；新标签获得新 ID |
| 无法扩展到 100 个以上标签 | 可扩展到 100K+ 标签 |

## 1.3 四层架构

```
+------------------------------------------------------------------+
|                        ARCHITECT (Pro / 人工)                      |
|  定义边界，设计命名空间，仲裁歧义                                   |
|  低吞吐量 — 高精度 — 最终权威                                      |
+------------------------------------------------------------------+
                                  |
                                  | 设计规则、审查输出
                                  v
+------------------------------------------------------------------+
|                        WORKER (Flash / 小模型)                     |
|  机械标准化、重复检测、置信度评分                                   |
|  高吞吐量 — 良好精度 — 仅作建议                                    |
+------------------------------------------------------------------+
                                  |
                                  | 产出标准化数据
                                  v
+------------------------------------------------------------------+
|                        VALIDATOR (脚本 / 自动化)                   |
|  基于规则的检查：重复 ID、循环、深度、命名空间                      |
|  零幻觉 — 确定性的 — 每个阶段后运行                                |
+------------------------------------------------------------------+
                                  |
                                  | 产出冻结的本体
                                  v
+------------------------------------------------------------------+
|                        RETRIEVAL LAYER (bge + Qwen)               |
|  嵌入生成、分面索引、候选检索                                       |
|  服务下游打标流水线 — 消费冻结的本体                               |
+------------------------------------------------------------------+
```

## 1.4 Factory 产出的内容

| 输出文件 | 用途 | 消费者 |
|-------------|---------|----------|
| `ontology_export_v1.json` | 冻结的规范本体 | 唯一权威来源 |
| `retrieval_index.json` | 嵌入优化索引 | bge 向量搜索 |
| `alias_graph.json` | 别名 → 主条目映射 | 查询标准化 |
| `domain_profile.json` | 领域配置（可复用） | 同领域的新项目 |
| `freeze_manifest.json` | 不可变版本记录 | 审计追踪 |

## 1.5 参考项目的关键数据

| 指标 | 数值 |
|--------|-------|
| 输入标签数 | 1,178 |
| 最终分类数 | 19 |
| 最终命名空间数 | 25 |
| 本体类型数 | 4 (flat_behavior, specialized_behavior, graph_native, meta_style) |
| 主条目数 | 1,175 |
| 别名条目数 | 3 |
| 可信关系数 | 624 |
| 平均置信度 | 0.934 |
| 审查队列（升级到 Pro） | 75 / 1178 (6.4%) |
| 重复 canonical ID 数 | 0 |
| 嵌入文本平均字符数 | 148 |

---

# 第二部分 — 最小化项目搭建

## 2.1 所需输入

至少需要一个文件：

```json
// raw_tags.json — 最小格式
[
  { "name": "tag_name_1" },
  { "name": "tag_name_2" }
]
```

更推荐的格式：

```json
// raw_tags.json — 推荐格式
[
  {
    "name": "tsundere",
    "definition": "A character who is initially cold/hostile before showing a warm side",
    "category": "character_archetype",
    "examples": ["taiga", "rin", "hitagi"],
    "heat": 1500
  }
]
```

字段优先级：`name`（必需）> `definition`（强烈推荐）> `category`（如有）> `examples`（可选）。

## 2.2 Domain Profile（唯一与领域相关的文件）

创建 `domain_profile.json`：

```json
{
  "domain": "your_domain_name",
  "language": "zh",
  "description": "Brief description of the domain",
  "namespace_map": { },
  "semantic_types": [ ],
  "trusted_relations": [ ],
  "ontology_types": [ ],
  "max_depth": 3,
  "merge_threshold": 0.90,
  "auto_accept_confidence": 0.85
}
```

详细的编写指南见第三部分。

## 2.3 搭建后的目录结构

```
your_project/
├── raw_tags.json              # 输入：你的原始标签目录
├── domain_profile.json        # 输入：领域配置
├── factory_config.yaml        # 输入：运行时参数
├── stage1_flash_prompt.md     # 生成：标准化提示词
├── stage1_batches/            # 中间产物：Flash 批次输出
├── stage1_all_normalized.json # 中间产物：合并后的标准化结果
├── stage3_review_queue.json   # 中间产物：需要 Pro 审查的条目
├── stage4_resolved.json       # 中间产物：架构师修正后
├── alias_proposals.json       # 中间产物：Flash 别名建议
├── ontology_export_v1.json    # 输出：冻结的规范本体
├── retrieval_index.json       # 输出：检索就绪索引
├── alias_graph.json           # 输出：别名解析映射
└── freeze_manifest.json       # 输出：不可变版本记录
```

## 2.4 规模推荐

| 标签数量 | 批次大小 | Flash 调用次数 | Pro 审查条目（估计） | 时间（估计） | 成本（估计） |
|-----------|------------|-------------|------------------------|-------------|-------------|
| 100 | 30 | 4 | 5-10 | 10 分钟 | $0.10 |
| 1,000 | 50 | 20 | 50-100 | 1 小时 | $1.00 |
| 10,000 | 50 | 200 | 500-1,000 | 8 小时 | $10.00 |
| 100,000 | 50 | 2,000 | 5,000-10,000 | 2-3 天 | $100.00 |

**对于 100K+ 标签**：使用命名空间分片（一次处理一个命名空间），将审查抽样从 100% 降低到 10% 随机审计，并计划 2-3 次人工审查会话。

## 2.5 前置条件检查

- [ ] Python 3.10+ 已安装
- [ ] DeepSeek API 密钥（或兼容的端点）
- [ ] 原始标签目录（任意格式：CSV, JSON, JSONL）
- [ ] 领域专业知识（你理解这些标签的含义）
- [ ] 用于检索：bge 模型已下载（可选；没有它也可以生成索引）
- [ ] 用于本地推理：Qwen 8B 或同等模型（可选；可导出用于云端推理）

---

# 第三部分 — Domain Profile 编写指南

## 3.1 Domain Profile 就是你的契约

Domain profile 定义了**所有与领域相关的内容**。一旦编写完成，Factory 引擎就完全与领域无关。所有提示词、验证规则和导出逻辑都从此文件派生。

## 3.2 步骤一：定义语义轴

**语义轴是标签沿其变化的独立维度。**

规则：同一轴上的两个标签互斥或可比较。不同轴上的两个标签可以共存。

```
示例：动漫角色类型

Axis 1: personality_type
  Values: tsundere, yandere, kuudere, dandere, genki, ...
  Question: "What is the character's core personality?"

Axis 2: relationship_role
  Values: childhood_friend, senpai, kouhai, imouto, onee-san, ...
  Question: "What relationship does this character have to the protagonist?"

Axis 3: archetype_role
  Values: protagonist, antagonist, love_interest, comic_relief, mentor, ...
  Question: "What narrative function does this character serve?"
```

一个角色可以同时是 `tsundere`（轴 1）和 `childhood_friend`（轴 2）以及 `love_interest`（轴 3）。三个轴，一个角色。

**需要多少个轴？**
- <100 个标签：2-4 个轴
- 100-1K 个标签：3-8 个轴
- 1K-10K 个标签：5-15 个轴
- 10K+ 个标签：8-20 个轴

**红旗警告**：如果一个轴包含超过 30% 的标签，可能需要拆分。
**红旗警告**：如果两个轴的标签集合有显著重叠，需要合并它们。

## 3.3 步骤二：设计命名空间策略

**命名空间是 canonical ID 的前缀。** 它对应一个语义轴或一组相关轴的集合。

```
规则：namespace = 标签的主要语义域
格式：小写、snake_case、英文
最大深度：3 段 (namespace.parent.child)
```

### 命名空间设计原则

1. **覆盖性**：每个标签必须恰好归入一个命名空间
2. **无重叠**：两个命名空间不应描述相同的语义域
3. **大小平衡**：目标每个命名空间 10-200 个标签。低于 10 → 合并。高于 200 → 拆分。
4. **稳定性**：命名空间在 S3 之后就冻结。选择你能永远使用的名称。

### 从轴到命名空间

并非每个轴都需要自己的命名空间。将相关轴分组：

```
轴: personality_type, dere_type
→ 命名空间: character_trait（涵盖两者）

轴: relationship_role, family_role
→ 命名空间: character_role（涵盖两者）

轴: narrative_function
→ 命名空间: narrative_role（一对一）
```

### 示例：anime_tropes 领域

```json
{
  "namespace_map": {
    "character_trait": {
      "description": "Character personality traits and archetypes",
      "axes": ["personality_type", "dere_type", "behavioral_trait"],
      "ontology_type": "flat_behavior",
      "examples": ["tsundere", "yandere", "kuudere", "genki", "chuunibyou"]
    },
    "character_role": {
      "description": "Character relationship and social roles",
      "axes": ["relationship_role", "social_role", "family_role"],
      "ontology_type": "graph_native",
      "examples": ["childhood_friend", "senpai", "imouto", "student_council_president"]
    },
    "narrative_role": {
      "description": "Narrative function in the story",
      "axes": ["protagonist_role", "antagonist_role", "supporting_role"],
      "ontology_type": "specialized_behavior",
      "examples": ["protagonist", "love_interest", "comic_relief", "mentor"]
    },
    "setting": {
      "description": "Story setting and context",
      "axes": ["location", "time_period", "genre_context"],
      "ontology_type": "graph_native",
      "examples": ["high_school", "isekai", "post_apocalyptic", "urban_fantasy"]
    },
    "relationship_dynamic": {
      "description": "Inter-character relationship patterns",
      "axes": ["romantic_dynamic", "rivalry_type", "power_dynamic"],
      "ontology_type": "graph_native",
      "examples": ["love_triangle", "rivals_to_lovers", "senpai_kouhai_dynamic"]
    }
  }
}
```

## 3.4 步骤三：分配本体类型

每个命名空间使用以下 4 种本体类型之一：

| 类型 | 使用场景 | 示例 |
|------|-------------|---------|
| `flat_behavior` | 标签是简单的属性标签；不需要内部结构 | `tsundere` — 是就是，不是就不是 |
| `specialized_behavior` | 标签是有子类型和强度变体的行为/角色 | `character_archetype` 有子原型 |
| `graph_native` | 标签互相蕴含；存在互惠关系 | `relationship_dynamic` — 三角恋意味着 3 个以上角色 |
| `meta_style` | 标签描述的是作品本身，而非内容 | `content_rating`, `target_audience`, `tone` |

**经验法则**：如果标签自然成对出现（master/slave, senpai/kouhai），则属于 `graph_native`。

## 3.5 步骤四：定义语义类型

语义类型比命名空间粒度更细。它们帮助 Flash 正确分类标签。

```
anime_tropes 的语义类型：
- personality_trait    (tsundere, yandere)
- relationship_role    (childhood_friend, senpai)
- narrative_function   (protagonist, antagonist)
- setting_element      (high_school, isekai)
- relationship_pattern (love_triangle, slow_burn)
- tone_attribute       (dark, comedic, wholesome)
- demographic          (shounen, shoujo, seinen)
```

目标：5-20 个语义类型。如果需要超过 20 个，说明你的命名空间可能过于粗糙。

## 3.6 步骤五：设置策略参数

```json
{
  "merge_policy": {
    "threshold": 0.90,
    "max_alias_rate": 0.10,
    "require_human_for_cross_namespace": true
  },
  "confidence_policy": {
    "auto_accept": 0.85,
    "flag_for_review": 0.70,
    "reject_below": 0.50
  },
  "depth_policy": {
    "max_depth": 3,
    "warn_at_depth": 3
  },
  "review_policy": {
    "max_queue_size": 100,
    "sample_audit_rate": 0.05
  }
}
```

## 3.7 完成的 Domain Profile 示例

```json
{
  "domain": "anime_character_tropes",
  "language": "en",
  "description": "Anime/manga character archetypes, personality types, relationship roles, and narrative functions",
  "namespace_map": {
    "character_trait": {
      "description": "Character personality traits and behavioral archetypes",
      "axes": ["personality_type", "behavioral_trait"],
      "ontology_type": "flat_behavior"
    },
    "character_role": {
      "description": "Character social, family, and relationship roles",
      "axes": ["relationship_role", "social_role", "family_role"],
      "ontology_type": "graph_native"
    },
    "narrative_role": {
      "description": "Character narrative function in the story",
      "axes": ["protagonist_role", "supporting_role", "antagonist_role"],
      "ontology_type": "specialized_behavior"
    },
    "setting": {
      "description": "Story setting, location, time period, genre context",
      "axes": ["location", "genre_context", "time_period"],
      "ontology_type": "graph_native"
    },
    "relationship_dynamic": {
      "description": "Inter-character relationship patterns and dynamics",
      "axes": ["romantic_dynamic", "power_dynamic", "relationship_development"],
      "ontology_type": "graph_native"
    },
    "meta_attribute": {
      "description": "Work-level attributes: demographic, tone, content rating",
      "axes": ["demographic", "tone", "content_rating"],
      "ontology_type": "meta_style"
    }
  },
  "semantic_types": [
    "personality_trait", "relationship_role", "narrative_function",
    "setting_element", "relationship_pattern", "tone_attribute",
    "demographic", "behavioral_trait", "family_role", "genre_context"
  ],
  "trusted_relations": [
    "specialization_of", "role_pair", "opposite_of", "context_of"
  ],
  "max_depth": 3,
  "merge_threshold": 0.90,
  "auto_accept_confidence": 0.85,
  "language": "en"
}
```

---

# 第四部分 — 分阶段操作

## 阶段速查

```
S1 TRIAGE → S2 NORMALIZE → S3 NAMESPACE → S4 FREEZE ID → S5 ALIAS → S6 VALIDATE → S7 RETRIEVAL → S8 FREEZE
 [Pro]       [Flash]        [Pro]           [Flash+Pro]     [Flash+Pro]   [Pro/Script]   [Script]      [Pro]
```

---

## S1：目录分拣

| 属性 | 值 |
|-----------|-------|
| **负责人** | Pro（或脚本） |
| **模型** | 无（纯计算） |
| **输入** | `raw_tags.json` |
| **输出** | `inventory_clean.json` + 统计报告 |
| **自动化？** | 100% 自动化 |

### 操作

```bash
# 1. 计算标签总数
python -c "import json; print(len(json.load(open('raw_tags.json'))))"

# 2. 检测并移除完全重复的标签（同名）
python deduplicate.py raw_tags.json --by name --output inventory_clean.json

# 3. 检测语言混合情况
python detect_language.py inventory_clean.json

# 4. 标记空名称或无效条目
python flag_garbage.py inventory_clean.json --min_name_length 2
```

### 检查清单

- [ ] 标签总数已确认：_____
- [ ] 完全重复的名称已移除：_____
- [ ] 空/无效名称已标记：_____
- [ ] 语言分布：zh=__% en=__% jp=__% mixed=__%
- [ ] 统计信息已保存至 `s1_stats.json`

### 关卡

> 所有标签均已记录。无空名称。语言混合情况已记录。

### 常见错误

| 错误 | 修复方法 |
|-------|-----|
| CSV 被当作 JSON 导入 | 使用 `csv_to_json.py` 转换 |
| 编码乱码 | 检测 BOM，使用 utf-8-sig |
| 同名但含义不同的标签 | 标记为人工审查，不要自动合并 |

---

## S2：语义标准化（Flash）

| 属性 | 值 |
|-----------|-------|
| **负责人** | Flash |
| **模型** | deepseek-v4-flash (temperature=0) |
| **输入** | `inventory_clean.json` |
| **输出** | `stage1_all_normalized.json` |
| **自动化？** | 95% 自动，5% 标记审查 |

### 操作

```bash
# 运行批次标准化
python stage1_orchestrator.py \
  --input inventory_clean.json \
  --domain domain_profile.json \
  --batch-size 50 \
  --output stage1_all_normalized.json \
  --progress progress.json
```

### Flash 做什么

1. 读取每批 50 个标签
2. 对每个标签，产出：
   - `canonical_id`：namespace.descriptor（snake_case 英文）
   - `normalized_name`：清理后的原始名称
   - `semantic_type`：来自 domain_profile.semantic_types
   - `aliases`：已知的变体名称
   - `possible_duplicates`：此批次中相同概念的标签
   - `confidence`：0.0-1.0
3. 返回 JSON 数组

### Flash 绝对不能做什么

- 设计新的命名空间
- 更改命名空间规则
- 编造本体类型
- 合并标签（仅标记为 possible_duplicates）
- 生成超出可信白名单的关系

### 批次大小调优

| 标签数量 | 批次大小 | 原因 |
|-----------|------------|--------|
| <200 | 30 | 较小的批次 = 对每个标签更好的注意力 |
| 200-1000 | 50 | 标准 |
| 1000-5000 | 50 | 标准 |
| 5000+ | 50 | 保持固定；增加并行度 |

### 重试策略

```
如果 JSON 解析失败：
  Retry 1：同一批次，相同参数
  Retry 2：将 batch_size 减少到 max(10, batch_size // 2)
  Retry 3：跳过批次，加入审查队列

最大重试次数：3
超时时间：每批次 300 秒
速率限制：批次间延迟 1 秒
```

### 检查清单

- [ ] 所有批次已处理：_____ / _____
- [ ] JSON 解析成功率：_____%
- [ ] 置信度 < 0.70 的标签：_____
- [ ] 标记审查的标签：_____
- [ ] 输出中的条目总数 = 输入中的标签总数？[ ] 是 [ ] 否

### 关卡

> 所有批次的 JSON 解析均正常。所有输入标签均已出现在输出中。审查队列 < 总数的 15%。

---

## S3：命名空间架构（Pro）

| 属性 | 值 |
|-----------|-------|
| **负责人** | Pro |
| **模型** | deepseek-v4-pro 或人工 |
| **输入** | S2 输出 + domain_profile.json |
| **输出** | 冻结的命名空间映射 |
| **自动化？** | 部分自动化（Pro 审查，人工签字） |

### 操作

Pro 审查 S2 输出以检查命名空间一致性：

1. 检查：每个标签的命名空间都在 `domain_profile.namespace_map` 中
2. 检查：没有命名空间包含语义类型差异极大的标签
3. 检查：命名空间大小平衡（没有命名空间包含超过 40% 的标签）
4. 冻结：写入 `namespace_freeze.json`，状态为 `"status": "FROZEN"`

### 冻结条件

一旦冻结，命名空间名称及其领域映射**不能**更改。添加新命名空间需要创建新的本体版本。

### 检查清单

- [ ] 所有命名空间都已定义在 domain_profile 中
- [ ] 命名空间大小：最小=___ 最大=___（目标：10-200）
- [ ] 命名空间内部没有 semantic_type 不匹配
- [ ] 交叉检查：命名空间 ↔ 分类一致性
- [ ] `namespace_freeze.json` 已写入，状态为 FROZEN

### 关卡

> ≤30 个命名空间。无命名空间重叠。大小平衡。已冻结。

---

## S4：Canonical ID 冻结（Flash + Pro 审查）

| 属性 | 值 |
|-----------|-------|
| **负责人** | Flash + Pro 审查 |
| **模型** | Flash 提议，Pro 解决冲突 |
| **输入** | S2 输出 + S3 冻结的命名空间 |
| **输出** | `stage4_resolved.json`（零重复 ID） |
| **自动化？**| ~90% 自动，~10% Pro 审查 |

### 操作

1. 将命名空间冻结规则应用于所有 S2 的 canonical_id 提案
2. 运行重复检测：

```python
from collections import Counter
cids = Counter(e["canonical_id"] for e in entries if not e.get("is_duplicate_of"))
duplicates = {c: n for c, n in cids.items() if n > 1}
# 继续之前必须为空
```

3. 对每个重复或标记的条目，Pro 做出决策：

```
ARCHITECT DECISION OPTIONS:
  ACCEPT     — Flash 的分配是正确的，保持不变
  OVERRIDE   — 更改 canonical_id、namespace 或 semantic_type
  QUARANTINE — 当前无法解决；标签需要领域专家介入
  SPLIT      — 两个标签看似相同但属于不同概念
```

4. 应用架构师修正：

```python
ARCHITECT_FIXES = {
    "tag_name": {
        "canonical_id": "corrected.id",
        "namespace": "corrected_ns",
        "semantic_type": "corrected_type",
        "reason": "why this fix was needed"
    }
}
```

### ID 截断规则

如果 canonical_id 的段数超过 3，则截断到 3 段：

```
body_condition.female.super_performance_girl  →  body_condition.super_performance_girl
play.extreme_expansion.clitoris_destruction   →  play.clitoris_destruction
```

### 检查清单

- [ ] 重复的 canonical ID：**必须为 0**
- [ ] 所有架构师修正已应用
- [ ] 所有审查队列条目已解决（ACCEPT/OVERRIDE/QUARANTINE）
- [ ] 无 canonical_id 超过 3 段深度
- [ ] 所有 canonical_id 使用有效的命名空间前缀
- [ ] `stage4_resolved.json` 已保存

### 关卡

> 零重复 canonical ID。所有架构师修正已应用。审查队列为空。

---

## S5：别名折叠（Flash 提议 + Pro 确认）

| 属性 | 值 |
|-----------|-------|
| **负责人** | Flash 提议 + Pro 确认 |
| **模型** | Flash 用于提案，Pro 用于最终合并决策 |
| **输入** | `stage4_resolved.json` |
| **输出** | `alias_graph.json` |
| **自动化？** | Flash 提议（自动），Pro 确认（合并需人工） |

### 操作

1. Flash 扫描每个命名空间中的真正同义词
2. 对每对候选标签，Flash 分配 `merge_confidence`：

```
merge_confidence ≥ 0.95 → AUTO-MERGE (必须 100% 确定)
0.90 ≤ merge_confidence < 0.95 → PROPOSE (Pro 审查)
merge_confidence < 0.90 → REJECT（不是别名）
```

3. Pro 审查所有提案并做出最终决策
4. 应用合并：`is_duplicate_of` 字段指向主条目

### 保守合并规则

**默认：不合并。**

仅在以下所有条件都满足时才合并：
- [ ] 定义相同（不仅仅是相似）
- [ ] 相同的分类/命名空间
- [ ] 无语义细微差异
- [ ] Pro 确认并说明理由

### 别名图结构

```json
{
  "primary": "fetish.foot_fetish",
  "aliases": ["足控", "恋足"],
  "merge_confidence": 0.98,
  "confirmed_by": "architect",
  "reason": "完全同义, 仅命名习惯不同"
}
```

### 检查清单

- [ ] Pro 已审查别名提案：_____
- [ ] 已合并的标签对：_____（目标：总数的 3-10%）
- [ ] 已拒绝的提案：_____
- [ ] 没有别名指向另一个别名
- [ ] `alias_graph.json` 已保存

### 关卡

> 无误合并（抽查 20 对随机合并的标签对）。别名率 3-10%。

---

## S6：验证与质量审计（Pro/脚本）

| 属性 | 值 |
|-----------|-------|
| **负责人** | 脚本（自动）+ Pro（审查报告） |
| **模型** | 无（确定性检查） |
| **输入** | S4 + S5 输出 |
| **输出** | `audit_report.json` |
| **自动化？** | 95% 自动，5% Pro 审查审计发现 |

### 自动检查

```python
CHECKS = [
    ("duplicate_canonical_ids", check_duplicate_cids),       # 必须为 0
    ("namespace_consistency", check_ns_semantic_match),      # 标记不匹配
    ("alias_loops", check_alias_chains),                     # 不允许 A→B→C→A
    ("parent_cycles", check_parent_graph),                   # DFS 循环检测
    ("max_depth_violation", check_depth_le_3),               # 所有路径 ≤ 3
    ("confidence_distribution", check_confidence_histogram), # 标记 <0.70 的聚集
    ("semantic_collapse", check_namespace_size_balance),     # 标记一个命名空间 >30%
    ("orphan_tags", check_all_tags_referenced),              # 无悬空引用
    ("relation_type_whitelist", check_relation_types),       # 仅可信类型
]
```

### 质量报告格式

```json
{
  "timestamp": "2026-05-14T12:00:00",
  "overall_status": "PASS|FAIL|WARN",
  "checks": {
    "duplicate_canonical_ids": { "status": "PASS", "count": 0 },
    "namespace_consistency": { "status": "WARN", "mismatches": 5 },
    ...
  },
  "confidence_histogram": {
    "0.95+": 818, "0.90-0.94": 305, "0.85-0.89": 45,
    "0.80-0.84": 7, "<0.80": 3
  },
  "mean_confidence": 0.934
}
```

### 检查清单

- [ ] 所有自动检查结果为 PASS 或 WARN（无 FAIL）
- [ ] Pro 已审查 WARN 条目
- [ ] 平均置信度 ≥ 0.85
- [ ] 置信度 <0.70 的数量 ≤ 总数的 2%
- [ ] `audit_report.json` 已保存

### 关卡

> 所有检查均为 PASS 或 WARN 已审查。平均置信度 ≥ 0.85。无 FAIL 条目。

---

## S7：检索导出（脚本）

| 属性 | 值 |
|-----------|-------|
| **负责人** | 脚本 |
| **模型** | 无（纯数据转换） |
| **输入** | S6 验证后的本体 |
| **输出** | `retrieval_index.json` |
| **自动化？** | 100% 自动化 |

### 操作

对于每个主条目（跳过别名）：

```python
# 构建嵌入文本（针对 bge 优化）
embedding_text = f"{name} | {' | '.join(aliases[:5])} | {definition[:200]} | 区别于: {distinction[:150]} | 示例: {'、'.join(examples[:5])}"

# 构建语义摘要（用于展示）
semantic_summary = f"{definition[:100]} [{distinction[:60]}]"

# 构建检索别名
retrieval_aliases = [name] + aliases[:10]

# 构建扩展词（用于查询扩展）
expansion_terms = [
    f"ns:{namespace}", f"type:{semantic_type}", f"cat:{category}",
    *examples[:3],
    *[f"axis:{a}" for a in axes]
]
```

### 分面索引

```python
by_namespace[namespace].append(canonical_id)
by_category[category].append(canonical_id)
by_semantic_type[semantic_type].append(canonical_id)
```

### 质量目标

| 指标 | 目标 |
|--------|--------|
| avg_embedding_chars | 100-200 |
| min_embedding_chars | 50 |
| max_embedding_chars | 500 |

### 检查清单

- [ ] 所有主条目都有 embedding_text
- [ ] avg_embedding_chars 在 [100, 200] 范围内
- [ ] 分面索引覆盖所有条目
- [ ] 检索索引中没有别名条目（它们都解析到主条目）
- [ ] `retrieval_index.json` 已保存

### 关卡

> 检索索引已准备就绪，可用于 bge 嵌入生成。

---

## S8：生产冻结（Pro 签字）

| 属性 | 值 |
|-----------|-------|
| **负责人** | Pro（签字） |
| **模型** | 无 |
| **输入** | 所有 S1-S7 输出 |
| **输出** | `freeze_manifest.json` + 版本化发布 |
| **自动化？** | 自动打包，Pro 签字 |

### 操作

1. 验证所有 S1-S7 的关卡均已通过
2. 写入冻结清单：

```json
{
  "version": "1.0.0",
  "status": "FROZEN",
  "freeze_date": "2026-05-14T12:00:00Z",
  "domain": "anime_character_tropes",
  "total_entries": 1178,
  "primary_entries": 1175,
  "alias_entries": 3,
  "namespaces": 25,
  "categories": 19,
  "mean_confidence": 0.934,
  "duplicate_ids": 0,
  "review_queue_remaining": 0,
  "checksums": {
    "ontology_export_v1.json": "sha256:...",
    "retrieval_index.json": "sha256:...",
    "alias_graph.json": "sha256:..."
  },
  "immutable": true
}
```

3. 对输出进行版本化：

```bash
cp ontology_export_v1.json releases/ontology_v1.0.0_2026-05-14.json
cp retrieval_index.json releases/retrieval_v1.0.0_2026-05-14.json
cp freeze_manifest.json releases/manifest_v1.0.0_2026-05-14.json
```

### 冻结规则

**冻结后允许的操作：**
- 添加新标签（使用新的 canonical ID）
- 为已有条目添加新别名
- 修正定义中的拼写错误
- 更新示例

**冻结后禁止的操作：**
- 更改任何 canonical ID
- 删除任何条目
- 更改任何命名空间
- 将两个主条目合并为一个
- 更改条目的 ontology_type
- 更改 parent_canonical_id（如果会产生新的循环或深度违规）

**如果必须更改已冻结的 ID**：创建一个新的本体版本（2.0.0）。旧版本仍可供依赖它的系统使用。

### 检查清单

- [ ] 所有 S1-S8 关卡均已通过
- [ ] `freeze_manifest.json` 已写入，含校验和
- [ ] 版本化发布已归档
- [ ] Pro 签字：__________（姓名/日期）

### 关卡

> 所有关卡已通过。清单已签署。发布已归档。本体已冻结。

---

# 第五部分 — Pro + Flash 协作协议

## 5.1 分工

```
+--------------------------------------------------+
|                    FLASH (Worker)                 |
|                                                  |
|  负责：                                          |
|  ✓ 机械化的名称标准化                            |
|  ✓ canonical_id 生成（遵循规则）                  |
|  ✓ 重复候选检测                                   |
|  ✓ 置信度自评估                                  |
|  ✓ 别名提案生成                                  |
|  ✓ 语言检测                                      |
|                                                  |
|  不负责：                                        |
|  ✗ 设计命名空间                                   |
|  ✗ 覆盖命名空间规则                               |
|  ✗ 做最终合并决策                                 |
|  ✗ 判断语义歧义                                   |
|  ✗ 发明关系类型                                   |
|  ✗ 更改本体架构                                   |
+--------------------------------------------------+
                          |
                          | 审查队列 (JSON)
                          v
+--------------------------------------------------+
|                    PRO (Architect)                |
|                                                  |
|  负责：                                          |
|  ✓ 定义命名空间架构                               |
|  ✓ 解决重复 ID 冲突                               |
|  ✓ 确认或拒绝别名合并                             |
|  ✓ 修复命名空间泄漏                               |
|  ✓ 判断语义近同义词                               |
|  ✓ 质量签字                                      |
|  ✓ 冻结本体                                      |
|                                                  |
|  不负责：                                        |
|  ✗ 做批量标准化（太慢）                           |
|  ✗ 生成嵌入文本（确定性操作）                     |
|  ✗ 运行验证检查（脚本负责）                       |
+--------------------------------------------------+
```

## 5.2 升级规则

Flash 在以下情况下将任务升级到 Pro：

```
confidence < 0.85           → "low_confidence" 标记
duplicate ambiguity         → "needs_review" 标记
namespace uncertainty        → "namespace_conflict" 标记
semantic type mismatch       → "type_ambiguity" 标记
parent assignment uncertain  → "parent_uncertainty" 标记
```

Pro 应该看到 **6-15%** 的标签。如果超过 20% 被升级，说明 domain profile 或命名空间规则需要重新设计。

## 5.3 批次编排

```python
# 最优批次流程
BATCH_SIZE = 50          # Flash 一次处理 50 个标签
MIN_BATCH = 10           # 解析失败时的回退值
MAX_RETRIES = 3          # 解析失败时重试
RATE_LIMIT_DELAY = 1.0   # API 调用间隔秒数
TIMEOUT = 300            # 每批次超时秒数

# 自适应批次大小
if json_parse_failed and batch_size > MIN_BATCH:
    batch_size = max(MIN_BATCH, batch_size // 2)
    retry()
```

## 5.4 成本优化

| 策略 | 节省 |
|----------|---------|
| 使用 Flash 而非 Pro 进行标准化 | 每 token 便宜 10 倍 |
| 每次调用处理 50 个标签（而非 1 个） | API 调用减少 50 倍 |
| 对于明显唯一的别名跳过 Flash | 别名调用减少约 30% |
| S7（检索）作为纯脚本运行（不使用 LLM） | S7 成本为 $0 |
| 缓存相同提示词的 Flash 响应 | 避免重复计算 |
| 使用 temperature=0 获得确定性输出 | 减少重试次数 |

## 5.5 置信度阈值调优

```
confidence ≥ 0.95  →  自动接受（无需人工审查）
0.85 ≤ conf < 0.95 →  自动接受（记录用于抽查）
0.70 ≤ conf < 0.85 →  标记审查（Pro 批量审查）
conf < 0.70        →  个别审查（Pro 逐一审查）
conf < 0.50        →  拒绝（重新运行标准化）
```

根据领域调整阈值：
- **高精度领域**（医疗、法律）：将自动接受提高到 0.90
- **高召回领域**（社交媒体标签）：将自动接受降低到 0.80
- **探索性领域**：标记更多用于审查以了解该领域

---

# 第六部分 — 验证与冻结纪律

## 6.1 验证流水线

```
Stage output → [VALIDATOR] → PASS? → next stage
                                |
                                v FAIL
                           [FIX] → re-validate
```

验证器是**确定性脚本**。零 LLM 调用。零幻觉风险。

## 6.2 冻结前强制检查

### 检查 1：重复的 Canonical ID

```python
from collections import Counter
primary = [e for e in entries if not e.get("is_duplicate_of")]
cids = Counter(e["canonical_id"] for e in primary)
assert all(v == 1 for v in cids.values()), f"DUPLICATES: {[(c,n) for c,n in cids.items() if n>1]}"
```

**关卡**：必须返回 0 个重复项。如果不是，停止并在继续之前解决。

### 检查 2：命名空间一致性

```python
VALID_NAMESPACES = set(domain_profile["namespace_map"].keys())
for e in entries:
    ns = e["namespace"]
    assert ns in VALID_NAMESPACES, f"INVALID NAMESPACE: {e['name']} → {ns}"
    
    # 交叉检查：命名空间应与语义域匹配
    sem = e.get("semantic_type", "")
    ns_axes = domain_profile["namespace_map"][ns].get("axes", [])
    # 如果 semantic_type 不适合此命名空间中的任何轴，标记
```

### 检查 3：别名完整性

```python
aliased = {e["name"] for e in entries if e.get("is_duplicate_of")}
for e in entries:
    target = e.get("is_duplicate_of")
    if target:
        # 目标必须是主条目（不能是另一个别名）
        assert target not in aliased, f"ALIAS LOOP: {e['name']} → {target} (target is also alias)"
        # 目标必须存在
        assert any(p["name"] == target for p in entries), f"ALIAS TARGET NOT FOUND: {target}"
```

### 检查 4：父级循环检测

```python
def has_cycle(entries):
    parent_map = {e["name"]: e.get("parent_canonical_id") for e in entries}
    for name in parent_map:
        visited = set()
        current = name
        while current and current in parent_map:
            if current in visited:
                return True, name  # 检测到循环
            visited.add(current)
            current = parent_map[current]
            if len(visited) > 3:
                return False, None  # 深度超限但无循环
    return False, None
```

### 检查 5：最大深度违规

```python
def check_depth(entries):
    parent_map = {e["name"]: e.get("parent_canonical_id") for e in entries}
    violations = []
    for name in parent_map:
        depth = 0
        current = name
        visited = set()
        while current and current in parent_map and current not in visited:
            visited.add(current)
            current = parent_map[current]
            depth += 1
        if depth > 3:
            violations.append((name, depth))
    return violations
```

**关卡**：零深度违规 > 3。

### 检查 6：置信度分布

```
目标分布：
  0.95+: 60-80%  ← 大多数标签应是高置信度
  0.85-0.94: 15-30%  ← 可接受
  0.70-0.84: 2-8%    ← 已标记，已审查
  <0.70: 0-2%        ← 必须逐一审查
```

**红旗警告**：超过 10% 的标签低于 0.85。重新审视命名空间设计或标准化提示词。

## 6.3 冻结后治理

### 冻结后可以更改的操作

```
允许：
  ✓ 修正定义文本中的拼写错误
  ✓ 更新示例列表
  ✓ 为已有条目添加新别名
  ✓ 添加新条目（使用新的 canonical ID）
  ✓ 弃用条目（标记 deprecated=true，保留 ID）
  ✓ 更新 embedding_text（非结构性更改）

需要新版本 (2.0.0)：
  △ 更改 canonical ID
  △ 删除条目
  △ 更改命名空间
  △ 合并两个主条目
  △ 添加新命名空间（结构性更改）
  △ 更改 max_depth

永久禁止：
  ✗ 不提升版本号就更改 canonical ID
  ✗ 未经弃用期就删除条目
  ✗ 将已弃用的 canonical ID 用于新概念
```

---

# 第七部分 — 检索集成

## 7.1 从本体到检索

```
ontology_export_v1.json          retrieval_index.json
(FROZEN, human-readable)    →    (embedding-optimized, machine-readable)

canonical_id: "fetish.foot_fetish"
name: "足控"                      embedding_text: "足控 | 恋足 | 对脚部..."
aliases: ["恋足"]                 semantic_summary: "对脚部的性偏好..."
definition: "对脚部的..."         expansion_terms: ["ns:fetish", ...]
distinction: "与腿控的区别..."    retrieval_aliases: ["足控", "恋足"]
```

## 7.2 嵌入文本构建

嵌入文本是 bge 编码成向量的内容。其质量直接影响检索召回率。

```python
def build_embedding_text(entry):
    parts = []
    
    # 第一层：主标识符（在 bge 注意力中权重最高）
    parts.append(entry["original_name"])
    
    # 第二层：别名（同义词扩展）
    if entry.get("aliases"):
        parts.append(" | ".join(entry["aliases"][:5]))
    
    # 第三层：定义（核心语义）
    if entry.get("definition"):
        parts.append(entry["definition"][:200])
    
    # 第四层：区分（判别信号 — 对消歧至关重要）
    if entry.get("distinction"):
        parts.append(f"区别于: {entry['distinction'][:150]}")
    
    # 第五层：示例（具体用法）
    if entry.get("examples"):
        parts.append("示例: " + "、".join(entry["examples"][:5]))
    
    return " | ".join(parts)
```

**此结构有效的原理**：
- bge 模型使用均值池化；位置靠前的 token 具有更高权重
- "区别于:" 前缀表示判别性内容
- 示例为关键词搜索提供具体的词项匹配
- 100-200 个字符是中文文本的 bge 最佳范围

## 7.3 分面索引构建

```python
from collections import defaultdict

by_namespace = defaultdict(list)
by_category = defaultdict(list)
by_semantic_type = defaultdict(list)

for entry in retrieval_entries:
    cid = entry["canonical_id"]
    by_namespace[entry["namespace"]].append(cid)
    by_category[entry["category"]].append(cid)
    by_semantic_type[entry["semantic_type"]].append(cid)

# 存储到 retrieval_index.json["indices"]
```

## 7.4 命名空间感知检索

当用户查询到来时：

```python
def retrieve(query, namespace=None, top_k=20):
    # 1. 嵌入查询
    query_vec = bge.encode(query)
    
    # 2. 如果指定了命名空间，限制候选池
    if namespace:
        candidate_ids = facet_index["by_namespace"][namespace]
        candidate_vecs = vectors[candidate_ids]
    else:
        candidate_vecs = all_vectors
    
    # 3. 余弦相似度搜索
    scores = cosine_similarity(query_vec, candidate_vecs)
    top_k_ids = argsort(scores)[-top_k:]
    
    # 4. 返回元数据
    return [
        {
            "canonical_id": cid,
            "name": entries[cid]["original_name"],
            "semantic_summary": entries[cid]["semantic_summary"],
            "score": float(scores[i])
        }
        for i, cid in enumerate(top_k_ids)
    ]
```

## 7.5 本地模型的候选选择

检索索引支持**候选预过滤** — 本地模型永远不需要看到全部 1K+ 标签：

```
Full ontology (1175 tags)
    ↓ facet index: namespace filter
Candidate pool (100-200 tags)
    ↓ bge vector similarity: top-k
Top candidates (20-50 tags)
    ↓ Qwen 8B reranking
Final tags (3-10 tags)
```

这将本地模型的上下文从 1175 个标签减少到 20-50 个候选 — 减少了 95% 以上。

---

# 第八部分 — 打标流水线集成

## 8.1 架构

```
+-----------+     +-----------+     +-----------+     +-----------+
|  Content  | --> | Candidate | --> |  Qwen 8B  | --> |   Final   |
|  Chunking |     | Retrieval |     | Reranking |     |   Tags    |
+-----------+     +-----------+     +-----------+     +-----------+
                        |                                  |
                        v                                  v
                 retrieval_index.json              confidence score
                 + bge embeddings                  + rationale
```

## 8.2 分块策略

对于长篇内容（小说、剧本）：

```python
CHUNK_SIZE = 2000      # 字符数
CHUNK_OVERLAP = 200    # 字符数

# 滑动窗口遍历文本
chunks = []
for i in range(0, len(text), CHUNK_SIZE - CHUNK_OVERLAP):
    chunks.append(text[i:i + CHUNK_SIZE])
```

对于短篇内容（评论、片段）：
- 无需分块；将全文作为一个块使用

## 8.3 候选检索

```python
def get_candidates(chunk_text, domain_profile, top_k=30):
    # 1. bge 嵌入文本块
    chunk_vec = bge.encode(chunk_text)
    
    # 2. 针对检索索引进行语义搜索
    all_scores = cosine_similarity(chunk_vec, retrieval_vectors)
    top_indices = argsort(all_scores)[-top_k:]
    
    # 3. 返回带元数据的候选
    candidates = []
    for idx in top_indices:
        entry = retrieval_entries[idx]
        candidates.append({
            "canonical_id": entry["canonical_id"],
            "name": entry["original_name"],
            "definition": entry["definition"],
            "distinction": entry.get("distinction", ""),
            "score": float(all_scores[idx])
        })
    
    return candidates
```

## 8.4 打标提示词模板

```
You are a content tagger. Tag the following content using ONLY the candidate tags provided.

## CANDIDATE TAGS (choose from these only)
{candidates_formatted}

## RULES
- Select tags that accurately describe the content
- Do NOT select tags just because they are available
- If unsure, prefer fewer tags over more
- Maximum 8 tags per chunk

## CONTENT
{chunk_text}

## OUTPUT
JSON array of selected canonical_ids with confidence:
[
  {"canonical_id": "character_trait.tsundere", "confidence": 0.95, "evidence": "character starts cold then shows warmth when..."},
  ...
]
```

## 8.5 多轮打标

对于长篇内容，独立标记每个块，然后汇总：

```python
# 第一轮：标记每个块
chunk_tags = []
for chunk in chunks:
    candidates = get_candidates(chunk, top_k=30)
    tags = call_llm(tagging_prompt, candidates, chunk)
    chunk_tags.append(tags)

# 第二轮：汇总并去重
from collections import Counter
tag_counts = Counter()
for tags in chunk_tags:
    for tag in tags:
        tag_counts[tag["canonical_id"]] += 1

# 第三轮：最终选择（出现在 >30% 块中的标签）
total_chunks = len(chunks)
final_tags = [
    cid for cid, count in tag_counts.items()
    if count / total_chunks >= 0.30
]
```

## 8.6 模型特定配置

| 模型 | VRAM | 最大候选数 | 批次大小 |
|-------|------|---------------|------------|
| Qwen 2.5 7B | 16 GB | 50 | 1 |
| Qwen 2.5 14B | 32 GB | 50 | 1 |
| Llama 3 8B | 16 GB | 40 | 1 |
| DeepSeek V3 (API) | N/A | 100 | 4 |
| Phi-3 14B | 32 GB | 30 | 1 |

---

# 第九部分 — 故障恢复

## 9.1 故障模式目录

### FM1：本体塌陷（维度性）

| 属性 | 详情 |
|-----------|--------|
| **症状** | 一个命名空间包含超过 40% 的标签；多个不相关的概念混合在一起 |
| **检测** | `check_namespace_size_balance()` — 标记任何包含超过 30% 标签的命名空间 |
| **根本原因** | Domain profile 没有足够细地分解轴 |
| **修复** | 将臃肿的命名空间沿正交轴拆分为 2-3 个新命名空间 |
| **回滚** | 回退到 S3（命名空间架构）输出。重新设计 namespace_map。重新运行 S4-S8。 |
| **需要人工？** | 是 — 需要领域专业知识来识别独立的轴 |

### FM2：过度合并（错误别名）

| 属性 | 详情 |
|-----------|--------|
| **症状** | 两个不同的概念共享相同的 canonical_id |
| **检测** | 抽查：审计 20 对随机合并的标签对。检查定义是否有显著差异。 |
| **根本原因** | Flash 或 Pro 过于激进；"它们听起来相似" → 合并 |
| **修复** | 移除 `is_duplicate_of` 链接。为被错误合并的标签赋予自己的 canonical_id。 |
| **回滚** | 编辑 `alias_graph.json`。使用更高的 merge_threshold 重新运行 S5。 |
| **需要人工？** | 是 — 只有人类能可靠地区分真正同义词和近同义词 |

### FM3：命名空间爆炸

| 属性 | 详情 |
|-----------|--------|
| **症状** | 命名空间过多（>30）；许多命名空间只有 5 个以下标签 |
| **检测** | 统计命名空间数量；标记任何少于 10 个标签的命名空间 |
| **根本原因** | Domain profile 过于细粒度；每个小轴都获得了自己的命名空间 |
| **修复** | 将小命名空间合并到父级或相关命名空间 |
| **回滚** | 重新设计 domain_profile.namespace_map。重新运行 S3-S8。 |
| **需要人工？** | 是 |

### FM4：检索漂移

| 属性 | 详情 |
|-----------|--------|
| **症状** | 搜索 "yandere" 返回 "tsundere" 作为最佳结果；召回率随时间下降 |
| **检测** | 每月运行评估集查询。跟踪 recall@10。如果召回率下降超过 5% 则标记。 |
| **根本原因** | embedding_text 过于泛化；distinction 字段区分性不够 |
| **修复** | 使用更具体的区分语言增强 distinction 字段 |
| **回滚** | 使用改进的 embedding_text 重新生成 retrieval_index.json。重建向量索引。 |
| **需要人工？** | 部分 — 自动召回率跟踪；人工编写更好的区分描述 |

### FM5：低置信度洪流

| 属性 | 详情 |
|-----------|--------|
| **症状** | 超过 20% 的标签置信度 < 0.85；审查队列压垮 Pro |
| **检测** | S2 后检查置信度直方图 |
| **根本原因** | Domain profile 不清晰；Flash 不理解该领域 |
| **修复** | 改进 domain_profile：为每个命名空间添加更多示例，澄清 semantic_type 定义 |
| **回滚** | 更新 domain_profile.json。重新运行 S2。 |
| **需要人工？** | 是 — Pro 必须澄清领域定义 |

### FM6：Canonical ID 冲突（冻结后）

| 属性 | 详情 |
|-----------|--------|
| **症状** | 两个条目意外获得了相同的 canonical_id（绕过了验证） |
| **检测** | 运行 `check_duplicate_cids()` — 应该在 S6 中捕获 |
| **根本原因** | 验证被跳过或有 bug |
| **修复** | 为其中一个条目分配新的 canonical_id。运行完整验证。 |
| **回滚** | 如果已冻结：创建包含修复的 v1.0.1。保留 v1.0.0 供参考。 |
| **需要人工？** | 是 |

### FM7：幻觉标签

| 属性 | 详情 |
|-----------|--------|
| **症状** | Flash 发明了一个不在原始目录中的标签 |
| **检测** | 交叉检查：所有输出标签必须有一个对应的输入标签 |
| **根本原因** | Flash 提示词过于开放；允许 "建议新标签" |
| **修复** | 在提示词中添加约束："不要发明新标签。仅处理输入中的标签。" |
| **回滚** | 删除幻觉条目。使用修复后的提示词重新运行 S2。 |
| **需要人工？** | 否 — 完全可自动化的交叉检查 |

## 9.2 恢复工作流

```
1. 检测：自动检查标记问题
2. 诊断：Pro 识别根本原因（使用上方的 FM 表）
3. 控制：在受影响的阶段停止流水线
4. 回滚：回退到上一个已知良好的阶段输出
5. 修复：应用修复（重新设计领域、修复提示词、更正条目）
6. 重新运行：从修复后的阶段向前重新运行流水线
7. 验证：运行完整验证套件
8. 恢复：继续到冻结
```

---

# 第十部分 — Factory 扩展

## 10.1 从 1K 到 100K 标签

| 规模 | 命名空间策略 | 批次策略 | 审查策略 |
|-------|-------------------|----------------|-----------------|
| **1K** | 5-10 个命名空间 | 50/批，顺序执行 | 100% 审查已标记项 |
| **10K** | 10-20 个命名空间 | 50/批，并行（4 个 worker） | 100% 审查已标记项 |
| **50K** | 15-25 个命名空间 | 命名空间分片，并行（8 个 worker） | 10% 审计抽样 |
| **100K** | 20-30 个命名空间 | 命名空间分片，并行（16 个 worker） | 5% 审计抽样 + 异常检测 |

## 10.2 命名空间分片

对于大型目录，一次处理一个命名空间：

```python
# 不要这样做：将所有 100K 标签 → 2000 个 Flash 批次
# 应该这样做：  命名空间_1: 5K 标签 → 100 个 Flash 批次
#               命名空间_2: 8K 标签 → 160 个 Flash 批次
#               ... (跨命名空间并行)

for namespace in domain_profile["namespace_map"]:
    namespace_tags = [t for t in all_tags if predict_namespace(t) == namespace]
    process_namespace(namespace, namespace_tags)
```

好处：
- Flash 提示词更小、更聚焦
- 更容易发现命名空间特定问题
- 可以跨命名空间并行处理
- 部分失败不会阻塞整个流水线

## 10.3 缓解人工瓶颈

大规模时最大的瓶颈是 Pro 审查。

| 策略 | 节省时间 |
|----------|-----------|
| 将自动接受阈值提高到 0.90 | 审查项减少 30% |
| 批量审查：将相似标记分组 | 每次审查会话效率提高 50% |
| 预批准常见模式 | 消除重复决策 |
| 审查 UI（见下文） | 比原始 JSON 快 3 倍 |
| 委派给经过领域培训的初级审查员 | 水平扩展 |

## 10.4 审查 UI 概念

```
+--------------------------------------------------+
|  ONTOLOGY FACTORY — REVIEW QUEUE (12 remaining)  |
+--------------------------------------------------+
|                                                   |
|  TAG:  chuunibyou                                 |
|  CANONICAL_ID:  character_trait.chuunibyou         |
|  NAMESPACE:     character_trait                    |
|  SEMANTIC_TYPE: personality_trait                  |
|  CONFIDENCE:    0.82  ⚠️ LOW                       |
|  REASON:        "Multiple possible namespace       |
|                  assignments: character_trait vs    |
|                  narrative_role"                   |
|                                                   |
|  DEFINITION:    A character who acts out delusional|
|                 fantasies, pretending to have      |
|                 special powers or a dark past.     |
|                                                   |
|  [ ACCEPT ]  [ OVERRIDE ]  [ QUARANTINE ]  [SKIP] |
+--------------------------------------------------+
```

## 10.5 检索扩展

| 规模 | 向量索引 | 硬件 | 查询延迟 |
|-------|-------------|----------|---------------|
| 1K 标签 | FAISS Flat | CPU | <10ms |
| 10K 标签 | FAISS IVF | CPU | <20ms |
| 100K 标签 | FAISS IVF+PQ | CPU | <50ms |
| 1M 标签 | Milvus | GPU | <100ms |

对于本地推理（RTX 3060 Ti 8GB）：
- 内存中最大向量数：约 50K（使用 bge-large，1024 维）
- 对于 100K+ 标签：使用 IVF 索引 + 磁盘存储

---

# 第十一部分 — 示例演练：动漫角色类型

## 11.1 原始输入

```
raw_tags.json (45 tags):
tsundere, yandere, kuudere, dandere, himedere, genki,
childhood_friend, senpai, kouhai, imouto, onee_san, student_council_president,
protagonist, antagonist, love_interest, comic_relief, mentor, sidekick,
high_school, isekai, post_apocalyptic, urban_fantasy, school_club,
love_triangle, slow_burn, enemies_to_lovers, fake_relationship, will_they_wont_they,
sensei, transfer_student, class_representative, deliquent, idol,
harem_protagonist, dense_protagonist, overpowered_protagonist, anti_hero,
shounen, shoujo, seinen, josei,
dark, comedic, wholesome, tragic, bittersweet
```

## 11.2 S1：分拣

```
总计：45 个标签
已移除重复项：0
语言：10% en, 90% en（含日语借词）
无效条目：0
```

## 11.3 S2：标准化（Flash，1 批 45 个）

Flash 输出示例：

```json
[
  {
    "name": "tsundere",
    "canonical_id": "character_trait.tsundere",
    "normalized_name": "tsundere",
    "semantic_type": "personality_trait",
    "aliases": [],
    "possible_duplicates": [],
    "confidence": 0.98
  },
  {
    "name": "childhood_friend",
    "canonical_id": "character_role.childhood_friend",
    "normalized_name": "childhood friend",
    "semantic_type": "relationship_role",
    "aliases": ["osananajimi"],
    "possible_duplicates": [],
    "confidence": 0.95
  },
  {
    "name": "harem_protagonist",
    "canonical_id": "narrative_role.harem_protagonist",
    "normalized_name": "harem protagonist",
    "semantic_type": "narrative_function",
    "aliases": [],
    "possible_duplicates": ["dense_protagonist"],
    "confidence": 0.78
  }
]
```

已标记：`harem_protagonist` 与 `dense_protagonist` — 可能的重复项，置信度 0.78。

## 11.4 S3：命名空间架构（Pro）

Pro 审查命名空间分配：

```
character_trait:    15 个标签 (tsundere, yandere, kuudere, dandere, himedere, genki, ...)
character_role:     12 个标签 (childhood_friend, senpai, kouhai, imouto, onee_san, ...)
narrative_role:     10 个标签 (protagonist, antagonist, love_interest, comic_relief, ...)
setting:             5 个标签 (high_school, isekai, post_apocalyptic, ...)
relationship_dynamic:5 个标签 (love_triangle, slow_burn, enemies_to_lovers, ...)
meta_attribute:      8 个标签 (shounen, shoujo, dark, comedic, ...)
```

Pro 决策：`setting`（5 个标签）和 `relationship_dynamic`（5 个标签）规模较小但在语义上是独立的。v1.0 保持原样。监控以便在 v2.0 中扩展。

命名空间冻结：已写入 `namespace_freeze.json`。

## 11.5 S4：Canonical ID 冻结

重复检查：

```
harem_protagonist (narrative_role.harem_protagonist)
dense_protagonist (narrative_role.dense_protagonist)
→ Pro 审查：不同概念。
  harem_protagonist = 被恋爱对象包围
  dense_protagonist = 对恋爱暗示迟钝
→ 保持独立。每个的置信度更新为 0.90。
```

架构师修正：需要 0 处。
重复 ID：0。

## 11.6 S5：别名折叠

Flash 提案：

```
childhood_friend ↔ osananajimi: 置信度 0.96 → 自动合并
  → childhood_friend 是规范名称；osananajimi 是别名

love_triangle ↔ triangle_relationship: 置信度 0.97 → 自动合并
  → love_triangle 是规范名称

enemies_to_lovers ↔ rivals_to_lovers: 置信度 0.88 → 提议审查
  → Pro 审查：相似但不同。Enemies = 积极对立。Rivals = 竞争关系。
  → 拒绝合并。保持独立。
```

别名图：2 个合并已确认，1 个已拒绝。

## 11.7 S6：验证

```
duplicate_canonical_ids:     PASS (0)
namespace_consistency:       PASS
alias_loops:                 PASS
parent_cycles:               PASS (尚无父级图定义)
max_depth_violation:         PASS
confidence_distribution:
  0.95+: 38 (84%)
  0.85-0.94: 5 (11%)
  0.70-0.84: 2 (4%)
  <0.70: 0
  平均: 0.94
```

所有检查 PASS。

## 11.8 S7：检索导出

```
检索条目：43（排除了 2 个别名）
平均嵌入字符数：135
命名空间：6
语义类型：10
```

## 11.9 S8：冻结

```json
{
  "version": "1.0.0",
  "status": "FROZEN",
  "domain": "anime_character_tropes",
  "total_entries": 45,
  "primary_entries": 43,
  "alias_entries": 2,
  "mean_confidence": 0.94
}
```

**完成。本体已冻结。准备就绪，可用于打标流水线。**

---

# 第十二部分 — 附录

## A. 推荐模型配置

| 组件 | 模型 | VRAM | 备注 |
|-----------|-------|------|-------|
| 标准化（Flash） | deepseek-v4-flash | N/A (API) | Temperature=0 |
| 架构师审查（Pro） | deepseek-v4-pro | N/A (API) | 或人工 |
| 嵌入 | bge-large-zh-v1.5 | 1.3 GB | 中文优化 |
| 嵌入（备选） | bge-m3 | 2.2 GB | 多语言 |
| 重排序 | Qwen 2.5 7B | 14 GB | 或 8B 量化版 |
| 本地推理 | Qwen 2.5 7B (GPTQ) | 8 GB | 兼容 RTX 3060 Ti |

## B. VRAM 预算（RTX 3060 Ti 8GB）

```
bge-large-zh-v1.5:              1.3 GB
向量索引 (10K × 1024-dim):       0.04 GB
Qwen 2.5 7B (4-bit GPTQ):       4.5 GB
开销 (CUDA, PyTorch):           1.0 GB
─────────────────────────────────────
总计：                           6.8 GB  ✓ 适合 8GB
```

## C. 本体存储 SQLite 模式

```sql
CREATE TABLE ontology_entries (
    canonical_id TEXT PRIMARY KEY,
    original_name TEXT NOT NULL,
    namespace TEXT NOT NULL,
    semantic_type TEXT,
    ontology_type TEXT,
    category TEXT,
    definition TEXT,
    distinction TEXT,
    parent_canonical_id TEXT,
    is_alias_of TEXT,
    confidence REAL,
    frozen INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (parent_canonical_id) REFERENCES ontology_entries(canonical_id),
    FOREIGN KEY (is_alias_of) REFERENCES ontology_entries(canonical_id)
);

CREATE TABLE aliases (
    alias_name TEXT,
    canonical_id TEXT,
    confidence REAL,
    PRIMARY KEY (alias_name, canonical_id),
    FOREIGN KEY (canonical_id) REFERENCES ontology_entries(canonical_id)
);

CREATE TABLE relations (
    source_id TEXT,
    target_id TEXT,
    relation_type TEXT,  -- specialization_of, role_pair, opposite_of, context_of
    confidence REAL,
    PRIMARY KEY (source_id, target_id, relation_type),
    FOREIGN KEY (source_id) REFERENCES ontology_entries(canonical_id),
    FOREIGN KEY (target_id) REFERENCES ontology_entries(canonical_id)
);

CREATE TABLE freeze_log (
    version TEXT PRIMARY KEY,
    freeze_date TEXT,
    total_entries INTEGER,
    checksum TEXT,
    manifest_json TEXT
);
```

## D. 文件命名规范

```
{阶段}_{描述}_{版本}.{扩展名}

示例：
  stage1_all_normalized.json        — S2 输出（合并的批次）
  stage3_review_queue.json          — S4 审查项
  ontology_export_v1.0.0.json       — S8 冻结发布
  retrieval_index_v1.0.0.json       — S7 冻结发布
  alias_graph_v1.0.0.json           — S5 冻结发布
  freeze_manifest_v1.0.0.json       — S8 清单
```

## E. 批次命名规范

```
stage1_batches/
  batch_001.json
  batch_002.json
  ...
  batch_024.json
  _progress.json      — { "last_completed_batch": 15, "total_batches": 24 }
```

## F. 日志格式

```
[2026-05-14 12:00:00] [STAGE2] [BATCH 001/024] START — 50 tags
[2026-05-14 12:00:03] [STAGE2] [BATCH 001/024] FLASH OK — 200ms, 50 entries
[2026-05-14 12:00:03] [STAGE2] [BATCH 001/024] VALIDATE PASS — 0 duplicates, 3 flagged
[2026-05-14 12:00:03] [STAGE2] [BATCH 001/024] SAVE — progress.json updated
[2026-05-14 12:00:04] [STAGE2] [BATCH 002/024] START — 50 tags
...
[2026-05-14 12:10:00] [STAGE2] COMPLETE — 24/24 batches, 1178 entries, 75 flagged
[2026-05-14 12:15:00] [STAGE4] ARCHITECT REVIEW — 75 items, 23 fixes, 52 auto-accept
[2026-05-14 12:20:00] [STAGE6] VALIDATION PASS — all checks green
[2026-05-14 12:25:00] [STAGE8] FREEZE — ontology_export_v1.0.0.json signed
```

## G. 快速参考卡片

```
┌─────────────────────────────────────────────────────────┐
│              ONTOLOGY FACTORY — 快速参考                  │
├─────────────────────────────────────────────────────────┤
│ S1 TRIAGE     → Pro     → inventory_clean.json         │
│ S2 NORMALIZE  → Flash   → stage1_all_normalized.json   │
│ S3 NAMESPACE  → Pro     → namespace_freeze.json         │
│ S4 FREEZE ID  → Flash+P → stage4_resolved.json          │
│ S5 ALIAS      → Flash+P → alias_graph.json              │
│ S6 VALIDATE   → Script  → audit_report.json             │
│ S7 RETRIEVAL  → Script  → retrieval_index.json          │
│ S8 FREEZE     → Pro     → freeze_manifest.json          │
├─────────────────────────────────────────────────────────┤
│ 关键关卡：                                               │
│  □ 重复 canonical ID = 0                                │
│  □ 所有命名空间在 domain_profile 中                       │
│  □ 无别名循环 (alias → alias)                             │
│  □ 所有父级路径深度 ≤ 3                                  │
│  □ 平均置信度 ≥ 0.85                                     │
│  □ 冻结前审查队列 = 0                                    │
├─────────────────────────────────────────────────────────┤
│ 冻结后：                                                 │
│  ✓ 可以添加新标签（新 ID）                                │
│  ✓ 可以修正定义中的拼写错误                               │
│  ✓ 可以添加别名                                         │
│  ✗ 不能更改 canonical ID                                │
│  ✗ 不能删除条目                                         │
│  ✗ 不能更改命名空间                                      │
└─────────────────────────────────────────────────────────┘
```

---

*Ontology Factory 操作手册 v1.0.0*
*基于生产本体系统（1178 个标签，冻结 v3，6 阶段流水线）*
*适用：任何领域。要求：领域专业知识 + DeepSeek API 访问。*
