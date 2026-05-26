# Ontology Factory

Turns clean tags into a frozen, versioned ontology with canonical IDs, namespaces, validation, and retrieval export.

## Pipeline

```
S0 enrich (LLM) → S1 triage (script) → S2 normalize (LLM) → S3 namespace (script)
→ S4 freeze ID (script) → S5 alias (script) → S6 validate (script)
→ S7 retrieval (script) → S8 freeze (script)
```

## Stages

| Stage | Name | Owner | Description |
|-------|------|-------|-------------|
| S0 | Tag Enrichment | Flash LLM | Reads acquisition output, generates semantic fields (category, definition, parent tag, distinction, examples). Writes Chinese keys for S1 compatibility. |
| S1 | Inventory Triage | Script | Deduplication, empty name removal, language detection, field normalization. |
| S2 | Semantic Normalization | Flash LLM | Assigns canonical_id, namespace, aliases, semantic type, confidence. Conservative mode: no translation, no expansion. |
| S3 | Namespace Architecture | Script | Validates namespace assignments against domain profile. Freezes active namespaces. |
| S4 | Canonical ID Freeze | Script | Applies architect fixes, truncates deep IDs, auto-deduplicates by confidence. |
| S5 | Alias Collapse | Script | Builds alias graph, resolves parent references, rejects unsafe merges. |
| S6 | Validation & Audit | Script | 7 deterministic checks: duplicate IDs, namespace consistency, alias integrity, parent cycles, max depth, relation whitelist, orphan tags. |
| S7 | Retrieval Export | Script | Generates embedding_text, retrieval_aliases, facet indices (by namespace/category/type). |
| S8 | Production Freeze | Script | Versioned ontology export, freeze manifest, migration map, deprecated IDs list. |

**API calls**: Only S0 and S2 call the LLM API. S1, S3–S8 are deterministic scripts.

## S0 Contract

S0 bridges the gap between `tag_acquisition` output and the ontology pipeline:

- **Input**: `[{"label": "腿控", "count": 42}, ...]`
- **Output**: `[{"标签名": "腿控", "分类建议": "恋物偏好", "定义说明": "...", "上位tag": "...", "区别": "...", "文学示例词": "..."}, ...]`
- S1 reads these Chinese keys directly — no additional normalization layer needed.

S1–S8 are not modified by S0. They operate on the enriched data as-is.

## Quick Start

```bash
# Full pipeline (requires API key)
export DEEPSEEK_API_KEY=YOUR_KEY
python3 run_factory.py \
  --profile profiles/adult_profile.json \
  --input ../tests/data/acquisition/raw_30.json \
  --stage s0 --end-stage s8

# Skip S0 (use pre-enriched data)
python3 run_factory.py \
  --profile profiles/adult_profile.json \
  --input ../tests/data/ontology/smoke_20.json \
  --stage s1 --end-stage s8

# Dry run (validate inputs only)
python3 run_factory.py \
  --profile profiles/adult_profile.json \
  --input ../tests/data/acquisition/raw_30.json \
  --stage s0 --end-stage s0 --dry-run
```

## Outputs

After a successful run:

| File | Location | Description |
|------|----------|-------------|
| `ontology_export_v1_0_0.json` | `exports/` | Frozen ontology — canonical IDs, namespaces, definitions, aliases, confidence |
| `retrieval_index.json` | `exports/` | Retrieval-ready entries with embedding_text and facet indices |
| `validation_report.json` | `work/` | S6 check results (pass/fail per check, warnings) |
| `freeze_manifest.json` | `work/ontology_versions/v1_0_0/` | Version metadata, checksums, immutability rules |

### Ontology Export Format

Each entry in `ontology_export_v1_0_0.json`:

```json
{
  "canonical_id": "fetish.foot_fetish",
  "original_name": "腿控",
  "aliases": ["恋足"],
  "namespace": "fetish",
  "ontology_type": "flat_behavior",
  "semantic_type": "preference",
  "category": "恋物偏好",
  "definition": "对女性腿部线条与触感的性偏好...",
  "distinction": "与足控的区别：足控聚焦脚部,腿控关注腿部整体。",
  "parent_canonical_id": null,
  "trusted_relations": [],
  "embedding_text": "",
  "examples": ["丝滑腿部", "修长玉腿"],
  "is_alias_of": null,
  "confidence": 0.95,
  "needs_review": false,
  "v3_validated": true
}
```

### Retrieval Index Format

Each entry in `retrieval_index.json`:

```json
{
  "canonical_id": "fetish.foot_fetish",
  "original_name": "腿控",
  "namespace": "fetish",
  "embedding_text": "腿控 | 恋足 | 对女性腿部线条与触感的性偏好...",
  "semantic_summary": "对女性腿部（大腿、小腿）线条与触感的性偏好",
  "retrieval_aliases": ["腿控", "恋足"],
  "category": "恋物偏好",
  "confidence": 0.95,
  "v3_validated": true
}
```

## Review Queue

Low-confidence entries are flagged for manual review:

- **Pending**: Awaiting human review
- **Reviewed**: Human has examined, decision recorded
- **Rejected**: Entry flagged as invalid, requires re-normalization

Review items are saved to `work/stage{N}_review_queue.json`. Each item includes the entry, reason for flagging, and suggested action.

## Configuration

| File | Purpose |
|------|---------|
| `config/factory_config.yaml` | Pipeline config (batch sizes, timeouts, confidence thresholds, model routing) |
| `profiles/adult_profile.json` | Domain profile (namespace map, semantic types, categories) |

To use a different domain, create a new profile and pass `--profile profiles/your_domain.json`.

## Directory Structure

```
ontology_factory/
├── run_factory.py              # Pipeline entry point
├── stages/                     # S0–S8 implementations
├── config/factory_config.yaml  # Pipeline configuration
├── profiles/                   # Domain profiles
├── validators/                 # Deterministic validation engine
├── review_queue/               # Manual review interface
├── exports/                    # Final outputs (gitignored)
├── work/                       # Intermediate outputs (gitignored)
├── metrics/                    # Observation data (gitignored)
└── docs/
    ├── 操作手册.md              # Operations manual (Chinese)
    └── ontology_factory_design.md  # Design document
```
