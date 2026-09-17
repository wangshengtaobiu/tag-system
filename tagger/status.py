"""Show corpus-run progress. Works the same in PowerShell, cmd and bash.

    python -m tagger.status
    python -m tagger.status --work tagger/work/corpus
"""

import argparse
import json
import time
from pathlib import Path


def count_lines(p: Path) -> int:
    n = 0
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
    return n


def tail(path: Path, n: int = 4):
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="tagger/work/corpus")
    ap.add_argument("--total", type=int, default=4342)
    args = ap.parse_args()

    work = Path(args.work)
    s1 = count_lines(work / ".stage1_cache.jsonl")
    s2 = count_lines(work / ".stage2_cache.jsonl")
    shards = sorted(p.name for p in work.glob("shard*") if p.is_dir())
    # Stage 3 writes into per-shard files; the merged final.jsonl only appears
    # after every shard finishes, so counting it alone shows 0 for hours.
    if shards:
        s3 = sum(count_lines(work / d / "final.jsonl") for d in shards)
        s3_src = f"{len(shards)} 个分片合计"
    else:
        s3 = count_lines(work / "final.jsonl")
        s3_src = "合并文件"
    total = args.total

    print("=" * 62)
    print(f"  {work}")
    print("=" * 62)
    for label, n, note in (("Stage 1  chunk 召回", s1, ""),
                           ("Stage 2  重排", s2, ""),
                           ("Stage 3  判定", s3, f"   ({s3_src})")):
        bar = "#" * int(28 * min(n / max(total, 1), 1)) if total else ""
        print(f"  {label:20s} {n:>6,} / {total:,}  {bar}{note}")
    print(f"  {'合计完成度':20s} {(s1 + s2 + s3) / max(3 * total, 1):>6.1%}")

    merged = count_lines(work / "final.jsonl")
    if shards and merged:
        print(f"\n  已合并: {merged:,} 本 -> {work / 'final.jsonl'}")
    if shards:
        print(f"\n  Stage 3 分片 ({len(shards)} 路):")
        for s in shards:
            print(f"    {s}: {count_lines(work / s / 'final.jsonl'):>6,} 本")

    print("\n  日志末尾:")
    logfiles = ([f"{s}/s3.log" for s in shards] or ["s1.log", "s2.log"])
    fresh = max((work / l for l in logfiles if (work / l).exists()),
                key=lambda p: p.stat().st_mtime, default=None)
    if fresh is not None:
        print(f"    [{fresh.name} (最近更新的)] ")
        for line in tail(fresh, 6):
            print(f"      {line[:100]}")

    latest = [work / "corpus_run.log", work / "s1.log", work / "s2.log"]
    latest += [work / s / "s3.log" for s in shards]
    times = [p.stat().st_mtime for p in latest if p.exists()]
    if times:
        idle = time.time() - max(times)
        flag = "  !! 超过 10 分钟没有写入，可能已停止" if idle > 600 else ""
        print(f"\n  最近一次写入: {idle:.0f} 秒前{flag}")


if __name__ == "__main__":
    main()
