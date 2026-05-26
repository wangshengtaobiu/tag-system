# 测试数据 Test Data — v0.1-stable

## 目录结构 Directory Structure

```
tests/
├── data/
│   ├── acquisition/          # tag_acquisition 输入格式
│   │   ├── raw_30.json       # 原始 Pixiv 格式：[{"label": "腿控", "count": 42}]
│   │   ├── adversarial_30.json  # 边界用例：日语 tag、缩写、歧义词
│   │   ├── small_50.json     # 50 条真实 tag（分层采样）
│   │   └── medium_200.json   # 200 条真实 tag（分层采样）
│   └── ontology/             # ontology_factory 输入格式（已语义化）
│       └── smoke_20.json     # 快速冒烟测试：20 条已语义化 tag
└── README.md
```

## 测试文件 Test Files

| 文件 File | 条数 | 格式 Format | 用途 Purpose |
|-----------|------|-------------|--------------|
| `raw_30.json` | 30 | `{"label", "count"}` | 原始 Pixiv 小说 tag 输出 |
| `adversarial_30.json` | 30 | `{"label", "count"}` | 边界用例：日语、缩写、歧义词 |
| `small_50.json` | 50 | `{"标签名", "分类建议", ...}` | 真实数据分层采样 |
| `medium_200.json` | 200 | `{"标签名", "分类建议", ...}` | 更大规模真实数据 |
| `smoke_20.json` | 20 | `{"标签名", "分类建议", ...}` | 快速 pipeline 冒烟测试 |

## 使用方法 Usage

### tag_acquisition 测试

```bash
# 原始输入测试
python3 -c "import json; print(json.load(open('tests/data/acquisition/raw_30.json'))[:2])"

# 对抗测试
python3 tag_acquisition/run.py --input tests/data/acquisition/adversarial_30.json
```

### ontology_factory 测试

```bash
# 冒烟测试（快速，无需 API — 使用已语义化数据）
python3 ontology_factory/run_factory.py \
  --profile ontology_factory/profiles/adult_profile.json \
  --input tests/data/ontology/smoke_20.json \
  --stage s1 --end-stage s2

# 完整 pipeline（需 API key）
DEEPSEEK_API_KEY="sk-xxx" python3 ontology_factory/run_factory.py \
  --profile ontology_factory/profiles/adult_profile.json \
  --input tests/data/acquisition/raw_30.json \
  --stage s0 --end-stage s8
```

## 指标 Metrics

| 测试 Test | 输入 Input | 输出 Output | 数据丢失 Data Loss | 平均置信度 Mean Conf |
|-----------|------------|-------------|-------------------|---------------------|
| adversarial_30 (S0→S8) | 30 | 34 | 0 | 0.807 |
| small_50 (S1→S8) | 50 | 50 | 0 | 0.898 |
| medium_200 (S1→S8) | 200 | 202 | 0 | 0.893 |

## 备注 Notes

- `medium_200.json` (102KB) 及更大数据集未来可能移出仓库
- `tag.json` (1178 条, 645KB) 是完整生产数据集 — 已通过 `.gitignore` 排除
