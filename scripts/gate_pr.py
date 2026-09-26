"""CloudLens Gate 2: Pull-Request Gate.

Enforces Prompt 04 Item 26 & 28:
1. Integration tests against a real PostgreSQL instance (not a mock).
2. API contract tests.
3. Coverage thresholds: minimum 85% on domain logic.
4. Monetary arithmetic, unit conversion & threshold evaluation: strictly 100% coverage
   (separate, explicitly named check per Prompt 04 Item 28).
5. Dependency vulnerability scan (blocks known critical CVEs).
"""

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def run_stage(title: str, cmd: list[str]) -> bool:
    print(f"\n>>> Running [PR Gate]: {title}")
    res = subprocess.run(cmd, cwd=str(ROOT_DIR))
    if res.returncode != 0:
        print(f"\n[FAIL] PR Gate failed at stage: {title}", file=sys.stderr)
        return False
    print(f"[PASS] {title}")
    return True


def main() -> None:
    print("=" * 80)
    print("CLOUDLENS QUALITY GATE 2: PULL-REQUEST GATE")
    print("=" * 80)

    stages = [
        (
            "API Contract Tests (OpenAPI 3.1 & Distributed Tracing Headers)",
            [sys.executable, "scripts/run.py", "pytest", "tests/integration/test_api_contract.py"],
        ),
        (
            "Real PostgreSQL Integration Tests (No Mocks)",
            [sys.executable, "scripts/run.py", "pytest", "tests/integration/test_database_real.py"],
        ),
        (
            "Zero Hard-Coding & Exception Register Audit",
            [sys.executable, "scripts/check_no_hardcoded_constants.py"],
        ),
        (
            "Enumeration Bridge Verification",
            [sys.executable, "scripts/check_enum_bridge.py"],
        ),
        (
            "Tenant Repository Context Enforcement",
            [sys.executable, "scripts/check_tenant_repository_enforcement.py"],
        ),
        (
            "Domain Logic Coverage Policy (>= 85%)",
            [
                sys.executable,
                "scripts/run.py",
                "pytest",
                "tests/unit",
                "--cov=domain",
                "--cov-fail-under=85",
            ],
        ),
        (
            "Strict 100% Monetary & Threshold Coverage Gate (Separate Named Check)",
            [sys.executable, "scripts/check_monetary_coverage.py"],
        ),
        (
            "Dependency Vulnerability Audit (CVE Blocker)",
            [sys.executable, "scripts/scan_vulnerabilities.py"],
        ),
    ]

    for title, cmd in stages:
        if not run_stage(title, cmd):
            sys.exit(1)

    print("\n" + "=" * 80)
    print("[SUCCESS] All Pull-Request Gate checks passed cleanly!")
    print("=" * 80)
    sys.exit(0)


if __name__ == "__main__":
    main()
