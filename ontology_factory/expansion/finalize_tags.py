#!/usr/bin/env python3
"""Finalise the tag values + definitions (data layer only, no pipeline).

Applies the 10 needs_review fixes to Gemini's re-enrichment result and writes a
clean, reviewable tag table. Nothing here touches work/ or runs any stage.

Outputs:
  rebuild/tags_final.json   full records
  rebuild/tags_final.csv    flat table for eyeballing (name, definition, aliases)
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
OF = HERE.parent
EXPORT = OF / "exports/ontology_export_v1_0_0.json"
OUT_JSON = OF / "rebuild/tags_final.json"
OUT_CSV = OF / "rebuild/tags_final.csv"

# --- Gemini needs_review 修订 + IP 清理（按名称/cid）---
RENAME_BY_NAME = {
    "中身女性": "中性女性",
    "四肢": "四肢张开",
    "肠子": "拽肠",
    "dom cos": "支配角色扮演",
    "扶上女": "主动女上",
}
RENAME_BY_CID = {"play.urethral": "尿道插入"}
DROP_NAME = ["火影", "星穹铁道", "碧蓝航线", "明日方舟"]
MERGE = {"骨科": "近亲相奸"}


def main():
    entries = [e for e in json.loads(EXPORT.read_text(encoding="utf-8"))["entries"]
               if not e.get("is_alias_of")]

    by_name = {e["original_name"]: e for e in entries}
    by_cid = {e["canonical_id"]: e for e in entries}

    dropped = set()
    # merge
    for loser, winner in MERGE.items():
        l, w = by_name.get(loser), by_name.get(winner)
        if l and w:
            w.setdefault("aliases", []).extend([loser] + (l.get("aliases") or []))
            dropped.add(loser)
            print(f"[final] merge {loser} -> {winner}")
    # drop IP
    for nm in DROP_NAME:
        if nm in by_name:
            dropped.add(nm)
            print(f"[final] drop IP {nm}")

    out = []
    for e in entries:
        nm = e["original_name"]
        if nm in dropped:
            continue
        # rename
        nm = RENAME_BY_NAME.get(nm, nm)
        if e["canonical_id"] in RENAME_BY_CID:
            nm = RENAME_BY_CID[e["canonical_id"]]
            print(f"[final] name -> {nm} ({e['canonical_id']})")
        # alias list: dedup, drop self
        seen, al = set(), []
        for a in e.get("aliases") or []:
            if a and a != nm and a not in seen:
                seen.add(a)
                al.append(a)
        out.append({
            "canonical_id": e["canonical_id"],
            "name": nm,
            "namespace": e["namespace"],
            "semantic_type": e.get("semantic_type"),
            "definition": (e.get("definition") or "").strip(),
            "distinction": (e.get("distinction") or "").strip(),
            "aliases": al,
            "confidence": e.get("confidence", 0),
        })

    out.sort(key=lambda r: (r["namespace"], r["canonical_id"]))
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["canonical_id", "name", "namespace", "semantic_type", "definition", "distinction", "aliases"])
        for r in out:
            w.writerow([r["canonical_id"], r["name"], r["namespace"], r["semantic_type"],
                        r["definition"], r["distinction"], "|".join(r["aliases"])])

    print(f"[final] tags={len(out)}  aliases={sum(len(r['aliases']) for r in out)}")
    print(f"[final] -> {OUT_JSON}")
    print(f"[final] -> {OUT_CSV}")


if __name__ == "__main__":
    main()
