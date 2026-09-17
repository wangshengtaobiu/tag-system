"""3-stage tagging pipeline orchestrator.

Usage:
  python -m tagger.pipeline --book-dir /path/to/novels
  python -m tagger.pipeline --books work/book_list.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tagger.config import PipelineConfig, CONFIGS
from tagger import stage1_recall
from tagger.stage1_recall import run_stage1
from tagger.stage2_rerank import run_stage2
from tagger.stage3_confirm import run_stage3


def scan_books(book_dir: str) -> list[dict]:
    """Recursively scan .txt files, return [{name, text}]."""
    books = []
    for root, _dirs, files in os.walk(book_dir):
        for f in files:
            if f.lower().endswith(".txt"):
                path = os.path.join(root, f)
                for enc in ("utf-8", "gbk", "latin-1"):
                    try:
                        text = Path(path).read_text(encoding=enc)
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
                else:
                    text = ""
                if text.strip():
                    books.append({"name": f, "text": text})
    return books


def main():
    parser = argparse.ArgumentParser(description="3-stage tagging pipeline")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--books", help="JSON file [{name, text}]")
    group.add_argument("--book-dir", help="Directory of .txt novels")
    parser.add_argument("--output", default="tagger/work/final_tags.jsonl")
    parser.add_argument("--config", default="default", choices=list(CONFIGS.keys()))
    parser.add_argument("--stages", default="1,2,3",
                        help="Comma-separated stages to run (e.g. 1,2,3)")
    args = parser.parse_args()

    config = CONFIGS[args.config]
    stages = [int(s) for s in args.stages.split(",") if s.strip()]

    # Only stage 1 needs the book list; stages 2 and 3 read their input from the
    # cache. Loading the corpus into memory for them would be pure waste (and
    # --books is optional, so it may not even be given).
    books = []
    if 1 in stages:
        if args.book_dir:
            print(f"Scanning {args.book_dir} ...")
            books = scan_books(args.book_dir)
            print(f"  Found {len(books)} books")
        elif args.books:
            with open(args.books, "r", encoding="utf-8") as f:
                books = json.load(f)
            print(f"  Loaded {len(books)} books from {args.books}")
        else:
            print("ERROR: stage 1 needs --books or --book-dir")
            sys.exit(1)

    out_dir = os.path.dirname(args.output) or "."
    os.makedirs(out_dir, exist_ok=True)

    stage1_path = os.path.join(out_dir, ".stage1_cache.jsonl")
    stage2_path = os.path.join(out_dir, ".stage2_cache.jsonl")

    if 1 in stages:
        print("=" * 60)
        print("STAGE 1: BGE-M3 Recall")
        print("=" * 60)
        run_stage1(books, config, stage1_path)

    if 2 in stages:
        print("\n" + "=" * 60)
        print("STAGE 2: candidate rerank")
        print("=" * 60)
        if not os.path.exists(stage1_path) and 1 not in stages:
            print(f"ERROR: Stage1 cache not found at {stage1_path}")
            sys.exit(1)
        if 1 in stages:
            stage1_recall.release()   # free bge-m3 VRAM before loading the reranker
        run_stage2(stage1_path, stage2_path, config)

    if 3 in stages:
        print("\n" + "=" * 60)
        print("STAGE 3: DeepSeek Confirmation")
        print("=" * 60)
        cache = stage2_path if os.path.exists(stage2_path) else stage1_path
        run_stage3(cache, args.output, config)

    print(f"\nDone. Output: {args.output}")


if __name__ == "__main__":
    main()
