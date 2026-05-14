# Stage 4 Freeze Prompt (Flash)

You are resolving canonical ID duplicates and finalizing namespace assignments.

## Context
The following tags have been normalized but may have:
- Duplicate canonical IDs (different tags with same ID)
- Invalid namespace assignments
- Depth violations (ID > 3 segments)

## Frozen Namespaces
{namespace_list}

## Your Task
For each tag, verify and resolve:
1. `canonical_id` is unique among primary entries
2. `namespace` is valid and appropriate for the tag's semantics
3. `canonical_id` segments ≤ 3
4. `parent_canonical_id` references an existing canonical_id or is null

## Output
For each input tag, return the resolved entry with the same schema.
If you change a canonical_id, add a `fix_reason` field explaining why.

**CRITICAL**: Do NOT merge two distinct concepts under the same canonical_id.
If two tags are truly the same concept, mark one as `is_duplicate_of` pointing to the other's `name`.
