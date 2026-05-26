# tag-system 架构优化设计文档

**日期**: 2026-05-24
**范围**: 全链路验证 + 架构优化（tag_acquisition + ontology_factory + tagger）
**方案**: 方案 A（渐进式修复）

---

## 现状分析

### tag_acquisition
- **状态**: 代码存在，规则已更新（汉字≥2），**未验证能否实际运行**
- **文件**: `collector.py`, `run.py`, `schema.py`, `config.yaml`, `analyze_noise.py`
- **已知问题**（基于实际读取代码）:
  - `config.yaml` 中 `min_tag_length: 2` 残留，代码已移除该参数
  - `analyze_noise.py` 硬编码代理地址，不使用 config.yaml
  - `CleanedTagEntry.to_dict()` 输出中文键名，ontology_factory 不读此格式
  - `--resume` 只检查输出文件，不检查采集中断状态
  - Pixiv API URL 未验证可用性

### ontology_factory
- **状态**: v1.0.0 已冻结（1145 本体 + 33 别名，25 命名空间），**已验证可运行**
- **已知问题**（基于代码审计报告）:
  - 配置分散在 3 个文件（factory_config.yaml, adult_profile.json, domain_profile.schema.json）
  - 8 阶段流水线可精简为 5 阶段
  - STAGE_REGISTRY 死代码
  - ReviewItem 数据类从未实例化
  - review_queue 未集成到流水线
  - 字段名不一致（name/original_name, is_alias_of/is_duplicate_of）
  - 无 circuit breaker，API 失败时浪费时间重试

### tagger
- **状态**: 未创建
- **计划**: BGE embedding + FAISS 检索 + Qwen 8B 重排

---

## Section 1: 配置统一（ontology_factory）

### 问题
配置分散在 3 个文件，相同设置重复定义，代码从不同地方读不同配置。

### 方案
合并为单一 `ontology_factory/config.yaml`：

```yaml
# ===== 领域配置 =====
namespaces:
  play: { description: "玩法/行为", categories: ["玩法", "行为"] }
  # ... 25 个 namespace

semantic_types:
  - behavior
  - mental_state
  # ... 16 种

forbidden_merges:
  - [足控, 腿控]
  - [男同, 男男]
  # ...

# ===== 运行时配置 =====
pipeline:
  stages: [s1, s2, s3, s4, s5]
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

### 删除文件
- `config/factory_config.yaml`
- `profiles/adult_profile.json`
- `profiles/domain_profile.schema.json`

### 依据
- 实际读取了 3 个配置文件，确认存在重复定义
- 用户明确偏好单一配置文件

---

## Section 2: 流水线精简（ontology_factory）

### 问题
8 阶段流水线存在冗余：
- S3（namespace 验证）只是校验+复制 profile 内容（基于审计报告，已验证代码）
- S4/S5 各自独立调 LLM，可合并
- STAGE_REGISTRY 是死代码（已验证 `run_factory.py` 硬编码阶段）

### 优化后 5 阶段

| 阶段 | 所有者 | 做什么 | 输出 |
|------|--------|--------|------|
| **S1 Inventory+Namespace** | 脚本 | 字段统一、去重、去空、namespace 验证 | `inventory_clean.json` |
| **S2 Semantic Normalize** | LLM | 分类 + ID 生成 + 别名候选 + 关系候选 + 定义（一次 LLM 调用） | `stage2_normalized.json` |
| **S3 Validate** | 脚本 | 9 项校验（精简：移除 vacuous orphan check） | `validation_report.json` |
| **S4 Retrieval** | 脚本 | 生成 embedding_text、semantic_summary、面索引 | `retrieval_index.json` |
| **S5 Freeze** | 脚本 | 版本冻结、manifest、migration_map | `exports/` |

### 清理死代码
- 删除 `STAGE_REGISTRY` 和 `@register_stage` 装饰器
- 删除 `ReviewItem` 数据类（实际用 dict）
- 统一字段名：`name`（不用 original_name）、`is_alias_of`（不用 is_duplicate_of）、`relation_candidates`（不用 trusted_relations）

### 依据
- 审计报告已验证具体问题及文件行号
- S3 代码确实只做验证+复制（`s3_namespace.py`）

---

## Section 3: tag_acquisition 验证与修复

### 待验证项
1. **Pixiv API 可用性** — 实际运行一次采集，确认 API 返回正常
2. **规则有效性** — 用 `analyze_noise.py` 采集原始数据，验证去噪规则覆盖率

### 待修复项
1. 删除 `config.yaml` 中 `min_tag_length: 2` 残留
2. `analyze_noise.py` 改用 config.yaml 的代理配置（通过 `_load_yaml_simple` 加载）
3. `CleanedTagEntry` 及 `to_dict()` — 确认 ontology_factory 是否真的需要此格式，如不需要则删除
4. `--resume` 逻辑增强：检查输出文件是否完整（有数据且非空）

### 依据
- 实际读取了全部 5 个文件
- `config.yaml` 第 32 行确认存在 `min_tag_length: 2`
- `collector.py` 第 134 行确认已移除 `self.min_tag_length`
- `analyze_noise.py` 第 26 行确认硬编码代理地址

---

## Section 4: review_queue 集成

### 问题
- `review_queue/schema.py` 有 ReviewQueueManager，流水线未使用
- `review_queue/reviewer.py` 是独立 CLI，未集成到流水线
- S2 产生 review 条目，S5 读 review 条目，S6/S8 不检查未解决条目

### 方案
1. S2 产生的低置信度条目（confidence < threshold_needs_review）进入 review_queue
2. S2 完成后、S3 之前插入 review 步骤：
   - 如有未解决条目，流水线暂停，调用 reviewer CLI
   - 用户审查通过后继续
3. S5（Validate）增加检查：review_queue 中无未解决条目
4. 统一用 dict 表示 review 条目（与现有代码一致）

### 依据
- 审计报告确认 review_queue 未集成
- `s5_alias.py` 第 116-129 行确认使用 dict 而非 ReviewItem

---

## Section 5: tagger 模块（新增）

### 目标
利用冻结本体对本地模型生成内容进行自动打标。

### 技术栈
| 组件 | 方案 |
|------|------|
| 文本编码 | BGE-large-zh-v1.5 |
| 向量检索 | FAISS（扁平索引或 IVF） |
| 重排序 | Qwen-8B |
| 推理环境 | 本地 GPU |

### 流程
```
输入文本 → 分段 → BGE 编码 → FAISS Top-K → Qwen 8B 重排 → 输出标签+置信度
```

### 输出格式
```json
{
  "text_segment": "...",
  "tags": [
    {"canonical_id": "play.bondage", "confidence": 0.92, "aliases_matched": ["捆绑"]},
    {"canonical_id": "mental.humiliation", "confidence": 0.78}
  ]
}
```

### 依赖
- ontology_factory 输出的冻结本体（`ontology_export_v1_0_0.json`）
- 检索索引（`retrieval_index.json`）

---

## Section 6: 错误处理增强

### 问题
- 无 circuit breaker，API 失败时遍历所有批次重试
- 无结构化日志，全部用 print()
- 无 idempotency，多次运行结果不一致

### 方案
1. **Circuit Breaker**: API 连续 N 次失败后跳过剩余批次，输出警告
2. **结构化日志**: 关键阶段输出到 `work/pipeline.log`
3. **幂等性**: `item_id` 生成不用 `time.time()`，改用确定性 hash

### 依据
- 审计报告确认上述问题
