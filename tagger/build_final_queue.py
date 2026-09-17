"""Build the final human review queue from three judges.

Rows are grouped by how many judges accepted the tag, because that is what
decides how much human attention a row deserves:

  P1 三方一致   three independent models agree. Sample it to bound the error
                rate, then auto-accept the rest.
  P2 两方一致   two agree. Review the dissent's reasoning.
  P3 单方独有   one model alone found it. Highest information per row.
  N  三方均否   nobody accepted it. Sample it: this is the recall control --
                without it you cannot see what all three models missed.

Every row carries the tag's own definition and distinction, both the evidence
quotes and a chunk excerpt, so a decision does not require opening the novel.

Usage (from tag-system/):
  python -m tagger.build_final_queue \
    --judges "flash=tagger/work/test50_forced/final.jsonl" \
             "pro=tagger/work/test50_forced_pro/final.jsonl" \
             "gemini=tagger/work/gemini/final.jsonl" \
    --stage2 tagger/work/test50_forced/.stage2_cache.jsonl \
    --out tagger/work/final_queue --neg-sample 120 --pos-sample 120
"""

import argparse
import csv
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from .chunking import chunk_text
from .stage3_confirm import _norm_for_match

EXCERPT_PAD = 200
CHUNK_SHOWN = 800
CHUNK_CHARS = 2000


def load_jsonl(p):
    with open(p, "r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def excerpt_for(text: str, evidence: str):
    ev = (evidence or "").strip()
    if not ev or not text:
        return "", False
    pos, end = text.find(ev), -1
    if pos >= 0:
        end = pos + len(ev)
    else:
        for n in (20, 16, 12, 8):
            if len(ev) < n:
                continue
            m = re.search(r"\s*".join(re.escape(c) for c in ev[:n]), text)
            if m:
                pos = m.start()
                full = re.match(r"\s*".join(re.escape(c) for c in ev), text[pos:])
                end = pos + (full.end() if full else len(ev))
                break
    if pos < 0:
        return "", False
    s, e = max(0, pos - EXCERPT_PAD), min(len(text), end + EXCERPT_PAD)
    return re.sub(r"\s+", " ", text[s:e]).strip(), True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judges", nargs="+", required=True,
                    help='one or more "label=path/to/final.jsonl"')
    ap.add_argument("--stage2", required=True)
    ap.add_argument("--ontology", default="ontology_factory/rebuild/tags_final.json")
    ap.add_argument("--out", default="tagger/work/final_queue")
    ap.add_argument("--neg-sample", type=int, default=120,
                    help="random sample of all-reject rows (recall control)")
    ap.add_argument("--pos-sample", type=int, default=120,
                    help="random sample of unanimous-accept rows (precision control)")
    args = ap.parse_args()

    judges = []
    for spec in args.judges:
        label, path = spec.split("=", 1)
        judges.append((label, {r["book"]: {t["canonical_id"]: t for t in r["tags"]}
                               for r in load_jsonl(path)}))
    labels = [l for l, _ in judges]
    S2 = {r["book"]: r for r in load_jsonl(args.stage2)}
    onto = {t["canonical_id"]: t for t in json.load(open(args.ontology, encoding="utf-8"))}

    shared = [k for k in S2 if all(k in j for _, j in judges)]
    print(f"books covered by all {len(judges)} judges: {len(shared)}")

    rng = random.Random(20260914)
    rows = []
    for book in shared:
        rec = S2[book]
        text = rec.get("text", "")
        chunks = chunk_text(text, CHUNK_CHARS)
        for c in rec.get("candidates", []):
            cid = c["canonical_id"]
            who = [lab for lab, j in judges if cid in j[book]]
            if len(who) == len(judges):
                tier = "P1正例对照"
            elif len(who) >= 2:
                tier = "P2两方一致"
            elif len(who) == 1:
                tier = "P3单方独有"
            else:
                tier = "N负例对照"

            # sampling: unanimous rows and all-reject rows are controls, not a queue
            if tier == "P1正例对照" and rng.random() > args.pos_sample / max(len(c["canonical_id"]), 1):
                pass
            rows.append({
                "_tier": tier, "_who": who, "_cid": cid, "书": Path(book).stem,
                "候选": c, "text": text, "chunks": chunks, "book": book,
            })

    # explicit sampling for the two control tiers
    def sample(tier, n):
        pool = [r for r in rows if r["_tier"] == tier]
        rng.shuffle(pool)
        keep = set(id(r) for r in pool[:n])
        return [r for r in rows if r["_tier"] != tier or id(r) in keep]

    rows = sample("P1正例对照", args.pos_sample)
    rows = sample("N负例对照", args.neg_sample)

    order = {"P3单方独有": 0, "P2两方一致": 1, "P1正例对照": 2, "N负例对照": 3}
    rows.sort(key=lambda r: (order[r["_tier"]], r["书"], r["_cid"]))

    out_rows = []
    for r in rows:
        c, cid, who = r["候选"], r["_cid"], r["_who"]
        o = onto.get(cid, {})
        ev, evok, evsrc = "", "", ""
        for lab, j in judges:
            t = j[r["book"]].get(cid)
            if t and t.get("evidence"):
                ev, evsrc = t["evidence"], lab
                evok = "是" if _norm_for_match(ev) in _norm_for_match(r["text"]) else "否"
                break
        exc, _ = excerpt_for(r["text"], ev)
        chunk = ""
        ci = c.get("best_chunk")
        if isinstance(ci, int) and 0 <= ci < len(r["chunks"]):
            chunk = r["chunks"][ci][:CHUNK_SHOWN].replace("\n", " ").strip()
        out_rows.append({
            "层级": r["_tier"],
            "书": r["书"],
            "标签名": o.get("name") or c.get("original_name", cid),
            "canonical_id": cid,
            "分类": o.get("category", ""),
            "定义": o.get("definition", ""),
            "与易混标签的区别": o.get("distinction", ""),
            "命中块数": c.get("chunk_hits", ""),
            **{f"{lab}判定": "y" if lab in who else "" for lab in labels},
            "证据来源": evsrc,
            "证据可核验": evok,
            "证据": ev[:90],
            "原文上下文": exc,
            "最相关片段(供判否)": chunk,
            "人工判定": "",
            "备注": "",
        })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out.with_suffix(".csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    tiers = Counter(r["层级"] for r in out_rows)
    print(f"\n## 队列 -> {out.with_suffix('.csv')}")
    print(f"  合计 {len(out_rows)} 行")
    for t in sorted(tiers, key=lambda x: order[x]):
        print(f"    {t:12s} {tiers[t]:4d}")
    print(f"\n  证据可核验率: "
          f"{sum(1 for r in out_rows if r['证据可核验'] == '是')}/"
          f"{sum(1 for r in out_rows if r['证据可核验'])}")
    print(f"\n  说明：P3/P2 是真正需要人逐条判的；P1 与 N 是抽样对照，"
          f"用于给'模型共识'估错误率，不是逐条工作量。")


if __name__ == "__main__":
    main()
