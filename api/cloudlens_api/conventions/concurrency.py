"""ETag Generation and Optimistic Concurrency Control (Prompt 34 / BBP Section 38).

Enforces:
- Deterministic ETag calculation for resources.
- If-Match validation on mutating requests.
- Returns 412 Precondition Failed with code 'PRECONDITION_FAILED' on mismatch.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def generate_etag(data: Any) -> str:
    """Generates strong ETag quoted string from entity dictionary or string."""
    if isinstance(data, (dict, list)):
        serialized = json.dumps(data, sort_keys=True, default=str)
    elif hasattr(data, "model_dump"):
        serialized = json.dumps(data.model_dump(), sort_keys=True, default=str)
    else:
        serialized = str(data)

    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
    return f'"{digest}"'


def validate_if_match(current_etag: str, if_match_header: str | None) -> bool:
    """Validates If-Match header against entity's current ETag.

    Returns True if matches or If-Match is wildcard '*'.
    Returns False if header is provided but does not match.
    If if_match_header is None, validation passes (no optimistic concurrency enforced).
    """
    if if_match_header is None:
        return True

    header_val = if_match_header.strip()
    if header_val == "*":
        return True

    # Strip quotes if present for comparison
    clean_current = current_etag.strip('"')
    clean_header = header_val.strip('"')
    return clean_current == clean_header
