# README Audit — v0.1-stable

**Date**: 2026-05-26

---

## Completed

| Document | Status | Lines | Notes |
|----------|--------|-------|-------|
| `README.md` (root) | **REWRITTEN** | ~170 | Full rewrite: overview, architecture diagram, modules, quick start, structure, status, exclusions, license |
| `tag_acquisition/README.md` | **CREATED** | ~150 | New file: pipeline flow, schema, config, snapshot, quick start |
| `ontology_factory/README.md` | **REWRITTEN** | ~160 | Full rewrite: S0-S8 stages table, S0 contract, outputs format, review queue, config, structure |

---

## Content Check

### Root README.md

| Required Section | Status |
|------------------|--------|
| Project overview (one sentence) | ✓ |
| Architecture ASCII diagram | ✓ |
| Module descriptions (tag_acquisition + ontology_factory) | ✓ |
| Quick start (real commands, env var for API key) | ✓ |
| Repository structure (core dirs only) | ✓ |
| Current status (v0.1-stable, metrics) | ✓ |
| What is NOT included | ✓ |
| License | ✓ (MIT) |

### tag_acquisition/README.md

| Required Section | Status |
|------------------|--------|
| Pipeline flow (normalize → split → filter → lang → dedup → snapshot) | ✓ |
| Schema (SurfaceCorpusEntry example) | ✓ |
| Config explanation (protected_phrases, delimiter_policy, blacklist) | ✓ |
| Snapshot (append-only corpus, rebuild from cache) | ✓ |

### ontology_factory/README.md

| Required Section | Status |
|------------------|--------|
| S0-S8 stages (one line each) | ✓ (table format) |
| S0 contract (input/output, Chinese keys, S1 compatibility) | ✓ |
| Outputs (ontology export format, retrieval index format) | ✓ (JSON examples) |
| Review queue (pending/reviewed/rejected) | ✓ |

---

## Style Check

| Rule | Status |
|------|--------|
| Engineering doc style | ✓ |
| English primary | ✓ (Chinese retained in examples/definitions only) |
| No marketing language | ✓ |
| No "AI revolutionary" claims | ✓ |
| No empty filler text | ✓ |
| No long background essays | ✓ |
| No excessive adult content disclaimers | ✓ |
| No complex theory | ✓ |

---

## Missing Items (Pre-Release)

| Item | Priority | Notes |
|------|----------|-------|
| `docs/internal/IMPLEMENTATION_PLAN.md` | Low | Internal planning doc — moved out of root, but still in repo. Consider removing before release. |
| `ontology_factory/操作手册.md` | Low | Chinese operations manual — useful but filename is non-standard. Consider renaming to `MANUAL.md`. |
| Root README quick start commands | Medium | Commands reference `tests/data/` paths — verify they work after the test data reorganization. |
| CONTRIBUTING.md | Optional | Not required for v0.1, but useful if expecting external contributors. |

---

## Remaining Actions

1. **Verify quick-start commands work** with reorganized test data paths
2. **Rename `操作手册.md` → `MANUAL.md`** (optional, for consistency)
3. **Decide on `IMPLEMENTATION_PLAN.md`** — keep in `docs/internal/` or remove
4. **Add `docs/internal/` to `.gitignore`** if these are truly internal notes

---

## Assessment

All three READMEs meet the v0.1-stable release requirements. They are:
- Clear to someone unfamiliar with the project
- Focused on engineering usability, not marketing
- Accurate (no exaggerated claims, no fake future features)
- Properly scoped (no sensitive data, no API keys)

**Ready for release pending command verification.**
