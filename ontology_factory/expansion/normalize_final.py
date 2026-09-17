#!/usr/bin/env python3
"""Character normalisation + alias de-duplication on rebuild/tags_final.json.

- convert traditional / Japanese shinjitai characters to Simplified Chinese
  (names and aliases)
- per-entry alias de-dup and self-name removal
- resolve cross-entry duplicate aliases: keep the alias on the most relevant
  owner (name match > definition match > higher confidence), drop elsewhere
Data layer only.
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from zhconv import convert as zh

OF = Path(__file__).parent.parent
TAGS = OF / "rebuild/tags_final.json"
CSV = OF / "rebuild/tags_final.csv"

# Japanese shinjitai / JP-only kanji that zhconv does not map
JP2CN = str.maketrans({
    "壊": "坏", "帰": "归", "続": "续", "実": "实", "悪": "恶", "売": "卖", "変": "变",
    "図": "图", "対": "对", "帯": "带", "圧": "压", "剣": "剑", "検": "检", "権": "权",
    "歯": "齿", "児": "儿", "獣": "兽", "収": "收", "従": "从", "渋": "涩", "焼": "烧",
    "縄": "绳", "脳": "脑", "剤": "剂", "険": "险", "庁": "厅", "広": "广", "応": "应",
    "総": "总", "戦": "战", "単": "单", "発": "发", "経": "经", "絵": "绘", "歳": "岁",
    "毎": "每", "気": "气", "駅": "驿", "沢": "泽", "訳": "译", "釈": "释", "摂": "摄",
    "択": "择", "亜": "亚", "奨": "奖", "搾": "榨", "妬": "妒", "丼": "丼",
    "処": "处", "転": "转", "拡": "扩", "撃": "击",
    "場": "场", "増": "增", "壌": "壤", "嬢": "娘", "剰": "剩", "舗": "铺", "圏": "圈",
    "帰": "归", "剤": "剂", "臓": "脏", "拠": "据", "壱": "壹", "弐": "贰", "斉": "齐",
})


def clean(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s))
    s = zh(s, "zh-cn")
    s = s.translate(JP2CN)
    return re.sub(r"\s+", " ", s).strip()


def key(s: str) -> str:
    return re.sub(r"\s+", "", clean(s)).lower()


def main():
    tags = json.loads(TAGS.read_text(encoding="utf-8"))

    renamed = 0
    for t in tags:
        c = clean(t["name"])
        if c != t["name"]:
            print(f"[norm] name {t['name']} -> {c} ({t['canonical_id']})")
            t["name"] = c
            renamed += 1

    fixed_alias = 0
    for t in tags:
        seen, al = set(), []
        for a in t["aliases"]:
            c = clean(a)
            if c != a:
                fixed_alias += 1
            k = key(c)
            if not k or k == key(t["name"]) or k in seen:
                continue
            seen.add(k)
            al.append(c)
        t["aliases"] = al
    print(f"[norm] names renamed={renamed} alias strings normalised={fixed_alias}")

    # cross-entry duplicate aliases: keep on the most relevant owner
    owner: dict[str, list] = defaultdict(list)
    for t in tags:
        for a in t["aliases"]:
            owner[key(a)].append(t)

    def score(t, a):
        s = 0.0
        if key(a) == key(t["name"]):
            s += 3
        if a in (t.get("definition") or ""):
            s += 1
        s += float(t.get("confidence") or 0)
        return s

    removed = 0
    for k, owners in owner.items():
        if len(owners) <= 1:
            continue
        keep = max(owners, key=lambda t: score(t, k))
        keep_keys = {key(x) for x in keep["aliases"]}
        for t in owners:
            if t is keep:
                continue
            t["aliases"] = [a for a in t["aliases"] if key(a) != k]
            removed += 1
    print(f"[norm] cross-entry duplicate aliases removed: {removed}")

    tags.sort(key=lambda r: (r["namespace"], r["canonical_id"]))
    TAGS.write_text(json.dumps(tags, ensure_ascii=False, indent=1), encoding="utf-8")
    with CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["canonical_id", "name", "namespace", "semantic_type", "definition", "distinction", "aliases"])
        for r in tags:
            w.writerow([r["canonical_id"], r["name"], r["namespace"], r["semantic_type"],
                        r["definition"], r["distinction"], "|".join(r["aliases"])])
    print(f"[norm] tags={len(tags)} aliases={sum(len(t['aliases']) for t in tags)}")


if __name__ == "__main__":
    main()
