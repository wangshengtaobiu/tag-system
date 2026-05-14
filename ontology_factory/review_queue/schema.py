"""
Review Queue System — Schema and management for human-in-the-loop review.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from pathlib import Path
import json
import hashlib
import time


class ReviewType(str, Enum):
    NAMESPACE_CONFLICT = "namespace_conflict"
    LOW_CONFIDENCE = "low_confidence"
    DUPLICATE_CANDIDATE = "duplicate_candidate"
    PARENT_CYCLE_RISK = "parent_cycle_risk"
    ONTOLOGY_SHAPE_CONFLICT = "ontology_shape_conflict"
    ALIAS_RISK = "alias_risk"
    SEMANTIC_TYPE_MISMATCH = "semantic_type_mismatch"
    RELATION_UNCERTAINTY = "relation_uncertainty"
    DEPTH_VIOLATION = "depth_violation"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    OVERRIDDEN = "overridden"
    QUARANTINED = "quarantined"
    SKIPPED = "skipped"
    ESCALATED = "escalated"


# =============================================================================
# Review Item Schema (JSON-compatible)
# =============================================================================

REVIEW_ITEM_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Ontology Factory Review Item",
    "type": "object",
    "required": [
        "item_id", "tag_name", "review_type", "severity",
        "confidence", "description", "escalation_rule"
    ],
    "properties": {
        "item_id": {
            "type": "string",
            "description": "Unique review item ID (hash of tag_name + review_type)"
        },
        "tag_name": {
            "type": "string",
            "description": "Original tag name being reviewed"
        },
        "canonical_id": {
            "type": "string",
            "description": "Proposed canonical ID"
        },
        "review_type": {
            "type": "string",
            "enum": [rt.value for rt in ReviewType],
            "description": "Type of review required"
        },
        "severity": {
            "type": "string",
            "enum": [s.value for s in Severity],
            "description": "Severity level"
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Flash confidence score"
        },
        "description": {
            "type": "string",
            "description": "Human-readable explanation of the issue"
        },
        "suggested_fix": {
            "type": "object",
            "description": "Suggested fix from Flash or validator",
            "properties": {
                "action": {"type": "string"},
                "new_canonical_id": {"type": "string"},
                "new_namespace": {"type": "string"},
                "new_semantic_type": {"type": "string"},
                "new_parent": {"type": "string"},
                "reason": {"type": "string"}
            }
        },
        "escalation_rule": {
            "type": "string",
            "description": "When to escalate this item"
        },
        "context": {
            "type": "object",
            "description": "Additional context for the reviewer",
            "properties": {
                "batch_id": {"type": "integer"},
                "category": {"type": "string"},
                "namespace": {"type": "string"},
                "semantic_type": {"type": "string"},
                "definition": {"type": "string"},
                "distinction": {"type": "string"},
                "aliases": {"type": "array", "items": {"type": "string"}},
                "parent_name": {"type": "string"},
                "similar_tags": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "canonical_id": {"type": "string"},
                            "similarity_reason": {"type": "string"}
                        }
                    }
                }
            }
        },
        "status": {
            "type": "string",
            "enum": [s.value for s in ReviewStatus],
            "default": "pending"
        },
        "resolution": {
            "type": "string",
            "description": "Final resolution decision"
        },
        "resolved_at": {
            "type": "string",
            "format": "date-time"
        },
        "resolved_by": {
            "type": "string",
            "enum": ["pro", "human", "auto"]
        }
    }
}

# =============================================================================
# Review Item Factory
# =============================================================================

def make_review_item(
    tag_name: str,
    review_type: ReviewType,
    severity: Severity,
    confidence: float,
    description: str,
    canonical_id: str | None = None,
    suggested_fix: dict | None = None,
    context: dict | None = None,
) -> dict:
    """Create a review item conforming to schema."""
    item_id = hashlib.md5(f"{tag_name}:{review_type.value}:{time.time()}".encode()).hexdigest()[:12]

    return {
        "item_id": item_id,
        "tag_name": tag_name,
        "canonical_id": canonical_id,
        "review_type": review_type.value,
        "severity": severity.value,
        "confidence": confidence,
        "description": description,
        "suggested_fix": suggested_fix,
        "escalation_rule": _escalation_rule(review_type, severity),
        "context": context or {},
        "status": ReviewStatus.PENDING.value,
        "resolution": None,
        "resolved_at": None,
        "resolved_by": None,
    }


def _escalation_rule(review_type: ReviewType, severity: Severity) -> str:
    if severity == Severity.CRITICAL:
        return "BLOCKING: must resolve before proceeding to next stage"
    if severity == Severity.HIGH:
        return "Escalate to Pro if unresolved within 48 hours"
    if review_type == ReviewType.LOW_CONFIDENCE:
        return "Escalate to Pro if confidence < 0.70"
    return "Advisory: review at Pro discretion"


# =============================================================================
# Queue Manager
# =============================================================================

class ReviewQueueManager:
    """Manages the review queue lifecycle."""

    def __init__(self, work_dir: Path):
        self.work_dir = Path(work_dir)
        self.queue_file = self.work_dir / "review_queue.json"
        self.items: list[dict] = []

    def add(self, item: dict):
        self.items.append(item)

    def add_batch(self, items: list[dict]):
        self.items.extend(items)

    def count_pending(self) -> int:
        return sum(1 for i in self.items if i.get("status") == "pending")

    def count_by_severity(self) -> dict[str, int]:
        counts = {}
        for i in self.items:
            counts[i.get("severity", "unknown")] = counts.get(i.get("severity", "unknown"), 0) + 1
        return counts

    def count_by_type(self) -> dict[str, int]:
        counts = {}
        for i in self.items:
            counts[i.get("review_type", "unknown")] = counts.get(i.get("review_type", "unknown"), 0) + 1
        return counts

    def resolve(self, item_id: str, status: str, resolution: str = "", resolved_by: str = "pro"):
        for item in self.items:
            if item["item_id"] == item_id:
                item["status"] = status
                item["resolution"] = resolution
                item["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                item["resolved_by"] = resolved_by
                return True
        return False

    def auto_accept_high_confidence(self, threshold: float = 0.85):
        """Auto-accept items with confidence >= threshold."""
        accepted = 0
        for item in self.items:
            if item["status"] == "pending" and item["confidence"] >= threshold:
                item["status"] = ReviewStatus.ACCEPTED.value
                item["resolution"] = "auto_accepted"
                item["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                item["resolved_by"] = "auto"
                accepted += 1
        return accepted

    def save(self):
        self.work_dir.mkdir(parents=True, exist_ok=True)
        with open(self.queue_file, "w", encoding="utf-8") as f:
            json.dump({
                "meta": {
                    "total": len(self.items),
                    "pending": self.count_pending(),
                    "by_severity": self.count_by_severity(),
                    "by_type": self.count_by_type(),
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                },
                "items": self.items,
            }, f, ensure_ascii=False, indent=2)

    def load(self) -> bool:
        if not self.queue_file.exists():
            return False
        with open(self.queue_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.items = data.get("items", [])
        return True

    def get_summary(self) -> dict:
        return {
            "total": len(self.items),
            "pending": self.count_pending(),
            "resolved": len(self.items) - self.count_pending(),
            "by_severity": self.count_by_severity(),
            "by_type": self.count_by_type(),
        }

    def get_pending(self) -> list[dict]:
        return [i for i in self.items if i.get("status") == "pending"]

    def get_critical(self) -> list[dict]:
        return [i for i in self.items if i.get("severity") == "critical" and i.get("status") == "pending"]
