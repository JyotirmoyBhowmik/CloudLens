"""Uniform Query Conventions: Pagination, Sorting, and Field Selection (Prompt 34).

Enforces:
- Cursor-based pagination encode and decode.
- Sort grammar with leading-minus descending (e.g. '-created_at', 'amount').
- Field selection projection (pruning JSON representations to requested attributes).
"""

from __future__ import annotations

import base64
import json
from typing import Any, TypeVar

T = TypeVar("T")


def encode_cursor(offset: int) -> str:
    """Encodes numeric offset into opaque base64 cursor token."""
    raw = json.dumps({"offset": offset})
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")


def decode_cursor(cursor: str | None) -> int:
    """Decodes opaque cursor token back to numeric offset. Returns 0 if None or invalid."""
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        data = json.loads(raw)
        return int(data.get("offset", 0))
    except Exception:
        return 0


def parse_sort_instruction(sort_str: str | None) -> list[tuple[str, bool]]:
    """Parses sort string formatted with leading-minus descending.

    Examples:
    - "-created_at" -> [("created_at", True)] (descending)
    - "amount" -> [("amount", False)] (ascending)
    - "-effective_cost,provider" -> [("effective_cost", True), ("provider", False)]
    """
    if not sort_str:
        return []

    instructions: list[tuple[str, bool]] = []
    tokens = [t.strip() for t in sort_str.split(",") if t.strip()]
    for token in tokens:
        if token.startswith("-"):
            instructions.append((token[1:], True))
        else:
            instructions.append((token, False))
    return instructions


def apply_field_selection(item: dict[str, Any], fields_str: str | None) -> dict[str, Any]:
    """Prunes item dictionary to include only specified fields (comma-separated).

    Always preserves 'id' and '_metadata' if present.
    """
    if not fields_str:
        return item

    selected = {f.strip() for f in fields_str.split(",") if f.strip()}
    if not selected:
        return item

    # Always preserve id and metadata
    selected.add("id")
    if "_metadata" in item:
        selected.add("_metadata")
    if "metadata" in item:
        selected.add("metadata")

    return {k: v for k, v in item.items() if k in selected}


def sort_items(items: list[dict[str, Any]], sort_str: str | None) -> list[dict[str, Any]]:
    """Sorts a list of dictionaries in-memory based on sort grammar."""
    instructions = parse_sort_instruction(sort_str)
    if not instructions:
        return items

    result = list(items)
    for field_name, descending in reversed(instructions):
        result.sort(
            key=lambda x: (x.get(field_name) is None, x.get(field_name)),
            reverse=descending,
        )
    return result
