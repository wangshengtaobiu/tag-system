"""Corpus management: dedup, append, export snapshot."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .schema import SurfaceCorpusEntry, Observation, SplitInfo, NormalizationInfo, Versions


def dedup_key(entry: SurfaceCorpusEntry) -> tuple[str, str]:
    return (entry.normalized, entry.lang)


def append_to_corpus(
    existing: list[SurfaceCorpusEntry],
    new_entries: list[SurfaceCorpusEntry],
    today: str | None = None,
) -> list[SurfaceCorpusEntry]:
    """Merge new entries into existing corpus. Append-only, dedup by (normalized, lang)."""
    if today is None:
        today = date.today().isoformat()

    index: dict[tuple[str, str], int] = {}
    for i, e in enumerate(existing):
        index[dedup_key(e)] = i

    for ne in new_entries:
        key = dedup_key(ne)
        if key in index:
            # Merge: append observations, update last_seen
            existing_entry = existing[index[key]]
            # Dedup observations
            existing_obs = {(o.source, o.keyword, o.raw_tag) for o in existing_entry.observations}
            for obs in ne.observations:
                if (obs.source, obs.keyword, obs.raw_tag) not in existing_obs:
                    existing_entry.observations.append(obs)
                    existing_obs.add((obs.source, obs.keyword, obs.raw_tag))
            existing_entry.last_seen = max(existing_entry.last_seen, ne.last_seen)
            if ne.source not in existing_entry.sources:
                existing_entry.sources.extend(ne.sources)
        else:
            existing.append(ne)

    return existing


def export_snapshot(
    entries: list[SurfaceCorpusEntry],
    output_path: str | Path,
    schema_version: str = "v1",
) -> Path:
    """Export corpus as JSONL snapshot. One SurfaceCorpusEntry per line."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
    return output_path
