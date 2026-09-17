#!/usr/bin/env python3
"""Apply curated expansions to the pipeline intermediates.

Reads every expansion/curation_*.json, each with:
    drop  : [tag, ...]                       ignored (documented only)
    alias : {new_name: target_cid | target_name}
    new   : [{name, canonical_id, namespace, semantic_type, category, definition}]

- alias -> appended to the target entry's `aliases` list
- new   -> appended to work/stage2_normalized.json (S3..S8 pick them up)

Idempotent: curated entries and previously-attached aliases are re-derived every
run. Validation rejects unknown alias targets, id collisions and known names.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from zhconv import convert as zh

HERE = Path(__file__).parent
OF = HERE.parent
sys.path.insert(0, str(OF))
from stages import validate_canonical_id  # noqa: E402


def n2(s: str) -> str:
    return zh(s, "zh-cn").strip()


def main():
    profile = json.loads((OF / "profiles/adult_profile.json").read_text(encoding="utf-8"))
    valid_ns = set(profile["namespace_map"])
    valid_st = {s["id"] for s in profile["semantic_types"]}

    files = sorted(HERE.glob("curation_*.json"))
    cur = {"drop": [], "alias": {}, "new": []}
    for cf in files:
        part = json.loads(cf.read_text(encoding="utf-8"))
        cur["drop"].extend(part.get("drop", []))
        cur["alias"].update(part.get("alias", {}))
        cur["new"].extend(part.get("new", []))
    print(f"[apply] curation files: {[p.name for p in files]} "
          f"(drop={len(cur['drop'])} alias={len(cur['alias'])} new={len(cur['new'])})")

    # ---- stage2 base (idempotent) ----
    s2 = json.loads((OF / "work/stage2_normalized.json").read_text(encoding="utf-8"))
    entries = [e for e in s2["entries"] if not e.get("curated")]
    for e in entries:
        prev = e.pop("_curated_aliases", None)
        if prev:
            e["aliases"] = [a for a in (e.get("aliases") or []) if a not in prev]

    by_cid = {e.get("canonical_id"): e for e in entries if e.get("canonical_id")}
    by_name = {n2(e.get("name", "")): e for e in entries if e.get("canonical_id")}
    known_names, name_owner = set(), {}
    for e in entries:
        nm = n2(e.get("name", ""))
        known_names.add(nm)
        if e.get("canonical_id"):
            name_owner.setdefault(nm, e["canonical_id"])
        for a in e.get("aliases", []) or []:
            known_names.add(n2(a))
    known_cids = set(by_cid)

    # ---- new entries (validated first so aliases may target them) ----
    new_ok, new_bad = [], []
    for e in cur["new"]:
        cid, nm, ns, st = e["canonical_id"], e["name"], e["namespace"], e["semantic_type"]
        problems = []
        if not validate_canonical_id(cid):
            problems.append("bad cid format")
        if cid in known_cids:
            problems.append("cid collides")
        if ns not in valid_ns:
            problems.append(f"bad namespace {ns}")
        if not cid.startswith(ns + "."):
            problems.append("cid prefix != namespace")
        if st not in valid_st:
            problems.append(f"bad semantic_type {st}")
        if n2(nm) in known_names:
            problems.append("name already known")
        if problems:
            new_bad.append((nm, cid, "; ".join(problems)))
            continue
        ent = {
            "canonical_id": cid, "name": nm, "namespace": ns, "semantic_type": st,
            "category": e.get("category", ""), "aliases": [],
            "definition": e.get("definition", ""),
            "distinction": e.get("distinction", ""), "examples": e.get("examples", []),
            "confidence": 0.9, "needs_review": False, "curated": True,
        }
        new_ok.append(ent)
        known_cids.add(cid)
        known_names.add(n2(nm))
        by_cid[cid] = ent
        by_name[n2(nm)] = ent

    # ---- aliases ----
    def resolve(target: str):
        return by_cid.get(target) or by_name.get(n2(target))

    alias_ok, alias_bad = 0, []
    for a_name, target in cur["alias"].items():
        ent = resolve(target)
        if ent is None:
            alias_bad.append((a_name, target, "target not found"))
            continue
        tcid = ent.get("canonical_id")
        owner = name_owner.get(n2(a_name))
        if owner and owner != tcid:
            alias_bad.append((a_name, target, f"name owned by {owner}"))
            continue
        if n2(a_name) == n2(ent.get("name", "")):
            alias_bad.append((a_name, target, "same as entry name"))
            continue
        al = ent.setdefault("aliases", [])
        if a_name in al:
            alias_bad.append((a_name, target, "already an alias"))
            continue
        al.append(a_name)
        ent.setdefault("_curated_aliases", []).append(a_name)
        alias_ok += 1

    print(f"[apply] new accepted={len(new_ok)} rejected={len(new_bad)}")
    for r in new_bad[:20]:
        print("   reject new:", r)
    print(f"[apply] aliases attached={alias_ok} rejected={len(alias_bad)}")
    for r in alias_bad[:25]:
        print("   reject alias:", r)

    entries.extend(new_ok)
    s2["entries"] = entries
    s2.setdefault("meta", {})["curated_additions"] = len(new_ok)
    (OF / "work/stage2_normalized.json").write_text(
        json.dumps(s2, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[apply] stage2 entries -> {len(entries)}")

    (HERE / "apply_report.json").write_text(json.dumps(
        {"new_ok": len(new_ok), "new_rejected": new_bad,
         "aliases_ok": alias_ok, "aliases_rejected": alias_bad},
        ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
