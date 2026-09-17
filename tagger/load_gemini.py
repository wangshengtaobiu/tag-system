"""Load adjudication output written by an agentic model (Antigravity / Gemini).

Reads `out/book_XX.md` files produced from the `in/book_XX.md` inputs written by
export_for_gemini.py, maps each decision index back to its canonical_id, and
applies exactly the same filters as the API judges (evidence must occur verbatim
in the book, duplicates collapsed). Output is the same JSONL shape as
`final.jsonl`, so compare_runs.py and build_review_queue.py work unchanged.

Usage (from tag-system/):
  python -m tagger.load_gemini --dir tagger/work/gemini \
      --stage2 tagger/work/test50_forced/.stage2_cache.jsonl \
      --out tagger/work/gemini/final.jsonl
"""

import argparse
import json
import re
from pathlib import Path

from .stage3_confirm import _norm_for_match, _verify_evidence
from .config import PipelineConfig


def extract_json(text: str) -> dict | None:
    """Pull the decisions object out of a markdown reply (fenced or bare)."""
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    candidates = [fence.group(1)] if fence else []
    if not candidates:
        i, j = text.find("{"), text.rfind("}")
        if i >= 0 and j > i:
            candidates.append(text[i:j + 1])
    for c in candidates:
        try:
            d = json.loads(c)
            if isinstance(d, dict) and "decisions" in d:
                return d
        except json.JSONDecodeError:
            # salvage objects one by one from a truncated array
            objs = []
            for o in re.findall(r'\{[^{}]*"i"\s*:\s*\d+[^{}]*\}', c):
                i = re.search(r'"i"\s*:\s*(\d+)', o)
                v = re.search(r'"v"\s*:\s*"?([yn])', o, re.I)
                e = re.search(r'"e"\s*:\s*"([^"]*)"', o)
                if i and v:
                    objs.append({"i": int(i.group(1)), "v": v.group(1),
                                 "e": e.group(1) if e else ""})
            if objs:
                return {"decisions": objs, "salvaged": True}
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="tagger/work/gemini")
    ap.add_argument("--stage2", default="tagger/work/test50_forced/.stage2_cache.jsonl")
    ap.add_argument("--out", default=None)
    ap.add_argument("--label", default="gemini")
    args = ap.parse_args()

    base = Path(args.dir)
    cfg = PipelineConfig()
    stage2 = {Path(r["book"]).stem: r
              for r in (json.loads(l) for l in open(args.stage2, encoding="utf-8"))}

    # in/book_XX.md -> which book it is
    index = {}
    for f in sorted((base / "in").glob("book_*.md")):
        first = f.read_text(encoding="utf-8").splitlines()[0]
        index[f.name] = first.lstrip("# ").strip()

    out_path = Path(args.out) if args.out else base / "final.jsonl"
    rows, problems = [], []
    for name, stem in index.items():
        src = base / "out" / name
        rec = stage2.get(stem)
        if rec is None:
            problems.append(f"{stem}: 不在 stage2 缓存里"); continue
        if not src.exists():
            problems.append(f"{stem}: 缺少输出文件 {src.name}"); continue

        parsed = extract_json(src.read_text(encoding="utf-8"))
        if parsed is None:
            problems.append(f"{stem}: 输出里找不到 decisions JSON"); continue
        if parsed.get("error"):
            problems.append(f"{stem}: 模型自报错误 {parsed['error'][:60]}"); continue

        cands = rec["candidates"]
        src_norm = _norm_for_match(rec.get("text", ""))
        seen_i, tags = set(), []
        n_items = len(parsed.get("decisions", []))
        for d in parsed["decisions"]:
            try:
                i = int(d.get("i", 0))
            except (TypeError, ValueError):
                continue
            if not (1 <= i <= len(cands)) or i in seen_i:
                continue
            seen_i.add(i)
            if str(d.get("v", "")).strip().lower() not in ("y", "yes", "1", "true", "是"):
                continue
            ev = d.get("e", "")
            if isinstance(ev, (list, tuple)):
                ev = " ".join(str(x) for x in ev)
            ev = str(ev or "")
            if not _verify_evidence(ev, src_norm, cfg):
                continue
            tags.append({"canonical_id": cands[i - 1]["canonical_id"],
                         "confidence": 0.9, "evidence": ev[:120],
                         "tag_name": cands[i - 1].get("original_name", "")})

        rows.append({"book": rec["book"], "tags": tags,
                     "status": "ok" if tags else "empty",
                     "elapsed_s": 0, "candidates_used": len(cands),
                     "llm_raw": n_items, "decisions_seen": len(seen_i)})
        print(f"  {stem[:30]:32s} 裁决 {len(seen_i):>3d}/{len(cands)}  "
              f"判y {len(tags):>3d}")

    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n写入 {out_path}: {len(rows)} 本, 共 {sum(len(r['tags']) for r in rows)} 个标签")
    if problems:
        print(f"\n问题 ({len(problems)}):")
        for p in problems:
            print(f"  - {p}")
    cover = [r["decisions_seen"] / max(r["candidates_used"], 1) for r in rows]
    if cover:
        print(f"\n裁决覆盖率: 中位 {sorted(cover)[len(cover)//2]:.0%} "
              f"(低覆盖说明模型跳过了条目，结果不可用)")


if __name__ == "__main__":
    main()
