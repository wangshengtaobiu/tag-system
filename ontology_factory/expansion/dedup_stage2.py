#!/usr/bin/env python3
"""Vocabulary-internal de-duplication at the stage2 layer.

Three passes:
  1. MERGE   : collapse true synonym entry pairs (loser_cid -> winner_cid):
               drop the loser, move its name and aliases onto the winner.
  2. CROSS   : remove any alias that normalizes to another entry's own name
               (a concept must not occupy both a slot and an alias elsewhere).
  3. IN-ENTRY: de-duplicate each entry's alias list by normalized form
               (traditional/simplified, case, full/half width).

Run after apply_curation.py and before run_factory.py. Idempotent.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

from zhconv import convert as zh

OF = Path(__file__).parent.parent
S2 = OF / "work/stage2_normalized.json"


def key(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s))
    s = zh(s, "zh-cn")
    return re.sub(r"\s+", "", s).lower()


# loser -> winner, addressed by NAME (stage2 runs before architect_fixes rename
# IDs, so canonical_ids are not yet final here)
MERGE = {
    "抖m": "抖M",
    "t台": "T台",
    "恋愛": "恋爱",
    "淫語": "淫语",
    "恋足": "足控",
    "大根": "巨根",
    "榨汁": "榨精",
    "吃烟": "吞精",
    "丧失": "意识丧失",
    "轮廓": "腹部轮廓",
    "花嫁": "婚纱",
    "憑依": "附身",
    "争宠": "雌竞",
    "认知修改": "常识改变",
    "偷情": "出轨",
}


def main():
    data = json.loads(S2.read_text(encoding="utf-8"))
    entries = data["entries"]
    by_name = {e.get("name"): e for e in entries if e.get("name")}

    # ---- pass 1: merge ----
    dropped = []
    for loser_name, winner_name in MERGE.items():
        loser, winner = by_name.get(loser_name), by_name.get(winner_name)
        if not loser or not winner:
            print(f"[dedup] skip merge {loser_name}->{winner_name} (missing)")
            continue
        al = winner.setdefault("aliases", [])
        al.append(loser_name)
        al.extend(a for a in (loser.get("aliases") or []))
        dropped.append(loser)
        print(f"[dedup] merge {loser_name} -> {winner_name}")
    if dropped:
        ids = {id(d) for d in dropped}
        entries = [e for e in entries if id(e) not in ids]

    # ---- pass 2: cross collisions (alias == another entry's name) ----
    primary_name_keys = {key(e.get("name", "")): e.get("canonical_id")
                         for e in entries if e.get("canonical_id")}
    removed = 0
    for e in entries:
        al = e.get("aliases") or []
        keep = []
        for a in al:
            owner = primary_name_keys.get(key(a))
            if owner and owner != e.get("canonical_id"):
                removed += 1
                continue
            keep.append(a)
        e["aliases"] = keep
    print(f"[dedup] cross-collision aliases removed: {removed}")

    # ---- pass 3: de-dup each alias list by normalized form ----
    deduped = 0
    for e in entries:
        seen, keep = set(), []
        for a in e.get("aliases") or []:
            k = key(a)
            if not k or k == key(e.get("name", "")) or k in seen:
                deduped += 1
                continue
            seen.add(k)
            keep.append(a)
        e["aliases"] = keep
    print(f"[dedup] in-entry duplicate/same-as-name aliases removed: {deduped}")

    data["entries"] = entries
    data.setdefault("meta", {})["deduped"] = True
    S2.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[dedup] entries now: {len(entries)}")


if __name__ == "__main__":
    main()
