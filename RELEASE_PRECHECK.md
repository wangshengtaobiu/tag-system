# Release Pre-Check Report — v0.1-stable

**Date**: 2026-05-26
**Scope**: Pre-GitHub upload readiness

---

## 1. Large File Check

```
git ls-files | xargs du -h | sort -h | tail -30
```

**Result**: All tracked files are small (< 24KB). No large files in git.

| File | Size | Status |
|------|------|--------|
| `ontology_factory/validators/validator.py` | 16K | ✓ Source code |
| `ontology_factory/stages/s2_normalize.py` | 24K | ✓ Source code (has prompt) |
| All others | ≤12K | ✓ |

**No files > 1MB tracked.** `tag.json` (645KB) and `work/` (~3MB) already excluded by gitignore.

**Action**: None needed.

---

## 2. Secrets / Token / Endpoint Scan

### 2.1 API Key Patterns (`sk-`)

```
grep -rn "sk-[a-zA-Z0-9]" ... (excluding placeholders)
```

**Result**: **No real API keys found.** All instances are placeholders:
- `操作手册.md`: `sk-你的key`, `sk-xxx` (documentation examples)

### 2.2 Bearer / Token / Password

```
grep -rni "bearer\|api_key.*=\|token.*=\|password.*="
```

| File | Line | Content | Status |
|------|------|---------|--------|
| `操作手册.md` | 134 | `export DEEPSEEK_API_KEY="sk-你的key"` | ✓ Placeholder |
| `stages/s0_enrich.py` | 32,235 | `self.api_key = flash_cfg.get("api_key", "")` + Bearer header | ✓ Reads from config/env, not hardcoded |
| `stages/s2_normalize.py` | 31,231 | Same pattern | ✓ Reads from config/env, not hardcoded |

**Result**: **No hardcoded secrets.** All API keys come from `config/factory_config.yaml` which uses `${DEEPSEEK_API_KEY}` env var expansion.

### 2.3 API Provider Names

| File | Mentions | Status |
|------|----------|--------|
| `操作手册.md` | `deepseek-v4-flash`, `api.deepseek.com` | ✓ Documentation — describes required service |
| `ontology_factory/README.md` | `api.deepseek.com`, `deepseek-v4-flash` | ✓ Documentation |
| `config/factory_config.yaml` | `deepseek-v4`, `api.deepseek.com/v1` | ✓ Config — public API endpoint |
| `work/*.json` | `deepseek-v4-flash` | ⚠ Runtime output (not tracked) |

**Result**: Provider names are fine — they document which service is required, not secrets.

### 2.4 Localhost / Internal URLs

| File | Content | Status |
|------|---------|--------|
| `.qoder/settings.local.json` | `127.0.0.1:7897`, `172.21.192.1:7897` (proxy) | ⚠ Already gitignored |
| `tag_acquisition/collector.py` | `Chrome/120.0.0.0` (User-Agent) | ✓ Standard browser UA |
| `tag_acquisition/config.yaml` | Same UA | ✓ Standard browser UA |

**Result**: Only `.qoder/settings.local.json` has internal IPs — already gitignored.

### 2.5 Hardcoded Local Paths

```
grep -rn "/home/\|/Users/\|C:\\\" ...
```

**Result**: **No hardcoded local paths in source code.**

### 2.6 Secrets Summary

| Check | Result |
|-------|--------|
| Real API keys | **CLEAN** — zero found |
| Bearer tokens hardcoded | **CLEAN** — all from config |
| Internal URLs in source | **CLEAN** — only in .qoder/ (gitignored) |
| Local paths in source | **CLEAN** — zero found |
| Provider names in docs | **OK** — documentation, not secrets |

**Risk Level**: LOW. No secrets to leak.

---

## 3. README Completeness Check

### Root README.md (34 lines)

| Required Section | Status |
|------------------|--------|
| 项目是什么 | ✓ Basic |
| 两个模块作用 | ✓ Brief |
| Pipeline 图 | **✗ MISSING** |
| 安装方式 | ✓ Basic |
| 快速开始 | ✓ Minimal |
| 数据流 | **✗ MISSING** |
| 不包含数据集 | ✓ (no dataset in repo) |
| 不包含 API key | ✓ |

**Verdict**: Too minimal. Needs expansion.

### tag_acquisition/README.md

| Required Section | Status |
|------------------|--------|
| 输入输出 | **✗ FILE MISSING** |
| normalize/split/filter 流程 | **✗ FILE MISSING** |
| config 说明 | **✗ FILE MISSING** |
| snapshot 说明 | **✗ FILE MISSING** |

**Verdict**: **FILE DOES NOT EXIST**. Must create.

### ontology_factory/README.md (127 lines)

| Required Section | Status |
|------------------|--------|
| S0~S8 说明 | ✓ Brief list |
| 每阶段职责 | **✗ TOO BRIEF** — only names, no descriptions |
| 输出格式 | **✗ MISSING** |
| review queue | **✗ MISSING** |
| retrieval export | **✗ MISSING** |

**Verdict**: Exists but needs significant expansion for each stage's responsibility and output format.

### README Priority

| Priority | Action |
|----------|--------|
| P0 | Create `tag_acquisition/README.md` |
| P0 | Expand root `README.md` (add pipeline diagram, data flow) |
| P1 | Expand `ontology_factory/README.md` (stage details, output format) |

---

## 4. LICENSE Check

**Status**: **NO LICENSE FILE**

Without a LICENSE, the repo defaults to **all rights reserved** under copyright law. Others cannot legally use, modify, or distribute the code.

### Option Comparison

| | MIT | Apache-2.0 |
|---|-----|------------|
| Length | 9 lines | 178 lines |
| Simplicity | Very simple | More complex |
| Patent grant | No | Yes (explicit) |
| Trademark grant | No | No |
| Liability disclaimer | Yes | Yes |
| Community standard | Most common on GitHub | Second most common |
| Good for v0.1 | **✓ Recommended** | Overkill for now |

**Recommendation**: MIT License. Short, permissive, standard for open-source tools. Can switch to Apache-2.0 later if patent protection becomes relevant.

**Action**: Awaiting your decision before creating LICENSE.

---

## Summary of Required Actions

| # | Action | Priority |
|---|--------|----------|
| 1 | Create `tag_acquisition/README.md` | P0 |
| 2 | Expand root `README.md` | P0 |
| 3 | Expand `ontology_factory/README.md` (stage details) | P1 |
| 4 | Create LICENSE (MIT recommended) | P0 (awaiting decision) |
| 5 | (Optional) Move `IMPLEMENTATION_PLAN.md` to `docs/internal/` | P2 |

**No blocking issues found. Repository is clean of secrets and large files.**
