"""CLI script to generate synthetic multi-cloud estates of configurable size.

Enforces Prompt 04 Item 30 & Acceptance:
"The synthetic generator produces a 100,000-resource estate and the numbers reconcile to its own manifest."
"""

import argparse
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from domain.synthetic import SyntheticEstateGenerator  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic multi-cloud estate.")
    parser.add_argument(
        "--size",
        "--count",
        dest="size",
        type=int,
        default=100000,
        help="Total resources to generate (default: 100,000)",
    )
    parser.add_argument("--out", type=str, default="", help="Optional output JSONL file path")
    parser.add_argument(
        "--seed", type=int, default=42, help="RNG seed for deterministic generation"
    )
    parser.add_argument(
        "--tag-gap-ratio", type=float, default=0.20, help="Tagging debt gap ratio (default: 0.20)"
    )
    args = parser.parse_args()

    print("=" * 80)
    print("CLOUDLENS SYNTHETIC MULTI-PROVIDER ESTATE GENERATOR")
    print(f"Target estate size: {args.size:,} resources")
    print("Providers: AWS, Azure, GCP, OCI")
    print(f"Tagging debt gap ratio: {args.tag_gap_ratio * 100:.1f}%")
    print("=" * 80)

    start_time = time.perf_counter()
    generator = SyntheticEstateGenerator(
        total_resources=args.size,
        tagging_gap_ratio=args.tag_gap_ratio,
        seed=args.seed,
    )

    out_file = Path(args.out) if args.out else None
    manifest = generator.generate_and_reconcile(output_file=out_file)
    duration = time.perf_counter() - start_time

    print(
        f"\n[GENERATION COMPLETE] Generated {manifest.resource_count:,} resources in {duration:.2f}s ({manifest.resource_count / duration:,.0f} res/sec)"
    )
    print("\n--- RECONCILIATION MANIFEST ---")
    print(f"  Total Estate Spend:       ${manifest.total_cost:,.2f}")
    print(
        f"  Dominant Services Spend:  ${manifest.dominant_spend:,.2f} ({(manifest.dominant_spend / manifest.total_cost) * 100:.1f}%)"
    )
    print(
        f"  Long-Tail Services Spend: ${manifest.long_tail_spend:,.2f} ({(manifest.long_tail_spend / manifest.total_cost) * 100:.1f}%)"
    )
    print(
        f"  Tag Compliant Resources:  {manifest.compliant_tags_count:,} ({manifest.tagging_compliance_percentage}%)"
    )
    print(f"  Tagging Gaps / Debt:      {manifest.tagging_gaps_count:,}")
    print(f"  Manifest SHA256 Hash:     {manifest.reconciliation_hash}")

    print("\n--- BREAKDOWN BY PROVIDER ---")
    for prov in sorted(manifest.spend_by_provider.keys()):
        count = manifest.count_by_provider[prov]
        spend = manifest.spend_by_provider[prov]
        print(f"  {prov.upper():5}: {count:6,} resources | ${spend:12,.2f}")

    # Self-reconciliation assertion
    provider_sum = sum(manifest.spend_by_provider.values())
    assert provider_sum == manifest.total_cost, "Discrepancy in provider spend reconciliation!"
    type_sum = manifest.dominant_spend + manifest.long_tail_spend
    assert (
        type_sum == manifest.total_cost
    ), "Discrepancy in dominant/long-tail spend reconciliation!"
    total_count = manifest.compliant_tags_count + manifest.tagging_gaps_count
    assert total_count == manifest.resource_count, "Discrepancy in tagging resource count!"

    print("\n[RECONCILIATION VERIFIED] Estate numbers reconcile to manifest with 0.00 drift.")
    print("=" * 80)


if __name__ == "__main__":
    main()
