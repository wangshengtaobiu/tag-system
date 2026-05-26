# Tag-System v0.1-stable — Release Audit Report

**Date**: 2026-05-26
**Auditor**: Release Audit Engineer
**Scope**: Full repository pre-GitHub audit
**Version**: v0.1-stable

---

## 1. Files That Must Be Gitignored

| Category | Files | Reason |
|----------|-------|--------|
| Python bytecode | `**/__pycache__/`, `*.pyc` | Already covered, but files exist on disk |
| Pipeline logs | `work/pipeline*.log` (8 files) | Runtime output, no source value |
| Work directory | `work/*.json` (35 files, ~3MB) | Pipeline runtime outputs, reproducible |
| Ontology versions | `work/ontology_versions/` | Frozen runtime snapshots |
| Exports | `exports/ontology_export_*.json`, `exports/retrieval_index.json` | Build outputs |
| Metrics | `metrics/real_*.json`, `metrics/failed_cases/` | Experiment data, not source |
| Observation report | `metrics/observation_report_*.md` | Experiment notes |

**Current .gitignore status**: Already covers `**/work/` and `**/exports/*`. But these directories are **already tracked** (files show as committed). The `.gitignore` won't untrack already-committed files — need `git rm --cached`.

---

## 2. Runtime Outputs Not Meant for Upload

| Path | Size | Action |
|------|------|--------|
| `ontology_factory/work/` (entire dir) | ~3MB | Untrack + gitignore |
| `ontology_factory/exports/` (except `.gitkeep`) | ~1MB | Untrack + gitignore |
| `ontology_factory/__pycache__/` | ~200KB | Untrack + gitignore |
| `ontology_factory/stages/__pycache__/` | ~50KB | Untrack + gitignore |
| `ontology_factory/validators/__pycache__/` | ~10KB | Untrack + gitignore |
| `ontology_factory/review_queue/__pycache__/` | ~10KB | Untrack + gitignore |

---

## 3. Test Data — Should Stay or Move

| File | Size | Location | Recommendation |
|------|------|----------|----------------|
| `tag_acquisition/test_raw_30.json` | 1KB | tag_acquisition/ | **KEEP** — small, useful for smoke test |
| `tag_acquisition/test_adversarial_30.json` | 1KB | tag_acquisition/ | **KEEP** — adversarial test |
| `ontology_factory/test_adversarial_30.json` | 1KB | ontology_factory/ | **REMOVE DUPLICATE** — same as above |
| `ontology_factory/test_input_20.json` | 719B | ontology_factory/ | **KEEP** — small smoke test |
| `tag_acquisition/test_real_50.json` | 25KB | tag_acquisition/ | **KEEP** — medium test |
| `tag_acquisition/test_real_200.json` | 104KB | tag_acquisition/ | **KEEP** — large test, still reasonable |
| `ontology_factory/tag.json` | 645KB | ontology_factory/ | **DECISION NEEDED** — 1178 real tags, domain-specific content |

**Recommendation for `tag.json`**: This is the real production dataset (1178 adult content tags). Consider:
- Option A: Keep it (it's the project's demonstration data)
- Option B: Move to a separate `data/` directory outside main repo
- Option C: Keep in repo but document it contains adult content

---

## 4. Security Scan Results

### 4.1 API Keys
| File | Status |
|------|--------|
| `ontology_factory/config/factory_config.yaml` | **SAFE** — uses `${DEEPSEEK_API_KEY}` env var |
| `ontology_factory/操作手册.md` | **SAFE** — uses placeholder `sk-你的key` / `sk-xxx` |
| No hardcoded real API keys found in source |

### 4.2 Local Paths
| File | Status |
|------|--------|
| `.qoder/settings.local.json` | **CONTAINS** `/home/wst/...` paths — but this dir is already gitignored |
| No hardcoded local paths in source code |

### 4.3 Logs
| File | Status |
|------|--------|
| `work/pipeline*.log` | **CLEAN** — no API key patterns found in logs |
| Logs contain pipeline output only, no secrets |

### 4.4 Tokens / Credentials
- No `.env` files found
- No `*.key` files found
- No credential files found

---

## 5. Missing READMEs

| Path | Status |
|------|--------|
| `README.md` (root) | **EXISTS** (34 lines) — minimal |
| `tag_acquisition/README.md` | **MISSING** — needs creation |
| `ontology_factory/README.md` | **EXISTS** (127 lines) — adequate |

---

## 6. Directory Structure Issues

### 6.1 Duplicate Files
- `test_adversarial_30.json` exists in both `tag_acquisition/` and `ontology_factory/`
- They are identical (diff shows no difference)

### 6.2 Mixed Content in `ontology_factory/`
- `tag.json` (645KB production data) sits alongside source code
- Test files (`test_*.json`) mixed with source files in root directory

### 6.3 `docs/` Directory
- Contains design docs and architecture docs
- `IMPLEMENTATION_PLAN.md` at root — unclear if needed for release
- `docs/superpowers/` — Qoder skill docs, may not be needed for external release

### 6.4 `.qoder/` Directory
- Contains `settings.local.json` with local paths
- Already gitignored, but check if it's actually ignored (may have been committed before gitignore)

---

## 7. File Names Not Suitable for Public Repo

| File | Issue | Recommendation |
|------|-------|----------------|
| `ontology_factory/操作手册.md` | Chinese filename | Rename to `MANUAL.md` or `USER_GUIDE.md` |
| `.qoder/settings.local.json` | Local IDE config | Already gitignored, verify |
| `IMPLEMENTATION_PLAN.md` | Internal planning doc | Consider removing or moving to `docs/internal/` |
| `docs/superpowers/specs/` | Qoder-specific skill docs | Consider if needed for external release |

---

## 8. Git Status Check

Current `.gitignore` already covers:
- `__pycache__/`, `*.pyc`
- `**/work/`
- `**/exports/*` (except `.gitkeep`)
- `tag.json`
- `.qoder/`
- `*.key`, `.env`

**Issue**: `git status` shows these as tracked (`M`, `A` prefixes), meaning they were committed **before** the gitignore was added. They need `git rm --cached` to untrack.

---

## 9. Summary of Required Actions

### Critical (must fix before release)
1. **Untrack runtime artifacts**: `git rm --cached` for `work/`, `exports/`, `__pycache__/`
2. **Remove duplicate**: Delete `ontology_factory/test_adversarial_30.json` (keep `tag_acquisition/` copy)
3. **Decide on `tag.json`**: Whether to include 645KB adult content dataset

### Recommended
4. **Rename `操作手册.md`** → `MANUAL.md`
5. **Create `tag_acquisition/README.md`**
6. **Update root `README.md`** to be more comprehensive
7. **Clean up internal docs**: Move `IMPLEMENTATION_PLAN.md` to `docs/internal/`

### Optional
8. **Remove `.qoder/` from repo** if committed (verify)
9. **Add `data/` directory** for large datasets (if moving tag.json)
10. **Remove `metrics/` experiment data** or move to separate branch

---

## 10. Risk Assessment

| Risk | Level | Notes |
|------|-------|-------|
| API key leak | **LOW** | No real keys in source |
| Local path leak | **LOW** | Only in `.qoder/` which is gitignored |
| Large repo size | **MEDIUM** | `tag.json` (645KB) + work/ (~3MB) + metrics/ |
| Adult content in public repo | **HIGH** | `tag.json` contains 1178 adult content tags with definitions |
| Duplicate files | **LOW** | Only 1 duplicate, easily fixed |

---

## Next Step

Proceed to Step 2 — Generate `.gitignore` improvements.
