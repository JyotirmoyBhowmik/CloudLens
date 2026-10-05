#!/usr/bin/env python3
"""Counts tests per Prompt 42/42B level marker directly from pytest collection (Prompt R-PERF Item 6)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON_EXE = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")

MARKERS = [
    ("level01", "Level 01: Unit Tests"),
    ("level02", "Level 02: Integration Tests"),
    ("level03", "Level 03: API Contract Tests"),
    ("level04", "Level 04: Connector Tests"),
    ("level05", "Level 05: Cloud-Provider Tests"),
    ("level06", "Level 06: Data Validation Tests"),
    ("level07", "Level 07: Cost Reconciliation Tests"),
    ("level08", "Level 08: Security & Isolation Tests"),
    ("level09", "Level 09: RBAC Matrix Tests"),
    ("level10", "Level 10: Performance Benchmarks"),
    ("level11", "Level 11: Load & Stress Tests"),
    ("level12", "Level 12: UI Contract Tests"),
    ("level13", "Level 13: End-to-End Business Processes"),
    ("level14", "Level 14: Disaster Recovery Exercise"),
    ("level15", "Level 15: Rolling Upgrade Tests"),
    ("level16", "Level 16: Regression & Defect Prevention Tests"),
    ("level17", "Level 17: Acceptance Quality Gates"),
    ("level18", "Level 18: Master-Data Integrity Suite"),
    ("level19", "Level 19: Workflow & Approval Engine Suite"),
    ("level20", "Level 20: Analytical Extract Suite"),
    ("phase2",  "Phase 2: Addendum B & Features (57-61)"),
]


def count_all_levels() -> dict[str, int]:
    # Single pytest collection run to read all marked items efficiently
    import pytest

    class MarkerCountPlugin:
        def __init__(self):
            self.counts: dict[str, int] = {m[0]: 0 for m in MARKERS}
            self.total = 0

        def pytest_collection_modifyitems(self, config, items):
            self.total = len(items)
            for item in items:
                for marker_name, _ in MARKERS:
                    if item.get_closest_marker(marker_name):
                        self.counts[marker_name] += 1

    plugin = MarkerCountPlugin()
    pytest.main(["--collect-only", "-q"], plugins=[plugin])

    print("=" * 80)
    print("CLOUDLENS PYTEST LEVEL MARKER COUNTS (Prompt 42/42B & R-PERF)")
    print("=" * 80)
    print(f"{'Level Marker':<12} | {'Description':<46} | {'Test Count':<10}")
    print("-" * 80)
    for marker_name, desc in MARKERS:
        print(f"{marker_name:<12} | {desc:<46} | {plugin.counts[marker_name]:<10}")
    print("=" * 80)
    print(f"Total Test Items Collected in Test Suite: {plugin.total}")
    print("=" * 80)
    return plugin.counts


if __name__ == "__main__":
    count_all_levels()
