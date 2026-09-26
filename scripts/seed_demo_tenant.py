#!/usr/bin/env python3
"""CloudLens Demonstration Tenant Seeder CLI Runner (Prompt 09 Item 63).

Brings a clean deployment to a fully populated, demonstratable state in under
two minutes, with all four deliberate anomalies discoverable in the data.
"""

import argparse
import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from domain.synthetic.demo_tenant import (  # noqa: E402
    DEMO_TENANT_ID,
    get_demo_tenant_service,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CloudLens Demonstration Tenant Seeder (Prompt 09)"
    )
    parser.add_argument(
        "--tenant-id",
        default=DEMO_TENANT_ID,
        help=f"Target demonstration tenant identifier (default: {DEMO_TENANT_ID})",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=50,
        help="Base sample size of cloud resources per provider (default: 50)",
    )
    parser.add_argument(
        "--force-reseed",
        action="store_true",
        help="Force regeneration and replacement of any existing demonstration estate",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate synthetic estate in-memory without persisting",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON seed result report",
    )
    args = parser.parse_args()

    service = get_demo_tenant_service()
    start = time.perf_counter()

    try:
        report = service.seed_demo_tenant(
            tenant_id=args.tenant_id,
            sample_size=args.size,
            force_reseed=args.force_reseed,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"[ERROR] Demonstration tenant seeding failed: {exc}", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - start

    if args.json:
        print(report.model_dump_json(indent=2))
        return 0

    print("========================================================================")
    print("   CLOUDLENS DEMONSTRATION TENANT LOADER (PROMPT 09)")
    print("   Populated Multi-Provider Estate & Injected Governance Anomalies")
    print("========================================================================")
    print(f"Status:               {report.status}")
    print(f"Tenant ID:            {report.tenant_id}")
    print(f"Tenant Name:          {report.tenant_name}")
    print(f"Reseeded:             {report.is_reseeded}")
    print(f"Catalogues Seeded:    {report.catalogues_seeded}")
    print(f"Execution Duration:   {report.elapsed_seconds:.4f}s (Total wall-clock: {elapsed:.4f}s)")
    print("------------------------------------------------------------------------")
    print("ESTATE OBJECT COUNTS:")
    print(f"  - Scopes (Multi-level Hierarchy):  {report.scopes_count}")
    print(f"  - Cloud Resources:                 {report.resources_count}")
    print(f"  - Cost Facts (Pareto Spend):       {report.cost_facts_count}")
    print(f"  - Usage Facts (Metrics):           {report.usage_facts_count}")
    print(f"  - Runtime States (Telemetry):      {report.runtime_states_count}")
    print(f"  - Resource Dependencies:           {report.dependencies_count}")
    print(f"  - Connector Sync Jobs:             {report.sync_jobs_count}")
    print("------------------------------------------------------------------------")
    print("INJECTED GOVERNANCE ANOMALIES (ALL 4 DISCOVERABLE):")
    for idx, anom in enumerate(report.anomalies, 1):
        print(f"  [{idx}] Type:      {anom.anomaly_type.value}")
        print(f"      Target:    {anom.target_id}")
        print(f"      Observed:  {anom.detected_value}")
        print(f"      Baseline:  {anom.expected_baseline}")
        print(f"      Detail:    {anom.description}")
    print("========================================================================")
    print("Demo tenant is ready for analytics, exploration, and API querying.")
    print("========================================================================")

    return 0


if __name__ == "__main__":
    sys.exit(main())
