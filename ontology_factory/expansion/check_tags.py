#!/usr/bin/env python3
"""Proper tag-table checker (set-based, not a hand-written map).

Detector:
  - traditional characters   : zhconv(zh-cn) changes the char
  - Japanese-only kanji       : char is outside GB2312 AND not in the legitimate
                                rare-Chinese allowlist (this is the exhaustive
                                set test; the allowlist only removes false
                                positives like 屌/丼/肏/齁)
  - full-width alphanumerics  : U+FF01..FF5E mapping to [0-9A-Za-z]
  - duplicates                : after NFKC + zhconv + casefold
  - cross-entry alias collisions
Data layer only; prints a report.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from zhconv import convert as zh

OF = Path(__file__).parent.parent
TAGS = OF / "rebuild/tags_final.json"

# legitimate Chinese characters that fall outside GB2312 (false positives)
ALLOW = set("屌丼肏齁屄")


def is_jp(s: str) -> list[str]:
    out = []
    for c in s:
        if c in ALLOW or not ("\u4e00" <= c <= "\u9fff"):
            continue
        try:
            c.encode("gb2312")
        except UnicodeEncodeError:
            out.append(c)
    return out


def is_trad(s: str) -> bool:
    return zh(s, "zh-cn") != s


def is_fullwidth(s: str) -> list[str]:
    out = []
    for c in s:
        if "\uff01" <= c <= "\uff5e" and chr(ord(c) - 0xFEE0).isalnum():
            out.append(c)
    return out


def norm(s: str) -> str:
    return re.sub(r"\s+", "", zh(unicodedata.normalize("NFKC", str(s)), "zh-cn")).lower()


def main():
    tags = json.loads(TAGS.read_text(encoding="utf-8"))
    names = [(t["canonical_id"], t["name"]) for t in tags]
    aliases = [(t["canonical_id"], a) for t in tags for a in t["aliases"]]
    problems = 0

    for label, items in (("NAME", names), ("ALIAS", aliases)):
        jp = [(c, s, is_jp(s)) for c, s in items if is_jp(s)]
        tr = [(c, s) for c, s in items if is_trad(s)]
        fw = [(c, s, is_fullwidth(s)) for c, s in items if is_fullwidth(s)]
        print(f"[{label}] 日文汉字 {len(jp)} | 繁体 {len(tr)} | 全角英数 {len(fw)}")
        for x in jp[:10]:
            print("    JP:", x)
        for x in tr[:10]:
            print("    TRAD:", x)
        problems += len(jp) + len(tr) + len(fw)

    g = defaultdict(list)
    for c, n in names:
        g[norm(n)].append(n)
    dupn = {k: v for k, v in g.items() if len(v) > 1}
    ag = defaultdict(list)
    for c, a in aliases:
        ag[norm(a)].append(c)
    dupa = {k: v for k, v in ag.items() if len(v) > 1}
    nm = {norm(n) for _, n in names}
    collide = [(c, a) for c, a in aliases if norm(a) in nm]
    print(f"[DUP] 名称重复 {len(dupn)} | 跨条目重复别名 {len(dupa)} | 别名撞名 {len(collide)}")
    for k, v in list(dupa.items())[:10]:
        print("    DUP-ALIAS:", k, v)
    problems += len(dupn) + len(dupa) + len(collide)

    print(f"\n[RESULT] tags={len(tags)} aliases={len(aliases)} problems={problems}")


if __name__ == "__main__":
    main()
