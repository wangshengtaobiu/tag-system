"""
Stage 6 — Validation & Audit (Script)
Owner: script (deterministic checks)
Input: stage5_alias_resolved.json
Output: validation_report.json
"""
from __future__ import annotations

import time
from pathlib import Path

from stages import BaseStage, StageResult, StageStatus, register_stage, PipelineContext
from validators.validator import Validator


@register_stage
class S6Validate(BaseStage):
    stage_id = "s6"
    stage_name = "Validation & Audit"
    owner = "script"

    def run(self) -> StageResult:
        t0 = time.time()
        result = StageResult(stage_id=self.stage_id, status=StageStatus.RUNNING)
        entries = self.ctx.normalized_entries

        # Fallback
        if not entries:
            for fname in ("stage5_aliases.json", "stage4_resolved.json", "stage2_normalized.json"):
                fpath = self.ctx.work_dir / fname
                if fpath.exists():
                    print(f"[S6] Loading entries from {fpath}")
                    data = self._load_json(fpath)
                    entries = data.get("entries", [])
                    self.ctx.normalized_entries = entries
                    break
            if not entries:
                result.status = StageStatus.FAILED
                result.errors.append("No normalized entries found.")
                return result

        validator = Validator(self.profile, self.config)
        report = validator.validate_all(entries, stage_id="s6")

        # Save report
        output_path = self.ctx.work_dir / "validation_report.json"
        self._save_json(output_path, {
            "meta": {
                "stage": "6",
                "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "passed": report.passed,
            },
            "checks": report.checks,
            "critical_failures": report.critical_failures,
            "warnings": report.warnings,
            "stats": report.stats,
        })

        if report.critical_failures:
            result.status = StageStatus.FAILED
            result.errors = report.critical_failures
            result.warnings = report.warnings
            result.stats = report.stats
            print(f"[S6] GATE FAILED: {len(report.critical_failures)} critical failures")
            for cf in report.critical_failures:
                print(f"  ❌ {cf}")
            return result

        result.status = StageStatus.PASSED
        result.output_file = str(output_path)
        result.warnings = report.warnings
        result.stats = report.stats
        result.duration_seconds = round(time.time() - t0, 2)

        # Print summary
        print(f"[S6] All checks passed:")
        for check in report.checks:
            status_icon = "✓" if check["passed"] else "⚠"
            print(f"  {status_icon} {check['check']}: {check['detail']}")

        print(f"[S6] Stats: {report.stats['primary_entries']} primary + {report.stats['alias_entries']} aliases, "
              f"mean_conf={report.stats['mean_confidence']}")

        return result
