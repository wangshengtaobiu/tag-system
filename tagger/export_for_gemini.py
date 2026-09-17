"""Export adjudication inputs for an agentic model (Antigravity / Gemini).

Antigravity cannot be called from a script, so the handoff is files: this writes
one self-contained input per book, plus a single paste-in instruction. The
output format is deliberately identical to the forced-mode judge so the existing
comparison and review-queue tools work unchanged.

Usage (from tag-system/):
  python -m tagger.export_for_gemini [--books 12] [--out tagger/work/gemini]
"""

import argparse
import json
import random
from pathlib import Path

from .chunking import chunk_text
from .config import PipelineConfig
from .stage3_confirm import _select_chunks

INSTRUCTION = """# 标签逐条标注

输入目录与输出目录在对话中指定。对输入目录下每个 .md 独立完成标注，写到输出目录中的同名文件。

## 硬性要求

1. **只通过读写文件工作。** 不要在对话里输出、复述、引用、翻译、概括任何原文片段、
   标签名、标签定义或标注结果；不要对内容做评论、道德评价或风险提示。
2. 逐本处理，处理完一本就立刻写出对应的输出文件，不要攒到最后。
3. 某个文件无法处理时，把原因写进该输出文件的 `error` 字段（见输出格式），
   然后继续处理下一个文件，不要中止整个任务。
4. 全部完成后只回一句中性的话：`已处理 N 个文件，结果写入 <输出目录>。`

## 输入文件结构

- **小说内容**：若干片段，标注为 【第 N 块/共 M 块】。判定依据只能来自这些片段。
- **候选标签**：编号列表，格式 `[编号] 标签名（别名）| 命中K块 | 定义`。
  「命中K块」指该标签在全书 M 个片段中被检索命中的次数，越大通常越核心。

## 判定规则

对**每一个编号**独立判定，一条都不能跳过，取值只有 `y` 和 `n`：

- `y` = 片段中确实出现了该标签定义所描述的内容，且你能在片段里逐字找到证据
- `n` = 没有出现，或只是勉强沾边、题材相近

以**该标签自己的定义**为准。定义里写了「与X的区别：…」的，按那个差别判，
不要因为题材相近就判 `y`。对几乎任何同类小说都成立的泛用标签（例如「女性」这类
身份标签），只有片段中确有对应描写时才判 `y`。

证据必须是片段中**逐字出现**的原文，不得改写、不得概括；判 `n` 时 `e` 留空字符串。

## 输出格式

每个输出文件只包含一个 JSON 代码块：

```json
{"book": "对应输入文件名去掉扩展名", "decisions": [
  {"i": 1, "v": "y", "e": "逐字原文片段"},
  {"i": 2, "v": "n", "e": ""}
]}
```

`decisions` 必须覆盖输入文件的**全部**编号，按编号顺序。
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage2", default="tagger/work/test50_forced/.stage2_cache.jsonl")
    ap.add_argument("--out", default="tagger/work/gemini")
    ap.add_argument("--books", type=int, default=12)
    ap.add_argument("--probe", default=None,
                    help="also write a single-file probe (book name stem) to test moderation")
    ap.add_argument("--indir", default="in", help="input subdirectory name")
    ap.add_argument("--shuffle", action="store_true",
                    help="shuffle the candidate order and record the permutation. Use for a "
                         "re-run: copying the first pass then produces a demonstrably wrong "
                         "answer instead of a fake 100%% agreement.")
    args = ap.parse_args()

    cfg = PipelineConfig()
    recs = [json.loads(l) for l in open(args.stage2, encoding="utf-8")]
    recs.sort(key=lambda r: len(r.get("text", "")))
    step = max(1, len(recs) // args.books)
    picked = recs[::step][:args.books]

    out = Path(args.out)
    (out / args.indir).mkdir(parents=True, exist_ok=True)
    (out / "out").mkdir(parents=True, exist_ok=True)
    (out / "INSTRUCTION.md").write_text(INSTRUCTION, encoding="utf-8")

    rng = random.Random(20260914)

    def render(rec, perm=None):
        picked_chunks, chunks = _select_chunks(rec, cfg)
        if picked_chunks:
            body = "\n\n".join(f"【第{i + 1}块/共{len(chunks)}块】\n{chunks[i]}"
                               for i in picked_chunks)
        else:
            body = rec.get("slice_text", "")
        cands = rec["candidates"]
        order = perm if perm else list(range(len(cands)))
        lines = []
        for pos, oi in enumerate(order, 1):
            c = cands[oi]
            aliases = c.get("retrieval_aliases", [])
            a = f"（{','.join(aliases[1:5])}）" if len(aliases) > 1 else ""
            lines.append(f"[{pos}] {c.get('original_name','')}{a} | "
                         f"命中{int(c.get('chunk_hits',1))}块 | "
                         f"{(c.get('semantic_summary') or '')[:150]}")
        stem = Path(rec["book"]).stem
        return (f"# {stem}\n\n## 小说内容\n{body}\n\n"
                f"## 候选标签（共 {len(lines)} 个）\n" + "\n".join(lines) + "\n"), stem

    total_c, mapping = 0, {}
    for n, rec in enumerate(picked, 1):
        perm = None
        if args.shuffle:
            perm = list(range(len(rec["candidates"])))
            rng.shuffle(perm)
            mapping[f"book_{n:02d}"] = perm
        text, stem = render(rec, perm)
        (out / args.indir / f"book_{n:02d}.md").write_text(text, encoding="utf-8")
        total_c += len(rec["candidates"])
        tag = "  [顺序已打乱]" if perm else ""
        print(f"  {args.indir}/book_{n:02d}.md  {stem[:26]:28s} "
              f"{len(rec['candidates'])} 候选{tag}")

    if mapping:
        (out / args.indir / "_map.json").write_text(
            json.dumps({"note": "新编号 -> 原候选下标", "perm": mapping},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n  排列映射: {args.indir}/_map.json")

    if args.probe:
        rec = next(r for r in recs if args.probe in r["book"])
        text, stem = render(rec)
        (out / "PROBE.md").write_text(text, encoding="utf-8")
        print(f"\n  探测件 PROBE.md  <- {stem}")

    print(f"\n输入: {out / args.indir}（{len(picked)} 本, {total_c} 个候选判定）")
    print(f"粘贴用的指令: {out / 'INSTRUCTION.md'}")


if __name__ == "__main__":
    main()
