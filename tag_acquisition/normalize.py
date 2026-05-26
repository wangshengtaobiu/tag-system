"""Surface normalization: NFKC, fullwidth, trim, delimiter compress."""

from __future__ import annotations

import re
import unicodedata

# Repeated delimiter compress: collapse consecutive same-type delimiters
_REPEATED_DELIM = re.compile(r"([/／|｜,，#＃_\-\.]{2,})")


def normalize_surface(tag: str) -> tuple[str, dict[str, bool]]:
    """Apply surface normalization. Returns (normalized, applied_flags).

    Operations (deterministic, order matters):
    1. NFKC normalization (includes fullwidth → halfwidth)
    2. Whitespace trim
    3. Repeated delimiter compress
    """
    applied = {
        "nfkc_applied": False,
        "fullwidth_normalized": False,
        "whitespace_trimmed": False,
        "symbol_compressed": False,
    }

    # Step 1: NFKC (handles fullwidth → halfwidth)
    nfkc = unicodedata.normalize("NFKC", tag)
    if nfkc != tag:
        applied["nfkc_applied"] = True
        # Detect if fullwidth was involved
        has_fullwidth = any(
            unicodedata.east_asian_width(c) in ("F", "W") for c in tag
        )
        applied["fullwidth_normalized"] = has_fullwidth
    tag = nfkc

    # Step 2: Trim whitespace
    trimmed = tag.strip()
    if trimmed != tag:
        applied["whitespace_trimmed"] = True
    tag = trimmed

    # Step 3: Compress repeated delimiters
    def _compress(m: re.Match) -> str:
        s = m.group(1)
        # Pick first char as representative
        return s[0]

    compressed = _REPEATED_DELIM.sub(_compress, tag)
    if compressed != tag:
        applied["symbol_compressed"] = True
    tag = compressed

    return tag, applied
