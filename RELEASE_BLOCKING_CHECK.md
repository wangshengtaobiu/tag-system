# Final Release Blocking Check — v0.1-stable

**Date**: 2026-05-26

---

## BLOCKING (must fix before release)

| # | Issue | Status |
|---|-------|--------|
| 1 | API key leak in source | **0 found** ✓ |
| 2 | Production data tracked in git | **0 found** ✓ |
| 3 | Runtime artifacts in repo | **0 found** ✓ |
| 4 | Missing LICENSE | **Resolved** (MIT added) ✓ |
| 5 | Missing root README | **Resolved** ✓ |
| 6 | Fresh clone fails | **Resolved** ✓ |
| 7 | Undeclared dependencies | **0 found** ✓ |
| 8 | Hardcoded local paths | **0 found** ✓ |

**BLOCKING count: 0** ✓

---

## SHOULD_FIX (recommended before release)

| # | Issue | Impact |
|---|-------|--------|
| 1 | `ontology_factory/操作手册.md` — Chinese filename | Minor confusion for non-Chinese users. Consider renaming to `MANUAL.md`. |
| 2 | `docs/internal/IMPLEMENTATION_PLAN.md` — internal planning doc | Not user-facing. Could move to `.github/` or remove. |
| 3 | `docs/superpowers/` — Qoder-specific skill docs | Not needed for external users. Could gitignore. |
| 4 | Smoke test command uses `--skip-flash` but still fails at S2 gate | UX issue — `--skip-flash` should skip S2 entirely, not just skip API call. |

---

## NICE_TO_HAVE (future releases)

| # | Issue | Priority |
|---|-------|----------|
| 1 | CONTRIBUTING.md | Low |
| 2 | CHANGELOG.md | Low |
| 3 | GitHub Actions CI (run smoke test on push) | Low |
| 4 | pyproject.toml (modern packaging) | Low |
| 5 | Dockerfile for reproducible runs | Low |
| 6 | More test datasets (non-adult domain example) | Medium |
| 7 | Local model fallback for S0/S2 | Medium |
| 8 | Review queue web UI | Low |

---

## Release Decision

**BLOCKING = 0** → **CLEARED FOR GITHUB RELEASE**

### Recommended pre-release commands:

```bash
# Tag the release
git tag -a v0.1-stable -m "v0.1-stable: First stable release"

# Verify tag
git tag -v v0.1-stable

# Push
git push origin master --tags
```

### Post-release checklist:

- [ ] README renders correctly on GitHub
- [ ] LICENSE visible on GitHub
- [ ] `tests/data/` files download correctly
- [ ] `pip install -r requirements.txt` works on clean machine
- [ ] Fresh clone smoke test passes on another machine
