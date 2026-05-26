# Test Data — v0.1-stable

## Directory Structure

```
tests/
├── data/
│   ├── acquisition/          # tag_acquisition input formats
│   │   ├── raw_30.json       # Raw Pixiv format: [{"label": "腿控", "count": 42}]
│   │   ├── adversarial_30.json  # Edge cases: JP tags, abbreviations, ambiguous
│   │   ├── small_50.json     # 50 real tags (stratified sample)
│   │   └── medium_200.json   # 200 real tags (stratified sample)
│   └── ontology/             # ontology_factory input formats (enriched)
│       └── smoke_20.json     # Quick smoke test: 20 enriched tags
└── README.md
```

## Test Files

| File | Tags | Format | Purpose |
|------|------|--------|---------|
| `raw_30.json` | 30 | `{"label", "count"}` | Raw Pixiv novel tag output |
| `adversarial_30.json` | 30 | `{"label", "count"}` | Edge cases: Japanese, abbreviations, ambiguous terms |
| `small_50.json` | 50 | `{"标签名", "分类建议", ...}` | Real data stratified sample |
| `medium_200.json` | 200 | `{"标签名", "分类建议", ...}` | Larger real data sample |
| `smoke_20.json` | 20 | `{"标签名", "分类建议", ...}` | Quick pipeline smoke test |

## Usage

### tag_acquisition tests

```bash
# Raw input test
python3 -c "import json; print(json.load(open('tests/data/acquisition/raw_30.json'))[:2])"

# Adversarial test
python3 tag_acquisition/run.py --input tests/data/acquisition/adversarial_30.json
```

### ontology_factory tests

```bash
# Smoke test (fast, no API needed — uses pre-enriched data)
python3 ontology_factory/run_factory.py \
  --profile ontology_factory/profiles/adult_profile.json \
  --input tests/data/ontology/smoke_20.json \
  --stage s1 --end-stage s2

# Full pipeline (requires API key)
DEEPSEEK_API_KEY="sk-xxx" python3 ontology_factory/run_factory.py \
  --profile ontology_factory/profiles/adult_profile.json \
  --input tests/data/acquisition/raw_30.json \
  --stage s0 --end-stage s8
```

## Metrics

| Test | Input | Output | Data Loss | Mean Conf |
|------|-------|--------|-----------|-----------|
| adversarial_30 (S0→S8) | 30 | 34 | 0 | 0.807 |
| small_50 (S1→S8) | 50 | 50 | 0 | 0.898 |
| medium_200 (S1→S8) | 200 | 202 | 0 | 0.893 |

## Notes

- `medium_200.json` (102KB) and larger datasets may be moved outside repo in future releases
- `tag.json` (1178 tags, 645KB) is the full production dataset — excluded from repo via `.gitignore`
