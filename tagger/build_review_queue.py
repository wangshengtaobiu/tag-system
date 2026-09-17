"""Build a human review queue from two judges' outputs.

The point is to make each decision cheap: every row carries the tag's own
definition and distinction, both judges' evidence quotes, and a short excerpt of
the book around the quote, so a reviewer can decide without opening the novel.

Two kinds of rows:
  * 分歧 (dispute)  — one judge accepted the tag, the other did not. These are
    the rows that actually need a human, and they are the cheapest gold labels
    you can buy.
  * 一致对照 (control) — a random sample where both judges agreed. Without a
    control you cannot tell whether agreement predicts correctness, which is the
    assumption the whole cheap-labelling scheme rests on.

Usage (from tag-system/):
  python -m tagger.build_review_queue \
      --a tagger/work/test50_wide/final.jsonl \
      --b tagger/work/test50_verify/final.jsonl \
      --stage2 tagger/work/test50_wide/.stage2_cache.jsonl \
      --out tagger/work/review_queue
"""

import argparse
import csv
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from .chunking import chunk_text

EXCERPT_PAD = 200
CHUNK_SHOWN = 800
CHUNK_CHARS = 2000


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def load_jsonl(path):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line.strip()))
    return out


def excerpt_for(text: str, evidence: str) -> tuple[str, bool]:
    """±EXCERPT_PAD chars around the evidence quote.

    The pipeline verifies evidence against whitespace/width-normalised text, so a
    plain find() misses whenever the quote and the source differ in spacing. Fall
    back to a whitespace-tolerant regex before giving up.
    """
    ev = (evidence or "").strip()
    if not ev or not text:
        return "", False

    pos = text.find(ev)
    end = pos + len(ev) if pos >= 0 else -1
    if pos < 0:
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

    s = max(0, pos - EXCERPT_PAD)
    e = min(len(text), end + EXCERPT_PAD)
    return re.sub(r"\s+", " ", text[s:e]).strip(), True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="judge A output (final.jsonl)")
    ap.add_argument("--b", required=True, help="judge B output (final.jsonl)")
    ap.add_argument("--stage2", required=True, help="stage2 cache (candidate metadata + book text)")
    ap.add_argument("--ontology", default="ontology_factory/rebuild/tags_final.json")
    ap.add_argument("--out", default="tagger/work/review_queue")
    ap.add_argument("--controls", type=int, default=100,
                    help="how many agreed items to include as a control sample")
    ap.add_argument("--mode", choices=["dispute", "full"], default="dispute",
                    help="dispute: only contested items (cheap, gives precision only). "
                         "full: every candidate for the chosen books (gives recall and the "
                         "retrieval/judge decomposition)")
    ap.add_argument("--books", type=int, default=12,
                    help="full mode: how many books to cover (size-stratified)")
    ap.add_argument("--label-a", default="deepseek-flash")
    ap.add_argument("--label-b", default="deepseek-v4-pro")
    args = ap.parse_args()

    A = {r["book"]: r for r in load_jsonl(args.a)}
    B = {r["book"]: r for r in load_jsonl(args.b)}
    S2 = {r["book"]: r for r in load_jsonl(args.stage2)}
    onto = {t["canonical_id"]: t for t in json.load(open(args.ontology, encoding="utf-8"))}

    shared = [k for k in A if k in B]
    print(f"books in both runs: {len(shared)} / A={len(A)} B={len(B)}")

    def tagmap(rec):
        return {t["canonical_id"]: t for t in rec["tags"]}

    def best_chunk_snippet(book_key: str, cid: str) -> str:
        """The chunk that scored highest for this tag.

        Needed to confirm a NEGATIVE: when neither judge accepted the tag there is
        no quote to show, and making a reviewer scan the whole novel is what makes
        full annotation unaffordable. The top-scoring chunk is where the tag would
        be if it applies at all.
        """
        rec = S2.get(book_key, {})
        c = next((x for x in rec.get("candidates", []) if x["canonical_id"] == cid), None)
        if not c:
            return ""
        chunks = chunk_text(rec.get("text", ""), CHUNK_CHARS)
        ci = c.get("best_chunk")
        if not isinstance(ci, int) or not (0 <= ci < len(chunks)):
            return ""
        return chunks[ci][:CHUNK_SHOWN].replace("\n", " ").strip()

    rows = []
    for book in shared:
        ta, tb = tagmap(A[book]), tagmap(B[book])
        text = S2.get(book, {}).get("text", "")
        cands = S2.get(book, {}).get("candidates", [])
        cand = {c["canonical_id"]: c for c in cands}

        if args.mode == "full":
            # every candidate the retriever offered, so a "no" is as informative
            # as a "yes" and recall becomes computable
            pairs = [("全候选", c["canonical_id"]) for c in cands]
        else:
            pairs = [("分歧", c) for c in (set(ta) ^ set(tb))]
            if len(pairs) < 3:      # thin: sample controls only where there is signal
                pairs += [("一致对照", c) for c in (set(ta) & set(tb))
                          if random.random() < 0.5]

        for kind, cid in pairs:
            a_t, b_t = ta.get(cid), tb.get(cid)
            t = a_t or b_t
            o = onto.get(cid, {})
            ev = (a_t or {}).get("evidence") or (b_t or {}).get("evidence") or ""
            exc, found = excerpt_for(text, ev)
            rows.append({
                "类型": kind,
                "书": Path(book).stem,
                "标签名": o.get("name") or t.get("tag_name", cid),
                "canonical_id": cid,
                "分类": o.get("category", ""),
                "定义": o.get("definition", ""),
                "与易混标签的区别": o.get("distinction", ""),
                "命中块数": cand.get(cid, {}).get("chunk_hits", ""),
                "本书候选总数": len(cand) if cand else "",
                f"{args.label_a}判定": "选中" if a_t else "",
                f"{args.label_a}置信度": (a_t or {}).get("confidence", ""),
                f"{args.label_a}证据": ((a_t or {}).get("evidence") or "")[:80],
                f"{args.label_b}判定": "选中" if b_t else "",
                f"{args.label_b}置信度": (b_t or {}).get("confidence", ""),
                f"{args.label_b}证据": ((b_t or {}).get("evidence") or "")[:80],
                "原文上下文": exc,
                "证据可定位": "是" if found else ("" if not ev else "否"),
                "最相关片段(供判否)": best_chunk_snippet(book, cid),
                "人工判定": "",
                "备注": "",
            })

    if args.mode == "full":
        # one book per size band, so the annotated set spans the gradient
        by_book = defaultdict(list)
        for r in rows:
            by_book[r["书"]].append(r)
        order = sorted(by_book, key=lambda b: -len(S2.get(next((k for k in S2 if Path(k).stem == b), b), {}).get("text", "")))
        keep = set(order[:args.books])
        final_rows = [r for r in rows if r["书"] in keep]
        disputes = [r for r in final_rows if r[f"{args.label_a}判定"] != r[f"{args.label_b}判定"]]
        controls = [r for r in final_rows if r not in disputes]
    else:
        disputes = [r for r in rows if r["类型"] == "分歧"]
        controls = [r for r in rows if r["类型"] == "一致对照"]
        random.shuffle(controls)
        controls = controls[:args.controls]
        final_rows = disputes + controls

    if args.mode == "full":
        # book-by-book order: the reviewer stays inside one novel at a time
        final_rows.sort(key=lambda r: (r["书"], r["canonical_id"]))
    else:
        per_tag = Counter(r["canonical_id"] for r in disputes)
        final_rows.sort(key=lambda r: (r["类型"] != "分歧",
                                       -per_tag.get(r["canonical_id"], 0),
                                       r["书"], r["canonical_id"]))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    csv_path = out.with_suffix(".csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(final_rows[0].keys()))
        w.writeheader()
        w.writerows(final_rows)

    jsonl_path = out.with_suffix(".jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in final_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n## 复核队列")
    print(f"  总计 {len(final_rows)} 行 -> {csv_path}")
    print(f"  分歧 {len(disputes)} 行, 其余 {len(controls)} 行")
    with_ev = [r for r in final_rows if r["证据可定位"]]
    loc = [r for r in with_ev if r["证据可定位"] == "是"]
    print(f"  有证据的行 {len(with_ev)}（可定位 {len(loc)} = "
          f"{len(loc) / max(len(with_ev), 1):.0%}），"
          f"双方均判否、无证据 {len(final_rows) - len(with_ev)} 行")
    print(f"  无证据的行靠『最相关片段(供判否)』列判定，不必翻原文")
    nb = Counter(r["书"] for r in disputes)
    print(f"\n  分歧最多的书 (前 10):")
    for b, n in nb.most_common(10):
        print(f"    {b[:40]:42s} {n} 条分歧")
    print(f"\n  争议最多的标签 (前 15, 跨书出现次数 = 本体定义可能有歧义):")
    tagname = {r["canonical_id"]: r["标签名"] for r in final_rows}
    for cid, n in per_tag.most_common(15):
        print(f"    {tagname.get(cid, cid):18s} {n} 次争议")
    print(f"\n  换个角度看一致度:")
    both_all = sum(len({t['canonical_id'] for t in A[k]['tags']} &
                       {t['canonical_id'] for t in B[k]['tags']}) for k in shared)
    tA = sum(len({t['canonical_id'] for t in A[k]['tags']}) for k in shared)
    tB = sum(len({t['canonical_id'] for t in B[k]['tags']}) for k in shared)
    print(f"    A 共 {tA} 条, B 共 {tB} 条, 交集 {both_all} 条")
    print(f"    A 的条目中 B 也认可: {both_all / max(tA,1):.0%};  "
          f"B 的条目中 A 也认可: {both_all / max(tB,1):.0%}")


if __name__ == "__main__":
    main()
