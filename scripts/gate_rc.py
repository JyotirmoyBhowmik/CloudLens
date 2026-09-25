"""CloudLens Gate 3: Release-Candidate Gate.

Enforces Prompt 04 Item 27, 29, 30:
1. Full regression suite across unit and integration domains.
2. RBAC matrix security suite.
3. Performance and latency benchmarks (generator >20k res/sec, arithmetic <0.1ms).
4. WCAG 2.1 AA Accessibility audit.
5. 100,000-resource synthetic estate generation with exact 0.00 mathematical reconciliation.
6. Reproducible container build with signed artifacts and CycloneDX SBOM.
"""

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def run_stage(title: str, cmd: list[str]) -> bool:
    print(f"\n>>> Running [RC Gate]: {title}")
    res = subprocess.run(cmd, cwd=str(ROOT_DIR))
    if res.returncode != 0:
        print(f"\n[FAIL] RC Gate failed at stage: {title}", file=sys.stderr)
        return False
    print(f"[PASS] {title}")
    return True


def main() -> None:
    print("=" * 80)
    print("CLOUDLENS QUALITY GATE 3: RELEASE-CANDIDATE GATE")
    print("=" * 80)

    stages = [
        (
            "Full Regression Test Suite",
            [sys.executable, "scripts/run.py", "pytest", "tests/unit", "tests/integration"],
        ),
        (
            "RBAC Permission Matrix Security Suite",
            [sys.executable, "scripts/run.py", "pytest", "tests/security/test_rbac_matrix.py"],
        ),
        (
            "Performance & Throughput Benchmarks",
            [sys.executable, "scripts/run.py", "pytest", "tests/perf/test_benchmarks.py"],
        ),
        (
            "WCAG 2.1 AA Accessibility Compliance Audit",
            [sys.executable, "scripts/check_accessibility.py"],
        ),
        (
            "Synthetic Multi-Provider Estate Generation (100k Resources with 0.00 Mathematical Drift)",
            [sys.executable, "scripts/generate_synthetic_estate.py", "--count", "100000"],
        ),
        (
            "Reproducible Container Build, CycloneDX SBOM & HMAC Signature Generation",
            [sys.executable, "scripts/build_signed_container.py"],
        ),
    ]

    for title, cmd in stages:
        if not run_stage(title, cmd):
            sys.exit(1)

    print("\n" + "=" * 80)
    print("[SUCCESS] All Release-Candidate Gate checks passed cleanly!")
    print("=" * 80)
    sys.exit(0)


if __name__ == "__main__":
    main()
