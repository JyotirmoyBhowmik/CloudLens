"""CloudLens Cross-Platform Tool Runner.

Dispatches commands to the local virtual environment (.venv) across Windows and POSIX.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def find_tool(tool_name: str) -> str:
    """Resolve executable in .venv or fall back to system PATH."""
    if os.name == "nt":
        win_path = ROOT_DIR / ".venv" / "Scripts" / f"{tool_name}.exe"
        if win_path.is_file():
            return str(win_path)
    else:
        unix_path = ROOT_DIR / ".venv" / "bin" / tool_name
        if unix_path.is_file():
            return str(unix_path)
    return tool_name


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/run.py <tool> [args...]", file=sys.stderr)
        sys.exit(1)

    tool = sys.argv[1]
    args = sys.argv[2:]
    executable = find_tool(tool)

    env = os.environ.copy()
    venv_scripts = str(ROOT_DIR / ".venv" / ("Scripts" if os.name == "nt" else "bin"))
    env["PATH"] = venv_scripts + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = str(ROOT_DIR)

    res = subprocess.run([executable, *args], cwd=str(ROOT_DIR), env=env)
    sys.exit(res.returncode)


if __name__ == "__main__":
    main()
