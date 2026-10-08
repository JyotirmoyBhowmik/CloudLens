"""CloudLens Gate 1: Commit Gate.

Enforces Prompt 04 Item 25:
Formatting, linting, layering rules, no-hardcoded-constants check, type checking, and unit tests.
Executed locally by developers before commit and in pre-commit git hooks.
"""

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def get_python_exe() -> str:
    if sys.platform == "win32":
        venv_py = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    else:
        venv_py = ROOT_DIR / ".venv" / "bin" / "python"
    return str(venv_py) if venv_py.is_file() else sys.executable


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

    py_exe = get_python_exe()
    stages = [
        ("Layering Rule Verification", [py_exe, "scripts/check_layering.py"]),
        (
            "No Hard-coded Constants Audit",
            [py_exe, "scripts/check_no_hardcoded_constants.py", "--mode", "report"],
        ),
        (
            "Enumeration Bridge Verification",
            [py_exe, "scripts/check_enum_bridge.py"],
        ),
        (
            "Tenant Repository Context Enforcement",
            [py_exe, "scripts/check_tenant_repository_enforcement.py"],
        ),
        ("Ruff Linter", [py_exe, "scripts/run.py", "ruff", "check", "."]),
        ("Ruff Format Check", [py_exe, "scripts/run.py", "ruff", "format", "--check", "."]),
        ("Mypy Static Type Checking", [py_exe, "scripts/run.py", "mypy", "."]),
        ("Unit Test Suite", [py_exe, "scripts/run.py", "pytest", "tests/unit"]),
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
