"""Data structures for tag_acquisition pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Observation:
    source: str       # "pixiv"
    keyword: str      # 搜索关键词
    raw_tag: str      # API 返回的原始标签


@dataclass
class SplitInfo:
    was_split: bool = False
    confidence: float = 1.0
    original_surface: str | None = None


@dataclass
class NormalizationInfo:
    nfkc_applied: bool = False
    fullwidth_normalized: bool = False
    whitespace_trimmed: bool = False
    symbol_compressed: bool = False


@dataclass
class Versions:
    schema_version: str = "v1"
    split_rule: str = "v1"
    blacklist_version: str = "v1"


@dataclass
class SurfaceCorpusEntry:
    surface: str                          # 当前 entry 的 surface token
    normalized: str                       # normalization 后的形式
    lang: str                             # cjk / ja_kana / mixed / abbrev / unknown
    sources: list[str] = field(default_factory=list)
    first_seen: str = ""                  # YYYY-MM-DD
    last_seen: str = ""                   # YYYY-MM-DD
    observations: list[Observation] = field(default_factory=list)
    split: SplitInfo = field(default_factory=SplitInfo)
    normalization: NormalizationInfo = field(default_factory=NormalizationInfo)
    versions: Versions = field(default_factory=Versions)

    def to_dict(self) -> dict:
        return {
            "surface": self.surface,
            "normalized": self.normalized,
            "lang": self.lang,
            "sources": self.sources,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "observations": [asdict(o) for o in self.observations],
            "split": asdict(self.split),
            "normalization": asdict(self.normalization),
            "versions": asdict(self.versions),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SurfaceCorpusEntry":
        obs = [Observation(**o) for o in d.get("observations", [])]
        sp = SplitInfo(**d.get("split", {}))
        nm = NormalizationInfo(**d.get("normalization", {}))
        vr = Versions(**d.get("versions", {}))
        return cls(
            surface=d["surface"],
            normalized=d["normalized"],
            lang=d["lang"],
            sources=d.get("sources", []),
            first_seen=d.get("first_seen", ""),
            last_seen=d.get("last_seen", ""),
            observations=obs,
            split=sp,
            normalization=nm,
            versions=vr,
        )
