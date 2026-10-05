"""Canary Secret Redaction Proof for Loki (Prompt R-OBS Item 3).

Verifies:
1. Emits structured JSON log containing a canary secret string:
   e.g. AWS Key 'AKIAIOSFODNN7CANARY99' and password 'CanarySuperSecret123!'
2. Verifies redaction engine strips the canary secrets BEFORE shipping:
   replaces with [REDACTED_AWS_KEY] and [REDACTED].
3. Ships structured JSON log stream to Loki (http://localhost:3100/loki/api/v1/push)
   with labels: tenant='tenant-canary', service='cloudlens-api', correlation_id='corr-canary-99'.
4. Queries Loki for the stream.
5. Asserts:
   - Canary secret raw strings are strictly ABSENT from Loki.
   - Redacted log message is PRESENT in Loki.
"""

import json
import logging
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from domain.observability.logging import (
    CloudLensJsonFormatter,
    current_correlation_id,
    current_tenant_id,
)

LOKI_PUSH_URL = "http://localhost:3100/loki/api/v1/push"
LOKI_QUERY_URL = "http://localhost:3100/loki/api/v1/query"


def push_log_to_loki(log_line: str, tenant: str, service: str, correlation_id: str):
    ts_ns = str(time.time_ns())
    payload = {
        "streams": [
            {
                "stream": {
                    "tenant": tenant,
                    "service": service,
                    "correlation_id": correlation_id,
                },
                "values": [
                    [ts_ns, log_line]
                ]
            }
        ]
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        LOKI_PUSH_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 204 or resp.status == 200, f"Loki push failed: {resp.status}"


def query_loki(query_str: str) -> list[str]:
    import urllib.parse
    url = f"{LOKI_QUERY_URL}?query={urllib.parse.quote(query_str)}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode())
        entries = []
        for result in data.get("data", {}).get("result", []):
            for val in result.get("values", []):
                entries.append(val[1])
        return entries


def main():
    print("=== Starting Loki Canary Secret Redaction Proof ===")
    canary_aws_key = "AKIAIOSFODNN7CANARY99"
    canary_password = "CanarySuperSecret123!"
    tenant = "tenant-canary-proof"
    service = "cloudlens-api"
    correlation_id = "corr-canary-12345"

    current_tenant_id.set(tenant)
    current_correlation_id.set(correlation_id)

    # 1. Format log through CloudLens structured JSON formatter
    formatter = CloudLensJsonFormatter(service_name=service)
    record = logging.LogRecord(
        name="test.canary",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Connecting to AWS with key %s and password=%s",
        args=(canary_aws_key, canary_password),
        exc_info=None,
    )
    formatted_log = formatter.format(record)
    print("\nFormatted Log Line (pre-shipping):")
    print(formatted_log)

    # Pre-ship verification: Assert canary secrets NOT in formatted line
    assert canary_aws_key not in formatted_log, "CRITICAL: Raw AWS key leaked into formatted log line!"
    assert canary_password not in formatted_log, "CRITICAL: Raw password leaked into formatted log line!"
    assert "[REDACTED_AWS_KEY]" in formatted_log
    assert "password=[REDACTED]" in formatted_log

    # 2. Ship log to Loki
    print("\nShipping formatted log to Loki (http://localhost:3100)...")
    push_log_to_loki(
        log_line=formatted_log,
        tenant=tenant,
        service=service,
        correlation_id=correlation_id,
    )

    # 3. Query Loki and verify
    print("Querying Loki for log stream {service=\"cloudlens-api\", tenant=\"tenant-canary-proof\"}...")
    time.sleep(1)
    entries = query_loki('{service="cloudlens-api", tenant="tenant-canary-proof"}')
    print(f"Retrieved {len(entries)} log entries from Loki.")

    for entry in entries:
        print("Loki Entry:", entry)
        # MUST NOT contain canary secrets
        assert canary_aws_key not in entry, f"LEAK DETECTED: {canary_aws_key} found in Loki entry!"
        assert canary_password not in entry, f"LEAK DETECTED: {canary_password} found in Loki entry!"

    # Verify that the redacted line was stored and returned
    assert any("[REDACTED_AWS_KEY]" in e for e in entries), "Redacted entry missing from Loki query results!"

    print("\n>>> CANARY PROOF PASSED: Canary secret ABSENT from Loki; redaction verified! <<<")


if __name__ == "__main__":
    main()
