"""Pixiv tag collector — search novels, raw cache, pipeline orchestration."""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import date
from pathlib import Path

import requests

from .schema import SurfaceCorpusEntry, Observation, SplitInfo, NormalizationInfo, Versions
from .normalize import normalize_surface
from .split import split_tag, load_protected_phrases, load_blacklist
from .filter import detect_lang, quality_check
from .corpus import append_to_corpus, export_snapshot


class PixivCollector:
    """Collect tags from Pixiv novel search results."""

    def __init__(self, config: dict):
        pixiv_cfg = config.get("pixiv", {})
        proxy_cfg = config.get("proxy", {})
        coll_cfg = config.get("collection", {})
        output_cfg = config.get("output", {})

        self.user_agent = pixiv_cfg.get("user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        self.referer = pixiv_cfg.get("referer", "https://www.pixiv.net/")

        # Proxy
        self.proxies: dict[str, str] | None = None
        if proxy_cfg.get("http"):
            self.proxies = {"http": proxy_cfg["http"], "https": proxy_cfg.get("https", proxy_cfg["http"])}

        self.keywords: list[str] = coll_cfg.get("search_keywords", [])
        self.pages_per_keyword: int = coll_cfg.get("pages_per_keyword", 10)
        self.request_delay: float = coll_cfg.get("request_delay", 2.0)
        self.timeout: int = coll_cfg.get("timeout", 15)
        self.max_retries: int = coll_cfg.get("max_retries", 3)
        self.target_tag_count: int = coll_cfg.get("target_tag_count", 3000)

        # Paths
        self.output_dir = Path(output_cfg.get("output_dir", "."))
        self.raw_dir = self.output_dir / "raw" / "pixiv"
        self.corpus_dir = self.output_dir / "corpus"
        self.export_dir = self.output_dir / "exports"
        self.state_dir = self.output_dir / "state"

        # Config paths for protected phrases / blacklist
        self.config_path = config.get("_config_path", None)
        self.protected = load_protected_phrases(self.config_path)
        self.blacklist = load_blacklist(self.config_path)

    def collect(self) -> list[SurfaceCorpusEntry]:
        """Run full collection pipeline."""
        today = date.today().isoformat()
        tag_counter: Counter[str] = Counter()
        raw_tags_seen: dict[str, list[Observation]] = {}  # normalized → observations

        headers = {
            "User-Agent": self.user_agent,
            "Referer": self.referer,
        }

        for keyword in self.keywords:
            print(f"\n--- 正在扫描关键词: [{keyword}] ---")
            for page in range(1, self.pages_per_keyword + 1):
                # Check resume state
                if self._is_page_done(keyword, page):
                    print(f"  第 {page} 页已采集，跳过")
                    continue

                url = (
                    f"https://www.pixiv.net/ajax/search/novels/{keyword}"
                    f"?word={keyword}&order=date_d&mode=all&p={page}"
                    f"&s_mode=s_tag"
                )
                ok, novel_tags = self._fetch_page(url, headers, keyword, page)
                if not ok:
                    break

                # Cache raw response
                self._cache_raw(keyword, page, novel_tags)

                # Process each raw tag
                for raw_tag in novel_tags:
                    # Normalize
                    normalized, norm_info = normalize_surface(raw_tag)

                    # Protected phrase check + split
                    candidates, was_split, split_conf, original = split_tag(
                        normalized, self.protected, self.blacklist
                    )

                    # For each candidate
                    for candidate in candidates:
                        # Quality filter
                        if not quality_check(candidate, self.blacklist):
                            continue

                        # Lang detection
                        lang = detect_lang(candidate)

                        # Dedup key
                        key = candidate

                        # Count
                        tag_counter[key] += 1

                        # Track observations
                        obs = Observation(source="pixiv", keyword=keyword, raw_tag=raw_tag)
                        if key not in raw_tags_seen:
                            raw_tags_seen[key] = []
                        raw_tags_seen[key].append(obs)

                self._mark_page_done(keyword, page)
                print(f"[{keyword}] 第 {page} 页完成，累计独立标签: {len(tag_counter)}")

                time.sleep(self.request_delay)

            if len(tag_counter) >= self.target_tag_count * 2:
                print(f"已收集 {len(tag_counter)} 个独立标签，停止后续关键词")
                break

        # Build SurfaceCorpusEntry list
        entries = []
        for surface, count in tag_counter.most_common(self.target_tag_count):
            obs_list = raw_tags_seen.get(surface, [])
            # Deduplicate observations
            seen_obs = set()
            unique_obs = []
            for o in obs_list:
                key = (o.source, o.keyword, o.raw_tag)
                if key not in seen_obs:
                    seen_obs.add(key)
                    unique_obs.append(o)

            entry = SurfaceCorpusEntry(
                surface=surface,
                normalized=surface,  # already normalized above
                lang=detect_lang(surface),
                sources=["pixiv"],
                first_seen=today,
                last_seen=today,
                observations=unique_obs,
                split=SplitInfo(was_split=False, confidence=1.0, original_surface=None),
                normalization=NormalizationInfo(nfkc_applied=True, fullwidth_normalized=True),
                versions=Versions(),
            )
            entries.append(entry)

        # Append to corpus
        corpus_path = self.corpus_dir / "tags.jsonl"
        existing = self._load_corpus(corpus_path)
        merged = append_to_corpus(existing, entries, today)
        corpus_path.parent.mkdir(parents=True, exist_ok=True)
        with open(corpus_path, "w", encoding="utf-8") as f:
            for e in merged:
                f.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")

        # Export snapshot
        snapshot_name = f"corpus_{Versions().schema_version}_{today.replace('-', '')}.jsonl"
        snapshot_path = self.export_dir / snapshot_name
        export_snapshot(merged, snapshot_path)

        # Also write latest.jsonl for enrichment to consume
        latest_path = self.export_dir / "latest.jsonl"
        export_snapshot(merged, latest_path)

        print(f"\n采集完成！共 {len(entries)} 个标签，输出到 {snapshot_path}")
        return merged

    def _is_page_done(self, keyword: str, page: int) -> bool:
        """Check resume state."""
        state_file = self.state_dir / "resume.json"
        if not state_file.exists():
            return False
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
        pages = state.get("pages_completed", {})
        done = pages.get(keyword, {})
        max_page = done.get("max_contiguous_page", 0)
        holes = done.get("holes", [])
        return page <= max_page and page not in holes

    def _mark_page_done(self, keyword: str, page: int):
        """Update resume state."""
        state_file = self.state_dir / "resume.json"
        state = {"pages_completed": {}}
        if state_file.exists():
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)

        pages = state.setdefault("pages_completed", {}).setdefault(keyword, {
            "max_contiguous_page": 0,
            "holes": [],
        })
        max_page = pages["max_contiguous_page"]
        holes = pages["holes"]

        if page == max_page + 1:
            pages["max_contiguous_page"] = page
            # Check if next hole is now filled
            while (max_page + 1) in holes:
                holes.remove(max_page + 1)
                pages["max_contiguous_page"] = max_page + 1
        elif page > max_page + 1:
            holes.append(page)

        state["last_run"] = date.today().isoformat()
        state["schema_version"] = "v1"
        state["split_rule"] = "v1"

        self.state_dir.mkdir(parents=True, exist_ok=True)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _cache_raw(self, keyword: str, page: int, novel_tags: list[str]):
        """Cache raw API response."""
        cache_file = self.raw_dir / keyword / f"{page}.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"keyword": keyword, "page": page, "tags": novel_tags}, f, ensure_ascii=False)

    def _load_corpus(self, path: Path) -> list[SurfaceCorpusEntry]:
        """Load existing corpus from JSONL."""
        if not path.exists():
            return []
        entries = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(SurfaceCorpusEntry.from_dict(json.loads(line)))
        return entries

    def _fetch_page(
        self,
        url: str,
        headers: dict,
        keyword: str,
        page: int,
    ) -> tuple[bool, list[str]]:
        """Fetch one page. Returns (success, list_of_raw_tags)."""
        for attempt in range(self.max_retries):
            try:
                resp = requests.get(
                    url, headers=headers, proxies=self.proxies, timeout=self.timeout
                )
                if resp.status_code != 200:
                    print(f"请求失败 ({resp.status_code})")
                    return False, []

                data = resp.json()
                novel_data = data.get("body", {}).get("novel", {}).get("data", [])
                if not novel_data:
                    print(f"[{keyword}] 第 {page} 页无数据，跳过")
                    return False, []

                raw_tags = []
                for novel in novel_data:
                    raw_tags.extend(novel.get("tags", []))
                return True, raw_tags

            except Exception as e:
                print(f"错误: {e}，尝试 {attempt + 1}/{self.max_retries}")
                if attempt < self.max_retries - 1:
                    time.sleep(5)
        return False, []
