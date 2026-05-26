"""Lang detection + quality filter."""

from __future__ import annotations


def detect_lang(tag: str) -> str:
    """Estimate language of a surface tag.

    Returns one of: cjk / ja_kana / mixed / abbrev / unknown
    """
    has_han = any("\u4e00" <= c <= "\u9fff" for c in tag)
    has_kana = any(
        "\u3040" <= c <= "\u309F" or "\u30A0" <= c <= "\u30FF" for c in tag
    )
    has_latin = any(c.isascii() and c.isalpha() for c in tag)

    if has_han and has_kana:
        return "mixed"
    if has_kana:
        return "ja_kana"
    if has_han:
        return "cjk"
    # Latin: check if it looks like an abbreviation
    if has_latin and len(tag) <= 5 and tag.isascii() and tag.isalpha():
        return "abbrev"
    if has_latin:
        return "unknown"  # Could be romaji, treat as unknown

    return "unknown"


def quality_check(tag: str, blacklist: set[str]) -> bool:
    """Check if tag passes quality filter. Returns True if KEEP.

    Rejects:
    - empty
    - blacklist exact match
    - emoji (simplified)
    - pure punctuation
    - pure numeric
    """
    if not tag:
        return False
    if tag in blacklist:
        return False
    if tag.isdigit():
        return False
    # Pure punctuation (no alphanumeric, no CJK)
    if all(not c.isalnum() and not ("\u4e00" <= c <= "\u9fff") for c in tag):
        return False
    # Simplified emoji check
    if any("\U0001F600" <= c <= "\U0001F64F" for c in tag):
        return False
    return True
