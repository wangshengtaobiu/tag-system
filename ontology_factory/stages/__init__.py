"""
Ontology Factory — Stage Registry & Base Classes
Frozen architecture: router_v3_lite, F1-F10 invariants.
"""
from __future__ import annotations

import json
import time
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from collections import Counter


# =============================================================================
# Frozen Constants (F1-F10 invariants)
# =============================================================================

ONTOLOGY_TYPES = ("flat_behavior", "specialized_behavior", "graph_native", "meta_style")
TRUSTED_RELATION_TYPES = ("specialization_of", "role_pair", "opposite_of", "context_of")
MAX_CANONICAL_ID_DEPTH = 3
CANONICAL_ID_PATTERN = r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?$"


class StageStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Severity(Enum):
    CRITICAL = "critical"   # Blocking: duplicate IDs, namespace violations
    HIGH = "high"           # Low confidence, parent cycles
    MEDIUM = "medium"       # Namespace conflicts, semantic type mismatch
    LOW = "low"             # Advisory suggestions


@dataclass
class StageResult:
    stage_id: str
    status: StageStatus
    output_file: str | None = None
    stats: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    review_items: list[dict] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status in (StageStatus.PASSED, StageStatus.SKIPPED)


@dataclass
class ReviewItem:
    """Review queue item for Pro/human review."""
    item_id: str
    tag_name: str
    canonical_id: str | None
    review_type: str  # namespace_conflict, low_confidence, duplicate_candidate, etc.
    severity: Severity
    confidence: float
    description: str
    suggested_fix: dict | None = None
    escalation_rule: str = ""
    context: dict = field(default_factory=dict)
    resolved: bool = False
    resolution: str | None = None

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "tag_name": self.tag_name,
            "canonical_id": self.canonical_id,
            "review_type": self.review_type,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "description": self.description,
            "suggested_fix": self.suggested_fix,
            "escalation_rule": self.escalation_rule,
            "context": self.context,
            "resolved": self.resolved,
            "resolution": self.resolution,
        }


@dataclass
class PipelineContext:
    """Shared state across all pipeline stages."""
    profile: dict
    config: dict
    raw_tags: list[dict]
    normalized_entries: list[dict] = field(default_factory=list)
    frozen_namespaces: dict = field(default_factory=dict)
    alias_graph: dict = field(default_factory=dict)
    review_queue: list[ReviewItem] = field(default_factory=list)
    stage_results: dict[str, StageResult] = field(default_factory=dict)
    work_dir: Path = Path(".")
    exports_dir: Path = Path("./exports")

    def resolve_entry_by_name(self, name: str) -> dict | None:
        for e in self.normalized_entries:
            if e.get("name") == name or e.get("original_name") == name:
                return e
        return None

    def resolve_entry_by_cid(self, cid: str) -> dict | None:
        for e in self.normalized_entries:
            if e.get("canonical_id") == cid:
                return e
        return None

    def primary_entries(self) -> list[dict]:
        return [e for e in self.normalized_entries if not e.get("is_alias_of") and not e.get("is_duplicate_of")]

    def alias_entries(self) -> list[dict]:
        return [e for e in self.normalized_entries if e.get("is_alias_of") or e.get("is_duplicate_of")]


# =============================================================================
# Stage Base Class
# =============================================================================

class BaseStage(ABC):
    """Abstract base for all pipeline stages."""

    stage_id: str
    stage_name: str
    owner: str  # "script" | "flash" | "pro" | "flash+pro"

    def __init__(self, ctx: PipelineContext):
        self.ctx = ctx
        self.profile = ctx.profile
        self.config = ctx.config

    @abstractmethod
    def run(self) -> StageResult:
        """Execute the stage. Return StageResult."""

    def _load_json(self, path: Path) -> dict | list:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_json(self, path: Path, data: Any):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _hash_file(self, path: Path) -> str:
        if not path.exists():
            return ""
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# =============================================================================
# Utility Functions
# =============================================================================

def validate_canonical_id(cid: str) -> bool:
    """Check canonical_id matches namespace.descriptor[.detail] format."""
    import re
    return bool(re.match(CANONICAL_ID_PATTERN, cid))


def count_duplicate_cids(entries: list[dict]) -> dict[str, int]:
    """Count duplicate canonical IDs across primary entries."""
    primary = [e for e in entries if not (e.get("is_alias_of") or e.get("is_duplicate_of"))]
    cids = Counter(e.get("canonical_id", "") for e in primary)
    return {c: n for c, n in cids.items() if n > 1}


def build_semantic_summary(entry: dict) -> str:
    """Build short semantic summary for search display."""
    definition = entry.get("definition", "")[:100]
    distinction = entry.get("distinction", "")[:60]
    if distinction:
        return f"{definition} [{distinction}]"
    return definition


def build_retrieval_embeddings(entries: list[dict]) -> list[dict]:
    """Build retrieval-optimized entries from frozen ontology entries."""
    retrieval_entries = []
    for e in entries:
        if e.get("is_alias_of") or e.get("is_duplicate_of"):
            continue

        name = e.get("original_name", e.get("name", ""))
        aliases = e.get("aliases", [])[:5]
        definition = e.get("definition", "")[:200]
        distinction = e.get("distinction", "")[:150]
        examples = e.get("examples", [])[:5]

        emb_parts = [name]
        if aliases:
            emb_parts.append(" | ".join(aliases))
        if definition:
            emb_parts.append(definition)
        if distinction:
            emb_parts.append(f"区别于: {distinction}")
        if examples:
            emb_parts.append("示例: " + "、".join(examples))

        embedding_text = " | ".join(p for p in emb_parts if p)
        semantic_summary = build_semantic_summary(e)

        expansion_terms = [
            f"ns:{e.get('namespace', '')}",
            f"type:{e.get('semantic_type', '')}",
            f"cat:{e.get('category', '')}",
        ] + examples[:3]
        for axis in e.get("semantic_axes", []):
            expansion_terms.append(f"axis:{axis}")

        retrieval_entries.append({
            "canonical_id": e.get("canonical_id"),
            "original_name": name,
            "namespace": e.get("namespace"),
            "semantic_type": e.get("semantic_type"),
            "category": e.get("category"),
            "ontology_type": e.get("ontology_type"),
            "embedding_text": embedding_text,
            "semantic_summary": semantic_summary,
            "retrieval_aliases": [name] + aliases[:10],
            "candidate_expansion_terms": expansion_terms[:15],
            "parent_canonical_id": e.get("parent_canonical_id"),
            "trusted_relations": e.get("trusted_relations", []),
            "confidence": e.get("confidence", 0),
            "v3_validated": e.get("v3_validated", False),
        })

    return retrieval_entries


# =============================================================================
# Stage Registry
# =============================================================================

STAGE_REGISTRY: dict[str, type[BaseStage]] = {}


def register_stage(cls: type[BaseStage]):
    """Decorator to register a pipeline stage."""
    STAGE_REGISTRY[cls.stage_id] = cls
    return cls
