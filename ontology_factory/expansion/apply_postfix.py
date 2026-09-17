#!/usr/bin/env python3
"""Apply Gemini's needs_review fixes (name normalisation, id fix, IP removal,
near-duplicate merge) to the stage2 intermediates. Addressed by NAME so it is
stable regardless of architect_fixes renames. Idempotent.

Run after apply_reenrich.py, before dedup_stage2.py.
"""
from __future__ import annotations

import json
from pathlib import Path

OF = Path(__file__).parent.parent
S2 = OF / "work/stage2_normalized.json"

# Gemini needs_review 建议 + 具体作品 IP 清理
RENAME = {
    "中身女性": "中性女性",     # body_shape.androgynous_female 笔误
    "四肢": "四肢张开",         # body_shape.limbs_spread 过宽
    "肠子": "拽肠",             # extreme.gut_pulling 名词化 → 动作
    "dom cos": "支配角色扮演",  # role.dom_cos 混英文
    "扶上女": "主动女上",       # sex_act.fu_shang_nv 拼音自造词
}
# 按 canonical_id 定向改名（名字已被上一轮改过、无法按旧名命中时使用）
RENAME_CID_NAME = {
    "play.urethral": "尿道插入",  # 避开 extreme.urethral_play 已用的「尿道玩法」
}
RENAME_CID = {
    "乱交": "group.orgy",      # group.orc 疑为 orgy 笔误
}
DROP_NAME = [                  # 具体作品 IP，按领域规则不入词表
    "火影", "星穹铁道", "碧蓝航线", "明日方舟",
]
MERGE = {                      # 近义条目合并（loser -> winner）
    "骨科": "近亲相奸",
}


def main():
    data = json.loads(S2.read_text(encoding="utf-8"))
    entries = data["entries"]
    by_name = {e.get("name"): e for e in entries if e.get("name")}

    # 1) merge
    dropped_ids = set()
    for loser_name, winner_name in MERGE.items():
        loser, winner = by_name.get(loser_name), by_name.get(winner_name)
        if not loser or not winner:
            print(f"[postfix] skip merge {loser_name}->{winner_name} (missing)")
            continue
        al = winner.setdefault("aliases", [])
        al.append(loser_name)
        al.extend(a for a in (loser.get("aliases") or []))
        dropped_ids.add(id(loser))
        print(f"[postfix] merge {loser_name} -> {winner_name}")

    # 2) drop IP
    for nm in DROP_NAME:
        e = by_name.get(nm)
        if e:
            dropped_ids.add(id(e))
            print(f"[postfix] drop IP: {nm}")

    entries = [e for e in entries if id(e) not in dropped_ids]

    # 3) rename cid
    for nm, new_cid in RENAME_CID.items():
        e = by_name.get(nm)
        if e and not e.get("is_duplicate_of"):
            old = e.get("canonical_id")
            e["canonical_id"] = new_cid
            print(f"[postfix] cid {old} -> {new_cid} ({nm})")

    # 4) rename name
    renamed = 0
    for old, new in RENAME.items():
        e = by_name.get(old)
        if e:
            e["name"] = new
            renamed += 1
            print(f"[postfix] name {old} -> {new}")
    for cid, new in RENAME_CID_NAME.items():
        for e in entries:
            if e.get("canonical_id") == cid and e.get("name") != new:
                print(f"[postfix] name {e.get('name')} -> {new} (cid {cid})")
                e["name"] = new
                renamed += 1
    print(f"[postfix] renamed={renamed} dropped={len(dropped_ids)} entries={len(entries)}")

    data["entries"] = entries
    S2.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
