# Ontology Factory 操作手册

> 本工程用于将原始标签目录转化为标准化的冻结本体。
> 适合从零开始的新手：按步骤走完一遍即可跑通，也能理解背后的原理。

---

## 一、系统概览

### 1.1 这是什么？

想象你有一堆杂乱的标签：

```
"足控"、"恋足"、"腿控"、"脚崇拜"、"足部恋物"
```

这些词说的可能是同一个概念，也可能不是。Ontology Factory 就是一个"标签身份证工厂"，把这些杂乱的标签整理成一份**标准化、机器可读的本体**：

```
fetish.foot_fetish  ── 主条目
  aliases: ["恋足", "脚崇拜"]        ← 同义词归一化
  namespace: fetish                  ← 归属明确的分类
  semantic_type: fetish_type         ← 语义类型
  definition: "对脚部的性偏好..."     ← 清晰定义
  distinction: "与腿控的区别..."       ← 与相似概念的差异

fetish.leg_fetish   ── 独立条目（不是别名）
```

### 1.2 完整流程

```
原始标签 JSON
       │
       ▼
┌─────────────────┐
│ S1 目录分拣      │  脚本自动：去重、清理空名、统一字段名
└───────┬─────────┘
        ▼
┌─────────────────┐
│ S2 语义标准化    │  调 DeepSeek Flash API：给每个标签分配
│                  │  canonical_id、命名空间、语义类型、置信度
└───────┬─────────┘
        ▼
┌─────────────────┐
│ S3 命名空间架构  │  校验命名空间分配是否合理
└───────┬─────────┘
        ▼
┌─────────────────┐
│ S4 ID 冻结      │  截断过深 ID、应用人工修正、检查重复
└───────┬─────────┘
        ▼
┌─────────────────┐
│ S5 别名折叠      │  合并同义词、构建别名图
└───────┬─────────┘
        ▼
┌─────────────────┐
│ S6 验证审计      │  9 项确定性检查（零 LLM，零幻觉）
└───────┬─────────┘
        ▼
┌─────────────────┐
│ S7 检索导出      │  生成向量检索就绪的索引
└───────┬─────────┘
        ▼
┌─────────────────┐
│ S8 生产冻结      │  打包版本化输出、生成冻结清单
└───────┬─────────┘
        ▼
  exports/ 目录 ← 最终产物
```

### 1.3 四层架构

| 层 | 角色 | 干什么 | 用什么 |
|----|------|--------|--------|
| **Architect（架构师）** | Pro 模型 / 人工 | 设计命名空间、仲裁歧义、质量签字 | DeepSeek Pro（或人工） |
| **Worker（工人）** | Flash 模型 | 批量标准化、重复检测、置信度评分 | DeepSeek Flash |
| **Validator（验证器）** | 脚本 | 9 项确定性检查：重复 ID、循环、深度、命名空间 | 纯 Python，零 LLM |
| **Retrieval（检索层）** | 脚本 | 生成分面索引、embedding_text | 纯 Python，零 LLM |

> 当前实现中，**只有 S2 调用 DeepSeek API**（Flash 模型）。S3~S8 已简化为脚本处理，不再额外调 API。完整架构设计中 S3/S4/S5/S8 有人工/Pro 审查回路，但当前版本通过 S2 的高置信度输出 + S6 验证来保证质量。

### 1.4 谁需要 AI？

| 阶段 | 需要 API？ | 用什么模型 |
|------|-----------|-----------|
| S1 分拣 | 否 | — |
| S2 标准化 | **是** | Flash（deepseek-v4-flash） |
| S3 命名空间 | 否 | 脚本校验（设计上是 Pro 审查） |
| S4 ID 冻结 | 否 | 脚本处理（设计上是 Flash+Pro） |
| S5 别名 | 否 | 脚本处理（设计上是 Flash+Pro） |
| S6 验证 | 否 | — |
| S7 导出 | 否 | — |
| S8 冻结 | 否 | 脚本打包（设计上是 Pro 签字） |

---

## 二、环境准备

### 2.1 检查 Python 版本

```bash
python3 --version
# 需要 3.10 或更高
```

### 2.2 安装依赖

```bash
cd ontology_factory
pip install requests pyyaml
```

就两个包，不需要 GPU、不需要 PyTorch。

### 2.3 配置 DeepSeek API Key

**方式一：直接写在配置文件中（最简单，适合个人使用）**

编辑 `config/factory_config.yaml`，找到 `api_key` 字段：

```yaml
models:
  pro:
    api_key: "sk-你的key"
  flash:
    api_key: "sk-你的key"
```

**方式二：环境变量（更安全，适合团队）**

```bash
export DEEPSEEK_API_KEY="sk-你的key"
```

API Key 申请地址：https://platform.deepseek.com

### 2.4 验证配置

```bash
python run_factory.py \
  --profile profiles/adult_profile.json \
  --input ../tag.json \
  --dry-run
```

看到 `Inputs validated. Exiting.` 就说明环境 OK。

---

## 三、第一次运行（跟着做）

### 3.1 准备数据

项目根目录下的 `tag.json` 包含 50 条中文成人标签，每条有：

```json
{
  "标签名": "挤奶",
  "分类建议": "玩法",
  "定义说明": "通过揉捏挤压乳房使乳汁喷射...",
  "上位tag": "变态",
  "区别": "与揉胸的区别：...",
  "文学示例词": "乳房挤奶, 挤奶高潮, 母乳喷射..."
}
```

### 3.2 运行完整流水线

```bash
cd ontology_factory
python run_factory.py \
  --profile profiles/adult_profile.json \
  --input ../tag.json
```

### 3.3 预期输出

```
ONTOLOGY FACTORY — Production System v1.0.0
============================================================

[LOAD] Profile: profiles/adult_profile.json
  Domain: adult_content_tags
  Namespaces: 25
  Semantic Types: 16

[LOAD] Input: ../tag.json
  Tags: 50

[PIPELINE] Stages: s1 → s8

[S1] GATE PASSED: All tags accounted for. 50 clean...

[S2] Processing 50 tags in 5 batches (size=10)
[S2] Batch 1/5 (10 tags)... OK (10 entries, 0 flagged)
...
[S2] GATE PASSED: 50 entries, mean_confidence=0.98, review_queue=0

[S3] GATE PASSED: 25 namespaces frozen...

[S4] GATE PASSED: 0 duplicate IDs...

[S5] GATE PASSED: 0 aliases...

[S6] All checks passed:
  ✓ duplicate_canonical_ids: ZERO duplicate IDs
  ✓ namespace_consistency: PASSED
  ...

[S7] GATE PASSED: 50 entries...

[S8] FREEZE COMPLETE: v1.0.0

PIPELINE SUMMARY
  ✓ [s1] passed
  ✓ [s2] passed
  ...
  ✓ [s8] passed
Final status: SUCCESS
```

### 3.4 查看结果

```bash
# 主产物（冻结本体）
ls -lh exports/ontology_export_v1_0_0.json

# 检索索引
ls -lh exports/retrieval_index.json

# 中间产物
ls work/
```

打开 `exports/ontology_export_v1_0_0.json` 可以看到每个标签的完整信息：

```json
{
  "canonical_id": "play.milking",
  "original_name": "挤奶",
  "namespace": "play",
  "ontology_type": "graph_native",
  "definition": "...",
  "aliases": [...],
  "confidence": 0.95,
  ...
}
```

---

## 四、理解输入格式

### 4.1 支持的字段名

S1（目录分拣）是唯一读取原始输入的地方。它接受**中英文 key 混用**：

| 标准化字段 | 可接受的原始 key | 必填 | 说明 |
|-----------|-----------------|------|------|
| `name` | `name` / `标签名` / `original_name` | **是** | 标签名 |
| `category` | `category` / `分类建议` / `分类` | 否 | 原始分类，影响 LLM 标准化质量 |
| `definition` | `definition` / `定义说明` / `描述` | 推荐 | 语义定义，60~200 字，大幅提升 LLM 准确度 |
| `distinction` | `distinction` / `区别` | 否 | 与相似标签的核心差异 |
| `parent_name` | `parent_name` / `上位tag` | 否 | 上位（父）标签名 |
| `examples` | `examples` / `示例词` / `文学示例词` / `示例` | 否 | 示例词（数组或逗号分隔字符串） |

### 4.2 JSON 格式

```json
[
  {
    "标签名": "口交",
    "分类建议": "核心性行为",
    "定义说明": "以口唇、舌部刺激对方生殖器的性行为方式",
    "上位tag": null,
    "文学示例词": "含入, 舐弄, 口内射精"
  }
]
```

### 4.3 哪些字段是必须的？

- **只有 `标签名`（或 `name`）是必须的。** 哪怕只给标签名，流水线也能跑。
- 但强烈建议提供 `定义说明` 和 `分类建议`，这会让 AI 标准化结果准确很多。

---

## 五、理解核心配置

### 5.1 运行时配置 `config/factory_config.yaml`

这是工厂的"控制面板"：

```yaml
models:
  flash:
    model: "deepseek-v4-flash"    # Flash 模型名
    api_key: "sk-xxx"             # API Key
    api_base: "https://api.deepseek.com/v1"

pipeline:
  stages:
    s2_normalize:
      batch_size: 10              # 每批送 AI 的标签数（50 太大容易失败，已调为 10）

confidence:
  auto_accept: 0.85               # ≥ 此值直接接受
  needs_review: 0.70              # 低于此值拒绝
```

**通常不需要改这个文件**，除非：
- 调整 `batch_size`（AI 返回空数组时调小）
- 修改 API Key

### 5.2 领域配置 `profiles/adult_profile.json`

这是工厂的"地图"，告诉 AI 有哪些命名空间、语义类型可用：

```json
{
  "domain": { "name": "adult_content_tags", "version": "1.0.0" },
  "namespace_map": {
    "play": {
      "label": "玩法",
      "description": "Play/scene types, BDSM activities",
      "categories": ["玩法", "SM倾向"]
    },
    "role": { "label": "角色身份", ... },
    "sex_act": { "label": "核心性行为", ... },
    ...  // 共 25 个命名空间
  },
  "semantic_types": [
    { "id": "behavior", "label": "性行为" },
    { "id": "character_role", "label": "角色身份" },
    ...  // 共 16 个
  ]
}
```

**换领域时，只需要替换这个文件。** 不需要改任何代码。

---

## 六、Domain Profile 编写指南（换领域必读）

### 6.1 语义轴：标签的"维度"

**语义轴是标签沿其变化的独立维度。** 同一轴上的两个标签互斥或可比较，不同轴上的标签可以共存。

例如"动漫角色"领域：

```
Axis 1: personality_type → tsundere, yandere, kuudere
Axis 2: relationship_role → childhood_friend, senpai, kouhai
Axis 3: narrative_function → protagonist, antagonist, love_interest

一个角色可以同时是 tsundere（轴1）+ childhood_friend（轴2）+ protagonist（轴3）。
```

**需要多少个轴？**
- <100 标签：2-4 个轴
- 100-1K 标签：3-8 个轴
- 1K+ 标签：5-15 个轴

### 6.2 命名空间：canonical ID 的前缀

每个语义轴（或一组相关轴）对应一个命名空间。

**设计原则：**
- **覆盖性**：每个标签必须恰好归入一个命名空间
- **无重叠**：两个命名空间不应描述相同语义域
- **大小平衡**：目标每个命名空间 10-200 个标签
- **稳定性**：命名空间一旦冻结就不能改，选能长期用的名称
- **格式**：小写 snake_case 英文，如 `character_trait`、`relationship_role`

### 6.3 本体类型：标签的"结构复杂度"

| 类型 | 何时用 | 示例 |
|------|--------|------|
| `flat_behavior` | 简单属性，非是即否 | `tsundere` — 是或不是 |
| `specialized_behavior` | 有子类型和强度变化 | `character_archetype` 有子原型 |
| `graph_native` | 标签之间有互相蕴含的关系 | `relationship_dynamic` — 三角恋涉及多个角色 |
| `meta_style` | 描述作品本身而非内容 | `content_rating`、`target_audience` |

### 6.4 完整示例：动漫角色领域

```json
{
  "domain": {
    "name": "anime_character_tropes",
    "version": "1.0.0",
    "language": "en",
    "description": "Anime character archetypes and roles"
  },
  "namespace_map": {
    "character_trait": {
      "label": "性格特征",
      "description": "Personality traits and behavioral archetypes",
      "axes": ["personality_type", "behavioral_trait"],
      "categories": ["性格"],
      "max_depth": 3,
      "ontology_type_hint": "flat_behavior"
    },
    "character_role": {
      "label": "角色身份",
      "description": "Social and relationship roles",
      "axes": ["relationship_role", "social_role"],
      "categories": ["身份"],
      "max_depth": 3,
      "ontology_type_hint": "graph_native"
    }
  },
  "semantic_types": [
    { "id": "personality_trait", "label": "Personality", "description": "Character personality descriptors" },
    { "id": "relationship_role", "label": "Relationship", "description": "Inter-character relationship roles" }
  ],
  "alias_policy": {
    "merge_threshold": 0.90,
    "conservative_merges": true,
    "max_aliases_per_entry": 10,
    "forbidden_merges": []
  },
  "confidence_thresholds": {
    "auto_accept": 0.85,
    "needs_review": 0.70
  },
  "relation_policy": {
    "trusted_types": ["specialization_of", "role_pair", "opposite_of", "context_of"]
  },
  "id_convention": {
    "format": "namespace.descriptor[.detail]",
    "max_depth": 3,
    "language": "en",
    "case": "snake_case"
  }
}
```

写好 profile 后，用它替换 `profiles/adult_profile.json`（或创建新的 profile 文件用 `--profile` 指定），流水线就能自动适配新领域。

---

## 七、运行命令详解

### 7.1 全部参数

| 参数 | 简写 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--profile` | `-p` | **是** | — | 领域配置 JSON |
| `--input` | `-i` | **是** | — | 原始标签文件（JSON） |
| `--config` | `-c` | 否 | `config/factory_config.yaml` | 工厂配置 |
| `--stage` | `-s` | 否 | `s1` | 起始阶段 (s1~s8) |
| `--end-stage` | `-e` | 否 | `s8` | 结束阶段 (s1~s8) |
| `--work-dir` | `-w` | 否 | `ontology_factory/work` | 中间产物目录 |
| `--exports-dir` | — | 否 | `ontology_factory/exports` | 最终输出目录 |
| `--skip-flash` | — | 否 | — | 跳过 AI 阶段（仅运行脚本） |
| `--dry-run` | — | 否 | — | 只校验输入，不执行 |

### 7.2 常用场景

```bash
# 完整流水线
python run_factory.py -p profiles/adult_profile.json -i ../tag.json

# 只校验输入格式，不跑流水线
python run_factory.py -p profiles/adult_profile.json -i ../tag.json --dry-run

# 跳过 AI，只跑脚本阶段（适合调试或没有 API Key 时）
python run_factory.py -p profiles/adult_profile.json -i ../tag.json --skip-flash

# 从 S4 开始（上次 S3 出错后重试）
python run_factory.py -p profiles/adult_profile.json -i ../tag.json --stage s4

# 只跑到 S6 验证，不冻结
python run_factory.py -p profiles/adult_profile.json -i ../tag.json --end-stage s6
```

### 7.3 断点续传

如果流水线在 S4 出错，可以从中断处继续：

```bash
python run_factory.py -p profiles/adult_profile.json -i ../tag.json --stage s4
```

前提是 `work/` 目录下的中间产物没有被删除。

---

## 八、结果解读

### 8.1 最终产物 `exports/`

| 文件 | 用途 | 谁用 |
|------|------|------|
| `ontology_export_v1_0_0.json` | 冻结的标准化本体。每个标签的 canonical_id、命名空间、定义、别名、层级关系、置信度。 | 本体维护者、数据消费者 |
| `retrieval_index.json` | 检索索引。把每个标签转成适合向量检索的 embedding_text，并建好分面索引。 | 下游打标系统 |

**给小说打 tag 应该用哪个？**

两个都要用：
1. **检索**：用 `retrieval_index.json` 里的 `embedding_text` 做向量检索，从小说文本中匹配候选 tag
2. **归一化**：用 `ontology_export_v1_0_0.json` 中的别名映射把同义词归一到同一个 canonical_id

### 8.2 中间产物 `work/`

| 文件 | 阶段 | 说明 |
|------|------|------|
| `inventory_clean.json` | S1 | 去重清理后的标签 |
| `stage2_normalized.json` | S2 | AI 标准化结果 + 置信度 |
| `namespace_freeze.json` | S3 | 命名空间冻结 |
| `stage4_resolved.json` | S4 | ID 冻结后（零重复） |
| `validation_report.json` | S6 | 9 项验证检查报告 |
| `retrieval_index.json` | S7 | 检索索引（中间版本） |
| `ontology_versions/` | S8 | 版本化归档 |

### 8.3 如何检查质量

```bash
# 查看本体条目数
python3 -c "
import json
d = json.load(open('exports/ontology_export_v1_0_0.json'))
print(f'总条目: {d[\"meta\"][\"total_entries\"]}')
print(f'主条目: {d[\"meta\"][\"primary_entries\"]}')
print(f'平均置信度: {d[\"quality\"][\"mean_confidence\"]}')
"

# 检查是否有重复 canonical ID（必须为 0）
python3 -c "
import json
from collections import Counter
d = json.load(open('exports/ontology_export_v1_0_0.json'))
cids = Counter(e['canonical_id'] for e in d['entries'] if not e.get('is_alias_of'))
dupes = {k:v for k,v in cids.items() if v>1}
print('重复ID:', len(dupes), list(dupes.keys())[:5] if dupes else '✓ 无')
"
```

---

## 九、常见问题

| 问题 | 解决 |
|------|------|
| **API 返回 401** | 检查 API Key 是否正确 |
| **ConnectionError** | 检查网络，确认能访问 `api.deepseek.com` |
| **S2 返回空数组（0 entries）** | batch_size 太大了。把 `config/factory_config.yaml` 中 `s2_normalize.batch_size` 调小（10~20） |
| **JSON 解析失败** | 会自动重试 3 次并降级 batch_size。如果仍失败，检查 `max_tokens` 是否够用（S2 已设为 8192） |
| **编码乱码** | JSON 文件确保 UTF-8 编码 |
| **PyYAML 未安装警告** | `pip install pyyaml`，或忽略（会自动回退 JSON 解析） |
| **重复 canonical ID 不为 0** | 重新跑 S4，检查是否有 architect_fixes.json 需要加载 |

---

## 十、后续扩展

### 10.1 怎么加新标签？

1. 把新标签追加到原始 JSON 文件中
2. 重新运行完整流水线
3. 新标签会自动获得新的 canonical_id，不会影响已有条目

### 10.2 冻结后能改什么、不能改什么？

**允许的日常操作（不需要新版本号）：**
- 修正定义中的错别字
- 更新示例列表
- 为已有条目添加新别名
- 添加新标签（用新的 canonical_id）
- 弃用条目（标记 `deprecated=true`，保留 ID）

**需要新版本的操作（2.0.0）：**
- 更改已有 canonical_id
- 删除条目
- 更改命名空间
- 合并两个主条目
- 添加新命名空间

**永久禁止：**
- 不升版本号就改 canonical_id
- 未经弃用期就删除条目
- 把已弃用的 canonical_id 用于新概念

### 10.3 怎么更新本体版本？

每次运行流水线，S8 会在 `work/ontology_versions/` 下创建新版本目录：

```
work/ontology_versions/
├── v1_0_0/          # 第一次运行
│   ├── freeze_manifest.json
│   ├── ontology_export_v1_0_0.json
│   └── ...
└── latest/          # 始终指向最新版本
```

修改 `profiles/adult_profile.json` 中的 `domain.version` 字段即可指定新版本号。

---

*Ontology Factory 操作手册 v1.0.0*
*适用：任何领域。要求：领域专业知识 + DeepSeek API 访问。*
