"""Error decomposition: is a miss the retriever's fault or the judge's?

The pipeline can fail in two independent places, and they need opposite fixes:
  * retrieval never put the tag in the candidate list  -> fix recall (chunking,
    embedding, caps). The judge never had a chance.
  * the tag WAS in the candidate list but the judge did not pick it -> fix the
    prompt / candidate presentation / model choice.

Without splitting these, an aggregate F1 tells you nothing actionable.

Input is the annotated review queue (the CSV produced by build_review_queue.py,
with the 人工判定 column filled in as 对 / 错) plus, optionally, tags the
reviewer had to add by hand because no judge proposed them.

Two modes:
  --full   every candidate for the reviewed books was annotated. Then recall and
           the decomposition are exact.
  (default) only the sampled rows were annotated (disputes + controls). Then
           only precision-type numbers are trustworthy and recall is a lower
           bound; the script says so explicitly instead of over-reporting.

Usage (from tag-system/):
  python -m tagger.evaluate --review tagger/work/review_queue.csv \
      --stage2 tagger/work/test50_wide/.stage2_cache.jsonl \
      --pred tagger/work/test50_wide/final.jsonl --full
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

YES = {"对", "是", "y", "yes", "1", "true", "正确", "o", "√", "v"}


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def norm_verdict(v: str) -> bool | None:
    s = (v or "").strip().lower()
    if s in YES:
        return True
    if s in {"错", "否", "n", "no", "0", "false", "错误", "x", "×"}:
        return False
    return None          # blank = not annotated


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", required=True, help="annotated review CSV")
    ap.add_argument("--stage2", required=True, help="stage2 cache (candidate lists)")
    ap.add_argument("--pred", required=True, help="system output to score (final.jsonl)")
    ap.add_argument("--added", default=None,
                    help="optional JSONL of human-added tags: {book, canonical_id}")
    ap.add_argument("--full", action="store_true",
                    help="all candidates for the reviewed books were annotated")
    args = ap.parse_args()

    S2 = {r["book"]: r for r in load_jsonl(args.stage2)}
    PRED = {r["book"]: r for r in load_jsonl(args.pred)}

    gold_pos = defaultdict(set)      # book -> cids a human confirmed apply
    gold_neg = defaultdict(set)      # book -> cids a human rejected
    n_blank = 0
    with open(args.review, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            v = norm_verdict(row.get("人工判定", ""))
            book = row.get("书", "")
            cid = row.get("canonical_id", "")
            if not book or not cid:
                continue
            if v is None:
                n_blank += 1
            elif v:
                gold_pos[book].add(cid)
            else:
                gold_neg[book].add(cid)

    if args.added and Path(args.added).exists():
        for r in load_jsonl(args.added):
            gold_pos[r["book"]].add(r["canonical_id"])

    books = sorted(gold_pos.keys() | gold_neg.keys())
    if not books:
        print("no annotated rows found — fill in the 人工判定 column first")
        return
    print("=" * 92)
    print(f"ERROR DECOMPOSITION   ({len(books)} books, "
          f"{sum(len(v) for v in gold_pos.values())} confirmed tags, "
          f"{sum(len(v) for v in gold_neg.values())} rejected, {n_blank} unannotated rows)")
    print("=" * 92)
    if not args.full:
        print("!! sample mode: only the annotated rows are known, so precision is")
        print("!! conditional on the sampled subset and recall is a LOWER BOUND.")

    # resolve book keys: review CSV stores the stem, caches store the filename
    def find(mapv, stem):
        for k in mapv:
            if Path(k).stem == stem:
                return k
        return None

    tp = fp = fn = 0
    in_cand_pos = 0          # gold positives that WERE in the candidate list
    miss_retrieval = 0       # gold positives never retrieved
    miss_judge = 0           # gold positives retrieved but not selected
    per_book = []
    wrong_accept = Counter()   # tags the system accepted that humans rejected
    wrong_reject = Counter()   # tags humans confirmed but the system missed

    for stem in books:
        k = find(S2, stem) or find(PRED, stem) or stem
        cands = {c["canonical_id"] for c in S2.get(k, {}).get("candidates", [])}
        pred = {t["canonical_id"] for t in PRED.get(k, {}).get("tags", [])}
        pos, neg = gold_pos[stem], gold_neg[stem]

        t = len(pred & pos)
        f_p = len(pred - pos) if args.full else len(pred & neg)
        f_n = len(pos - pred)
        tp += t
        fp += f_p
        fn += f_n

        reach = pos & cands
        unreach = pos - cands
        in_cand_pos += len(reach)
        miss_retrieval += len(unreach)
        miss_judge += len(reach - pred)

        for c in pred & neg:
            wrong_accept[c] += 1
        for c in pos - pred:
            wrong_reject[c] += 1

        per_book.append((stem, len(pos), len(pred), t, len(unreach), len(reach - pred)))

    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    all_pos = tp + fn
    cand_recall = in_cand_pos / max(all_pos, 1)
    judge_recall = (in_cand_pos - miss_judge) / max(in_cand_pos, 1)

    print(f"\n## 端到端指标")
    print(f"  微平均 precision {prec:.1%}  recall {rec:.1%}  F1 {f1:.1%}   (TP={tp} FP={fp} FN={fn})")

    print(f"\n## 错误拆解（这就是它存在的理由）")
    print(f"  金标正例总数                     {all_pos}")
    print(f"  ① 检索没召回（裁判根本没机会）    {miss_retrieval}  ({miss_retrieval/max(all_pos,1):.1%})")
    print(f"  ② 检索到了但裁判漏选              {miss_judge}  ({miss_judge/max(all_pos,1):.1%})")
    print(f"  候选召回率 = |金标 ∩ 候选|/|金标|  {cand_recall:.1%}")
    print(f"  裁判在候选内的召回率              {judge_recall:.1%}")
    print(f"  -> 修哪里：{'检索侧' if miss_retrieval > miss_judge else '判定侧'}"
          f"（{max(miss_retrieval, miss_judge) / max(miss_retrieval + miss_judge, 1):.0%} 的漏检来自它）")

    print(f"\n## 逐本")
    print(f"  {'书':40s} {'金标':>4s} {'预测':>4s} {'命中':>4s} {'检索漏':>6s} {'判定漏':>6s}")
    for stem, np_, pr, t, mr, mj in sorted(per_book, key=lambda x: -(x[4] + x[5]))[:20]:
        print(f"  {stem[:40]:40s} {np_:>4d} {pr:>4d} {t:>4d} {mr:>6d} {mj:>6d}")

    if wrong_accept:
        print(f"\n## 最常被错误接受的标签（本体定义可能有歧义）")
        for c, n in wrong_accept.most_common(12):
            print(f"  {c:36s} {n}")
    if wrong_reject:
        print(f"\n## 最常被漏掉的标签（提示词或检索需要改进）")
        for c, n in wrong_reject.most_common(12):
            print(f"  {c:36s} {n}")
    print("=" * 92)


if __name__ == "__main__":
    main()
