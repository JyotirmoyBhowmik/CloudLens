"""File Upload, Encoding Detection, and Delimiter Parsing Engine (Prompt 53).

Provides:
- Encoding detection (UTF-8, UTF-8-BOM, UTF-16, Latin-1, CP1252).
- Delimiter detection (comma, semicolon, tab, pipe).
- Format parsing for CSV, TSV, JSON with line/row numbering.
- Cryptographic SHA-256 fingerprinting of uploaded payloads.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from typing import Any


def compute_content_hash(content_bytes: bytes) -> str:
    """Computes standard SHA-256 hexadecimal hash for payload provenance."""
    return hashlib.sha256(content_bytes).hexdigest()


def detect_encoding(content_bytes: bytes) -> str:
    """Detects character encoding of uploaded file content."""
    # Check for byte-order marks first
    if content_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if content_bytes.startswith(b"\xff\xfe") or content_bytes.startswith(b"\xfe\xff"):
        return "utf-16"

    # Attempt UTF-8 decode
    try:
        content_bytes.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    # Attempt Windows-1252 / ISO-8859-1
    try:
        content_bytes.decode("cp1252")
        return "cp1252"
    except UnicodeDecodeError:
        return "latin1"


def detect_delimiter(sample_text: str) -> str:
    """Detects CSV delimiter from sample text (comma, semicolon, tab, pipe)."""
    # Count occurrences of candidate delimiters in the first non-comment lines
    lines = [
        ln.strip()
        for ln in sample_text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ][:5]
    if not lines:
        return ","

    candidates = [",", ";", "\t", "|"]
    counts = dict.fromkeys(candidates, 0)

    for ln in lines:
        for delim in candidates:
            counts[delim] += ln.count(delim)

    # Pick candidate with max count
    best_delim = max(counts, key=lambda k: counts[k])
    return best_delim if counts[best_delim] > 0 else ","


def parse_file_content(
    content_bytes: bytes,
    filename: str,
    explicit_encoding: str | None = None,
    explicit_delimiter: str | None = None,
) -> tuple[str, str, list[tuple[int, dict[str, Any]]]]:
    """Parses raw uploaded file content into 1-based numbered row dictionaries.

    Returns:
        (detected_encoding, detected_delimiter, rows_with_line_numbers)
    """
    encoding = explicit_encoding or detect_encoding(content_bytes)
    text_content = content_bytes.decode(encoding, errors="replace")

    fname_lower = filename.lower()
    if fname_lower.endswith(".json") or (
        text_content.strip().startswith("[") and text_content.strip().endswith("]")
    ):
        # JSON parsing
        try:
            parsed = json.loads(text_content)
            if not isinstance(parsed, list):
                raise ValueError("JSON import root must be an array of objects.")
            result_rows = []
            for idx, item in enumerate(parsed, start=1):
                if isinstance(item, dict):
                    result_rows.append((idx, item))
                else:
                    raise ValueError(f"JSON row {idx} is not an object.")
            return encoding, "json", result_rows
        except Exception as e:
            raise ValueError(f"Failed to parse JSON file: {e}") from e

    # Delimited tabular parsing (CSV, TSV, DSV)
    delimiter = explicit_delimiter or detect_delimiter(text_content[:4096])

    # Strip comment lines starting with #
    clean_lines = []
    for line in text_content.splitlines():
        if line.strip().startswith("#"):
            continue
        clean_lines.append(line)

    clean_content = "\n".join(clean_lines)
    reader = csv.DictReader(io.StringIO(clean_content), delimiter=delimiter)

    rows: list[tuple[int, dict[str, Any]]] = []
    # DictReader starts on header line (row 1 in file), so data rows start at row 2
    for row_idx, raw_dict in enumerate(reader, start=2):
        cleaned_row = {
            k.strip(): (v.strip() if isinstance(v, str) else v)
            for k, v in raw_dict.items()
            if k is not None
        }
        rows.append((row_idx, cleaned_row))

    return encoding, delimiter, rows
