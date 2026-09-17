#!/usr/bin/env python3
"""Harvest Pixiv novel tags via the public search AJAX endpoint.

For each keyword, page through search results and collect every tag attached to
the returned novels. Resumable: completed (keyword, page) pairs are recorded in
harvest_progress.json and skipped on a later run.

Usage:
    python harvest_pixiv.py --pages 8 --delay 1.0
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import requests

HERE = Path(__file__).parent
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Referer": "https://www.pixiv.net/",
           "Accept": "application/json"}
API = "https://www.pixiv.net/ajax/search/novels/{kw}"


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keywords", default=str(HERE / "keywords_zh.json"))
    ap.add_argument("--pages", type=int, default=8)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--out", default=str(HERE / "harvested_tags.json"))
    args = ap.parse_args()

    keywords = json.loads(Path(args.keywords).read_text(encoding="utf-8"))
    progress_path = HERE / "harvest_progress.json"
    done = set(load_json(progress_path, {"done": []})["done"])

    tag_counter: Counter[str] = Counter(load_json(Path(args.out), {}))
    novel_count = 0
    sess = requests.Session()
    sess.headers.update(HEADERS)

    for kw in keywords:
        for page in range(1, args.pages + 1):
            key = f"{kw}|{page}"
            if key in done:
                continue
            url = API.format(kw=requests.utils.quote(kw))
            params = {"word": kw, "order": "date_d", "mode": "all",
                      "p": page, "s_mode": "s_tag"}
            tags_here = []
            for attempt in range(3):
                try:
                    r = sess.get(url, params=params, timeout=20)
                    if r.status_code == 200:
                        body = (r.json() or {}).get("body", {}) or {}
                        data = (body.get("novel", {}) or {}).get("data", []) or []
                        for nov in data:
                            tags_here.extend(nov.get("tags", []) or [])
                            novel_count += 1
                        break
                    time.sleep(3)
                except Exception:
                    time.sleep(3)
            for t in tags_here:
                if isinstance(t, str) and t.strip():
                    tag_counter[t.strip()] += 1
            done.add(key)
            if len(done) % 25 == 0:
                progress_path.write_text(
                    json.dumps({"done": sorted(done)}, ensure_ascii=False),
                    encoding="utf-8")
                Path(args.out).write_text(
                    json.dumps(dict(tag_counter.most_common()), ensure_ascii=False, indent=1),
                    encoding="utf-8")
                print(f"[harvest] {len(done)} pages, {novel_count} novels, "
                      f"{len(tag_counter)} unique tags", flush=True)
            time.sleep(args.delay)

    progress_path.write_text(json.dumps({"done": sorted(done)}, ensure_ascii=False),
                             encoding="utf-8")
    Path(args.out).write_text(
        json.dumps(dict(tag_counter.most_common()), ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"[harvest] DONE: {len(done)} pages, {novel_count} novels, "
          f"{len(tag_counter)} unique tags -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
