#!/usr/bin/env python3
"""
噪音分析工具 — 采集原始标签，按模式分类，输出分析报告。

用法（在 tag-system 根目录下运行）：
    python -m tag_acquisition.analyze_noise
    python -m tag_acquisition.analyze_noise --keywords 扩张 束缚 --pages 5
    python -m tag_acquisition.analyze_noise --output noise_report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

# 代理
PROXY = {"http": "http://172.21.192.1:7897", "https": "http://172.21.192.1:7897"}
DEFAULT_KEYWORDS = ["扩张", "重口", "NTR", "SM", "痴女", "束缚", "人体改造", "自虐", "灌肠", "破坏"]

# 噪音分类规则
_PATTERNS = {
    "纯英文": re.compile(r"^[A-Za-z]+$"),
    "纯数字": re.compile(r"^\d+$"),
    "英文+数字": re.compile(r"^[A-Za-z0-9_\-]+$"),
    "纯日文假名": re.compile(r"^[\u3040-\u309F\u30A0-\u30FF]+$"),
    "日文为主(含少量汉字)": re.compile(r"^[\u3040-\u309F\u30A0-\u30FF\u4e00-\u9fa5]+$"),
    "含特殊符号": re.compile(r"[^\w\u4e00-\u9fa5\u3040-\u309F\u30A0-\u30FF\s]"),
    "单汉字": re.compile(r"^[\u4e00-\u9fa5]$"),
    "纯标点": re.compile(r"^[/／\s,，|｜._#＃\-]+$"),
}

_HAN = re.compile(r"[\u4e00-\u9fa5]")


def classify_tag(tag: str) -> str:
    """Classify a raw tag into a noise category."""
    for name, pat in _PATTERNS.items():
        if pat.match(tag):
            return name
    if not _HAN.search(tag):
        return "无汉字"
    return "有效中文"


def collect_raw_tags(keywords: list[str], pages: int) -> Counter[str]:
    """Collect all raw tags (before any filtering) from Pixiv."""
    counter: Counter[str] = Counter()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.pixiv.net/",
    }

    for kw in keywords:
        for page in range(1, pages + 1):
            url = (
                f"https://www.pixiv.net/ajax/search/novels/{kw}"
                f"?word={kw}&order=date_d&mode=all&p={page}&s_mode=s_tag"
            )
            try:
                resp = requests.get(url, headers=headers, proxies=PROXY, timeout=15)
                if resp.status_code != 200:
                    print(f"  [{kw}] 第{page}页 请求失败({resp.status_code})")
                    break
                data = resp.json()
                novels = data.get("body", {}).get("novel", {}).get("data", [])
                if not novels:
                    print(f"  [{kw}] 第{page}页 无数据")
                    break
                for novel in novels:
                    for t in novel.get("tags", []):
                        counter[t] += 1
                print(f"  [{kw}] 第{page}页 OK，累计原始标签数: {len(counter)}")
                time.sleep(2)
            except Exception as e:
                print(f"  [{kw}] 第{page}页 错误: {e}")
                break
    return counter


def analyze(counter: Counter[str], top_n: int = 0) -> dict:
    """Analyze noise distribution."""
    categories: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for tag, count in counter.most_common():
        cat = classify_tag(tag)
        categories[cat].append((tag, count))

    # Summary
    summary = {}
    total_tags = len(counter)
    total_count = sum(counter.values())
    for cat, tags in sorted(categories.items(), key=lambda x: -len(x[1])):
        cat_count = sum(c for _, c in tags)
        summary[cat] = {
            "count": len(tags),
            "total_mentions": cat_count,
            "tag_ratio": f"{len(tags)/total_tags*100:.1f}%",
            "mention_ratio": f"{cat_count/total_count*100:.1f}%",
            "examples": tags[:10],  # top 10 examples
        }

    # Top N most frequent tags by category
    if top_n > 0:
        top_by_cat = {}
        for cat, tags in categories.items():
            top_by_cat[cat] = tags[:top_n]
    else:
        top_by_cat = None

    return {
        "total_unique_tags": total_tags,
        "total_mentions": total_count,
        "summary": summary,
        "top_by_category": top_by_cat,
    }


def main():
    parser = argparse.ArgumentParser(description="噪音分析工具")
    parser.add_argument("--keywords", "-k", nargs="*", default=DEFAULT_KEYWORDS)
    parser.add_argument("--pages", "-p", type=int, default=3, help="每个关键词采集页数")
    parser.add_argument("--output", "-o", default="noise_report.json")
    parser.add_argument("--top", type=int, default=20, help="每类显示前N个标签示例")
    args = parser.parse_args()

    print(f"采集: {len(args.keywords)} 个关键词 × {args.pages} 页")
    counter = collect_raw_tags(args.keywords, args.pages)

    if not counter:
        print("\n未采集到任何标签，请检查代理配置")
        return

    print(f"\n共采集 {len(counter)} 个原始标签，正在分析...")
    report = analyze(counter, top_n=args.top)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print(f"噪音分析报告 — {args.output}")
    print(f"{'='*60}")
    print(f"  独立标签总数: {report['total_unique_tags']}")
    print(f"  总出现次数:   {report['total_mentions']}")
    print()
    for cat, info in report["summary"].items():
        print(f"  [{cat}]")
        print(f"    标签数: {info['count']} ({info['tag_ratio']})")
        print(f"    出现次数: {info['total_mentions']} ({info['mention_ratio']})")
        if info["examples"]:
            print(f"    示例: {', '.join(t for t, _ in info['examples'][:10])}")
        print()


if __name__ == "__main__":
    main()
