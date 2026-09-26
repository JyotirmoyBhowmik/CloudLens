#!/usr/bin/env python3
"""CloudLens Superuser Provisioning CLI Runner (Prompt 49B).

Provisions the single named superuser identity from master data, establishes
unrestricted platform scope, enforces mandatory MFA, consolidates break-glass,
and generates the authoritative identity verification report.
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from domain.bootstrap import get_superuser_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CloudLens Superuser Provisioning & Break-Glass Consolidation (Prompt 49B)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON verification report",
    )
    args = parser.parse_args()

    service = get_superuser_service()
    try:
        user, token = service.provision_superuser()
        report = service.generate_verification_report()
    except Exception as exc:
        print(f"[ERROR] Superuser provisioning failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(report.model_dump_json(indent=2))
        return 0

    print("========================================================================")
    print("   CLOUDLENS SUPERUSER PROVISIONING & BREAK-GLASS (STAGE 5 — PROMPT 49B)")
    print("   Closes Defect D-01: Single Named Identity with Consolidated Break-Glass")
    print("========================================================================")
    print(f"Status:               {report.status}")
    print(f"Superuser Email:      {report.superuser_email}")
    print(f"Role:                 {report.role} (Unrestricted Scope: {report.unrestricted_scope})")
    print(
        f"MFA Enforced:         {report.mfa_enforced} (Non-Disableable: {not report.mfa_disableable})"
    )
    print(
        f"Credential State:     {'Activated' if report.has_password else 'Pending First-Use Activation'}"
    )
    print(f"Activation Channel:   {report.activation_channel}")
    print(
        f"Break-Glass Paths:    {report.break_glass_count} ({', '.join(report.break_glass_paths)})"
    )
    print("------------------------------------------------------------------------")
    print(f"Activation Link:      {token.activation_link}")
    print(f"Activation Token:     {token.token}")
    print(f"Token Expires At:     {token.expires_at.isoformat()}")
    print("========================================================================")
    print("[SUCCESS] Identity Verification Report published to docs/configuration/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
