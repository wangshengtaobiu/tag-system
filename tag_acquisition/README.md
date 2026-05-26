# tag_acquisition

Collects raw tags from external sources, normalizes surface forms, splits compound tags, filters noise, and exports a clean corpus.

## Pipeline

```
Raw tags (from API or file)
    ↓
normalize    — surface cleanup, full-width → half-width, whitespace
    ↓
split        — protected phrase splitting ("足控・M属性" → 2 entries)
    ↓
filter       — quality filter (length, noise patterns, blacklist)
    ↓
lang_detect  — language tagging (zh / jp / en / mixed)
    ↓
dedup        — surface-level deduplication
    ↓
snapshot     — append-only corpus export
```

### normalize

Cleans surface form: trims whitespace, normalizes full-width characters to half-width, collapses repeated spaces. No semantic changes.

### split

Splits compound tags using delimiter policy. Protected phrases (e.g., "NTR・寝取られ") are preserved as-is or split based on configuration. Rollback to original if split produces no valid entries.

### filter

Removes entries that match noise patterns:
- Too short (< 2 chars)
- Too long (> 30 chars)
- Matches blacklist entries
- Fails quality heuristics (e.g., all numbers, random chars)

### lang_detect

Tags each entry with detected language: `zh`, `jp`, `en`, or `mixed`. Uses Unicode range analysis, not external libraries.

### dedup

Surface-level deduplication by normalized label. Keeps the first occurrence, logs duplicates.

### snapshot

Exports clean corpus as append-only snapshot:
- `corpus_v1_YYYYMMDD.jsonl` — one entry per line
- Metadata: total entries, language distribution, filter stats

---

## Schema

Each entry in the output corpus:

```json
{
  "label": "腿控",
  "count": 42
}
```

| Field | Type | Description |
|-------|------|-------------|
| `label` | string | Normalized surface form |
| `count` | int | Frequency / heat score (0 if unavailable) |

---

## Configuration

`config.yaml`:

```yaml
protected_phrases:
  - "NTR・寝取られ"
  - "SM・BDSM"

delimiter_policy:
  chars: ["・", " ", "/", "|"]
  min_split_length: 2

blacklist:
  - "unknown"
  - "misc"

quality:
  min_length: 2
  max_length: 30
  noise_patterns:
    - "^\\d+$"
    - "^[a-zA-Z]{1,2}$"
```

| Key | Description |
|-----|-------------|
| `protected_phrases` | Phrases that should NOT be split, even if they contain delimiters |
| `delimiter_policy.chars` | Characters used to split compound tags |
| `delimiter_policy.min_split_length` | Minimum length of each split part to be valid |
| `blacklist` | Labels to exclude entirely |
| `quality.min_length` | Minimum label length (chars) |
| `quality.max_length` | Maximum label length (chars) |
| `quality.noise_patterns` | Regex patterns for noise detection |

---

## Snapshot

Corpus snapshots are append-only:

```
data/
├── corpus_v1_20260520.jsonl   # Snapshot 1
├── corpus_v1_20260525.jsonl   # Snapshot 2 (includes new entries)
└── corpus_v1_latest.jsonl     # Symlink → latest snapshot
```

**Rebuilding from raw cache:** Snapshots are derived from the raw tag cache. If a snapshot is corrupted, re-run the pipeline from the raw cache — no data is lost.

---

## Quick Start

```bash
# Process raw tags
python3 -m tag_acquisition.run --input tests/data/acquisition/raw_30.json

# Process with custom config
python3 -m tag_acquisition.run --input raw_tags.json --config config.yaml
```

Output: `work/corpus_v1_YYYYMMDD.jsonl`
