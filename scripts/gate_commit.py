"""CloudLens Gate 1: Commit Gate.

Enforces Prompt 04 Item 25:
Formatting, linting, layering rules, no-hardcoded-constants check, type checking, and unit tests.
Executed locally by developers before commit and in pre-commit git hooks.
"""

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def run_stage(title: str, cmd: list[str]) -> bool:
    print(f"\n>>> Running [Commit Gate]: {title}")
    res = subprocess.run(cmd, cwd=str(ROOT_DIR))
    if res.returncode != 0:
        print(f"\n[FAIL] Commit Gate failed at stage: {title}", file=sys.stderr)
        return False
    print(f"[PASS] {title}")
    return True


def main() -> None:
    print("=" * 80)
    print("CLOUDLENS QUALITY GATE 1: COMMIT GATE")
    print("=" * 80)

    stages = [
        ("Layering Rule Verification", [sys.executable, "scripts/check_layering.py"]),
        (
            "No Hard-coded Constants Audit",
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
        ("Ruff Linter", [sys.executable, "scripts/run.py", "ruff", "check", "."]),
        ("Ruff Format Check", [sys.executable, "scripts/run.py", "ruff", "format", "--check", "."]),
        ("Mypy Static Type Checking", [sys.executable, "scripts/run.py", "mypy", "."]),
        ("Unit Test Suite", [sys.executable, "scripts/run.py", "pytest", "tests/unit"]),
    ]

    for title, cmd in stages:
        if not run_stage(title, cmd):
            sys.exit(1)

    print("\n" + "=" * 80)
    print("[SUCCESS] All Commit Gate checks passed cleanly!")
    print("=" * 80)
    sys.exit(0)


if __name__ == "__main__":
    main()
