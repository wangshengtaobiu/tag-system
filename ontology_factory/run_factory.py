#!/usr/bin/env python3
"""
Ontology Factory — One-Command Production Entry Point.

Usage:
    python run_factory.py --profile profiles/adult_profile.json --input raw_tags.json
    python run_factory.py --profile profiles/adult_profile.json --input raw_tags.json --stage s4

Stages:
    s1  Inventory Triage (script, auto)
    s2  Semantic Normalization (flash, needs API key)
    s3  Namespace Architecture (pro, optional)
    s4  Canonical ID Freeze (flash+pro)
    s5  Alias Collapse (flash+pro)
    s6  Validation & Audit (script, auto)
    s7  Retrieval Export (script, auto)
    s8  Production Freeze (pro)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Add factory to path
sys.path.insert(0, str(Path(__file__).parent))

from stages import PipelineContext, STAGE_REGISTRY
from stages.s1_triage import S1Triage
from stages.s2_normalize import S2Normalize
from stages.s3_namespace import S3Namespace
from stages.s4_freeze_id import S4FreezeID
from stages.s5_alias import S5Alias
from stages.s6_validate import S6Validate
from stages.s7_retrieval import S7RetrievalExport
from stages.s8_freeze import S8Freeze


def _expand_env_vars(obj):
    """Recursively expand ${VAR} and ${VAR:-default} in strings."""
    import re
    if isinstance(obj, str):
        def _replacer(m):
            expr = m.group(1)
            if ":-" in expr:
                var, default = expr.split(":-", 1)
                return os.environ.get(var.strip(), default.strip())
            return os.environ.get(expr.strip(), "")
        return re.sub(r"\$\{([^}]+)\}", _replacer, obj)
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars(v) for v in obj]
    return obj


def load_config(config_path: str | None = None) -> dict:
    """Load YAML config, expand env vars, fall back to defaults."""
    if config_path and Path(config_path).exists():
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            return _expand_env_vars(raw)
        except ImportError:
            print("[WARN] PyYAML not installed. Trying json fallback...")

    # Fallback: try as JSON first, then YAML via literal read
    cfg_path = Path("config/factory_config.yaml")
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            return _expand_env_vars(raw)
        except Exception:
            pass
    return {}


def load_profile(profile_path: str) -> dict:
    """Load domain profile JSON."""
    with open(profile_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_raw_tags(input_path: str) -> list[dict]:
    """Load raw tags from JSON or CSV."""
    path = Path(input_path)
    if path.suffix == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("tags") or data.get("entries") or data.get("data") or []
    elif path.suffix == ".csv":
        import csv
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return [row for row in reader]
    else:
        raise ValueError(f"Unsupported input format: {path.suffix}")


def run_pipeline(ctx: PipelineContext, start_stage: str = "s1", end_stage: str = "s8") -> bool:
    """Run the pipeline from start_stage to end_stage."""
    stage_order = ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"]
    stage_map = {
        "s1": S1Triage,
        "s2": S2Normalize,
        "s3": S3Namespace,
        "s4": S4FreezeID,
        "s5": S5Alias,
        "s6": S6Validate,
        "s7": S7RetrievalExport,
        "s8": S8Freeze,
    }

    running = False
    for sid in stage_order:
        if sid == start_stage:
            running = True
        if not running:
            print(f"  [{sid}] SKIPPED (before start)")
            continue

        stage_cls = stage_map.get(sid)
        if stage_cls is None:
            continue

        print(f"\n{'='*60}")
        print(f"[{sid.upper()}] {stage_cls.stage_name} ({stage_cls.owner})")
        print(f"{'='*60}")

        stage = stage_cls(ctx)
        t0 = time.time()
        result = stage.run()
        ctx.stage_results[sid] = result

        if not result.ok:
            print(f"\n[FATAL] Stage {sid} FAILED. Pipeline stopped.")
            for err in result.errors:
                print(f"  ❌ {err}")
            return False

        if sid == end_stage:
            print(f"\n[STOP] Reached end stage: {sid}")
            break

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Ontology Factory — Canonical Ontology Production System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_factory.py --profile profiles/adult_profile.json --input raw_tags.json
  python run_factory.py --profile profiles/adult_profile.json --input raw_tags.json --stage s4
  python run_factory.py --profile profiles/adult_profile.json --input raw_tags.json --end-stage s6
  python run_factory.py --profile profiles/adult_profile.json --input raw_tags.json --skip-flash
        """,
    )
    parser.add_argument("--profile", "-p", required=True, help="Path to domain profile JSON")
    parser.add_argument("--input", "-i", required=True, help="Path to raw_tags.json or CSV")
    parser.add_argument("--config", "-c", default="config/factory_config.yaml", help="Path to factory_config.yaml")
    parser.add_argument("--stage", "-s", default="s1", help="Start stage (s1-s8)")
    parser.add_argument("--end-stage", "-e", default="s8", help="End stage (s1-s8)")
    parser.add_argument("--work-dir", "-w", default="./work", help="Working directory for intermediate files")
    parser.add_argument("--exports-dir", default="./exports", help="Output directory for frozen exports")
    parser.add_argument("--skip-flash", action="store_true", help="Skip Flash-dependent stages (s2, s4, s5)")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs only, don't execute")

    args = parser.parse_args()

    # Validate inputs
    if not Path(args.profile).exists():
        print(f"ERROR: Profile not found: {args.profile}")
        sys.exit(1)
    if not Path(args.input).exists():
        print(f"ERROR: Input not found: {args.input}")
        sys.exit(1)

    print("=" * 60)
    print("ONTOLOGY FACTORY — Production System v1.0.0")
    print("=" * 60)

    # Load configuration
    print(f"\n[LOAD] Profile: {args.profile}")
    profile = load_profile(args.profile)
    print(f"  Domain: {profile.get('domain', {}).get('name', 'unknown')}")
    print(f"  Namespaces: {len(profile.get('namespace_map', {}))}")
    print(f"  Semantic Types: {len(profile.get('semantic_types', []))}")

    print(f"\n[LOAD] Config: {args.config}")
    config = load_config(args.config) if Path(args.config).exists() else {}

    print(f"\n[LOAD] Input: {args.input}")
    raw_tags = load_raw_tags(args.input)
    print(f"  Tags: {len(raw_tags)}")

    if args.dry_run:
        print("\n[DRY RUN] Inputs validated. Exiting.")
        return

    # Setup context
    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    exports_dir = Path(args.exports_dir)
    exports_dir.mkdir(parents=True, exist_ok=True)

    ctx = PipelineContext(
        profile=profile,
        config=config,
        raw_tags=raw_tags,
        work_dir=work_dir,
        exports_dir=exports_dir,
    )

    # Handle skip-flash
    if args.skip_flash:
        print("\n[CONFIG] Flash stages disabled. S2/S4/S5 will be skipped.")
        config.setdefault("pipeline", {}).setdefault("stages", {})
        for sid in ["s2_normalize", "s4_freeze_id", "s5_alias"]:
            config["pipeline"]["stages"].setdefault(sid, {})["enabled"] = False

    # Run pipeline
    start = args.stage
    end = args.end_stage
    print(f"\n[PIPELINE] Stages: {start} → {end}")
    print(f"[PIPELINE] Work dir: {work_dir}")
    print(f"[PIPELINE] Exports dir: {exports_dir}")

    success = run_pipeline(ctx, start_stage=start, end_stage=end)

    # Summary
    print(f"\n{'='*60}")
    print("PIPELINE SUMMARY")
    print(f"{'='*60}")
    for sid, result in ctx.stage_results.items():
        icon = "✓" if result.ok else "✗"
        print(f"  {icon} [{sid}] {result.status.value:8s}  {result.stats}")
    print(f"\nTotal stages: {len(ctx.stage_results)}")
    print(f"Final status: {'SUCCESS' if success else 'FAILED'}")

    if success and "s8" in ctx.stage_results:
        print(f"\nFrozen ontology available at: {exports_dir}/")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
