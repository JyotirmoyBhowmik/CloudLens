#!/usr/bin/env python3
"""CloudLens Named Demo Scenario Loader CLI Runner (Prompt 47 Item 32).

Allows a presenter to select and load any of the 7 named demonstration
scenarios in one click or command.
"""

import argparse
import sys
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
        description="CloudLens Named Demo Scenario Loader (Prompt 47 Item 32)"
    )
    parser.add_argument(
        "--tenant-id",
        default="T-DEMO",
        help="Target tenant identifier (default: T-DEMO)",
    )
    parser.add_argument(
        "--scenario",
        choices=[s.value for s in DemoScenario],
        help="Named demo scenario to load",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available named demonstration scenarios with descriptions",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON scenario info",
    )
    args = parser.parse_args()

    service = get_demo_mode_service()

    if args.list or not args.scenario:
        scenarios = service.get_scenarios()
        if args.json:
            import json

            print(json.dumps([s.model_dump() for s in scenarios], indent=2))
            return 0

        print("========================================================================")
        print("   CLOUDLENS NAMED DEMONSTRATION SCENARIOS (PROMPT 47 ITEM 32)")
        print("========================================================================")
        for idx, sc in enumerate(scenarios, 1):
            print(f"[{idx}] {sc.scenario.value}")
            print(f"    Title:        {sc.title}")
            print(f"    Description:  {sc.description}")
            print(f"    Focus Story:  {sc.focus_story}")
            print(f"    Key Metrics:  {sc.key_metrics}")
            print("------------------------------------------------------------------------")
        return 0

    try:
        info = service.load_scenario(tenant_id=args.tenant_id, scenario=args.scenario)
    except Exception as exc:
        print(f"[ERROR] Loading scenario failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(info.model_dump_json(indent=2))
        return 0

    print("========================================================================")
    print("   CLOUDLENS DEMO SCENARIO LOADED")
    print("========================================================================")
    print(f"Tenant ID:    {args.tenant_id}")
    print(f"Scenario:     {info.scenario.value}")
    print(f"Title:        {info.title}")
    print(f"Description:  {info.description}")
    print(f"Focus Story:  {info.focus_story}")
    print(f"Key Metrics:  {info.key_metrics}")
    print("========================================================================")
    print("Scenario is active and visible across UI dashboards and API queries.")
    print("========================================================================")

    return 0


if __name__ == "__main__":
    sys.exit(main())
