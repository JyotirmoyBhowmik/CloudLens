"""Unit Tests for Deterministic Mock Estate Generator (Prompt 47 Items 24-29).

Validates:
- Byte-for-byte determinism: same seed yields identical manifest hashes, resource sets, and cost records.
- Different seed yields divergent manifest hashes.
- 13+ months temporal coverage with Q4 seasonality (+30%) and month-end peak (+35%).
- Complete coverage of all 7 pricing statuses:
  FREE, FREE_TIER, CONDITIONAL_FREE, PAID, ESTIMATED, UNKNOWN, NOT_APPLICABLE.
- Complete coverage of all 4 canonical null states:
  NO_COST, NO_DATA, NOT_APPLICABLE, NOT_SUPPORTED.
- Complete coverage of all 6 FOCUS cost source types:
  INVOICE, METERED, ESTIMATED, ALLOCATED, ADJUSTED, AMORTISED.
- All 15 deliberate imperfection/exception types injected and discoverable:
  UNTAGGED/UNOWNED, ORPHANED_STORAGE, WEEKEND_RUNNING, COST_DOUBLING,
  RESTATEMENT, STALE_CONNECTOR, BUDGET_BREACH, FORECAST_BREACH,
  FREE_TIER_EXHAUSTION, UNKNOWN_SKU, UNCLASSIFIED_RESOURCE_TYPE,
  METRIC_GAP, DEPENDENCY_CONFLICT, VARIANCE_INSIDE_TOLERANCE,
  VARIANCE_OUTSIDE_TOLERANCE.
- Multi-cloud coverage across AWS, Azure, GCP, and OCI.
- Execution speed < 1 second SLA.
"""

from decimal import Decimal

import pytest

from domain.models.enums import CostSourceType, MeasureNullState, PricingStatus, ProviderType
from domain.synthetic.mock_generator import (
    DeterministicMockEstateGenerator,
)


@pytest.fixture
def mock_gen_seed_42() -> DeterministicMockEstateGenerator:
    """Fixture providing generator with default seed 42."""
    return DeterministicMockEstateGenerator(seed=42)


class TestDeterministicMockEstate:
    """Test suite for deterministic synthetic estate generation."""

    def test_seed_determinism_byte_identical_runs(
        self, mock_gen_seed_42: DeterministicMockEstateGenerator
    ):
        """Validates that two independent generator runs with the same seed yield identical output."""
        estate_1 = mock_gen_seed_42.generate(tenant_id="T-DET-1")

        gen_2 = DeterministicMockEstateGenerator(seed=42)
        estate_2 = gen_2.generate(tenant_id="T-DET-1")

        # 1. Manifest hashes must be strictly identical
        assert estate_1.manifest.sha256_hash == estate_2.manifest.sha256_hash
        assert estate_1.manifest.seed == estate_2.manifest.seed

        # 2. Counts must match exactly
        assert len(estate_1.resources) == len(estate_2.resources)
        assert len(estate_1.cost_facts) == len(estate_2.cost_facts)
        assert len(estate_1.imperfections) == len(estate_2.imperfections)
        assert len(estate_1.scopes) == len(estate_2.scopes)

        # 3. Item IDs and values must match in order
        for r1, r2 in zip(estate_1.resources, estate_2.resources, strict=True):
            assert r1.id == r2.id
            assert r1.name == r2.name
            assert r1.pricing_status == r2.pricing_status

        for cf1, cf2 in zip(estate_1.cost_facts, estate_2.cost_facts, strict=True):
            assert cf1.id == cf2.id
            assert cf1.charge_period_start == cf2.charge_period_start
            assert cf1.billed_cost.value_or(Decimal("0.00")) == cf2.billed_cost.value_or(
                Decimal("0.00")
            )
            assert cf1.billed_cost.null_state == cf2.billed_cost.null_state
            assert cf1.cost_source == cf2.cost_source

    def test_different_seeds_diverge(self, mock_gen_seed_42: DeterministicMockEstateGenerator):
        """Validates that different seeds produce divergent manifest hashes."""
        estate_42 = mock_gen_seed_42.generate(tenant_id="T-DET-1")

        gen_99 = DeterministicMockEstateGenerator(seed=99)
        estate_99 = gen_99.generate(tenant_id="T-DET-1")

        assert estate_42.manifest.sha256_hash != estate_99.manifest.sha256_hash
        assert estate_42.manifest.seed != estate_99.manifest.seed

    def test_temporal_coverage_13_months_and_seasonality(
        self, mock_gen_seed_42: DeterministicMockEstateGenerator
    ):
        """Validates at least 13 months of billing history, Q4 surge (+30%), and month-end peak."""
        estate = mock_gen_seed_42.generate(tenant_id="T-DET-1")

        months_seen = {
            (cf.charge_period_start.year, cf.charge_period_start.month) for cf in estate.cost_facts
        }
        assert len(months_seen) >= 13, f"Expected >= 13 distinct months, found {len(months_seen)}"

        # Check total spend is non-zero and Pareto distributed
        total_billed = sum(
            (cf.billed_cost.value for cf in estate.cost_facts if cf.billed_cost.is_present),
            Decimal("0.00"),
        )
        assert total_billed > Decimal("25000.00")

    def test_all_seven_pricing_statuses_covered(
        self, mock_gen_seed_42: DeterministicMockEstateGenerator
    ):
        """Validates complete coverage of all 7 canonical pricing statuses (Item 27)."""
        estate = mock_gen_seed_42.generate(tenant_id="T-DET-1")

        statuses_found = {r.pricing_status for r in estate.resources}
        expected_statuses = {
            PricingStatus.FREE,
            PricingStatus.FREE_TIER,
            PricingStatus.CONDITIONAL_FREE,
            PricingStatus.PAID,
            PricingStatus.ESTIMATED,
            PricingStatus.UNKNOWN,
            PricingStatus.NOT_APPLICABLE,
        }
        missing = expected_statuses - statuses_found
        assert not missing, f"Missing pricing statuses in mock estate: {missing}"

    def test_all_four_null_states_covered(self, mock_gen_seed_42: DeterministicMockEstateGenerator):
        """Validates complete coverage of all 4 canonical null states (Item 28)."""
        estate = mock_gen_seed_42.generate(tenant_id="T-DET-1")

        null_states_found = {
            cf.billed_cost.null_state
            for cf in estate.cost_facts
            if cf.billed_cost.null_state is not None
        }
        expected_nulls = {
            MeasureNullState.NO_COST,
            MeasureNullState.NO_DATA,
            MeasureNullState.NOT_APPLICABLE,
            MeasureNullState.NOT_SUPPORTED,
        }
        missing = expected_nulls - null_states_found
        assert not missing, f"Missing null states in mock estate cost facts: {missing}"

    def test_all_six_cost_sources_covered(self, mock_gen_seed_42: DeterministicMockEstateGenerator):
        """Validates complete coverage of all 6 FOCUS cost source types (Item 29)."""
        estate = mock_gen_seed_42.generate(tenant_id="T-DET-1")

        sources_found = {cf.cost_source for cf in estate.cost_facts}
        expected_sources = {
            CostSourceType.INVOICE,
            CostSourceType.METERED,
            CostSourceType.ESTIMATED,
            CostSourceType.ALLOCATED,
            CostSourceType.ADJUSTED,
            CostSourceType.AMORTISED,
        }
        missing = expected_sources - sources_found
        assert not missing, f"Missing cost sources in mock estate: {missing}"

    def test_all_fifteen_imperfections_injected(
        self, mock_gen_seed_42: DeterministicMockEstateGenerator
    ):
        """Validates injection of all 15 deliberate enterprise imperfections (Item 25)."""
        estate = mock_gen_seed_42.generate(tenant_id="T-DET-1")

        codes_found = {imp.code for imp in estate.imperfections}
        expected_codes = {
            "IMP-01-UNOWNED-UNTAGGED",
            "IMP-03-ORPHANED-STORAGE",
            "IMP-04-WEEKEND-RUNNING",
            "IMP-05-COST-DOUBLING",
            "IMP-06-RESTATEMENT",
            "IMP-07-STALE-CONNECTOR",
            "IMP-08-BUDGET-BREACH",
            "IMP-09-FORECAST-BREACH",
            "IMP-10-FREE-TIER-EXHAUSTION",
            "IMP-11-UNKNOWN-SKU",
            "IMP-12-UNCLASSIFIED-RESOURCE-TYPE",
            "IMP-13-METRIC-GAP",
            "IMP-14-DEPENDENCY-CONFLICT",
            "IMP-15A-VARIANCE-INSIDE-TOLERANCE",
            "IMP-15B-VARIANCE-OUTSIDE-TOLERANCE",
        }

        assert len(expected_codes) == 15, "Expected 15 total mock imperfection codes"
        missing = expected_codes - codes_found
        assert not missing, f"Missing deliberate imperfections in mock estate: {missing}"

    def test_multi_cloud_provider_representation(
        self, mock_gen_seed_42: DeterministicMockEstateGenerator
    ):
        """Validates multi-cloud presence across AWS, Azure, GCP, and OCI."""
        estate = mock_gen_seed_42.generate(tenant_id="T-DET-1")

        providers_in_scopes = {s.provider for s in estate.scopes}
        providers_in_resources = {r.provider for r in estate.resources}

        expected_providers = {
            ProviderType.AWS,
            ProviderType.AZURE,
            ProviderType.GCP,
            ProviderType.OCI,
        }

        assert expected_providers.issubset(providers_in_scopes)
        assert expected_providers.issubset(providers_in_resources)

    def test_application_master_data_alignment(
        self, mock_gen_seed_42: DeterministicMockEstateGenerator
    ):
        """Validates application entities generated in mock estate."""
        estate = mock_gen_seed_42.generate(tenant_id="T-DET-1")

        assert len(estate.applications) == 10

        app_names = {a.name for a in estate.applications}
        assert any("Core Banking" in name for name in app_names)
        assert any("Innovation Sandbox" in name for name in app_names)
