"""Unit and Acceptance Tests for Synthetic Multi-Provider Estate Generator.

Acceptance: The synthetic generator produces a 100,000-resource estate and the numbers reconcile to its own manifest.
"""

from decimal import Decimal

from domain.synthetic import SyntheticEstateGenerator


def test_synthetic_estate_generator_reconciles_at_100k():
    """Acceptance: The synthetic generator produces a 100,000-resource estate

    and the numbers reconcile to its own manifest.
    """
    generator = SyntheticEstateGenerator(total_resources=100000, seed=42)
    manifest = generator.generate_and_reconcile()

    # 1. Total resource count matches exactly 100,000
    assert manifest.resource_count == 100000

    # 2. Spend breakdown across all providers matches total cost
    provider_sum = sum(manifest.spend_by_provider.values())
    assert provider_sum == manifest.total_cost

    # 3. Dominant and long-tail spend sums exactly to total cost
    type_sum = manifest.dominant_spend + manifest.long_tail_spend
    assert type_sum == manifest.total_cost

    # 4. Tagging breakdown equals total resource count
    assert manifest.compliant_tags_count + manifest.tagging_gaps_count == 100000
    assert manifest.tagging_gaps_count > 0  # Deliberate tagging debt present

    # 5. All 4 providers represented evenly
    for provider in ("aws", "azure", "gcp", "oci"):
        assert manifest.count_by_provider[provider] == 25000
        assert manifest.spend_by_provider[provider] > Decimal("0.00")

    # 6. Cryptographic reconciliation hash verified
    assert len(manifest.reconciliation_hash) == 64
    assert manifest.reconciliation_hash == manifest.compute_hash()


def test_synthetic_estate_generator_custom_shape():
    """Verify generator responds to custom size, seed, and tagging gap ratio."""
    custom_size = 500
    custom_gap_ratio = 0.50
    gen = SyntheticEstateGenerator(
        total_resources=custom_size,
        tagging_gap_ratio=custom_gap_ratio,
        seed=123,
    )
    manifest = gen.generate_and_reconcile()

    assert manifest.resource_count == custom_size
    # With 50% gap ratio, gap count should be roughly around half
    assert 200 <= manifest.tagging_gaps_count <= 300
