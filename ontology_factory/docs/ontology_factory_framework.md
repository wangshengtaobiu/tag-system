# 本体规范化框架 —— 领域无关的工厂蓝图

> 摘自已完成的成人标签本体项目（1178 个标签，6 个阶段，冻结 v3）。
> 这是一份**工程框架**，而非理论论文。
> 目标：任何具有原始大众分类 → 冻结规范本体的领域。

---

## 产出 1 —— 通用 8 阶段规范化流水线

基于实际生产经验，而非理论设计。每个阶段有明确的输入、输出、负责模型和验证关卡。

```
                         +-------------------+
                         |  原始清单          |
                         |  (标签, 别名,      |
                         |   定义)            |
                         +--------+----------+
                                  |
                    +-------------v-------------+
                    | S1: 清单分类             |  Pro
                    | - 计数、去重原始数据      |
                    | - 检测语言混合情况        |
                    | - 标记垃圾条目            |
                    +-------------+-------------+
                                  |
                    +-------------v-------------+
                    | S2: 语义                  |  Flash (批量)
                    |     规范化                 |
                    | - 规范化名称              |
                    | - 提议规范 ID             |
                    | - 检测真正重复项          |
                    | - 分配置信度              |
                    +-------------+-------------+
                                  |
                    +-------------v-------------+
                    | S3: 命名空间              |  Pro
                    |     架构                  |
                    | - 定义命名空间映射        |
                    | - 分配类别→命名空间       |
                    | - 设置 max_depth=3        |
                    | - 冻结命名空间规则        |
                    +-------------+-------------+
                                  |
                    +-------------v-------------+
                    | S4: 规范                  |  Flash + Pro 审查
                    |     ID 冻结               |
                    | - 解决 ID 冲突            |
                    | - 应用架构修正            |
                    | - 验证无重复项            |
                    | - 标记为不可变            |
                    +-------------+-------------+
                                  |
                    +-------------v-------------+
                    | S5: 别名                   |  Flash 提议 +
                    |     合并                    |  Pro 确认
                    | - 识别真正同义词           |
                    | - 仅保守合并               |
                    | - 拒绝错误合并             |
                    | - 构建别名图               |
                    +-------------+-------------+
                                  |
                    +-------------v-------------+
                    | S6: 验证                  |  Pro
                    |     与质量审计             |
                    | - 重复 ID 检查            |
                    | - 命名空间违规            |
                    | - 语义合并检查            |
                    | - 置信度分布              |
                    +-------------+-------------+
                                  |
                    +-------------v-------------+
                    | S7: 检索                  |  脚本 (自动化)
                    |     导出                  |
                    | - 构建嵌入文本            |
                    | - 生成分面索引            |
                    | - 准备扩展词              |
                    | - 针对 bge/Qwen 优化      |
                    +-------------+-------------+
                                  |
                    +-------------v-------------+
                    | S8: 生产                  |  Pro (签署)
                    |     冻结                  |
                    | - 标记版本                |
                    | - 写入不可变清单          |
                    | - 归档所有中间产物        |
                    | - 激活下游系统            |
                    +---------------------------+
```

### 各阶段详情

| # | 阶段 | 负责方 | 输入 | 输出 | 关卡 |
|---|-------|-------|-------|--------|------|
| S1 | 清单分类 | Pro | 原始 CSV/JSON | 清洗后的清单 + 统计 | 所有标签已计入 |
| S2 | 语义规范化 | Flash (批量 30-50) | 清洗后的清单 | canonical_id 提议、置信度 | JSON 解析成功，所有标签都在输出中 |
| S3 | 命名空间架构 | Pro | 领域分析 | 冻结的命名空间映射 | 命名空间 ≤30 个，无重叠 |
| S4 | 规范 ID 冻结 | Flash + Pro 审查 | S2 输出 + S3 规则 | 已解决的 ID，零重复 | Counter({cid}) 全为 1 |
| S5 | 别名合并 | Flash 提议 + Pro 确认 | S4 输出 | 别名图，3-10% 别名率 | 无错误合并（审计抽样） |
| S6 | 验证与审计 | Pro | S4+S5 输出 | 审计报告，审查队列 | 所有关卡通过 |
| S7 | 检索导出 | 脚本 | 冻结的本体 | retrieval_index.json | 嵌入文本平均 >100 字符 |
| S8 | 生产冻结 | Pro | 所有资产 | 版本化、不可变发布 | 清单已签署 |

### 核心流水线特性

- **渐进冻结**：先冻结命名空间（S3），再冻结 ID（S4），最后冻结整个本体（S8）
- **S2 批量并行**：Flash 调用天然可并行（批次间无依赖）
- **S4、S5、S6 架构师在回路中**：Pro 审查模糊案例；Flash 处理机械性工作
- **S7 确定性**：不调用 LLM；纯数据转换
- **S8 不可变**：一旦冻结，下游系统将永远依赖 ID 稳定性

---

## 产出 2 —— 不变量

### 领域无关的不变量（适用于任何本体项目）

| # | 不变量 | 理由 |
|---|-----------|-----------|
| I1 | **规范 ID 不可变** | 一旦冻结，永不更改。下游嵌入、索引和模型依赖 ID 稳定性。类比数据库主键。 |
| I2 | **命名空间不可变** | 命名空间是 ID 前缀的一部分。更改命名空间 = 更改 ID = 破坏所有下游引用。 |
| I3 | **max_depth ≤ 3** | 深层层次结构会降低嵌入质量。本地模型（Qwen 8B、bge）在浅层、宽幅结构上表现最佳。 |
| I4 | **别名从不指向别名** | 传递别名会制造维护噩梦。每个别名必须通过 ≤1 跳解析到主条目。 |
| I5 | **保守合并策略** | 错误合并是灾难性的（丢失一个概念）。重复存留是可以接受的（有噪音，但不会遗漏）。默认：不合并。 |
| I6 | **检索索引与本体图分离** | 本体是真实数据源。检索索引是物化视图。两者独立演化。 |
| I7 | **语义模糊案例必须经过架构师审查** | 任何置信度 < 0.85、命名空间冲突或疑似语义合并的案例，必须经过人工/Pro 审查。 |
| I8 | **关系类型采用白名单制，而非开放式** | 限制在 3-4 种可信类型。更丰富的类型 = 更多幻觉。稀疏 + 稳定 > 丰富 + 幻觉。 |
| I9 | **snake_case、英文标识符** | 机器可读、嵌入友好、语言中立。ID 中不使用 Unicode。 |
| I10 | **每个输出字段都有明确归属** | Flash 字段：`canonical_id`、`normalized_name`、`confidence`。Pro 字段：`namespace`、`ontology_type`、`final_id`。可追溯性不可妥协。 |

### 领域特定的不变量（来自成人标签项目，可能不具通用性）

| # | 不变量 | 上下文 |
|---|-----------|---------|
| D1 | **身体分类体系解析：5 个独立轴** | 身体特征需要将 body_anatomy、body_shape、body_size、body_condition、body_aesthetic 作为独立轴。一般本体可能不需要这种粒度。 |
| D2 | **标签数 < 10 时合并类别** | 成人领域原有 22 个类别；合并了小类别（≤7 个标签），除非在语义上具有独特性。阈值因领域而异。 |
| D3 | **强度/严重程度作为一等轴** | 成人内容需要强度分级（轻度→极端）。许多领域不需要。 |
| D4 | **多语言别名检测** | 成人标签有中文/日文/英文变体。单语领域可跳过此项。 |
| D5 | **心理维度分离** | 权力关系、禁忌关系、心理状态在成人领域中属于独立类别。其他领域可能将其合并。 |
| D6 | **meta_style 用于内容级与作品级属性区分** | "高H"（高频率）是作品级风格，而非内容标签。这种区分在较简单的领域中可能不存在。 |

### 如何推导领域不变量

1. 列出你领域中的所有概念
2. 识别哪些概念是**正交的**（可以独立同时出现）→ 独立轴
3. 识别哪些概念是**层次的**（一个包含另一个）→ 父子关系
4. 识别哪些概念是**互斥的** → 同一轴，不同值
5. 在规范化开始之前冻结轴定义

---

## 产出 3 —— 角色分离

### 双模型架构

```
+------------------+          +------------------+
|   架构师          |          |   工人            |
|   (Pro / 人工)   |          |   (Flash)        |
+------------------+          +------------------+
|                  |          |                  |
| 本体边界           |  设计   | 机械性            |
| 命名空间设计       | ------->| 规范化            |
| 语义判断           |          |                  |
| 别名仲裁           |  审查   | 重复项            |
| 故障诊断           | <-------| 候选              |
| 质量签署           |          |                  |
|                  |          | 置信度评分         |
| 低吞吐量          |          | 高吞吐量          |
| 高精度           |          | 良好精度          |
+------------------+          +------------------+
```

### 架构师职责（Pro 模型 / 人工）

| 职责 | 为何 Flash 无法胜任 |
|----------------|--------------------------|
| **本体边界定义** | 需要理解完整的领域范围并做出排除决策 |
| **命名空间架构** | 需要一次性查看整个标签清单；Flash 只能看到批次 |
| **语义模糊判断** | 需要对近义词有细致理解（如 贱婊 vs 骚货） |
| **别名仲裁** | 错误合并 = 灾难。需要人工级语义验证 |
| **类别合并/拆分决策** | 需要理解下游用例和检索模式 |
| **故障模式诊断** | 需要元认知能力来分析流水线为何产生特定错误 |
| **质量签署与冻结** | 对下游系统稳定性负责 |
| **不变量执行** | 必须验证所有冻结规则是否被遵守 |

### 工人职责（Flash / 小模型）

| 职责 | 为何 Flash 足够胜任 |
|----------------|------------------------|
| **名称规范化** | 机械性：去除后缀、标准化标点、检测语言 |
| **canonical_id 生成** | 机械性：应用命名空间规则、翻译为英文、应用 snake_case |
| **重复项候选生成** | 模式匹配：查找近乎相同的字符串或高度相似的定义 |
| **置信度评分** | 自我评估：Flash 对自己输出的确定性有多高？ |
| **嵌入文本生成** | 机械性：将结构化字段拼接为面向检索优化的文本 |
| **字母/排序操作** | 纯粹计算，无需语义判断 |
| **批量处理** | 高吞吐量、低成本、可并行化 |

### 通信协议

```
Flash → Pro:  normalized_entry { canonical_id, confidence, needs_review, review_reason }
Pro → Flash:  (无直接反馈；Pro 的修正在后处理中应用)

Pro 从不问 Flash "这个标签应该属于哪个命名空间？"
Pro 只问 Flash "在这些已冻结的命名空间规则下，canonical_id 是什么？"
```

### 成本模型

| 阶段 | 模型 | 调用次数 | 每 1000 个标签成本 |
|-------|-------|-------|-------------------|
| 规范化 | Flash | 20-30 批次 | ~$0.50-1.00 |
| 别名检测 | Flash | 每个类别 1 次调用 | ~$0.10-0.30 |
| 架构师审查 | Pro/人工 | 1 遍 | ~5-10% 标签被标记 |
| 导出 | 脚本 | 0 次 LLM 调用 | $0 |

目标：**90%+ 标签自动处理**，<10% 需要架构师审查。

---

## 产出 4 —— 故障分类体系

记录了成人标签项目中遇到的实际故障。

### F1：维度坍塌

| 属性 | 描述 |
|-----------|-------------|
| **症状** | 多个正交概念被归并到一个轴中（例如，身体特征全放在 `physical_attribute` 下） |
| **根因** | 分类体系解析度不足；架构师未将领域分解为独立轴 |
| **检测** | 统计每个类别的标签数量；若一个"轴"拥有 >30% 的全部标签，怀疑存在坍塌。检查该类别中的标签是互斥的还是可以共存。 |
| **修复** | 分解为正交轴。来自项目：身体特征 → 5 个轴（解剖、形状、大小、状态、审美） |
| **是否需要人工？** | 是 —— 需要领域专业知识来识别独立轴 |

### F2：过度合并别名（错误合并）

| 属性 | 描述 |
|-------------|-----------|
| **症状** | 两个不同概念被赋予相同的 canonical_id |
| **根因** | Flash 或审查者在别名检测中过于激进；"它们听起来相似" → 合并 |
| **检测** | 审计合并对的抽样；检查它们是否有不同的定义、不同的类别或不同的父标签 |
| **修复** | 撤销合并；给每个概念分配自己的 canonical_id。接受重复存留。 |
| **是否需要人工？** | 是 —— 只有人工/Pro 才能可靠地区分真正同义词和近义词 |

### F3：命名空间泄漏

| 属性 | 描述 |
|-------------|-----------|
| **症状** | 标签被分配到命名空间 X，但其 semantic_type 属于命名空间 Y（例如，将 `clothing.foot_worship` 用于一个恋物概念） |
| **根因** | Flash 使用原始 `category` 字段来确定命名空间，但该类别是错误的。Flash 无权覆盖类别。 |
| **检测** | 交叉检查：命名空间 vs semantic_type 一致性。如果 `namespace=clothing` 但 `semantic_type=fetish_type`，标记审查。 |
| **修复** | 架构师覆盖命名空间。在项目中：足崇拜从 `clothing` 移至 `fetish`。 |
| **是否需要人工？** | 是 —— 需要理解每个命名空间的语义域 |

### F4：语义漂移（LLM 不稳定性）

| 属性 | 描述 |
|-------------|-----------|
| **症状** | 不同 Flash 批次为同一概念分配不同的 canonical_id；或同一批次产生不一致的命名空间选择 |
| **根因** | LLM 非确定性；各批次间提示词的解读存在细微差异 |
| **检测** | 跨所有批次的事后重复 ID 检查。比较相似概念标签的命名空间分配。 |
| **修复** | 在规范化之前冻结命名空间规则（S3 在 S2 之前）。使用确定性的 temperature=0。架构师后处理解决冲突。 |
| **是否需要人工？** | 部分 —— 自动重复检测能捕获大多数；架构师解决剩余部分 |

### F5：关系幻觉

| 属性 | 描述 |
|-------------|-----------|
| **症状** | Flash 虚构不存在的关系（例如，`A causes B`、`A is associated_with B`） |
| **根因** | 白名单未严格执行；Flash 被允许提议开放式关系类型 |
| **检测** | 对照 TRUSTED_RELATION_TYPES 白名单过滤所有关系。统计被拒绝的关系数量。 |
| **修复** | 严格执行白名单（最多 4 种类型）。丢弃所有非白名单关系。要求置信度 ≥ 0.85。 |
| **是否需要人工？** | 否 —— 可通过白名单过滤器全自动处理 |

### F6：本体形态失真

| 属性 | 描述 |
|-------------|-----------|
| **症状** | 标签被强制置入 `flat_behavior` 形态，而它们本质上是图结构的（例如，互相隐含的关系角色） |
| **根因** | 类别 → ontology_type 映射过于死板；未考虑边界情况 |
| **检测** | 检查是否有标签的 `ontology_type` 与其自然结构相矛盾（例如，互惠关系被标记为 flat_behavior） |
| **修复** | 允许基于命名空间覆盖 ontology_type。在项目中：`meta_style` 命名空间强制使用 `meta_style` ontology_type，无论类别如何。 |
| **是否需要人工？** | 是 —— 需要理解本体形态理论 |

### F7：父节点循环风险

| 属性 | 描述 |
|-------------|-----------|
| **症状** | parent_canonical_id 链中出现 A → B → C → A 循环 |
| **根因** | 未检查父节点分配；Flash 提议父节点时没有循环检测 |
| **检测** | 在父图上的 DFS/BFS。检测已访问节点。同时检查所有路径的深度 ≤ 3。 |
| **修复** | 拒绝会创建循环或深度 > 3 的父节点分配。将问题标签的父节点设为 null。 |
| **是否需要人工？** | 否 —— 可通过图循环检测全自动处理 |

### F8：类别派生的命名空间错误

| 属性 | 描述 |
|-------------|-----------|
| **症状** | 标签被分配到错误的命名空间，因为 Flash 信任了原始 `category` 字段，而该字段本身是错误的 |
| **根因** | 原始数据质量问题：标签在源数据中被错误分类。Flash 无法覆盖。 |
| **检测** | 检查所有 `namespace` 与 `semantic_type` 不匹配的标签。在项目中：美腿(身体特征) 在 `role` 命名空间中。 |
| **修复** | 架构师根据实际语义内容而非原始类别覆盖命名空间。 |
| **是否需要人工？** | 是 —— 需要理解标签的语义 |

### 故障预防检查清单

- [ ] S3：命名空间规则在 S2 规范化开始前冻结
- [ ] S4：每次架构修正后运行重复 ID 检查
- [ ] S5：别名审计抽样（随机检查 20 个合并对是否存在错误合并）
- [ ] S6：父图循环检测（自动化）
- [ ] S6：命名空间与 semantic_type 一致性交叉检查
- [ ] S6：置信度分布审查（标记 <0.80 的聚类）
- [ ] S8：冻结前验证所有不变量

---

## 产出 5 —— 通用提示词模板

所有模板均为**领域无关**且**参数化**的。将 `{DOMAIN}`、`{LANGUAGE}`、`{NAMESPACES}`、`{SEMANTIC_TYPES}` 替换为领域特定值。

### 模板 1：规范化提示词（用于 Flash，批量模式）

```
You are a mechanical tag normalizer. You do NOT design ontology. You do NOT invent concepts.

## TASK
For each tag in the batch, produce:
1. normalized_name: clean the name (remove redundant suffixes, standardize {LANGUAGE})
2. canonical_id: apply these FROZEN namespace rules:
   {NAMESPACE_RULES}
3. semantic_type: choose from: {SEMANTIC_TYPES}
4. aliases: list any known variant names for this concept (max 5)
5. possible_duplicates: list other tags in THIS BATCH that appear to be the same concept
6. confidence: 0.0-1.0 for your canonical_id assignment

## RULES
- canonical_id format: {namespace}.{descriptor} (max depth 3, snake_case, English)
- Only use namespaces from the FROZEN list above
- If unsure about semantic_type, mark as "unknown" and set confidence < 0.7
- Do NOT merge tags. Mark as possible_duplicates only.
- Do NOT invent relation types. Leave relations empty.

## OUTPUT FORMAT
Return a JSON array:
[
  {
    "name": "original_tag_name",
    "normalized_name": "...",
    "canonical_id": "...",
    "semantic_type": "...",
    "aliases": [...],
    "possible_duplicates": [...],
    "confidence": 0.0
  }
]

## BATCH
{batch_json}
```

### 模板 2：别名检测提示词（用于 Flash，按类别）

```
You are an alias detector. Your ONLY job is to identify true synonyms.

## DEFINITION
TRUE ALIAS = exactly the same concept, only the name differs.
Examples: {foot_控, 恋足} → same concept "foot fetish".
NOT aliases: different sub-types, different intensities, different categories.

## RULES
1. Only merge if you are 95%+ certain they are the same concept
2. Different names for the same category-internal concept → likely alias
3. Different categories → NEVER alias
4. One is a sub-type of another → NOT alias

## INPUT
Category: {category_name}
Tags:
{tag_list_with_definitions}

## OUTPUT FORMAT
JSON array of alias groups:
[
  {
    "canonical_name": "most_common_name",
    "canonical_id": "existing_canonical_id",
    "aliases": ["variant1", "variant2"],
    "merge_confidence": 0.95,
    "reason": "brief explanation"
  }
]

If no aliases found, return empty array [].
```

### 模板 3：命名空间分配提示词（用于 Pro 架构审查）

```
## CONTEXT
You are reviewing a batch of tags that Flash could not confidently assign to namespaces.

## FROZEN NAMESPACES
{namespace_definitions_with_examples}

## TASK
For each tag below, assign the correct namespace and explain your reasoning.

## CONSIDERATIONS
- A tag belongs to ONE namespace only
- Choose the namespace whose semantic domain BEST matches the tag's core concept
- Ignore the original category field if it conflicts with the tag's actual meaning
- If a tag genuinely spans two domains, pick the PRIMARY one

## TAGS FOR REVIEW
{tags_with_definitions}

## OUTPUT
[
  {
    "name": "...",
    "assigned_namespace": "...",
    "confidence": 0.0,
    "reasoning": "why this namespace"
  }
]
```

### 模板 4：本体审查提示词（用于 Pro，冻结前审计）

```
You are an ontology auditor. The ontology below is about to be FROZEN (immutable).

## AUDIT CHECKLIST
For each entry, verify:
1. canonical_id follows namespace convention ({format})
2. semantic_type is from the allowed set
3. No duplicate canonical_ids exist
4. Aliases point to existing primary entries (not other aliases)
5. Parent chains have no cycles and depth ≤ 3
6. No tag has confidence < 0.60 without a review note

## ENTRIES TO AUDIT
{sample_of_entries}

## FLAGGED ITEMS (pre-marked for review)
{review_queue_items}

## TASK
For each flagged item, make a FINAL decision:
- ACCEPT: the current assignment is correct
- FIX: provide corrected values
- QUARANTINE: tag needs domain expert review (cannot be resolved now)

## OUTPUT
[
  {
    "name": "...",
    "decision": "ACCEPT|FIX|QUARANTINE",
    "changes": { ... },  // if FIX
    "justification": "why"
  }
]
```

### 模板 5：检索准备模板（用于脚本，不调用 LLM）

```
This is a SCRIPT template, not a prompt. No LLM call.

## INPUT
Frozen ontology JSON (ontology_export_v1.json)

## PROCESSING (per entry)
1. Skip entries where is_alias_of != null
2. Build embedding_text:
   embedding_text = "{name} | {aliases joined} | {definition[:200]} | 区别于: {distinction[:150]} | 示例: {examples[:5] joined}"
3. Build semantic_summary:
   semantic_summary = "{definition[:100]} [{distinction[:60]}]"
4. Build retrieval_aliases:
   [name] + aliases[:10]
5. Build candidate_expansion_terms:
   ["ns:{namespace}", "type:{semantic_type}", "cat:{category}"] + examples[:3] + ["axis:{a}" for a in axes]
6. Collect facet indices:
   by_namespace[namespace].append(canonical_id)
   by_category[category].append(canonical_id)
   by_semantic_type[semantic_type].append(canonical_id)

## OUTPUT
retrieval_index.json with:
- entries: list of retrieval-optimized tag records
- indices: facet lookup maps
- meta: stats (avg_embedding_chars, namespace count, etc.)
```

---

## 产出 6 —— 规范化理论（工程原则）

源自项目实践，表述为可操作的原则。

### 原则 1：渐进冻结

**本体分层次冻结，而非一次性全部冻结。**

```
命名空间规则  →  先冻结  (S3)
规范 ID       →  其次冻结 (S4)
别名图        →  再次冻结 (S5)
完整本体      →  最后冻结 (S8)
```

**原因**：每一层都约束下一层。如果命名空间规则在 ID 分配后更改，所有 ID 将失效。先冻结基础。

### 原则 2：ID 即主键

**将规范 ID 完全视为数据库主键来对待。**

- 一旦分配，永不更改
- 如果发现某个概念有误，创建一个带有新 ID 的新条目
- 旧 ID 变为弃用状态，永不删除
- 下游系统（嵌入、搜索索引、模型）依赖 ID 稳定性

### 原则 3：保守合并

**错误合并是灾难性的。重复存留是可以接受的。**

- 默认立场：不合并
- 仅在 95%+ 确定时合并（生产环境中需人工验证）
- 如果两个标签有不同的定义、类别或父标签 → 不是别名
- 本体中的重复是噪音。错误合并则是遗漏（概念丢失）。

### 原则 4：浅且宽

**深层层次结构会降低检索质量。优先采用浅层、宽幅结构。**

- max_depth = 3（硬限制）
- 目标：80%+ 标签在深度 ≤ 2
- 每个命名空间应有 5-20 个直接子项，而非长链
- BGE 嵌入和 Qwen 重排序在扁平结构上表现更好

### 原则 5：分面优于树

**标签天然属于多个分面。树结构会强制做出错误选择。**

- 像"桌下口交"这样的标签既是 sex_act 又是 scene。不要强制归入其一。
- 使用分面索引（by_namespace、by_category、by_semantic_type）进行检索
- 本体图提供结构；分面提供访问路径
- 树是近似；分面才是现实

### 原则 6：尽可能确定性

**每个可以是确定性的阶段都应该是确定性的。**

- S7（检索导出）：纯数据转换，零 LLM 调用
- S6（验证）：基于规则的检查、循环检测
- S1（分类）：计数、排序、去重
- 仅 S2（规范化）和 S5（别名）需要 LLM 调用

### 原则 7：置信度作为质量信号

**每个 LLM 生成的字段都有一个置信度评分。低置信度 → 审查。**

- confidence ≥ 0.95：自动接受
- 0.85 ≤ confidence < 0.95：自动接受，记录用于抽样
- 0.70 ≤ confidence < 0.85：标记进行批量审查
- confidence < 0.70：需要单独架构师审查

### 原则 8：嵌入优化的文本

**本体不只是为人类设计的。它必须为嵌入模型进行优化。**

- 嵌入文本应为 100-200 字符（bge 最佳区间）
- 包含：名称 + 别名 + 定义 + 区分 + 示例
- 使用"区别于:"前缀使区分信息可搜索
- 包含命名空间/类型/类别作为扩展词，用于查询扩展

### 原则 9：可追溯性

**每次变更都必须可追溯到其来源。**

- Flash 输出字段：标记 source="flash"
- Pro 覆盖字段：标记 source="architect"
- reason 字段：始终存在于手动更改中
- 这实现了：调试、质量度量、Flash 模型评估

### 原则 10：下游优先设计

**为本体的消费者设计本体，而非为其自身的美观设计。**

- 主要消费者：bge 嵌入 → 向量检索
- 次要消费者：Qwen 8B → 重排序和新标签分类
- 设计决策应为检索 recall@k 优化，而非为图论的优美性优化
- 如果某个设计选择能提升 2% 检索效果但使图更丑陋，选择那 2%

---

## 产出 7 —— 未来工厂架构

### 系统蓝图

```
+===========================================================+
|                    本体工厂                                 |
+===========================================================+
|                                                           |
|  +-----------+    +-----------+    +-----------+          |
|  | 原始输入   |    |   领域    |    |   配置     |          |
|  | tags.csv  |    |  配置文件  |    |  参数      |          |
|  | tags.json |    |  .json    |    |  .yaml    |          |
|  +-----+-----+    +-----+-----+    +-----+-----+          |
|        |                |                |                 |
|        +----------------+----------------+                 |
|                         |                                  |
|                    +----v----+                             |
|                    |  工厂   |                             |
|                    |  引擎   |                             |
|                    +----+----+                             |
|                         |                                  |
|         +---------------+----------------+                 |
|         |               |                |                 |
|    +----v----+    +----v----+    +----v----+              |
|    |  FLASH  |    |   PRO   |    |  脚本   |              |
|    |  工人   |    |  审查   |    |  验证   |              |
|    +----+----+    +----+----+    +----+----+              |
|         |               |                |                 |
|         +---------------+----------------+                 |
|                         |                                  |
|                    +----v----+                             |
|                    |  导出   |                             |
|                    |  流水线 |                             |
|                    +----+----+                             |
|                         |                                  |
|         +---------------+----------------+                 |
|         |               |                |                 |
|    +----v----+    +----v----+    +----v----+              |
|    |ontology |    |retrieval|    |  alias  |              |
|    |_v1.json |    |_idx.json|    |graph.json|             |
|    +---------+    +---------+    +---------+              |
|                                                           |
+===========================================================+
```

### 领域配置文件（唯一的领域特定文件）

```json
{
  "domain": "adult_content",
  "language": "zh",
  "namespace_map": {
    "body_anatomy": { "category": "身体特征", "ontology_type": "graph_native" },
    "sex_act": { "category": "核心性行为", "ontology_type": "flat_behavior" },
    ...
  },
  "semantic_types": [
    "behavior", "body_anatomy", "body_shape", "body_size",
    "body_condition", "body_aesthetic", "role", "relationship",
    "emotion", "scene", "item", "fetish_type", "style", "intensity"
  ],
  "trusted_relations": ["specialization_of", "role_pair", "opposite_of", "context_of"],
  "max_depth": 3,
  "alias_merge_threshold": 0.90,
  "auto_accept_confidence": 0.85,
  "batch_size": 50
}
```

### 配置参数

```yaml
# factory_config.yaml
model:
  flash: "deepseek-v4-flash"
  pro: "deepseek-v4-pro"  # or human review mode

pipeline:
  batch_size: 50
  min_batch: 10
  max_retries: 3
  rate_limit_delay: 1  # seconds between API calls

quality:
  auto_accept_confidence: 0.85
  review_sample_rate: 0.10  # review 10% of auto-accepted items
  max_review_queue: 100     # escalate if review queue exceeds this

output:
  format: "json"
  indent: 2
  frozen: true  # immutable after export

retrieval:
  embedding_model: "bge-large-zh-v1.5"
  reranker: "qwen-8b"
  min_embedding_chars: 80
  max_embedding_chars: 300
```

### 执行流程

```python
# Pseudocode for the Factory Engine

class OntologyFactory:
    def __init__(self, domain_profile, config):
        self.domain = domain_profile
        self.config = config
        self.flash = FlashClient(config.model.flash)
        self.pro = ProClient(config.model.pro)  # or HumanReviewInterface
    
    def run(self, raw_tags_path):
        # S1: Triage
        inventory = self.triage(raw_tags_path)
        
        # S2: Normalization (parallel Flash calls)
        batches = self.split_batches(inventory, self.config.pipeline.batch_size)
        normalized = self.parallel_map(self.flash.normalize, batches)
        
        # S3: Namespace Architecture (Pro)
        namespace_map = self.pro.design_namespaces(normalized, self.domain)
        self.freeze(namespace_map, "namespaces")
        
        # S4: Canonical ID Freeze (Flash + Pro review)
        canonical = self.assign_canonical_ids(normalized, namespace_map)
        review_queue = self.pro.review(canonical)
        resolved = self.pro.resolve(review_queue)
        self.freeze(resolved, "canonical_ids")
        
        # S5: Alias Collapse
        alias_groups = self.flash.detect_aliases(resolved, self.domain)
        confirmed_aliases = self.pro.confirm_aliases(alias_groups)
        
        # S6: Validation
        self.validate(resolved, confirmed_aliases)
        
        # S7: Retrieval Export
        retrieval_index = self.build_retrieval_index(resolved)
        
        # S8: Freeze
        self.export_and_freeze(resolved, retrieval_index, confirmed_aliases)
        
        return OntologyRelease(
            ontology="ontology_export_v1.json",
            retrieval="retrieval_index.json",
            aliases="alias_graph.json",
            manifest="freeze_manifest.json"
        )
```

### 扩展特性

| 标签数量 | 批次 (Flash) | Pro 审查项 | 总成本 (估算) | 时间 (估算) |
|-----------|----------------|-----------------|-------------------|-------------|
| 100 | 2 | 5-10 | $0.10 | 2 分钟 |
| 1,000 | 20 | 50-100 | $1.00 | 30 分钟 |
| 10,000 | 200 | 500-1000 | $10.00 | 4 小时 |
| 100,000 | 2000 | 5000-10000 | $100.00 | 2 天 |

### 人机协同集成

```
+------------------+
|   工厂            |
|   (自动化)       |
+--------+---------+
         |
         | review_queue (JSON)
         v
+------------------+
|   审查界面        |  ← 人工审查被标记的条目
|   (Web 或 CLI)   |
+--------+---------+
         |
         | decisions (JSON)
         v
+------------------+
|   工厂            |
|   (继续执行)     |
+------------------+
```

审查界面展示：
- 标签名称 + 定义
- Flash 提议的 canonical_id + 置信度
- 被标记的原因
- 架构师操作：接受 / 覆盖 / 隔离

### 可移植性：适配新领域

1. **创建 `domain_profile.json`**：定义命名空间、semantic_types、trusted_relations
2. **准备原始清单**：标签至少包含 {name, definition} 或 {name, category}
3. **配置 factory_config.yaml**：设置语言、模型、batch_size
4. **运行**：`python factory.py --domain domain_profile.json --input tags.csv`
5. **审查**：检查 review_queue.json，做出架构决策
6. **冻结**：`python factory.py --freeze` 将本体标记为不可变

---

## 附录：项目产物参考

| 产物 | 文件 | 在框架中的角色 |
|----------|------|-------------------|
| 原始清单 | tag4.json (1178 标签) | S1 输入 |
| 规范化提示词 | stage1_flash_prompt.md | S2 Flash 模板 |
| 命名空间设计 | stage_d_canonical_ids.json | S3 架构 |
| 别名提示词 | stage_e_alias_prompt.md | S5 Flash 模板 |
| 架构修正 | stage3_review_resolve.py (23 处修正) | S4 Pro 审查 |
| 验证 | stage2_resolve.py | S6 自动检查 |
| 最终本体 | ontology_export_v1.json | S8 冻结输出 |
| 检索索引 | retrieval_index.json | S7 检索就绪 |
| 类别架构 | stage_c_category_architecture.json | 领域配置文件 |
| 处理规范 | 处理规范.md | 质量准则 |
| 重建计划 | tag体系重建规划.md | 多维模型 |
| 试点日志 | pilot/pilot_log.md | 经验教训 |
| 评估集 | pilot/eval_set.md | 测试用例 |

---

*框架提取于 2026-05-14，来自生产本体系统 v3（已冻结）。*
*专为 DeepSeek Pro + Flash 协作设计。目标：本地 Qwen 8B + bge 推理。*
