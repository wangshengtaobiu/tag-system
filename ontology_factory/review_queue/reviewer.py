"""
Reviewer — Simple CLI-based review interface for human-in-the-loop.
Supports accept/override/quarantine/skip for each review item.
"""
from __future__ import annotations

import json
from pathlib import Path

from review_queue.schema import ReviewQueueManager


class Reviewer:
    """Interactive CLI review tool for the review queue."""

    def __init__(self, queue: ReviewQueueManager):
        self.queue = queue

    def interactive_review(self):
        """Run interactive review session."""
        pending = self.queue.get_pending()
        if not pending:
            print("No pending review items.")
            return

        print(f"\n{'='*60}")
        print(f"ONTOLOGY FACTORY — REVIEW QUEUE ({len(pending)} remaining)")
        print(f"{'='*60}")

        for i, item in enumerate(pending):
            if item.get("severity") == "critical":
                self._review_item(item, i + 1, len(pending))
                # Check if queue is clear of critical
                remaining_critical = len(self.queue.get_critical())
                if remaining_critical == 0:
                    break

    def _review_item(self, item: dict, idx: int, total: int):
        """Review a single item."""
        print(f"\n{'─'*50}")
        print(f"[{idx}/{total}] Review Item: {item['item_id']}")
        print(f"  TAG:         {item['tag_name']}")
        print(f"  CANONICAL:   {item.get('canonical_id', 'N/A')}")
        print(f"  TYPE:        {item['review_type']}")
        print(f"  SEVERITY:    {item['severity'].upper()}")
        print(f"  CONFIDENCE:  {item['confidence']}")
        print(f"  REASON:      {item['description']}")

        ctx = item.get("context", {})
        if ctx.get("definition"):
            print(f"  DEFINITION:  {ctx['definition'][:120]}")
        if ctx.get("distinction"):
            print(f"  DISTINCTION: {ctx['distinction'][:120]}")
        if ctx.get("namespace"):
            print(f"  NAMESPACE:   {ctx['namespace']}")
        if ctx.get("semantic_type"):
            print(f"  SEMANTIC:    {ctx['semantic_type']}")

        fix = item.get("suggested_fix")
        if fix:
            print(f"\n  SUGGESTED FIX:")
            for k, v in fix.items():
                if v:
                    print(f"    {k}: {v}")

        print(f"\n  [A]ccept  [O]verride  [Q]uarantine  [S]kip  [E]xit")
        choice = input("  Choice: ").strip().lower()

        if choice == "a":
            self.queue.resolve(item["item_id"], "accepted", "Accepted by reviewer", "human")
            print("  ✓ ACCEPTED")
        elif choice == "o":
            new_cid = input("  New canonical_id (or Enter to keep): ").strip()
            resolution = f"Override: canonical_id={new_cid}" if new_cid else "Override: accepted"
            self.queue.resolve(item["item_id"], "overridden", resolution, "human")
            print("  ✓ OVERRIDDEN")
        elif choice == "q":
            reason = input("  Quarantine reason: ").strip()
            self.queue.resolve(item["item_id"], "quarantined", f"Quarantined: {reason}", "human")
            print("  ✓ QUARANTINED")
        elif choice == "s":
            print("  → SKIPPED")
        elif choice == "e":
            print("  → EXIT")
            return True
        else:
            print("  → INVALID, skipping")
        return False

    def auto_accept(self, threshold: float = 0.85) -> int:
        """Auto-accept high-confidence items."""
        return self.queue.auto_accept_high_confidence(threshold)

    def print_summary(self):
        """Print queue summary."""
        s = self.queue.get_summary()
        print(f"\nReview Queue Summary:")
        print(f"  Total:    {s['total']}")
        print(f"  Pending:  {s['pending']}")
        print(f"  Resolved: {s['resolved']}")
        print(f"  By severity: {s['by_severity']}")
        print(f"  By type:     {s['by_type']}")
