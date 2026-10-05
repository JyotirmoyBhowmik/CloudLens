#!/usr/bin/env python3
"""Automated Rolling Upgrade Verification Runner (Prompt 42 Level 15).

Verifies zero-downtime rolling upgrades across schema versions on production datasets.
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.upgrade.test_rolling_upgrade import TestRollingUpgradeSuite  # noqa: E402


def main() -> int:
    print("=" * 70)
    print("CloudLens Rolling Upgrade & Zero Data Loss Exercise (Level 15)")
    print("=" * 70)
    suite = TestRollingUpgradeSuite()
    try:
        suite.test_rolling_upgrade_data_integrity_and_zero_loss()
        print("\n[SUCCESS] Rolling Upgrade Test Completed Successfully:")
        print(" - Dual-Version Interoperability (v1 & v2): PASS")
        print(" - Zero Downtime Concurrent Read/Write: PASS")
        print(" - Zero Data Loss Verification: PASS (All historical records intact)")
        print("=" * 70)
        return 0
    except Exception as exc:
        print(f"\n[FAILURE] Rolling Upgrade Test Failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
