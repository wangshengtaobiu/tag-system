# tag-system

A pipeline system for acquiring, enriching, and freezing domain-specific content tags into a structured ontology.

This project focuses on adult content tags (e.g., from Pixiv novels), but the pipeline is domain-agnostic — any tag corpus can be processed by swapping the domain profile.

**What this repo includes:**
- Source code for tag acquisition and ontology pipeline
- Domain profile configuration (adult_content_tags)
- Small test datasets (30–200 tags)

**What this repo does NOT include:**
- Production datasets
- Model weights or local AI models
- API credentials
- Pre-computed embeddings or indexes

---

## Architecture

```
Pixiv / API
    ↓
tag_acquisition (normalize, split, filter, dedup)
    ↓
Surface Corpus (raw tags → clean tags)
    ↓
ontology_factory S0 (LLM enrichment)
    ↓
ontology_factory S1–S8 (ontology pipeline)
    ↓
Frozen Ontology + Retrieval Export
```

Data flows in one direction. No stage mutates upstream data. Each stage reads from the previous stage's output and writes to its own file.

---

## Modules

### tag_acquisition

Collects raw tags from external sources, normalizes surface forms, splits compound tags, filters noise, and exports a clean corpus.

**Responsibilities:**
- Surface normalization (full-width → half-width, whitespace cleanup)
- Protected phrase splitting (e.g., "足控・M属性" → two entries)
- Delimiter policy enforcement
- Language detection
- Quality filtering (length, frequency, noise patterns)
- Deduplication
- Append-only corpus snapshots

**Does NOT:** semantic enrichment, ontology construction, translation, alias merging.

### ontology_factory

Takes clean tags and runs them through a 9-stage pipeline (S0–S8) to produce a frozen, versioned ontology with canonical IDs, namespaces, validation, and retrieval export.

**Responsibilities:**
- S0: LLM-based semantic enrichment (category, definition, parent tag)
- S1–S8: Ontology pipeline (triage, normalization, namespace assignment, ID freeze, alias resolution, validation, retrieval export, production freeze)
- Review queue for low-confidence entries
- Versioned ontology exports with freeze manifests

**Does NOT:** raw web crawling, source data mutation, external API calls (except S0/S2 LLM enrichment).

---

## Quick Start

### Requirements

- Python 3.10+
- DeepSeek API key (for S0 enrichment and S2 normalization)

### 1. Install

```bash
# No package install needed. Clone and run directly.
git clone <repo-url>
cd tag-system
```

### 2. Configure API Key

```bash
export DEEPSEEK_API_KEY=YOUR_KEY
```

The key is read from the `DEEPSEEK_API_KEY` environment variable. Never hardcode it in config files.

### 3. Run ontology_factory (demo, with API key)

```bash
export DEEPSEEK_API_KEY=YOUR_KEY
python3 ontology_factory/run_factory.py \
  --profile ontology_factory/profiles/adult_profile.json \
  --input tests/data/acquisition/raw_30.json \
  --stage s0 --end-stage s8
```

Processes 30 tags through all 9 stages → outputs frozen ontology + retrieval index.

### 4. Run ontology_factory (demo, no API key)

```bash
# Skip LLM stages, start from S3 (uses work/stage2_normalized.json from a previous run)
python3 ontology_factory/run_factory.py \
  --profile ontology_factory/profiles/adult_profile.json \
  --input tests/data/ontology/smoke_20.json \
  --stage s3 --end-stage s6
```

Runs S3–S6 (script-only stages). Validates namespace, ID freeze, alias, and pipeline logic without API calls.

### 5. Run ontology_factory (skip S0, use pre-enriched data)

```bash
export DEEPSEEK_API_KEY=YOUR_KEY
python3 ontology_factory/run_factory.py \
  --profile ontology_factory/profiles/adult_profile.json \
  --input tests/data/acquisition/small_50.json \
  --stage s1 --end-stage s8
```

Processes 50 pre-enriched tags through S1–S8. No S0 enrichment needed.

---

## Repository Structure

```
tag-system/
├── tag_acquisition/          # Tag collection and cleaning
│   ├── collector.py          # Pixiv API collector
│   ├── normalize.py          # Surface form normalization
│   ├── split.py              # Compound tag splitting
│   ├── filter.py             # Quality filtering
│   └── run.py                # Entry point
│
├── ontology_factory/         # Ontology pipeline (S0–S8)
│   ├── run_factory.py        # Pipeline entry point
│   ├── stages/               # S0–S8 stage implementations
│   ├── config/               # Pipeline configuration
│   ├── profiles/             # Domain profiles (adult_content_tags)
│   ├── validators/           # Deterministic validation
│   └── review_queue/         # Manual review interface
│
├── tests/data/               # Test datasets
│   ├── acquisition/          # Raw and adversarial test sets
│   └── ontology/             # Pre-enriched smoke tests
│
└── docs/                     # Design documents
```

Runtime outputs (`work/`, `exports/`, `metrics/`) are excluded from version control.

---

## Current Status

**Version:** v0.1-stable

| Metric | Value |
|--------|-------|
| Pipeline stages | S0–S8 (9 stages) |
| Test runs passed | 30 / 50 / 200 tags |
| Data loss | 0 across all runs |
| Review rate | ~18% (conservative policy) |
| Mean confidence | ~0.89 |
| Architecture | Frozen (no changes to S1–S8) |

The system is stable for small-scale use (hundreds of tags). Large-scale production runs (1000+ tags) have not been validated yet.

---

## What Is NOT Included

This repository intentionally excludes:

- **Production datasets** — real tag corpora are domain-specific and may contain sensitive content
- **Full Pixiv dumps** — only small test samples are included
- **Embedding files** — retrieval indexes are generated at runtime, not stored
- **Cache / work artifacts** — all intermediate outputs are reproducible from source + config
- **API credentials** — keys must be provided via environment variable

---

## License

MIT License. See [LICENSE](LICENSE) for details.
