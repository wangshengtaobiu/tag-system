#!/usr/bin/env python3
"""Apply recheck_plan.json (round-2 review fixes) to rebuild/tags_final.json.
Data layer only. Idempotent.
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from zhconv import convert as zh

OF = Path(__file__).parent.parent
TAGS = OF / "rebuild/tags_final.json"
PLAN = OF / "rebuild/recheck_plan.json"
CSV = OF / "rebuild/tags_final.csv"


def key(s: str) -> str:
    return re.sub(r"\s+", "", zh(unicodedata.normalize("NFKC", str(s)), "zh-cn")).lower()


def main():
    tags = json.loads(TAGS.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    by_cid = {t["canonical_id"]: t for t in tags}
    removed = set()

    for loser, winner in plan["merge"].items():
        l, w = by_cid.get(loser), by_cid.get(winner)
        if l and w:
            w.setdefault("aliases", []).extend([l["name"]] + list(l.get("aliases") or []))
            removed.add(loser)
            print(f"[recheck] merge {loser} -> {winner}")
    tags = [t for t in tags if t["canonical_id"] not in removed]

    for cid, nm in plan["rename"].items():
        e = by_cid.get(cid)
        if e and cid not in removed:
            print(f"[recheck] rename {e['name']} -> {nm}")
            e["name"] = nm
    for old, new in plan["rename_cid"].items():
        e = by_cid.get(old)
        if e and old not in removed:
            print(f"[recheck] cid {old} -> {new}")
            e["canonical_id"] = new
    for old, new in plan["move_ns"].items():
        e = by_cid.get(old)
        if e and old not in removed:
            print(f"[recheck] move {old} -> {new}")
            e["canonical_id"] = new
            e["namespace"] = new.split(".")[0]
    for cid, st in plan["fix_semantic_type"].items():
        e = by_cid.get(cid)
        if e and cid not in removed:
            e["semantic_type"] = st
    na = 0
    for cid, drop in plan["drop_aliases"].items():
        e = by_cid.get(cid)
        if not e or cid in removed:
            continue
        dropk = {key(d) for d in drop}
        before = len(e["aliases"])
        e["aliases"] = [a for a in e["aliases"] if key(a) not in dropk]
        na += before - len(e["aliases"])
    print(f"[recheck] aliases dropped: {na}")

    # cleanup: dedup, self, cross-name collisions
    name_owner = {key(t["name"]): t["canonical_id"] for t in tags}
    fx = 0
    for t in tags:
        seen, al = set(), []
        for a in t["aliases"]:
            k = key(a)
            if not k or k == key(t["name"]) or k in seen:
                continue
            o = name_owner.get(k)
            if o and o != t["canonical_id"]:
                continue
            seen.add(k)
            al.append(a)
        fx += len(t["aliases"]) - len(al)
        t["aliases"] = al
    print(f"[recheck] alias cleanup removed: {fx}")

    tags.sort(key=lambda r: (r["namespace"], r["canonical_id"]))
    TAGS.write_text(json.dumps(tags, ensure_ascii=False, indent=1), encoding="utf-8")
    with CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["canonical_id", "name", "namespace", "semantic_type", "definition", "distinction", "aliases"])
        for r in tags:
            w.writerow([r["canonical_id"], r["name"], r["namespace"], r["semantic_type"],
                        r["definition"], r["distinction"], "|".join(r["aliases"])])
    print(f"[recheck] tags={len(tags)} aliases={sum(len(t['aliases']) for t in tags)}")


if __name__ == "__main__":
    main()
