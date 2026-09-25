"""CloudLens Monetary & Threshold Arithmetic Coverage Gate.

STRICT RULE (Prompt 04 Item 28):
Minimum 100% coverage on monetary arithmetic, unit conversion, and threshold band evaluation.
This check is separate and explicitly named so that financial calculation correctness
cannot be diluted by overall project coverage averages.
"""

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

TARGET_MODULES = [
    "domain/rules/monetary.py",
    "domain/rules/thresholds.py",
    "normalisation/units/converter.py",
]

TEST_FILES = [
    "tests/unit/test_monetary_arithmetic.py",
    "tests/unit/test_threshold_bands.py",
    "tests/unit/test_unit_conversions.py",
]


def main() -> None:
    print("=" * 80)
    print("CLOUDLENS QUALITY GATE: 100% MONETARY ARITHMETIC & THRESHOLD COVERAGE CHECK")
    print("Enforcing Prompt 04 Item 28 / BBP Section 47")
    print("=" * 80)

    pytest_bin = sys.executable
    cov_args = [
        "--cov=domain.rules.monetary",
        "--cov=domain.rules.thresholds",
        "--cov=normalisation.units.converter",
    ]

    cmd = [
        pytest_bin,
        "-m",
        "pytest",
        *TEST_FILES,
        *cov_args,
        "--cov-report=term-missing",
        "--cov-fail-under=100",
    ]

    print(f"Running: {' '.join(cmd)}\n")
    res = subprocess.run(cmd, cwd=str(ROOT_DIR))

    if res.returncode == 0:
        print("\n" + "=" * 80)
        print("[PASS] 100% Coverage achieved on all financial, unit, and threshold rules!")
        print("=" * 80)
        sys.exit(0)
    else:
        print("\n" + "=" * 80, file=sys.stderr)
        print("[FAIL] Monetary/Threshold coverage fell below required 100.0%!", file=sys.stderr)
        print(
            "Every line, branch, and edge case in financial calculations must be tested.",
            file=sys.stderr,
        )
        print("=" * 80, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
