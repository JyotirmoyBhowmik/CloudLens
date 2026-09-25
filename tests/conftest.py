"""Pytest configuration and shared fixtures."""

import sys
from pathlib import Path

# Add project root to sys.path so all monorepo packages are importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
