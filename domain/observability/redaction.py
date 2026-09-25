"""CloudLens PII & Secret Redaction Engine.

Strips credentials, auth tokens, private keys, API keys, and sensitive PII from log lines
and structured telemetry before emission (Enterprise Rule 4.3 / Prompt 03 Item 22).
"""

import re
from typing import Any

# Regex patterns for credential formats and PII
CREDENTIAL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # JWT Tokens: eyJ...
    (
        re.compile(r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),
        "[REDACTED_JWT]",
    ),
    # Authorization: Bearer <token>
    (
        re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.~+/]+=*", re.IGNORECASE),
        "Bearer [REDACTED_TOKEN]",
    ),
    # AWS Access Key ID
    (
        re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"),
        "[REDACTED_AWS_KEY]",
    ),
    # Google / GitHub / Slack API key tokens
    (
        re.compile(r"(?:ghp_[A-Za-z0-9]{36}|xox[baprs]-[A-Za-z0-9_\-]+|AIza[0-9A-Za-z-_]{35})"),
        "[REDACTED_API_KEY]",
    ),
    # Key-Value assignments in logs: e.g. password=secret, "token": "val", api_key: "abc"
    (
        re.compile(
            r"""(?i)(["']?(?:password|passwd|secret|client_secret|token|auth_token|api_key|access_key|private_key|db_password)["']?\s*[:=]\s*["']?)(?!\[REDACTED|Bearer\s+\[REDACTED)(?:Bearer\s+)?[^"'}\s,]+(["']?)"""
        ),
        r"\1[REDACTED]\2",
    ),
    # Credit Card Numbers
    (
        re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
        "[REDACTED_CREDIT_CARD]",
    ),
    # US Social Security Number (SSN)
    (
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[REDACTED_SSN]",
    ),
]

SENSITIVE_KEY_SUBSTRINGS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "client_secret",
    "authorization",
    "cert",
    "credentials",
)


def redact_text(text: str) -> str:
    """Scans plain text and replaces credential patterns and PII with redaction placeholders."""
    if not text:
        return text

    sanitized = text
    for pattern, replacement in CREDENTIAL_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def redact_value(val: Any) -> Any:
    """Recursively redacts values in strings, dicts, lists, and tuples."""
    if isinstance(val, str):
        return redact_text(val)
    if isinstance(val, dict):
        redacted_dict: dict[str, Any] = {}
        for k, v in val.items():
            k_lower = str(k).lower()
            if any(sub in k_lower for sub in SENSITIVE_KEY_SUBSTRINGS):
                redacted_dict[k] = "[REDACTED]"
            else:
                redacted_dict[k] = redact_value(v)
        return redacted_dict
    if isinstance(val, list):
        return [redact_value(item) for item in val]
    if isinstance(val, tuple):
        return tuple(redact_value(item) for item in val)
    return val
