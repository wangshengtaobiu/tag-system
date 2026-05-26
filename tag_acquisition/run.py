#!/usr/bin/env python3
"""Tag Acquisition — Entry point.

Usage:
    python -m tag_acquisition.run [--config CONFIG] [--resume] [--output-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


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


def _load_yaml_simple(path: str) -> dict:
    """Load YAML config with env var expansion."""
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return _expand_env_vars(raw)
    except ImportError:
        print("[ERROR] PyYAML not installed. Run: pip install pyyaml")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Tag Acquisition — Pixiv tag collection")
    parser.add_argument("--config", "-c", default="tag_acquisition/config.yaml", help="Config path")
    parser.add_argument("--resume", action="store_true", help="Resume from last state")
    parser.add_argument("--output-dir", "-o", default=None, help="Output directory override")

    args = parser.parse_args()

    # Load config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"[ERROR] Config not found: {config_path}")
        sys.exit(1)

    config = _load_yaml_simple(str(config_path))
    config["_config_path"] = str(config_path)

    # Override output dir
    if args.output_dir:
        config.setdefault("output", {})["output_dir"] = args.output_dir

    from tag_acquisition.collector import PixivCollector

    collector = PixivCollector(config)
    entries = collector.collect()

    print(f"\n共 {len(entries)} 个 surface tag")
    return 0


if __name__ == "__main__":
    sys.exit(main())
