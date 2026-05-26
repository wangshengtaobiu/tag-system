# Release Notes — v0.1-stable

**Date**: 2026-05-26
**License**: MIT

---

## What's New

This is the first stable release of tag-system — a pipeline system for acquiring, enriching, and freezing domain-specific content tags into a structured ontology.

### tag_acquisition

- Rewritten tag collection pipeline
- Surface normalization (full-width → half-width, whitespace)
- Protected phrase splitting with delimiter policy
- Quality filtering (length, noise patterns, blacklist)
- Language detection (zh / jp / en / mixed)
- Append-only corpus snapshots

### ontology_factory

- Added S0 Tag Enrichment stage (LLM-based semantic field generation)
- Stable S1–S8 pipeline (triage → normalization → namespace → ID freeze → alias → validation → retrieval → freeze)
- Conservative normalization mode (no translation, no expansion, stability-first)
- Cardinality validator (detects and recovers LLM-dropped tags)
- Alias post-processing filter (removes English translations, preserves CJK/abbreviations)
- Review queue for low-confidence entries
- Versioned ontology exports with freeze manifests

### Infrastructure

- Organized test data in `tests/data/` (30/50/200 tag samples)
- Observation framework (`collect_observation.py`, `metrics/failed_cases/`)
- Complete README documentation (root + per-module)
- MIT License

---

## Observation Metrics

| Metric | Value |
|--------|-------|
| Test runs | 30 / 50 / 200 tags |
| Data loss | 0 across all runs |
| Review rate | ~18% |
| Mean confidence | ~0.89 |
| Placeholders | 0.5% (LLM-dropped tags recovered) |
| Alias merges | 0 (conservative policy) |

---

## Known Limitations

1. **LLM dependency** — S0 and S2 require DeepSeek API access. No local model fallback.
2. **Japanese tag handling** — LLM occasionally drops Japanese-only tags (recovered by cardinality validator as placeholders).
3. **Small-scale only** — validated up to 200 tags. 1000+ tag runs not yet tested.
4. **No alias auto-merge** — conservative policy means all potential aliases require human review.
5. **Single domain** — only `adult_content_tags` profile included. Domain-agnostic pipeline, but profiles for other domains must be created manually.
6. **No web UI** — all interaction via CLI.

---

## Roadmap (Not Committed)

- Larger-scale validation (1000+ tags)
- Additional domain profiles
- Local model fallback for S0/S2
- Alias auto-merge with confidence threshold tuning
- Web UI for review queue management

---

## Installation

```bash
git clone <repo-url>
cd tag-system
pip install -r requirements.txt
export DEEPSEEK_API_KEY=YOUR_KEY
```

## Quick Start

```bash
# Full pipeline (30 tags, ~5 minutes)
python3 ontology_factory/run_factory.py \
  --profile ontology_factory/profiles/adult_profile.json \
  --input tests/data/acquisition/raw_30.json \
  --stage s0 --end-stage s8
```

See [README.md](README.md) for full documentation.
