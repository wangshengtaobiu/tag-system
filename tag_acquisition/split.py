"""Three-layer split engine: protected phrase → delimiter policy → heuristic rollback."""

from __future__ import annotations

import re
from pathlib import Path

# Delimiter categories
_HIGH_CONF_DELIMITERS = re.compile(r"[/／|｜]+")
_MEDIUM_CONF_DELIMITERS = re.compile(r"[,，#＃]+")
_LOW_CONF_DELIMITERS = re.compile(r"[_\-\.]+")

# All delimiters combined (for initial splitting attempt)
_ALL_DELIMITERS = re.compile(r"[/／|｜,，#＃]+")  # 低可信默认不拆，只拆高+中


def load_protected_phrases(config_path: str | Path | None = None) -> set[str]:
    """Load protected phrases from config. Exact match set."""
    # Default built-in set
    protected = {
        "父女丼", "SM調教", "SM调教", "NTR人妻", "逆NTR",
        "JK制服", "ASMR", "メス堕ち", "オホ声",
        "3P", "4P", "R18", "R18G",
        "NTR", "SM", "JK",
    }
    if config_path:
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            extra = cfg.get("protected_phrases", [])
            if isinstance(extra, list):
                protected.update(extra)
        except Exception:
            pass
    return protected


def load_blacklist(config_path: str | Path | None = None) -> set[str]:
    """Load blacklist from config."""
    blacklist = {
        "中文", "中国语", "中国語", "中文翻訳", "中国語翻訳",
        "小説", "小说", "小説版", "漫画版", "漫画", "イラスト",
        "男性向け", "女性向け", "腐向け", "一般向け",
        "二次創作", "同人", "原创", "オリジナル", "パロディ",
        "R18", "R-18", "R18G", "R-18G", "R15", "R-15",
        "AI", "AI生成",
        "タグ", "複数タグ", "単タグ",
    }
    if config_path:
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            extra = cfg.get("blacklist", [])
            if isinstance(extra, list):
                blacklist.update(extra)
        except Exception:
            pass
    return blacklist


def _is_garbage(tag: str, blacklist: set[str]) -> bool:
    """Check if a tag is obviously garbage.

    Rejects:
    - empty
    - pure punctuation
    - emoji (simplified check)
    - pure numeric
    - blacklist exact match
    """
    if not tag:
        return True
    if tag in blacklist:
        return True
    if tag.isdigit():
        return True
    # Pure punctuation
    if all(not c.isalnum() and not _is_cjk(c) for c in tag):
        return True
    return False


def _is_cjk(c: str) -> bool:
    return "\u4e00" <= c <= "\u9fff"


def _has_kana(tag: str) -> bool:
    return any("\u3040" <= c <= "\u309F" or "\u30A0" <= c <= "\u30FF" for c in tag)


def _is_abbrev(tag: str) -> bool:
    """Check if tag looks like a known abbreviation (2-5 uppercase letters or common terms)."""
    if len(tag) < 2 or len(tag) > 5:
        return False
    return tag.isascii() and tag.isalpha() and tag.isupper()


def _split_heuristic_valid(candidates: list[str], blacklist: set[str]) -> bool:
    """Validate all split candidates. Reject if ANY is garbage."""
    for c in candidates:
        if _is_garbage(c, blacklist):
            return False
    return True


def split_tag(
    tag: str,
    protected: set[str],
    blacklist: set[str],
) -> tuple[list[str], bool, float, str | None]:
    """Three-layer split.

    Returns:
        (candidates, was_split, confidence, original_surface)

    Rules:
    - Protected phrase exact match → no split
    - High-confidence delimiters → split
    - Medium-confidence delimiters → split + heuristic validation
    - Low-confidence delimiters → no split
    - Any candidate fails heuristic → rollback (keep original)
    """
    # Layer 1: Protected phrase check
    if tag in protected:
        return [tag], False, 1.0, None

    # Layer 2: Try high-confidence delimiters first
    if _HIGH_CONF_DELIMITERS.search(tag):
        parts = [p.strip() for p in _HIGH_CONF_DELIMITERS.split(tag) if p.strip()]
        if len(parts) > 1 and _split_heuristic_valid(parts, blacklist):
            return parts, True, 0.95, tag

    # Layer 3: Try medium-confidence delimiters
    if _MEDIUM_CONF_DELIMITERS.search(tag):
        parts = [p.strip() for p in _MEDIUM_CONF_DELIMITERS.split(tag) if p.strip()]
        if len(parts) > 1 and _split_heuristic_valid(parts, blacklist):
            return parts, True, 0.80, tag

    # Low-confidence delimiters: default no split
    return [tag], False, 1.0, None
