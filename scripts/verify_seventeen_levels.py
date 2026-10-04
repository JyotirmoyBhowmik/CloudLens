#!/usr/bin/env python3
"""Master 17-Level Test Strategy & Quality Gate Verification Orchestrator (BBP Section 47).

Orchestrates and reports execution across all seventeen test levels:
 1. Unit Tests
 2. Integration Tests
 3. API Contract Tests
 4. Connector Tests (Dual-Mode Kit)
 5. Cloud-Provider Compatibility Tests
 6. Data Validation Tests
 7. Cost Reconciliation Tests (100% Hand-Calculated Fixtures)
 8. Security & Isolation Tests
 9. RBAC & Access Matrix Tests
10. Performance Benchmarks (MVP & Design-Headroom)
11. Load & Stress Tests
12. UI Contracts & Explanation Layer Tests
13. End-to-End Business Processes (All 20 BP-01 to BP-20)
14. Disaster Recovery Automated Exercise
15. Rolling Upgrade & Zero Downtime Tests
16. Regression & Defect Prevention Tests
17. Master Acceptance & Quality Gates
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON_EXE = str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe")
if not os.path.exists(PYTHON_EXE):
    PYTHON_EXE = sys.executable


@dataclass
class LevelTarget:
    level_num: int
    name: str
    target_command: list[str]
    description: str


SEVENTEEN_LEVELS: list[LevelTarget] = [
    LevelTarget(
        1,
        "Unit Tests",
        [PYTHON_EXE, "-m", "pytest", "tests/unit/test_monetary_arithmetic.py", "tests/unit/test_threshold_bands.py", "-q"],
        "Deterministic units, mathematical rules, and threshold bands",
    ),
    LevelTarget(
        2,
        "Integration Tests",
        [PYTHON_EXE, "-m", "pytest", "tests/integration/test_database_real.py", "-q"],
        "Real database repository lifecycle, schema validation",
    ),
    LevelTarget(
        3,
        "API Contract Tests",
        [PYTHON_EXE, "-m", "pytest", "tests/contracts/test_public_api_catalogue.py", "tests/contracts/test_connector_conformance.py", "-q"],
        "REST API envelopes, response headers, error representations",
    ),
    LevelTarget(
        4,
        "Connector Tests",
        [PYTHON_EXE, "scripts/run_connector_test_kit.py", "--mode", "both"],
        "Dual-mode connector test kit (CI contract fixtures & sandbox canary)",
    ),
    LevelTarget(
        5,
        "Cloud-Provider Tests",
        [PYTHON_EXE, "-m", "pytest", "tests/cloud_provider/test_cloud_provider_suite.py", "-q"],
        "AWS, Azure, GCP, and OCI hierarchy and schema compatibility",
    ),
    LevelTarget(
        6,
        "Data Validation Tests",
        [PYTHON_EXE, "-m", "pytest", "tests/data_validation/test_data_validation_suite.py", "-q"],
        "4-state null discipline (NO_COST, NO_DATA, NOT_APPLICABLE, NOT_SUPPORTED)",
    ),
    LevelTarget(
        7,
        "Cost Reconciliation Tests",
        [PYTHON_EXE, "-m", "pytest", "tests/cost_reconciliation/test_cost_correctness_suite.py", "-q"],
        "100% hand-calculated coverage for tiered, commitments, discounts, currency",
    ),
    LevelTarget(
        8,
        "Security & Isolation Tests",
        [PYTHON_EXE, "-m", "pytest", "tests/security/test_tenant_isolation_suite.py", "tests/security/test_auth_security_controls.py", "-q"],
        "OIDC login, token kill, break-glass, cross-tenant boundary isolation",
    ),
    LevelTarget(
        9,
        "RBAC Matrix Tests",
        [PYTHON_EXE, "-m", "pytest", "tests/rbac/test_rbac_matrix_suite.py", "-q"],
        "Role permissions, financial detail redaction, non-disclosure",
    ),
    LevelTarget(
        10,
        "Performance Benchmarks",
        [PYTHON_EXE, "-m", "pytest", "tests/perf/test_performance_suite.py", "-q"],
        "MVP (10k) and design-headroom (100k) streaming with zero drift",
    ),
    LevelTarget(
        11,
        "Load & Stress Tests",
        [PYTHON_EXE, "-m", "pytest", "tests/load/test_load_suite.py", "-q"],
        "50-100 parallel workers concurrent ingestion and query stress",
    ),
    LevelTarget(
        12,
        "UI Contract Tests",
        [PYTHON_EXE, "-m", "pytest", "tests/ui/test_ui_contracts.py", "-q"],
        "35-field inventory, 6 lateral lenses, 11 explanation panels, 6 alerts",
    ),
    LevelTarget(
        13,
        "End-to-End Business Processes",
        [PYTHON_EXE, "-m", "pytest", "tests/e2e/test_twenty_business_processes.py", "-q"],
        "All twenty business processes (BP-01 through BP-20)",
    ),
    LevelTarget(
        14,
        "Disaster Recovery Exercise",
        [PYTHON_EXE, "scripts/run_dr_exercise.py"],
        "Automated restore, failover, verification within RTO <= 4h, RPO <= 1h",
    ),
    LevelTarget(
        15,
        "Rolling Upgrade Tests",
        [PYTHON_EXE, "scripts/run_upgrade_test.py"],
        "Zero-downtime rolling upgrade on active dataset with zero data loss",
    ),
    LevelTarget(
        16,
        "Regression & Defect Tests",
        [PYTHON_EXE, "-m", "pytest", "tests/regression/test_regression_suite.py", "-q"],
        "Bi-temporal restatements, leap year, no float drift, strict nulls",
    ),
    LevelTarget(
        17,
        "Acceptance Quality Gates",
        [PYTHON_EXE, "-m", "pytest", "tests/acceptance/test_acceptance_suite.py", "-q"],
        "Full suite passing, 100% monetary coverage, zero float math, zero bare nulls",
    ),
]


def main() -> int:
    print("=" * 80)
    print(" CloudLens 17-Level Test Strategy Verification (BBP Section 47)")
    print("=" * 80)
    print(f"Working Directory: {PROJECT_ROOT}")
    print(f"Python Runtime:    {PYTHON_EXE}\n")

    overall_start = time.perf_counter()
    passed_levels = 0
    results: list[tuple[LevelTarget, bool, float, str]] = []

    for target in SEVENTEEN_LEVELS:
        print(f"Running Level {target.level_num:02d}: {target.name} ... ", end="", flush=True)
        level_start = time.perf_counter()
        proc = subprocess.run(
            target.target_command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        duration = time.perf_counter() - level_start
        success = proc.returncode == 0
        if success:
            passed_levels += 1
            print(f"[PASSED] ({duration:.2f}s)")
        else:
            print(f"[FAILED] ({duration:.2f}s)")
            print(f"--- Output for Level {target.level_num} ---")
            print(proc.stdout)
            print(proc.stderr)
            print("------------------------------------------")

        results.append((target, success, duration, proc.stdout))

    overall_duration = time.perf_counter() - overall_start

    print("\n" + "=" * 80)
    print(" 17-Level Verification Summary")
    print("=" * 80)
    print(f"{'Level':<6} | {'Test Suite':<30} | {'Status':<8} | {'Duration':<8} | {'Description'}")
    print("-" * 80)
    for target, success, dur, _ in results:
        status_str = "PASSED" if success else "FAILED"
        print(f"L-{target.level_num:02d}  | {target.name:<30} | {status_str:<8} | {dur:5.2f}s  | {target.description}")
    print("-" * 80)
    print(f"Total Levels: 17 | Passed: {passed_levels}/17 | Duration: {overall_duration:.2f}s")

    # Also verify 100% monetary coverage
    print("\nVerifying 100% Monetary Test Coverage Gate...")
    cov_proc = subprocess.run(
        [PYTHON_EXE, "scripts/check_monetary_coverage.py"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    print(cov_proc.stdout)

    if passed_levels == 17 and cov_proc.returncode == 0:
        print("[SUCCESS] All 17 Test Levels and Quality Gates Satisfied!")
        return 0
    else:
        print("[FAILURE] Some Test Levels or Quality Gates Failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
