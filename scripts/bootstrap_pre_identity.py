#!/usr/bin/env python3
"""CloudLens Pre-Identity System Bootstrap CLI Runner (Prompt 49A).

Brings a clean deployment to a fully seeded, master-data-complete state
with zero identities, zero credentials, and zero grants.
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from domain.bootstrap import get_pre_identity_bootstrap_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CloudLens Pre-Identity System Bootstrap (Prompt 49A)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate seeds, masters, and configurations without mutating storage",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON verification report",
    )
    args = parser.parse_args()

    service = get_pre_identity_bootstrap_service()
    try:
        report = service.bootstrap(dry_run=args.dry_run)
    except Exception as exc:
        print(f"[ERROR] Pre-identity bootstrap failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(report.model_dump_json(indent=2))
        return 0

    print("========================================================================")
    print("   CLOUDLENS PRE-IDENTITY SYSTEM BOOTSTRAP (STAGE 3 — PROMPT 49A)")
    print("   Closes Defect D-01: Foundation Decoupled from Identity & Auth")
    print("========================================================================")
    print(f"Status:               {report.status}")
    print(f"Already Initialized:  {report.is_already_initialized}")
    print(f"Correlation ID:       {report.correlation_id}")
    print(f"Timestamp:            {report.timestamp.isoformat()}")
    print("------------------------------------------------------------------------")
    print(f"System Tenant ID:     {report.tenant_id}")
    print(f"Tenant Name:          {report.tenant_name}")
    print(f"Reporting Currency:   {report.reporting_currency}")
    print(
        f"Fiscal Calendar:      {report.fiscal_calendar_code} (Start Month: {report.fiscal_calendar_start_month})"
    )
    print(f"Default Timezone:     {report.time_zone}")
    print("------------------------------------------------------------------------")
    print("RECONCILED CATALOGUE COUNTS (PROMPT 00R PARITY):")
    for cat, count in report.catalogues_populated.items():
        print(f"  - {cat:25}: {count}")
    print("------------------------------------------------------------------------")
    print("RBAC Foundation:")
    print(f"  - Total Permissions:  {report.permission_count}")
    print(f"  - Built-in Roles (9): {', '.join(report.roles_defined)}")
    print("------------------------------------------------------------------------")
    print("CLOUD PROVIDER REGISTRATIONS & CAPABILITIES:")
    for prov, caps in report.providers_registered.items():
        has_quota = "C-18" in caps
        print(
            f"  - {prov:10}: {len(caps)} capabilities [Quota C-18: {'YES' if has_quota else 'NO'}]"
        )
    print("------------------------------------------------------------------------")
    print(f"Audit Stream:         Initialized ({report.first_audit_event_id})")
    print(f"Identities Count:     {report.identities_count} (Mandatory Zero)")
    print(f"Credentials Count:    {report.credentials_count} (Mandatory Zero)")
    print(f"Scope Grants Count:   {report.grants_count} (Mandatory Zero)")
    print(f"Interactively Usable: {report.is_interactively_usable} (Explicit Declaration)")
    print("------------------------------------------------------------------------")
    print(f"NOTICE:\n  {report.status_statement}")
    print("========================================================================")

    return 0


if __name__ == "__main__":
    sys.exit(main())
