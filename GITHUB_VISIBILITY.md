# GitHub Visibility Recommendation

## Assessment: Public-safe (with caveats)

### Why Public-safe

| Check | Result |
|-------|--------|
| Real API keys | **NONE** |
| Production datasets | **EXCLUDED** (gitignored) |
| Pixiv platform dumps | **NONE** |
| Cache / embeddings | **NONE** |
| Secrets / credentials | **NONE** |
| Internal URLs / paths | **NONE** |
| README complete | **YES** |
| LICENSE present | **YES (MIT)** |
| Fresh clone works | **YES** |

### Caveats

1. **Test data contains adult content labels** — `tests/data/acquisition/` includes 30-200 real adult content tags (Chinese/Japanese). These are public-facing but relatively mild (e.g., "腿控", "巨乳", "NTR"). Not illegal, not explicit imagery, but domain-specific.

2. **Domain profile is adult-focused** — `profiles/adult_profile.json` defines 25 namespaces for adult content categorization. The profile itself contains no explicit content, just category names.

3. **Operations manual is in Chinese** — `操作手册.md` — not a security issue, but may confuse non-Chinese readers.

### Recommendation

**PUBLIC** — with the following notes in README (already included):

> "This project focuses on adult content tags (e.g., from Pixiv novels)."

The test datasets are small samples (≤200 tags), not production dumps. They serve as demonstration data and are appropriate for a public repository of this nature.

### If you prefer caution:

**PRIVATE** initially, share selectively. The system architecture is domain-agnostic — the pipeline works for any tag corpus. You can release the code publicly later while keeping the adult profile and test data private.

### Final recommendation:

**PUBLIC** — the code is clean, the test data is small and representative, and the README clearly states the domain. Anyone searching for "ontology pipeline" or "tag normalization" should be able to understand and use this project.
