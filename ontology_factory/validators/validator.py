"""
Validation Engine — Deterministic checks for pre-freeze gates.
Zero LLM calls. Zero hallucination risk.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from stages import validate_canonical_id


@dataclass
class ValidationReport:
    """Aggregate validation report."""
    passed: bool = True
    checks: list[dict] = field(default_factory=list)
    critical_failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def add_check(self, name: str, passed: bool, detail: str = "", data: Any = None):
        self.checks.append({"check": name, "passed": passed, "detail": detail, "data": data})
        if not passed:
            self.passed = False

    def add_critical(self, msg: str):
        self.critical_failures.append(msg)
        self.passed = False

    def add_warning(self, msg: str):
        self.warnings.append(msg)


class Validator:
    """Deterministic validation engine. Run after S3/S4/S5/S6."""

    def __init__(self, profile: dict, config: dict | None = None):
        self.profile = profile
        self.config = config or {}
        self.valid_namespaces = set(profile.get("namespace_map", {}).keys())
        self.valid_semantic_types = {st["id"] for st in profile.get("semantic_types", [])}
        self.conf_thresholds = profile.get("confidence_thresholds", {})
        self.auto_accept = self.conf_thresholds.get("auto_accept", 0.85)

    # ------------------------------------------------------------------
    # Check 1: Duplicate Canonical IDs
    # ------------------------------------------------------------------
    def check_duplicate_cids(self, entries: list[dict]) -> tuple[bool, dict]:
        primary = [e for e in entries if not (e.get("is_alias_of") or e.get("is_duplicate_of"))]
        cids = Counter(e.get("canonical_id", "") for e in primary)
        dups = {c: n for c, n in cids.items() if n > 1}
        passed = len(dups) == 0
        detail = f"ZERO duplicate IDs" if passed else f"FOUND {len(dups)} duplicate ID groups"
        return passed, {"duplicate_count": len(dups), "duplicates": dups, "detail": detail}

    # ------------------------------------------------------------------
    # Check 1b: Empty Canonical ID (every primary entry must carry an ID)
    # ------------------------------------------------------------------
    def check_empty_canonical_id(self, entries: list[dict]) -> tuple[bool, dict]:
        violations = [
            {"name": e.get("original_name", e.get("name")), "namespace": e.get("namespace")}
            for e in entries
            if not (e.get("is_alias_of") or e.get("is_duplicate_of")) and not e.get("canonical_id")
        ]
        passed = len(violations) == 0
        detail = ("ZERO empty canonical IDs" if passed
                  else f"FOUND {len(violations)} primary entries without canonical_id")
        return passed, {"violations": violations, "count": len(violations), "detail": detail}

    # ------------------------------------------------------------------
    # Check 1c: Canonical ID format (frozen convention)
    # ------------------------------------------------------------------
    def check_canonical_id_format(self, entries: list[dict]) -> tuple[bool, dict]:
        violations = [
            {"name": e.get("original_name", e.get("name")), "canonical_id": e.get("canonical_id")}
            for e in entries
            if e.get("canonical_id") and not validate_canonical_id(e["canonical_id"])
        ]
        passed = len(violations) == 0
        detail = ("ZERO malformed canonical IDs" if passed
                  else f"FOUND {len(violations)} malformed canonical IDs")
        return passed, {"violations": violations, "count": len(violations), "detail": detail}

    # ------------------------------------------------------------------
    # Check 2: Namespace Consistency
    # ------------------------------------------------------------------
    def check_namespace_consistency(self, entries: list[dict]) -> tuple[bool, dict]:
        violations = []
        for e in entries:
            ns = e.get("namespace", "")
            if ns and ns not in self.valid_namespaces:
                violations.append({
                    "name": e.get("original_name", e.get("name")),
                    "namespace": ns,
                    "canonical_id": e.get("canonical_id"),
                })
        passed = len(violations) == 0
        return passed, {"violations": violations, "count": len(violations)}

    # ------------------------------------------------------------------
    # Check 3: Alias Integrity (no alias→alias chains)
    # ------------------------------------------------------------------
    def check_alias_integrity(self, entries: list[dict]) -> tuple[bool, dict]:
        aliased_names = {e.get("original_name", e.get("name")) for e in entries
                        if e.get("is_alias_of") or e.get("is_duplicate_of")}
        # Primary = entries that are NOT aliases. Keeping alias names out of this
        # set is what makes loop / missing-target detection meaningful.
        primary_names = {e.get("original_name", e.get("name")) for e in entries
                        if not (e.get("is_alias_of") or e.get("is_duplicate_of"))}

        loops = []
        missing_targets = []
        for e in entries:
            target = e.get("is_alias_of") or e.get("is_duplicate_of")
            if target:
                if target in aliased_names:
                    loops.append({
                        "alias": e.get("original_name", e.get("name")),
                        "targets": target,
                        "error": "alias_loop",
                    })
                if target not in primary_names:
                    missing_targets.append({
                        "alias": e.get("original_name", e.get("name")),
                        "target": target,
                        "error": "target_not_found",
                    })

        passed = len(loops) == 0 and len(missing_targets) == 0
        return passed, {
            "alias_loops": loops,
            "missing_targets": missing_targets,
            "total_alias_issues": len(loops) + len(missing_targets),
        }

    # ------------------------------------------------------------------
    # Check 6: Confidence Distribution
    # ------------------------------------------------------------------
    def check_confidence_distribution(self, entries: list[dict]) -> tuple[bool, dict]:
        bins = {"0.95+": 0, "0.85-0.94": 0, "0.70-0.84": 0, "<0.70": 0}
        for e in entries:
            c = e.get("confidence", 0)
            if c >= 0.95:
                bins["0.95+"] += 1
            elif c >= 0.85:
                bins["0.85-0.94"] += 1
            elif c >= 0.70:
                bins["0.70-0.84"] += 1
            else:
                bins["<0.70"] += 1

        total = len(entries) or 1
        pct = {k: round(v / total * 100, 1) for k, v in bins.items()}
        mean = round(sum(e.get("confidence", 0) for e in entries) / total, 3) if entries else 0

        warnings = []
        passed = True
        if mean < 0.80:
            warnings.append(f"Mean confidence {mean} is low (target ≥ 0.85)")
            passed = False
        if bins["<0.70"] / total > 0.05:
            warnings.append(f"{(bins['<0.70'] / total * 100):.0f}% items below 0.70 (target ≤ 2%)")

        return passed, {
            "distribution": bins,
            "percentages": pct,
            "mean": mean,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Check 8: Semantic Type Validity
    # ------------------------------------------------------------------
    def check_semantic_types(self, entries: list[dict]) -> tuple[bool, dict]:
        violations = []
        for e in entries:
            st = e.get("semantic_type", "")
            # "unknown" is the explicit sentinel emitted for review placeholders
            # (tags the LLM dropped); it is carried as needs_review, not a violation.
            if st and st not in self.valid_semantic_types and st != "unknown":
                violations.append({
                    "name": e.get("original_name", e.get("name")),
                    "semantic_type": st,
                })
        passed = len(violations) == 0
        return passed, {"violations": violations, "count": len(violations)}

    # ------------------------------------------------------------------
    # Run All Checks
    # ------------------------------------------------------------------
    def validate_all(self, entries: list[dict], stage_id: str = "s6") -> ValidationReport:
        """Run all mandatory pre-freeze checks."""
        report = ValidationReport()

        checks = [
            ("duplicate_canonical_ids", self.check_duplicate_cids, True),
            ("empty_canonical_id", self.check_empty_canonical_id, True),
            ("canonical_id_format", self.check_canonical_id_format, True),
            ("namespace_consistency", self.check_namespace_consistency, True),
            ("alias_integrity", self.check_alias_integrity, True),
            ("confidence_distribution", self.check_confidence_distribution, False),
            ("semantic_type_validity", self.check_semantic_types, False),
        ]

        for name, check_fn, blocking in checks:
            passed, data = check_fn(entries)
            detail = data.get("detail", f"{'PASSED' if passed else 'FAILED'} — {data.get('count', data.get('total_alias_issues', data.get('issues', 0)))} issues")
            report.add_check(name, passed, detail=detail, data=data)
            if not passed and blocking:
                report.add_critical(f"[{name}] {detail}")

        # Compute aggregate stats
        primary = [e for e in entries if not (e.get("is_alias_of") or e.get("is_duplicate_of"))]
        report.stats = {
            "total_entries": len(entries),
            "primary_entries": len(primary),
            "alias_entries": len(entries) - len(primary),
            "unique_namespaces": len(set(e.get("namespace") for e in entries)),
            "unique_categories": len(set(e.get("category") for e in entries)),
            "mean_confidence": round(
                sum(e.get("confidence", 0) for e in entries) / max(len(entries), 1), 3
            ),
        }

        return report


def quick_validate(entries: list[dict], profile: dict) -> bool:
    """Quick pre-freeze check: duplicates only. Returns True if clean."""
    primary = [e for e in entries if not (e.get("is_alias_of") or e.get("is_duplicate_of"))]
    cids = Counter(e.get("canonical_id", "") for e in primary)
    return all(n == 1 for n in cids.values())
