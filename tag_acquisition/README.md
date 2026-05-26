# tag_acquisition

从外部源采集原始 tag，进行 surface form 归一化、复合 tag 拆分、噪声过滤，导出干净的语料库。

## English Summary

Collects raw tags from external sources, normalizes surface forms, splits compound tags, filters noise, and exports a clean corpus. No semantic enrichment or ontology construction happens here — that's handled by ontology_factory downstream.

---

## Pipeline 流水线

```
Raw tags (来自 API 或文件)
    ↓
normalize    — surface 清理，全角 → 半角，空白整理
    ↓
split        — 保护短语拆分（"足控・M属性" → 2 条）
    ↓
filter       — 质量过滤（长度、噪声模式、黑名单）
    ↓
lang_detect  — 语言标记（zh / jp / en / mixed）
    ↓
dedup        — surface 级去重
    ↓
snapshot     — 追加式语料导出
```

### normalize

清理 surface form：去除首尾空白、全角字符归一化为半角、合并多余空格。不做语义变更。

### split

使用 delimiter policy 拆分复合 tag。保护短语（如 "NTR・寝取られ"）按配置保留或拆分。如果拆分后无有效条目，回滚到原始 tag。

### filter

移除匹配噪声模式的条目：
- 过短（< 2 字符）
- 过长（> 30 字符）
- 匹配黑名单
- 未通过质量启发式检查（如纯数字、随机字符）

### lang_detect

为每条标记检测到的语言：`zh`、`jp`、`en` 或 `mixed`。使用 Unicode 范围分析，不依赖外部库。

### dedup

基于归一化 label 的 surface 级去重。保留首次出现，记录重复项。

### snapshot

以追加式快照导出干净语料：
- `corpus_v1_YYYYMMDD.jsonl` — 每行一条
- 元数据：总条目数、语言分布、过滤统计

---

## Schema 数据结构

输出语料中每条条目：

```json
{
  "label": "腿控",
  "count": 42
}
```

| 字段 Field | 类型 Type | 说明 Description |
|------------|-----------|------------------|
| `label` | string | 归一化后的 surface form |
| `count` | int | 频次 / 热度评分（无则为 0） |

---

## Configuration 配置

`config.yaml`:

```yaml
protected_phrases:
  - "NTR・寝取られ"
  - "SM・BDSM"

delimiter_policy:
  chars: ["・", " ", "/", "|"]
  min_split_length: 2

blacklist:
  - "unknown"
  - "misc"

quality:
  min_length: 2
  max_length: 30
  noise_patterns:
    - "^\\d+$"
    - "^[a-zA-Z]{1,2}$"
```

| 配置 Key | 说明 |
|----------|------|
| `protected_phrases` | 即使包含分隔符也不应拆分的短语 |
| `delimiter_policy.chars` | 用于拆分复合 tag 的分隔符 |
| `delimiter_policy.min_split_length` | 拆分后每部分的最小有效长度 |
| `blacklist` | 要完全排除的 label |
| `quality.min_length` | label 最小长度（字符） |
| `quality.max_length` | label 最大长度（字符） |
| `quality.noise_patterns` | 噪声检测的正则表达式 |

---

## Snapshot 快照机制

语料快照是追加式的：

```
data/
├── corpus_v1_20260520.jsonl   # 快照 1
├── corpus_v1_20260525.jsonl   # 快照 2（含新条目）
└── corpus_v1_latest.jsonl     # 符号链接 → 最新快照
```

**从原始缓存重建：** 快照从原始 tag 缓存派生。如果快照损坏，从原始缓存重新运行 pipeline 即可——不会丢失数据。

---

## 快速开始 Quick Start

```bash
# 处理原始 tag
python3 -m tag_acquisition.run --input tests/data/acquisition/raw_30.json

# 使用自定义配置
python3 -m tag_acquisition.run --input raw_tags.json --config config.yaml
```

输出：`work/corpus_v1_YYYYMMDD.jsonl`
