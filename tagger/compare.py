"""Compare different slice/top-K configs on 10 test books.

Usage:
  python -m tagger.compare --books tests/data/test_books.json --configs default,big_slice,mid_slice
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tagger.config import PipelineConfig, CONFIGS
from tagger.stage1_recall import run_stage1
from tagger.stage2_rerank import run_stage2
from tagger.stage3_confirm import run_stage3


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Compare tagger configs")
    parser.add_argument("--books", required=True)
    parser.add_argument("--configs", default="default",
                        help="Comma-separated config names from config.py")
    parser.add_argument("--work-dir", default="work/compare")
    args = parser.parse_args()

    config_names = [c.strip() for c in args.configs.split(",")]
    os.makedirs(args.work_dir, exist_ok=True)

    with open(args.books, "r", encoding="utf-8") as f:
        books = json.load(f)

    results = {}
    for name in config_names:
        config = CONFIGS[name]
        stage1 = os.path.join(args.work_dir, f"stage1_{name}.jsonl")
        stage2 = os.path.join(args.work_dir, f"stage2_{name}.jsonl")
        stage3 = os.path.join(args.work_dir, f"final_{name}.jsonl")

        print(f"\n{'#'*60}")
        print(f"# Config: {name}")
        print(f"#  slice: head={config.slice.head_chars}, tail={config.slice.tail_chars}")
        print(f"#  stages: 300→{config.stage2_top_k}→confirm")
        print(f"{'#'*60}")

        t0 = time.time()
        run_stage1(books, config, stage1)
        run_stage2(stage1, stage2, config)
        run_stage3(stage2, stage3, config)
        elapsed = time.time() - t0

        # Collect stats
        with open(stage3, "r", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f]
        n_tags = [len(r["tags"]) for r in rows]
        n_times = [r.get("elapsed_s", 0) for r in rows]
        results[name] = {
            "books": len(rows),
            "avg_tags": sum(n_tags) / len(rows) if rows else 0,
            "avg_time_s3": sum(n_times) / len(n_times) if n_times else 0,
            "total_time": round(elapsed, 1),
        }

    # Summary
    print(f"\n{'='*60}")
    print(f"COMPARISON SUMMARY")
    print(f"{'='*60}")
    print(f"{'Config':<16} {'Books':>6} {'AvgTags':>8} {'AvgS3':>8} {'Total':>8}")
    print(f"{'-'*16:<16} {'-'*6:>6} {'-'*8:>8} {'-'*8:>8} {'-'*8:>8}")
    for name, r in results.items():
        print(f"{name:<16} {r['books']:>6} {r['avg_tags']:>8.1f} "
              f"{r['avg_time_s3']:>7.1f}s {r['total_time']:>7.1f}s")
    print(f"\nResults: {args.work_dir}")


if __name__ == "__main__":
    main()
