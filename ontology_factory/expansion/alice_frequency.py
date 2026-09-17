#!/usr/bin/env python3
"""Measure each alicesw candidate tag's TRUE popularity.

The BFS harvest count is biased by traversal order. The search result page for a
tag exposes the last pagination page (e.g. 绿母 -> p=131), which is a real
frequency signal (~10 novels/page). One request per tag. Resumable.

Usage:
    python alice_frequency.py [--min-bfs-count 1]
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import requests

HERE = Path(__file__).parent
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Referer": "https://www.alicesw.com/"}
SEARCH = "https://www.alicesw.com/search.html"
_PAGE_RE = re.compile(r"[?&]p=(\d+)&(?:amp;)?serialize")


def pages_for(sess, tag: str) -> int:
    params = {"q": tag, "f": "tag", "sort": "relevance", "p": 1, "serialize": ""}
    for _ in range(3):
        try:
            r = sess.get(SEARCH, params=params, timeout=20)
            if r.status_code == 200:
                nums = [int(x) for x in _PAGE_RE.findall(r.text)]
                return max(nums) if nums else (1 if "/novel/" in r.text else 0)
            time.sleep(2)
        except Exception:
            time.sleep(2)
    return -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", default=str(HERE / "alice_candidates.json"))
    ap.add_argument("--min-bfs-count", type=int, default=1)
    ap.add_argument("--delay", type=float, default=0.6)
    ap.add_argument("--out", default=str(HERE / "alice_freq.json"))
    args = ap.parse_args()

    cands = json.loads(Path(args.candidates).read_text(encoding="utf-8"))["new"]
    tags = [c["tag"] for c in cands if c["count"] >= args.min_bfs_count]
    freq: dict[str, int] = json.loads(Path(args.out).read_text(encoding="utf-8")) if Path(args.out).exists() else {}
    todo = [t for t in tags if t not in freq]
    print(f"[freq] {len(tags)} tags, {len(todo)} to measure", flush=True)

    sess = requests.Session()
    sess.headers.update(HEADERS)
    for i, t in enumerate(todo, 1):
        freq[t] = pages_for(sess, t)
        if i % 50 == 0:
            Path(args.out).write_text(json.dumps(freq, ensure_ascii=False), encoding="utf-8")
            nz = sum(1 for v in freq.values() if v > 0)
            print(f"[freq] {i}/{len(todo)} measured, {nz} with results", flush=True)
        time.sleep(args.delay)

    Path(args.out).write_text(json.dumps(freq, ensure_ascii=False), encoding="utf-8")
    nz = sum(1 for v in freq.values() if v > 0)
    print(f"[freq] DONE: {len(freq)} tags, {nz} real (>=1 page)", flush=True)


if __name__ == "__main__":
    main()
