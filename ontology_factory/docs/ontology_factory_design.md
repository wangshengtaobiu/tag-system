# Ontology Factory 设计文档

> **版本 1.0.0 — 生产版**
> 目标读者：需要将新领域标签目录转化为冻结本体的架构师。

---

## 一、系统概览

Ontology Factory 是一个**半自动化生产系统**，用于将原始的、非结构化的标签目录转换为冻结的、机器可读的规范本体。

```
RAW FOLKSONOMY              CANONICAL ONTOLOGY            RETRIEVAL SYSTEM
(chaotic, human labels)  →  (structured, frozen IDs)  →  (embedding-ready index)

"足控"                        fetish.foot_fetish            bge vector → top-k match
"恋足"                        (alias of above)              Qwen 8B reranking
"腿控"                        fetish.leg_fetish             candidate selection
```

### 四层架构

```
ARCHITECT (Pro / 人工)  →  定义边界，设计命名空间，仲裁歧义
       ↓
WORKER (Flash / 小模型) →  机械标准化、重复检测、置信度评分
       ↓
VALIDATOR (脚本)        →  基于规则的检查：重复ID、循环、深度、命名空间
       ↓
RETRIEVAL (bge + Qwen)  →  嵌入生成、分面索引、候选检索
```

### 8 阶段流水线

```
S1 分拣 → S2 标准化 → S3 命名空间 → S4 ID冻结 → S5 别名 → S6 验证 → S7 导出 → S8 冻结
```

| 阶段 | 执行者 | 是否需要 API |
|------|--------|-------------|
| S1 目录分拣 | 脚本 | 否 |
| S2 语义标准化 | Flash | **是** |
| S3 命名空间架构 | Pro | **是** |
| S4 ID 冻结 | Flash+Pro | **是** |
| S5 别名折叠 | Flash+Pro | **是** |
| S6 验证审计 | 脚本 | 否 |
| S7 检索导出 | 脚本 | 否 |
| S8 生产冻结 | 脚本 | 否 |

---

## 二、Domain Profile 编写指南

Domain Profile 是**唯一的领域相关文件**。Factory 引擎完全与此文件解耦。

### 2.1 定义语义轴

**语义轴是标签沿其变化的独立维度。** 同一轴上的两个标签互斥或可比较，不同轴上的标签可以共存。

```
示例：动漫角色类型

Axis 1: personality_type → tsundere, yandere, kuudere, ...
Axis 2: relationship_role → childhood_friend, senpai, kouhai, ...
Axis 3: narrative_function → protagonist, antagonist, love_interest, ...

一个角色可以同时是 tsundere（轴1）和 childhood_friend（轴2）和 protagonist（轴3）。
```

**需要多少个轴？**
- <100 标签：2-4 个轴
- 100-1K 标签：3-8 个轴
- 1K-10K 标签：5-15 个轴

**红旗警告**：如果一个轴包含超过 30% 的标签，可能需要拆分。如果两个轴的标签集合有显著重叠，需要合并。

### 2.2 设计命名空间

命名空间是 canonical ID 的前缀，对应一个或多个语义轴。

**原则：**
- **覆盖性**：每个标签必须恰好归入一个命名空间
- **无重叠**：两个命名空间不应描述相同的语义域
- **大小平衡**：目标每个命名空间 10-200 个标签
- **稳定性**：命名空间在 S3 后冻结，选择能长期使用的名称

**格式：** 小写、snake_case、英文，最大深度 3 段。

### 2.3 分配本体类型

| 类型 | 使用场景 | 示例 |
|------|---------|------|
| `flat_behavior` | 简单属性标签，不需要内部结构 | `tsundere` — 是就是，不是就不是 |
| `specialized_behavior` | 有子类型和强度变体的行为/角色 | `character_archetype` 有子原型 |
| `graph_native` | 标签互相蕴含，存在互惠关系 | `relationship_dynamic` — 三角恋涉及多个角色 |
| `meta_style` | 描述作品本身而非内容 | `content_rating`, `target_audience` |

### 2.4 定义语义类型

语义类型比命名空间粒度更细，帮助 Flash 正确分类标签。目标 5-20 个。

### 2.5 完整示例

```json
{
  "domain": {
    "name": "anime_character_tropes",
    "version": "1.0.0",
    "language": "en",
    "description": "Anime/manga character archetypes and roles"
  },
  "namespace_map": {
    "character_trait": {
      "label": "Character Traits",
      "description": "Personality traits and behavioral archetypes",
      "axes": ["personality_type", "behavioral_trait"],
      "categories": ["性格特征"],
      "max_depth": 3,
      "ontology_type_hint": "flat_behavior"
    },
    "character_role": {
      "label": "Character Roles",
      "description": "Social, family, and relationship roles",
      "axes": ["relationship_role", "social_role", "family_role"],
      "categories": ["角色身份"],
      "max_depth": 3,
      "ontology_type_hint": "graph_native"
    }
  },
  "semantic_types": [
    {"id": "personality_trait", "label": "Personality Trait", "description": "Character personality descriptors"},
    {"id": "relationship_role", "label": "Relationship Role", "description": "Inter-character relationship roles"},
    {"id": "narrative_function", "label": "Narrative Function", "description": "Character narrative function"}
  ],
  "ontology_type_rules": {
    "flat_behavior": {"type_dominant_ratio_min": 0.80, "tag_count_min": 20},
    "specialized_behavior": {"type_dominant_ratio_min": 0.60, "type_dominant_ratio_max": 0.80},
    "graph_native": {"type_dominant_ratio_max": 0.60, "tag_count_min": 10},
    "meta_style": {"tag_count_max": 10, "meta_style_ratio_min": 0.50}
  },
  "alias_policy": {
    "merge_threshold": 0.90,
    "auto_accept_threshold": 0.85,
    "max_aliases_per_entry": 10,
    "forbidden_merges": [],
    "conservative_merges": true
  },
  "confidence_thresholds": {
    "auto_accept": 0.85,
    "needs_review": 0.70,
    "reject": 0.60,
    "target_mean": 0.85
  },
  "relation_policy": {
    "trusted_types": ["specialization_of", "role_pair", "opposite_of", "context_of"],
    "max_relations_per_entry": 5,
    "min_relation_confidence": 0.85
  },
  "id_convention": {
    "format": "namespace.descriptor[.detail]",
    "max_depth": 3,
    "language": "en",
    "case": "snake_case",
    "separator": "."
  }
}
```

### 2.6 关键策略参数

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `auto_accept` | 0.85 | 置信度 ≥ 此值直接接受 |
| `needs_review` | 0.70 | 介于 auto_accept 和此值之间标记审查 |
| `reject` | 0.60 | < 此值拒绝 |
| `merge_threshold` | 0.90 | 别名合并最低置信度 |
| `max_depth` | 3 | canonical ID 最大段数 |

---

## 三、核心设计原则

### 渐进冻结

本体分层次冻结，而非一次性全部：

```
命名空间规则 → 先冻结 (S3)
规范 ID      → 其次冻结 (S4)
别名图       → 再次冻结 (S5)
完整本体     → 最后冻结 (S8)
```

### 保守合并

**错误合并是灾难性的。重复存留是可以接受的。** 默认不合并，仅在 95%+ 确定时才合并。

### 浅且宽

max_depth = 3（硬限制）。深层层次结构会降低嵌入质量。本地模型在浅层、宽幅结构上表现最佳。

### 尽可能确定性

S1/S6/S7/S8 全是纯脚本，零 LLM 调用。仅 S2/S3/S4/S5 需要 API。

### 关系类型白名单

只允许 4 种可信关系类型：`specialization_of`、`role_pair`、`opposite_of`、`context_of`。稀疏 + 稳定 > 丰富 + 幻觉。

### 嵌入优化

本体必须为嵌入模型优化。embedding_text 应为 100-200 字符，包含：名称 + 别名 + 定义 + 区分 + 示例。

---

## 四、冻结后治理

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

*Ontology Factory 设计文档 v1.0.0*
