#!/usr/bin/env python3
"""CloudLens One-Command Demo Reset CLI Runner (Prompt 47 Item 31).

Purges, reseeds, and reloads the demonstration estate to a known state
in a single action with zero manual setup.
"""

import argparse
import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from domain.demo import (  # noqa: E402
    DemoScenario,
    get_demo_mode_service,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CloudLens One-Command Demo Reset (Prompt 47 Item 31)"
    )
    parser.add_argument(
        "--tenant-id",
        default="T-DEMO",
        help="Target tenant identifier (default: T-DEMO)",
    )
    parser.add_argument(
        "--scenario",
        default=DemoScenario.MONTH_END_REVIEW.value,
        choices=[s.value for s in DemoScenario],
        help="Target demonstration scenario to load after reset",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic pseudorandom seed (default: 42)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON reset result report",
    )
    args = parser.parse_args()

    service = get_demo_mode_service()
    start = time.perf_counter()

    try:
        report = service.reset_demo(
            tenant_id=args.tenant_id,
            scenario=args.scenario,
            seed=args.seed,
        )
    except Exception as exc:
        print(f"[ERROR] Demonstration estate reset failed: {exc}", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - start

    if args.json:
        print(report.model_dump_json(indent=2))
        return 0

    print("========================================================================")
    print("   CLOUDLENS DEMONSTRATION RESET (PROMPT 47 ITEM 31)")
    print("   Deterministic Purge, Reseed, and Scenario Initialization")
    print("========================================================================")
    print(f"Status:               {report.status}")
    print(f"Tenant ID:            {report.tenant_id}")
    print(f"Active Scenario:      {report.scenario}")
    print(f"Purged Records:       {report.purged_records}")
    print(f"Reseeded Resources:   {report.reseeded_resources}")
    print(f"Reseeded Cost Facts:  {report.reseeded_cost_facts}")
    print(f"Manifest SHA256:      {report.manifest_hash}")
    print(f"Reset Duration:       {report.elapsed_seconds:.4f}s (Total wall-clock: {elapsed:.4f}s)")
    print("========================================================================")
    print("Demonstration estate is cleanly restored and ready for presentation.")
    print("========================================================================")

    return 0


if __name__ == "__main__":
    sys.exit(main())
