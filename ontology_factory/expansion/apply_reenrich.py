#!/usr/bin/env python3
"""Merge Gemini's re-enrichment into the stage2 intermediates.

Policy:
  - definition / distinction : take Gemini's version (better quality)
  - aliases                   : UNION of existing ontology aliases and Gemini's
                                (Gemini rewrites rather than preserves, so a
                                 straight replace would drop recall)
  - canonical_id/name/namespace/semantic_type: keep the existing values

Matching is by tag NAME (stage2 runs before architect_fixes rename IDs, so
canonical_ids differ there); Gemini's cids are final, resolved back to names via
the current export.

Run: apply_curation.py -> apply_reenrich.py -> dedup_stage2.py -> run_factory.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

OF = Path(__file__).parent.parent
S2 = OF / "work/stage2_normalized.json"
EXPORT = OF / "exports/ontology_export_v1_0_0.json"
REENRICH = OF / "rebuild/reenriched.json"


def main():
    exp = json.loads(EXPORT.read_text(encoding="utf-8"))
    cid2name = {e["canonical_id"]: e["original_name"]
                for e in exp["entries"] if e.get("canonical_id")}
    name2old = {e["original_name"]: (e.get("aliases") or [])
                for e in exp["entries"] if e.get("canonical_id") and not e.get("is_alias_of")}

    re_ = {x["canonical_id"]: x for x in json.loads(REENRICH.read_text(encoding="utf-8"))}
    by_name = {}
    for cid, rec in re_.items():
        nm = cid2name.get(cid)
        if nm:
            by_name[nm] = rec
    print(f"[reenrich] gemini records={len(re_)}  resolved by name={len(by_name)}")

    data = json.loads(S2.read_text(encoding="utf-8"))
    hit = miss = 0
    for e in data["entries"]:
        if e.get("is_duplicate_of"):
            continue
        nm = e.get("name")
        rec = by_name.get(nm)
        if not rec:
            miss += 1
            continue
        e["definition"] = rec.get("definition", "") or e.get("definition", "")
        e["distinction"] = rec.get("distinction", "") or e.get("distinction", "")
        # alias union: existing ontology aliases + gemini aliases
        merged, seen = [], set()
        for a in list(name2old.get(nm, [])) + list(rec.get("aliases") or []) + list(e.get("aliases") or []):
            if a and a not in seen:
                seen.add(a)
                merged.append(a)
        e["aliases"] = merged
        if rec.get("confidence") is not None:
            e["confidence"] = max(float(e.get("confidence") or 0), float(rec["confidence"]))
        # a re-enriched entry is considered reviewed
        e["needs_review"] = bool(rec.get("needs_review", False))
        hit += 1

    S2.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[reenrich] stage2 entries updated: {hit}  unmatched: {miss}")


if __name__ == "__main__":
    main()
