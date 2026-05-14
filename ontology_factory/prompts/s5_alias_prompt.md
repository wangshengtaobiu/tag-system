# Stage 5 Alias Detection Prompt (Flash)

You are detecting alias (synonym) relationships between canonical tags.

## Context
These tags have been normalized with canonical IDs. Some may be synonyms/aliases of each other.

## Conservative Merge Policy
- **Default: DO NOT merge.** Only merge when you are VERY confident two tags are the EXACT same concept.
- **False merge** (merging distinct concepts) is CATASTROPHIC.
- **Duplicate survival** (keeping separate entries for same concept) is TOLERABLE.

## Alias Rules
1. An alias entry MUST have `is_duplicate_of` pointing to the PRIMARY tag's `name`
2. An alias MUST NOT point to another alias (no alias chains)
3. Two tags are aliases if they differ ONLY in:
   - Language/script variants (e.g., 后宫 vs 后宮)
   - Regional terminology for the EXACT same concept
   - Historical/archaic naming for the SAME concept
4. Two tags are NOT aliases if they have:
   - Different semantic nuances (e.g., 足控 vs 腿控)
   - Different scope/granularity (e.g., 束缚 vs 捆绑束缚)
   - Different cultural meaning (e.g., 男同 vs 男男)

## Forbidden Merges
The following pairs MUST NOT be merged:
{forbidden_merges_list}

## Your Task
For each pair of tags, output:
```json
{
  "tag_a": "name1",
  "tag_b": "name2", 
  "are_aliases": true/false,
  "confidence": 0.95,
  "primary": "name_to_keep_as_primary",
  "reason": "explanation"
}
```

Return ONLY a JSON array. No markdown.
