# Test Layout Plan — v0.1-stable

## Current State

Test data files are scattered across two directories:

| File | Size | Location | Purpose |
|------|------|----------|---------|
| `tag_acquisition/test_raw_30.json` | 1KB | tag_acquisition/ | Raw Pixiv output (label+count) |
| `tag_acquisition/test_adversarial_30.json` | 1KB | tag_acquisition/ | Adversarial test set |
| `tag_acquisition/test_real_50.json` | 25KB | tag_acquisition/ | 50 real tags (stratified) |
| `tag_acquisition/test_real_200.json` | 104KB | tag_acquisition/ | 200 real tags (stratified) |
| `ontology_factory/test_adversarial_30.json` | 1KB | ontology_factory/ | **DUPLICATE** of above |
| `ontology_factory/test_input_20.json` | 719B | ontology_factory/ | Quick smoke test |
| `ontology_factory/tag.json` | 645KB | ontology_factory/ | Full dataset (1178 tags, gitignored) |

## Proposed Layout

```
tag-system/
├── tests/
│   ├── data/
│   │   ├── acquisition/
│   │   │   ├── raw_30.json              # Raw Pixiv format (label+count)
│   │   │   └── adversarial_30.json      # Adversarial test set
│   │   └── ontology/
│   │       ├── smoke_20.json             # Quick smoke test (enriched format)
│   │       ├── small_50.json             # 50 real tags
│   │       └── adversarial_30.json       # Adversarial test set
│   └── README.md                         # Test data description
```

## Rules

1. **Keep in repo** (all ≤ 104KB, acceptable):
   - `raw_30.json` — raw format example
   - `adversarial_30.json` — edge case coverage
   - `smoke_20.json` — quick verification
   - `small_50.json` — medium test

2. **Move outside repo** (pending decision):
   - `test_real_200.json` (104KB) — borderline, keep for now
   - `tag.json` (645KB, 1178 tags) — **gitignored, not in repo**

3. **Remove**:
   - `ontology_factory/test_adversarial_30.json` — duplicate of `tag_acquisition/` copy

4. **Rename for clarity**:
   - `test_raw_30.json` → `raw_30.json`
   - `test_input_20.json` → `smoke_20.json`
   - `test_real_50.json` → `small_50.json`
   - `test_real_200.json` → `medium_200.json`

## Migration Steps

1. Create `tests/data/acquisition/` and `tests/data/ontology/`
2. Copy files from `tag_acquisition/` to `tests/data/acquisition/`
3. Copy files from `ontology_factory/` to `tests/data/ontology/`
4. Remove `ontology_factory/test_adversarial_30.json` (duplicate)
5. Remove originals from source dirs (keep only in `tests/data/`)
6. Create `tests/README.md` describing each file

## Impact

- **Zero impact on S1-S8 pipeline** — test data is not imported by code
- Pipeline uses `--input <path>` CLI argument, can point to `tests/data/` or anywhere
- No code changes required
