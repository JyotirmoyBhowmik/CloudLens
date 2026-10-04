"""CLI Runner for Dual-Mode Connector Test Kit (Prompt 42 Level 4 & Level 5).

Usage:
  python scripts/run_connector_test_kit.py --mode fixture
  python scripts/run_connector_test_kit.py --mode sandbox
  python scripts/run_connector_test_kit.py --mode both
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Dual-Mode Connector Test Kit")
    parser.add_argument(
        "--mode",
        choices=["fixture", "sandbox", "both"],
        default="both",
        help="Execution mode (fixture, sandbox, or both)",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("CLOUDLENS DUAL-MODE CONNECTOR TEST KIT RUNNER")
    print(f"Target Mode: {args.mode.upper()}")
    print("=" * 80)

    pytest_args = [sys.executable, "-m", "pytest"]
    if args.mode == "fixture":
        pytest_args.extend([
            "tests/connectors/test_connector_test_kit.py::TestFixtureBasedContractMode",
            "-v",
        ])
    elif args.mode == "sandbox":
        pytest_args.extend([
            "tests/connectors/test_connector_test_kit.py::TestLiveSandboxVerificationMode",
            "-v",
        ])
    else:
        pytest_args.extend([
            "tests/connectors/test_connector_test_kit.py",
            "-v",
        ])

    res = subprocess.run(pytest_args, cwd=str(ROOT_DIR))
    if res.returncode == 0:
        print("\n" + "=" * 80)
        print(f"[SUCCESS] Connector Test Kit ({args.mode}) passed cleanly!")
        print("=" * 80)
        sys.exit(0)
    else:
        print("\n" + "=" * 80, file=sys.stderr)
        print(f"[FAIL] Connector Test Kit ({args.mode}) encountered failures!", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        sys.exit(res.returncode)


if __name__ == "__main__":
    main()
