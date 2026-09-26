"""Script runner for CloudLens Enumeration Bridge Verification (Prompt 48 Item 36)."""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from masterdata.enum_bridge import verify_enumeration_bridge  # noqa: E402


def main() -> None:
    success = verify_enumeration_bridge()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
