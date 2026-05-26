#!/usr/bin/env python3
"""
Observation script — collects metrics and failed cases from a pipeline run.
Saves: review items, dropped tags, placeholders, malformed outputs, merge mistakes.
"""
import json
import sys
from pathlib import Path
from collections import Counter

WORK_DIR = Path("work")
METRICS_DIR = Path("metrics")
FAILED_DIR = METRICS_DIR / "failed_cases"


def load_json(path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Saved: {path}")


def collect_observation(run_id: str):
    print(f"\n=== Collecting observation: {run_id} ===\n")

    # Load stage outputs
    s0 = load_json(WORK_DIR / "enriched_tags.json")
    s2 = load_json(WORK_DIR / "stage2_normalized.json")
    s4 = load_json(WORK_DIR / "stage4_resolved.json")
    s5 = load_json(WORK_DIR / "stage5_alias_resolved.json")
    export = load_json(WORK_DIR / "ontology_versions/latest/ontology_export_v1_0_0.json")
    retrieval = load_json(WORK_DIR / "retrieval_index.json")

    # Review queues
    s0_review = load_json(WORK_DIR / "stage0_review_queue.json")
    s2_review = load_json(WORK_DIR / "stage2_review_queue.json")

    # 1. Dropped tags (cardinality gaps)
    print("[1] Dropped tags analysis...")
    dropped_cases = []

    if s2 and s0 and s0.get("meta", {}).get("stage") == "0":
        s0_labels = {
            t.get("标签名") or t.get("label") or t.get("name", "")
            for t in s0.get("entries", [])
        }
        s2_names = {e.get("name", "") for e in s2.get("entries", [])}
        dropped = s0_labels - s2_names
    elif s2 and s0 and s0.get("meta", {}).get("stage") != "0":
        pass  # S0 was skipped, skip S0→S2 comparison
        if dropped:
            print(f"  Found {len(dropped)} dropped tags from S0→S2")
            dropped_cases.extend([{"tag": t, "stage": "s2", "type": "dropped"} for t in dropped])

    if s2 and s4:
        s2_names = {e.get("name", "") for e in s2.get("entries", [])}
        s4_names = {e.get("name", "") for e in s4.get("entries", [])}
        dropped = s2_names - s4_names
        if dropped:
            print(f"  Found {len(dropped)} dropped tags from S2→S4")
            dropped_cases.extend([{"tag": t, "stage": "s4", "type": "dropped"} for t in dropped])

    save_json(FAILED_DIR / f"{run_id}_dropped_tags.json", {
        "run_id": run_id,
        "total_dropped": len(dropped_cases),
        "cases": dropped_cases,
    })

    # 2. Placeholder entries
    print("[2] Placeholder entries...")
    placeholders = []
    if s2:
        for e in s2.get("entries", []):
            if e.get("confidence", 0) == 0:
                placeholders.append({
                    "name": e.get("name"),
                    "namespace": e.get("namespace"),
                    "review": e.get("needs_review"),
                    "reason": "llm_dropped_recovered",
                })
    if export:
        for e in export.get("entries", []):
            if e.get("confidence", 0) == 0:
                # Avoid duplicates
                if not any(p["name"] == e.get("original_name") for p in placeholders):
                    placeholders.append({
                        "name": e.get("original_name"),
                        "namespace": e.get("namespace"),
                        "review": e.get("needs_review"),
                        "reason": "placeholder",
                    })
    print(f"  Found {len(placeholders)} placeholders")
    save_json(FAILED_DIR / f"{run_id}_placeholders.json", {
        "run_id": run_id,
        "total": len(placeholders),
        "cases": placeholders,
    })

    # 3. Review items
    print("[3] Review items...")
    review_items = []
    for rq, stage in [(s0_review, "s0"), (s2_review, "s2")]:
        if rq:
            items = rq if isinstance(rq, list) else rq.get("items", rq.get("queue", []))
            if isinstance(items, list):
                for item in items:
                    review_items.append({**item, "source_stage": stage})
    print(f"  Found {len(review_items)} review items")
    save_json(FAILED_DIR / f"{run_id}_review_items.json", {
        "run_id": run_id,
        "total": len(review_items),
        "cases": review_items,
    })

    # 4. Alias merges
    print("[4] Alias/duplicate analysis...")
    alias_cases = []
    if s5:
        for e in s5.get("entries", []):
            if e.get("is_alias_of") or e.get("is_duplicate_of"):
                alias_cases.append({
                    "name": e.get("name", e.get("original_name")),
                    "is_alias_of": e.get("is_alias_of"),
                    "is_duplicate_of": e.get("is_duplicate_of"),
                    "canonical_id": e.get("canonical_id"),
                    "confidence": e.get("confidence"),
                })
    print(f"  Found {len(alias_cases)} alias/duplicate entries")
    save_json(FAILED_DIR / f"{run_id}_aliases.json", {
        "run_id": run_id,
        "total": len(alias_cases),
        "cases": alias_cases,
    })

    # 5. Malformed outputs
    print("[5] Malformed outputs...")
    malformed = []
    if s2:
        for i, e in enumerate(s2.get("entries", [])):
            issues = []
            if not e.get("name"):
                issues.append("missing_name")
            if not e.get("canonical_id"):
                issues.append("missing_canonical_id")
            if not e.get("namespace"):
                issues.append("missing_namespace")
            if issues:
                malformed.append({"index": i, "name": e.get("name", "UNKNOWN"), "issues": issues})
    print(f"  Found {len(malformed)} malformed entries")
    save_json(FAILED_DIR / f"{run_id}_malformed.json", {
        "run_id": run_id,
        "total": len(malformed),
        "cases": malformed,
    })

    # 6. Summary metrics
    print("[6] Summary metrics...")
    if export:
        entries = export.get("entries", [])
        conf_dist = Counter()
        for e in entries:
            c = e.get("confidence", 0)
            if c >= 0.95: conf_dist["0.95+"] += 1
            elif c >= 0.85: conf_dist["0.85-0.94"] += 1
            elif c >= 0.70: conf_dist["0.70-0.84"] += 1
            else: conf_dist["<0.70"] += 1

        review_count = sum(1 for e in entries if e.get("needs_review"))
        summary = {
            "run_id": run_id,
            "total_entries": len(entries),
            "review_count": review_count,
            "review_rate": round(review_count / max(len(entries), 1) * 100, 1),
            "mean_confidence": round(sum(e.get("confidence", 0) for e in entries) / max(len(entries), 1), 3),
            "confidence_distribution": dict(conf_dist),
            "namespaces": len(set(e.get("namespace") for e in entries)),
            "categories": len(set(e.get("category") for e in entries)),
            "placeholders": sum(1 for e in entries if e.get("confidence", 0) == 0),
            "aliases": sum(1 for e in entries if e.get("is_alias_of") or e.get("is_duplicate_of")),
            "dropped_tags": len(dropped_cases),
            "malformed": len(malformed),
        }
        save_json(METRICS_DIR / f"{run_id}_summary.json", summary)

        print(f"\n=== {run_id} Summary ===")
        for k, v in summary.items():
            print(f"  {k}: {v}")

        if retrieval:
            ri_meta = retrieval.get("meta", {})
            print(f"\nRetrieval index:")
            print(f"  entries: {ri_meta.get('total_entries')}")
            print(f"  avg_embedding_chars: {ri_meta.get('avg_embedding_chars')}")
    else:
        print("  No export found — pipeline may have failed")

    print(f"\n=== Observation complete: {run_id} ===")
    print(f"Failed cases saved to: {FAILED_DIR}/")
    print(f"Summary saved to: {METRICS_DIR}/{run_id}_summary.json")


if __name__ == "__main__":
    run_id = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    collect_observation(run_id)
