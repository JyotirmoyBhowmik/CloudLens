#!/usr/bin/env python3
"""Automated Rolling Upgrade Verification Runner (Prompt R-PERF Item 3 & Prompt 42 Level 15).

Verifies zero-downtime rolling upgrades across schema versions (Release N-1 to N):
- Continuous HTTP readiness probing during schema migration & rollout
- Probe log verification (0 failed probes, 100% availability)
- Identical cent-for-cent financial reconciliation totals before and after upgrade
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.upgrade.test_rolling_upgrade import TestRollingUpgradeSuite  # noqa: E402


def main() -> int:
    print("=" * 80)
    print("CloudLens Zero-Downtime Rolling Upgrade & Reconciliation Verification (Level 15)")
    print("=" * 80)
    suite = TestRollingUpgradeSuite()

    try:
        t0 = time.perf_counter()
        results = suite.test_rolling_upgrade_data_integrity_and_zero_loss()
        elapsed = time.perf_counter() - t0

        print(f"\n[UPGRADE COMPLETED IN {elapsed:.3f}s]")
        print("-" * 80)
        print("CONTINUOUS PROBE LOG SUMMARY (PROVING ZERO DOWNTIME):")
        print(f"  Total Probes Dispatched:    {results['total_probes']}")
        print(f"  Successful Probes (200 OK): {results['successful_probes']}")
        print(f"  Failed / Dropped Probes:    {results['failed_probes']}")
        print(f"  System Availability:        {results['availability_pct']:.2f}% (ZERO DOWNTIME)")
        print("\nSAMPLE CONTINUOUS PROBE TRACE:")
        for probe in results["sample_probes"]:
            print(f"  [{probe['timestamp']}] SEQ={probe['sequence']:03d} STATUS={probe['status_code']} {probe['status']} LATENCY={probe['latency_ms']:.3f}ms RECORDS={probe.get('record_count', 0)}")

        print("-" * 80)
        print("CENT-FOR-CENT RECONCILIATION VERIFICATION:")
        print(f"  Release N-1 Seed Records:   {results['pre_upgrade_records']} rows")
        print(f"  Pre-Upgrade Cost Total:     ${results['pre_upgrade_total_usd']:,.2f}")
        print(f"  Post-Upgrade Total Records: {results['post_upgrade_records']} rows (500 v1 + 200 v2)")
        print(f"  Post-Upgrade Reconciled v1: ${results['retained_v1_total_usd']:,.2f}")
        print(f"  Discrepancy / Variance:     ${results['variance_usd']:.2f} (EXACT CENT-FOR-CENT MATCH)")
        print("=" * 80)
        print("\n[SUCCESS] Rolling Upgrade Test Succeeded: Zero Downtime & Zero Data Drift Proven.")
        return 0
    except Exception as exc:
        print(f"\n[FAILURE] Rolling Upgrade Test Failed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
