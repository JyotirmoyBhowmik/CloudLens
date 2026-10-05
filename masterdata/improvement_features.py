"""Helper to load master data configuration for IMP-01 through IMP-10 features."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CACHE: dict[str, dict[str, Any]] = {}


def load_improvement_features_master() -> dict[str, dict[str, Any]]:
    """Loads and caches improvement feature master parameters from seed file."""
    global _CACHE
    if _CACHE:
        return _CACHE

    seed_path = Path(__file__).resolve().parent / "seeds" / "improvement_features.json"
    if not seed_path.exists():
        return {}

    with open(seed_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data:
        code = item.get("code")
        attrs = item.get("attributes", {})
        if code:
            _CACHE[code] = attrs
    return _CACHE


def get_feature_config(feature_code: str) -> dict[str, Any]:
    """Retrieves attribute configuration dictionary for a given feature code."""
    features = load_improvement_features_master()
    return features.get(feature_code, {})


def list_active_features() -> list[dict[str, Any]]:
    """Returns raw list of all improvement feature objects from seed file."""
    seed_path = Path(__file__).resolve().parent / "seeds" / "improvement_features.json"
    if not seed_path.exists():
        return []
    with open(seed_path, "r", encoding="utf-8") as f:
        return json.load(f)

