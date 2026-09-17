"""Compare two stage-3 runs over the same books.

Two uses:
  1. coverage: default (stage2_top_k=40) vs wide (120) — is the 40-slot budget
     capping how many tags a book can receive?
  2. accuracy proxy: two judges over identical candidates — where they agree is
     the high-confidence set, where they disagree is the human review queue.

Usage (from tag-system/):
  python -m tagger.compare_runs A/final.jsonl B/final.jsonl [--label-a 40] [--label-b 120]
"""

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path


def load(path):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line.strip()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--out-queue", default=None, help="write the disagreement queue as JSONL")
    args = ap.parse_args()

    A = {r["book"]: r for r in load(args.a)}
    B = {r["book"]: r for r in load(args.b)}
    shared = [k for k in A if k in B]
    la, lb = args.label_a, args.label_b

    ta = {k: {t["canonical_id"] for t in A[k]["tags"]} for k in shared}
    tb = {k: {t["canonical_id"] for t in B[k]["tags"]} for k in shared}

    na = [len(ta[k]) for k in shared]
    nb = [len(tb[k]) for k in shared]
    print("=" * 92)
    print(f"RUN COMPARISON:  {la}  vs  {lb}   ({len(shared)} shared books)")
    print("=" * 92)

    print(f"\n## 每本标签数")
    print(f"  {la:>8s}: 中位 {statistics.median(na):.0f}, 均值 {statistics.mean(na):.1f}, "
          f"合计 {sum(na)}")
    print(f"  {lb:>8s}: 中位 {statistics.median(nb):.0f}, 均值 {statistics.mean(nb):.1f}, "
          f"合计 {sum(nb)}")
    grew = sum(1 for k in shared if len(tb[k]) > len(ta[k]))
    shrank = sum(1 for k in shared if len(tb[k]) < len(ta[k]))
    same = len(shared) - grew - shrank
    print(f"  标签数变化: 增加 {grew} 本, 不变 {same} 本, 减少 {shrank} 本")
    if statistics.median(na) == statistics.median(nb) and grew <= len(shared) * 0.2:
        print(f"  -> {la} 的候选预算【没有】成为瓶颈")
    else:
        print(f"  -> {la} 的候选预算很可能【压住了】覆盖率")

    # how close to the slot budget did books get?
    for lab, recs in ((la, A), (lb, B)):
        used = []
        for k in shared:
            cands = recs[k].get("candidates_used") or 0
            if cands:
                used.append(len(recs[k]["tags"]) / cands)
        hits = sum(1 for u in used if u > 0.7)
        if used:
            print(f"  {lab} 的候选使用率: 中位 {statistics.median(used):.0%}, "
                  f"超过 70% 的书 {hits}/{len(used)}")

    print(f"\n## 标签集合")
    ua = set().union(*ta.values()) if ta else set()
    ub = set().union(*tb.values()) if tb else set()
    print(f"  {la} 用到不同标签: {len(ua)}")
    print(f"  {lb} 用到不同标签: {len(ub)}")
    print(f"  只有 {lb} 找到  : {len(ub - ua)}   <- 若 40 是瓶颈，这里会有量")
    print(f"  只有 {la} 找到  : {len(ua - ub)}")
    print(f"  两者都找到     : {len(ua & ub)}")

    print(f"\n## 逐本一致度 (Jaccard)")
    jac = [len(ta[k] & tb[k]) / max(len(ta[k] | tb[k]), 1) for k in shared]
    print(f"  中位 {statistics.median(jac):.0%}, 均值 {statistics.mean(jac):.0%}, "
          f"最低 {min(jac):.0%}, 最高 {max(jac):.0%}")
    both = sum(len(ta[k] & tb[k]) for k in shared)
    only_a = sum(len(ta[k] - tb[k]) for k in shared)
    only_b = sum(len(tb[k] - ta[k]) for k in shared)
    tot = both + only_a + only_b
    print(f"  条目级: 一致 {both}/{tot} ({both / max(tot, 1):.0%}), "
          f"仅 {la} {only_a}, 仅 {lb} {only_b}")

    # which tags do they fight over
    fa = Counter(c for k in shared for c in ta[k])
    fb = Counter(c for k in shared for c in tb[k])
    name = {}
    for recs in (A, B):
        for r in recs.values():
            for t in r["tags"]:
                name.setdefault(t["canonical_id"], t.get("tag_name", t["canonical_id"]))
    print(f"\n## 分歧最大的标签（按 |差| 排序）")
    diffs = sorted(set(fa) | set(fb), key=lambda c: -abs(fa.get(c, 0) - fb.get(c, 0)))
    for c in diffs[:15]:
        d = fa.get(c, 0) - fb.get(c, 0)
        if d:
            print(f"  {name.get(c, c):18s} {la}={fa.get(c, 0):3d} {lb}={fb.get(c, 0):3d}  ({d:+d})")

    if args.out_queue:
        with open(args.out_queue, "w", encoding="utf-8") as f:
            for k in shared:
                onlya = ta[k] - tb[k]
                onlyb = tb[k] - ta[k]
                f.write(json.dumps({
                    "book": k,
                    f"only_{la}": sorted(onlya),
                    f"only_{lb}": sorted(onlyb),
                    "agreed": sorted(ta[k] & tb[k]),
                }, ensure_ascii=False) + "\n")
        print(f"\n  分歧队列已写入: {args.out_queue}")


if __name__ == "__main__":
    main()
