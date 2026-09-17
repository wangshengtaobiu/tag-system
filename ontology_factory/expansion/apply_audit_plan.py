#!/usr/bin/env python3
"""Apply audit_plan.json to rebuild/tags_final.json — DATA LAYER ONLY.

No pipeline, no work/, no FAISS. Reads and rewrites the final tag table:
  drop_meta / merge / rename / rename_cid / move_ns / fix_semantic_type
  keep_as_is -> keep the name, but add Gemini's suggested wording as aliases
Then de-duplicates aliases and removes cross-entry name collisions.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

from zhconv import convert as zh

OF = Path(__file__).parent.parent
TAGS = OF / "rebuild/tags_final.json"
PLAN = OF / "rebuild/audit_plan.json"
CSV = OF / "rebuild/tags_final.csv"


def key(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s))
    s = zh(s, "zh-cn")
    return re.sub(r"\s+", "", s).lower()


# keep_as_is 条目：名称保留，把 Gemini 的规范写法收作别名
KEEP_ALIASES = {
    "ntr.ntr": ["戴绿帽", "被戴绿帽"],
    "play.sm": ["虐恋调教", "施虐受虐"],
    "play.light_sm": ["轻度虐恋调教", "轻度调教"],
    "mental.masochist": ["受虐倾向", "重度受虐心理"],
    "role.male_masochist": ["男受虐者", "男性被调教者"],
    "orientation.female_masochist": ["受虐女性", "女被虐者"],
    "power_rel.female_s": ["女施虐者", "女支配者"],
    "power_rel.male_s": ["男施虐者", "男性支配者"],
    "power_rel.female_dom": ["女性支配者", "女支配"],
    "power_rel.female_dom_male_sub": ["女支配男服从", "女虐男受"],
    "body_size.i_cup": ["I杯胸围"],
    "clothing.jk_uniform": ["女高中生制服", "水手服"],
    "role.jk_gal": ["高校辣妹", "女高辣妹"],
    "role.office_lady": ["职场女性", "办公室女职员"],
    "scene.runway": ["走秀T台"],
    "body_shape.limbs_spread": ["大字展开"],
}


def main():
    tags = json.loads(TAGS.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    by_cid = {t["canonical_id"]: t for t in tags}
    removed = []

    # 1) drop_meta
    for cid in plan["drop_meta"]["items"]:
        if cid in by_cid:
            removed.append(cid)
            print(f"[audit] drop meta {cid}")

    # 2) merge
    for loser, winner in plan["merge"]["pairs"].items():
        l, w = by_cid.get(loser), by_cid.get(winner)
        if not l or not w:
            print(f"[audit] skip merge {loser}->{winner}")
            continue
        w.setdefault("aliases", []).extend([l["name"]] + list(l.get("aliases") or []))
        removed.append(loser)
        print(f"[audit] merge {loser} -> {winner}")

    rm = set(removed)
    tags = [t for t in tags if t["canonical_id"] not in rm]

    # 3) rename name / rename cid / move ns / fix semantic_type
    for cid, new_name in plan["rename"]["by_cid"].items():
        e = by_cid.get(cid)
        if e and cid not in rm:
            print(f"[audit] rename {e['name']} -> {new_name} ({cid})")
            e["name"] = new_name
    for old, new in {**plan["rename_cid"]["pairs"]}.items():
        e = by_cid.get(old)
        if e and old not in rm:
            print(f"[audit] cid {old} -> {new}")
            e["canonical_id"] = new
    for old, new in plan["move_ns"]["by_cid"].items():
        e = by_cid.get(old)
        if e and old not in rm:
            print(f"[audit] move {old} -> {new}")
            e["canonical_id"] = new
            e["namespace"] = new.split(".")[0]
    for cid, st in plan["fix_semantic_type"]["by_cid"].items():
        e = by_cid.get(cid)
        if e and cid not in rm:
            e["semantic_type"] = st
    for cid, extra in KEEP_ALIASES.items():
        e = by_cid.get(cid)
        if e and cid not in rm:
            e.setdefault("aliases", []).extend(extra)

    # 4) cleanup: dedup aliases, drop self-name, drop cross-entry name collisions
    name_owner = {key(t["name"]): t["canonical_id"] for t in tags}
    fixed = 0
    for t in tags:
        seen, al = set(), []
        for a in t.get("aliases") or []:
            k = key(a)
            if not k or k == key(t["name"]) or k in seen:
                continue
            owner = name_owner.get(k)
            if owner and owner != t["canonical_id"]:
                continue  # alias collides with another entry's official name
            seen.add(k)
            al.append(a)
        fixed += len(t.get("aliases") or []) - len(al)
        t["aliases"] = al
    print(f"[audit] alias cleanup removed: {fixed}")

    tags.sort(key=lambda r: (r["namespace"], r["canonical_id"]))
    TAGS.write_text(json.dumps(tags, ensure_ascii=False, indent=1), encoding="utf-8")

    with CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["canonical_id", "name", "namespace", "semantic_type", "definition", "distinction", "aliases"])
        for r in tags:
            w.writerow([r["canonical_id"], r["name"], r["namespace"], r["semantic_type"],
                        r["definition"], r["distinction"], "|".join(r["aliases"])])

    # report
    dupc = [c for c, n in __import__("collections").Counter(t["canonical_id"] for t in tags).items() if n > 1]
    g = {}
    for t in tags:
        g.setdefault(key(t["name"]), []).append(t["name"])
    dupn = {k: v for k, v in g.items() if len(v) > 1}
    print(f"[audit] tags={len(tags)} aliases={sum(len(t['aliases']) for t in tags)} "
          f"dup_cid={len(dupc)} dup_name={len(dupn)}")
    if dupc:
        print("  dup cid:", dupc)
    if dupn:
        print("  dup name:", dupn)


if __name__ == "__main__":
    main()
