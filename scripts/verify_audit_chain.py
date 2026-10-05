#!/usr/bin/env python3
"""Audit Hash Chain Verification Utility (Prompt R-FEAT / IMP-03).

Verifies the cryptographic append-only SHA-256 hash chaining of audit event streams.
Usage:
    python scripts/verify_audit_chain.py [--tenant TENANT_ID]
Returns:
    Exit code 0 on intact chain.
    Exit code 1 on tampered or corrupted chain.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from domain.audit.service import get_audit_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify cryptographic hash chain of audit records.")
    parser.add_argument(
        "--tenant",
        default="demo-corp",
        help="Target tenant ID to verify (default: demo-corp)",
    )
    args = parser.parse_args()

    tenant_id = args.tenant
    print(f"============================================================")
    print(f" CLOUDLENS AUDIT STREAM CRYPTOGRAPHIC HASH CHAIN VERIFIER   ")
    print(f" Target Tenant: {tenant_id}                                 ")
    print(f" Algorithm:     SHA-256 (HMAC/Chain Link)                   ")
    print(f"============================================================")

    audit_svc = get_audit_service()
    result = audit_svc.verify_audit_hash_chain(tenant_id=tenant_id)

    if result.get("valid"):
        count = result.get("verified_count", 0)
        head = result.get("chain_head", "GENESIS")
        print(f"STATUS:        PASS")
        print(f"RECORDS:       {count} audit events cryptographically verified")
        print(f"CHAIN HEAD:    {head}")
        print(f"INTEGRITY:     Tamper-proof seal intact. No records altered or deleted.")
        print(f"============================================================")
        return 0
    else:
        err = result.get("error", "UNKNOWN")
        idx = result.get("broken_at_index", -1)
        ev_id = result.get("event_id", "N/A")
        print(f"STATUS:        FAIL — AUDIT STREAM CORRUPTION DETECTED!")
        print(f"ERROR:         {err}")
        print(f"INDEX:         {idx}")
        print(f"EVENT ID:      {ev_id}")
        print(f"INTEGRITY:     CHAIN VIOLATION DETECTED. IMMEDIATE SECURITY AUDIT REQUIRED.")
        print(f"============================================================")
        return 1


if __name__ == "__main__":
    sys.exit(main())
