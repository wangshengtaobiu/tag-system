#!/usr/bin/env python3
"""Harvest alicesw.com (爱丽丝书屋) novel TAGS.

Tags live only on search result pages, rendered as `标签：#a #b ...` where each
tag links to /search?q=<tag>&f=tag. So we seed from a tag list and BFS: every
result page exposes the tags of its 10 novels and, transitively, new tags.

Pagination: /search.html?q=<tag>&f=tag&sort=relevance&p=<N>&serialize=

Usage:
    python harvest_alicesw.py --max-requests 800 --pages-per-tag 3
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
from collections import Counter, deque
from pathlib import Path

import requests

HERE = Path(__file__).parent
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Referer": "https://www.alicesw.com/",
           "Accept": "text/html"}
SEARCH = "https://www.alicesw.com/search.html"
# tag links look like  /search?q=<encoded>&f=tag  or  /search.html?q=<encoded>&f=tag
_TAG_RE = re.compile(r"/search(?:\.html)?\?q=([^&\"'\s]+)&(?:amp;)?f=tag")

SEEDS = [
    "绿母", "小马拉大车", "NTR", "催眠", "熟女", "痴女", "调教", "重口", "乱伦", "母子",
    "人妻", "萝莉", "正太", "伪娘", "百合", "耽美", "媚黑", "露出", "多P", "群交",
]


def load_json(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-requests", type=int, default=800)
    ap.add_argument("--pages-per-tag", type=int, default=3)
    ap.add_argument("--delay", type=float, default=0.8)
    ap.add_argument("--out", default=str(HERE / "alicesw_harvested.json"))
    ap.add_argument("--seeds", default=str(HERE / "keywords_zh.json"))
    args = ap.parse_args()

    seeds = list(load_json(Path(args.seeds), [])) + SEEDS
    tag_counter: Counter[str] = Counter(load_json(Path(args.out), {}))
    progress_path = HERE / "alicesw_progress.json"
    done = set(load_json(progress_path, {"done": []})["done"])

    queue = deque(seeds)
    seen_q = set(seeds)
    sess = requests.Session()
    sess.headers.update(HEADERS)
    requests_made = 0

    while queue and requests_made < args.max_requests:
        q = queue.popleft()
        for p in range(1, args.pages_per_tag + 1):
            key = f"{q}|{p}"
            if key in done:
                continue
            if requests_made >= args.max_requests:
                break
            params = {"q": q, "f": "tag", "sort": "relevance", "p": p, "serialize": ""}
            html = ""
            for _ in range(3):
                try:
                    r = sess.get(SEARCH, params=params, timeout=20)
                    requests_made += 1
                    if r.status_code == 200:
                        html = r.text
                        break
                    time.sleep(2)
                except Exception:
                    time.sleep(2)
            tags = [urllib.parse.unquote(m) for m in _TAG_RE.findall(html)]
            for t in tags:
                t = t.strip()
                if t and len(t) <= 40:
                    tag_counter[t] += 1
                    if t not in seen_q:
                        seen_q.add(t)
                        queue.append(t)
            done.add(key)
            if requests_made % 25 == 0:
                progress_path.write_text(json.dumps({"done": sorted(done)}, ensure_ascii=False),
                                         encoding="utf-8")
                Path(args.out).write_text(json.dumps(dict(tag_counter.most_common()),
                                                     ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"[alice] req={requests_made} queue={len(queue)} "
                      f"tags={len(tag_counter)}", flush=True)
            time.sleep(args.delay)

    progress_path.write_text(json.dumps({"done": sorted(done)}, ensure_ascii=False),
                             encoding="utf-8")
    Path(args.out).write_text(json.dumps(dict(tag_counter.most_common()),
                                         ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[alice] DONE: req={requests_made} unique_tags={len(tag_counter)} -> {args.out}",
          flush=True)


if __name__ == "__main__":
    main()
