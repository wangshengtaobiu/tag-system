# FINAL RELEASE SUMMARY — v0.1-stable

**Date**: 2026-05-26
**License**: MIT

---

## Version

**v0.1-stable** — First stable release.

---

## Modules

| Module | Lines | Files | Purpose |
|--------|-------|-------|---------|
| `tag_acquisition/` | ~600 | 8 .py | Tag collection, normalization, splitting, filtering, corpus export |
| `ontology_factory/` | ~1800 | 15 .py | 9-stage ontology pipeline (S0-S8), validation, retrieval, freeze |
| `tests/data/` | 5 files | — | Test datasets (30/50/200 raw + 20 enriched smoke) |
| `docs/` | 1 design doc | — | Architecture specification |

Total: **~2400 lines** of Python across **23 source files**.

---

## Pipeline

```
tag_acquisition: raw tags → normalize → split → filter → lang → dedup → snapshot
ontology_factory: S0 enrich → S1 triage → S2 normalize → S3 namespace → S4 freeze ID
               → S5 alias → S6 validate → S7 retrieval → S8 freeze
```

| Stage | Type | API | Description |
|-------|------|-----|-------------|
| S0 | LLM | Flash | Semantic enrichment (category, definition, parent) |
| S1 | Script | — | Dedup, clean, field normalize |
| S2 | LLM | Flash | Canonical ID, namespace, aliases, confidence |
| S3 | Script | — | Namespace validation |
| S4 | Script | — | ID freeze, dedup, depth truncation |
| S5 | Script | — | Alias graph, parent resolution |
| S6 | Script | — | 7 deterministic validation checks |
| S7 | Script | — | Retrieval index with embedding text |
| S8 | Script | — | Versioned export, freeze manifest |

---

## Test Status

| Test | Tags | Data Loss | Mean Conf | Review Rate |
|------|------|-----------|-----------|-------------|
| adversarial_30 (full) | 30 | 0 | 0.807 | 32.4% |
| real_50 (S1-S8) | 50 | 0 | 0.898 | 12.0% |
| real_200 (S1-S8) | 200 | 0 | 0.893 | 18.3% |
| Fresh clone smoke | 20 | N/A | N/A | N/A |

**0 data loss** across all validated runs.

---

## Known Limitations

1. Requires DeepSeek API key (S0, S2)
2. Japanese tags occasionally dropped by LLM (recovered by cardinality validator)
3. Validated up to 200 tags only
4. No alias auto-merge (conservative policy)
5. Single domain profile (adult_content_tags)
6. CLI only, no web UI

---

## Excluded Artifacts

The following are intentionally excluded from the repository:

- Production datasets (gitignored)
- Runtime outputs (`work/`, `exports/`)
- Experiment metrics (`metrics/`)
- Cache, embeddings, logs
- Internal docs (`docs/internal/`)
- API credentials

---

## Dependencies

| Package | Version | Used By |
|---------|---------|---------|
| `requests` | >=2.28.0 | API calls (S0, S2, collector) |
| `pyyaml` | >=6.0 | Config loading |

All other imports are Python standard library.

---

## Future Roadmap

- Larger-scale validation (1000+ tags)
- Additional domain profiles
- Local model fallback for LLM stages
- Alias auto-merge tuning
- Review queue web UI
- CI/CD pipeline

---

## Repository Stats

| Metric | Value |
|--------|-------|
| Tracked files | 52 |
| Python files | 23 |
| Test datasets | 5 |
| Documentation | 6 files (3 READMEs, 1 design doc, 2 manuals) |
| External dependencies | 2 |
| License | MIT |
