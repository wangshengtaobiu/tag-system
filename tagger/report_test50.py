"""Build the effect report for the 50-book test run.

Reads the stage-2 cache and the stage-3 output, and runs one local ablation:
re-query the index the OLD way (book stem + first 2000 chars, top-500) and check
how many of the final tags that would have been reachable. The complement is
what chunk-level recall added.

Usage (from tag-system/):
  python -m tagger.report_test50 [--work tagger/work/test50]
"""

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line.strip()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="tagger/work/test50")
    ap.add_argument("--no-ablation", action="store_true")
    args = ap.parse_args()

    work = Path(args.work)
    s2 = load_jsonl(work / ".stage2_cache.jsonl")
    s3 = load_jsonl(work / "final.jsonl")
    by_book = {r["book"]: r for r in s3}

    print("=" * 96)
    print("50-BOOK TEST REPORT")
    print("=" * 96)

    # ---------- 1. retrieval / rerank ----------
    print("\n## 1. 召回与重排（本地）\n")
    n_chunks = [r.get("n_chunks", 0) for r in s2]
    before = [r.get("candidates_before_rerank", 0) for r in s2]
    after = [len(r.get("candidates", [])) for r in s2]
    multi = []
    for r in s2:
        cands = r.get("candidates", [])
        multi.append(sum(1 for c in cands if c.get("chunk_hits", 1) > 1) / max(len(cands), 1))
    print(f"  书数              : {len(s2)}")
    print(f"  总 chunk 数       : {sum(n_chunks):,}  (中位 {statistics.median(n_chunks):.0f}/本, "
          f"最大 {max(n_chunks):,})")
    print(f"  并集候选数        : 中位 {statistics.median(before):.0f}, 最大 {max(before):,}")
    print(f"  多块命中候选占比  : 中位 {statistics.median(multi):.0%}")
    print(f"  重排后            : {statistics.median(after):.0f}/本")

    # ---------- 2. stage 3 status ----------
    print("\n## 2. 判定结果（远程 deepseek-flash）\n")
    st = Counter(r.get("status", "?") for r in s3)
    total = len(s3)
    for k, v in st.most_common():
        print(f"  {k:14s} {v:3d}  ({v / total:.0%})")
    ok = [r for r in s3 if r.get("status") == "ok"]
    empty = [r for r in s3 if r.get("status") == "empty"]
    tags_per = [len(r["tags"]) for r in ok]
    if tags_per:
        print(f"\n  有效书的标签数    : 中位 {statistics.median(tags_per):.0f}, "
              f"均值 {statistics.mean(tags_per):.1f}, 范围 {min(tags_per)}–{max(tags_per)}")
    print(f"  总标签数          : {sum(len(r['tags']) for r in s3):,}")
    raw = sum(r.get("llm_raw", 0) for r in s3)
    print(f"  模型原始输出      : {raw:,}  → 存活 {sum(len(r['tags']) for r in s3):,} "
          f"({sum(len(r['tags']) for r in s3) / max(raw, 1):.0%} 通过全部校验)")
    el = [r.get("elapsed_s", 0) for r in s3 if r.get("elapsed_s")]
    if el:
        print(f"  单本耗时          : 中位 {statistics.median(el):.0f}s, 合计 {sum(el) / 60:.1f} 分钟")

    # ---------- 3. tag frequency ----------
    print("\n## 3. 命中最多的标签\n")
    freq = Counter()
    for r in s3:
        for t in r["tags"]:
            freq[t.get("tag_name") or t["canonical_id"]] += 1
    for name, n in freq.most_common(15):
        print(f"  {name:20s} {n:3d} 本")
    print(f"\n  不同标签总数: {len(freq):,} / 1304 词表 "
          f"({len(freq) / 1304:.0%}); 只出现 1 次的: {sum(1 for v in freq.values() if v == 1)}")

    # ---------- 4. ablation ----------
    if not args.no_ablation and s2:
        print("\n## 4. 消融：旧设计（书名+前2000字，top500）能不能产出这些标签\n")
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from tagger import stage1_recall as s1
        from tagger.config import PipelineConfig
        cfg = PipelineConfig()
        s1.init(cfg)

        reach_all, miss_all, tot_all = 0, 0, 0
        per_book = []
        for r in s2:
            stem = Path(r["book"]).stem
            head_ids = {c["canonical_id"] for c in s1.recall(f"{stem} {r.get('text', '')[:2000]}", k=500)}
            rec = by_book.get(r["book"])
            if not rec or not rec["tags"]:
                continue
            got = [t["canonical_id"] for t in rec["tags"]]
            reach = sum(1 for c in got if c in head_ids)
            miss = len(got) - reach
            reach_all += reach
            miss_all += miss
            tot_all += len(got)
            per_book.append((stem, len(got), miss))
        s1.release()
        if tot_all:
            print(f"  最终标签总数                      : {tot_all:,}")
            print(f"  旧设计可达                        : {reach_all:,} ({reach_all / tot_all:.0%})")
            print(f"  旧设计【不可能产出】              : {miss_all:,} ({miss_all / tot_all:.0%})")
            print(f"\n  每本漏掉的标签数（前15本，按漏得多排序）:")
            for stem, n, miss in sorted(per_book, key=lambda x: -x[2])[:15]:
                print(f"    {stem[:44]:46s} {n:3d} 标签, 其中 {miss:3d} 个旧设计看不到 "
                      f"({miss / max(n, 1):.0%})")
        else:
            print("  （没有可比较的标签）")

    print("\n" + "=" * 96)


if __name__ == "__main__":
    main()
