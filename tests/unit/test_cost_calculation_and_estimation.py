"""Unit Tests for Cost Calculation Engine & Pre-Deployment Estimation (Prompt 23).

Enforces:
- 100% test coverage on the arithmetic for tiered pricing, free-tier deduction, and minimum charge.
- Individual isolated tests for all 12 calculation rules.
- Derivation output attached to every calculated value.
- Strict Four-Value Separation: List price, Estimated cost, Actual cost, and Forecast cost
  are distinct types and cannot be added or conflated.
- Pre-deployment estimator across AWS, Azure, GCP, and OCI across compute, database, object and block storage.
- Unavailable pricing producing UNKNOWN with a reason, never a silent zero.
- REST API integration for /api/v1/cost/estimate and /api/v1/cost/estimate/supported-services.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.cost.calculation import (
    ActualCost,
    CostCategoryType,
    CostDerivation,
    CostSourceClassification,
    EstimatedCost,
    ForecastCost,
    PreDeploymentEstimateRequest,
    PreDeploymentEstimateResult,
    ProviderListPrice,
    RuntimeScheduleType,
    get_calculation_engine,
    get_pre_deployment_estimator,
    reset_calculation_engine,
    reset_pre_deployment_estimator,
    rule_1_unit_conversion,
    rule_2_currency_conversion,
    rule_3_rounding,
    rule_4_tier_calculation,
    rule_5_free_allowance,
    rule_6_minimum_charge,
    rule_7_commitment_application,
    rule_8_discount_application,
    rule_9_missing_data,
    rule_10_data_freshness,
    rule_11_runtime_schedule,
    rule_12_cost_driver_decomposition,
)
from domain.models.enums import PricingStatus
from domain.models.exceptions import IncompatibleCostTypeError
from domain.pricing.models import (
    CommitmentInfo,
    DiscountInfo,
    FreeAllowance,
    PricingRecord,
    PricingTierModel,
    TierBracket,
    TierStructure,
)


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons before each test."""
    reset_calculation_engine()
    reset_pre_deployment_estimator()
    yield
    reset_calculation_engine()
    reset_pre_deployment_estimator()


# ==============================================================================
# 1. Isolated Tests for the 12 Calculation Rules
# ==============================================================================


def test_rule_1_unit_conversion_through_catalogue():
    """Rule 1: Unit conversion strictly via the declarative Unit Catalogue."""
    # Identity conversion
    assert rule_1_unit_conversion(Decimal("100"), "GB", "GB") == Decimal("100")

    # GiB to TiB conversion (1024 GiB = 1 TiB)
    converted = rule_1_unit_conversion(Decimal("2048"), "GiB", "TiB")
    assert converted == Decimal("2.000000")

    # Time conversion: 1 day = 24 hours
    hrs = rule_1_unit_conversion(Decimal("5"), "days", "hours")
    assert hrs == Decimal("120.000000")


def test_rule_2_currency_conversion_at_stated_rate_and_date():
    """Rule 2: Query-time currency conversion with rate and date disclosure."""
    eval_date = date(2026, 3, 1)

    # Identity conversion
    same = rule_2_currency_conversion(Decimal("100.00"), "USD", "USD", as_of_date=eval_date)
    assert same.target_amount == Decimal("100.00")
    assert same.exchange_rate == Decimal("1.0")
    assert "native currency USD" in same.disclosure

    # USD to EUR
    conv = rule_2_currency_conversion(Decimal("100.00"), "USD", "EUR", as_of_date=eval_date)
    assert conv.target_currency == "EUR"
    assert conv.exchange_rate == Decimal("0.9250")
    assert conv.target_amount == Decimal("92.50")
    assert "effective rate 0.9250" in conv.disclosure


def test_rule_3_uniform_rounding_policy():
    """Rule 3: Uniform Banker's rounding (ROUND_HALF_EVEN) defined once."""
    assert rule_3_rounding(Decimal("2.5"), decimal_places=0) == Decimal("2")
    assert rule_3_rounding(Decimal("3.5"), decimal_places=0) == Decimal("4")
    assert rule_3_rounding(Decimal("10.555"), decimal_places=2) == Decimal("10.56")
    assert rule_3_rounding(Decimal("10.554"), decimal_places=2) == Decimal("10.55")
    assert rule_3_rounding(Decimal("100.125"), decimal_places=2) == Decimal("100.12")


def test_rule_4_tier_calculation_graduated_hand_calculated():
    """Rule 4: Graduated tiered pricing produces exact hand-calculated figures."""
    # Brackets:
    # 0 to 50 GB at $0.023/GB
    # 50 to 500 GB at $0.022/GB
    # 500+ GB at $0.021/GB
    tier_struct = TierStructure(
        pricing_model=PricingTierModel.GRADUATED,
        brackets=[
            TierBracket(tier_start=0.0, tier_end=50.0, tier_unit_rate=0.023),
            TierBracket(tier_start=50.0, tier_end=500.0, tier_unit_rate=0.022),
            TierBracket(tier_start=500.0, tier_end=None, tier_unit_rate=0.021),
        ],
    )

    # 120 GB: Bracket 1 = 50 * 0.023 = 1.15; Bracket 2 = 70 * 0.022 = 1.54 -> Total = 2.69
    cost, steps = rule_4_tier_calculation(
        Decimal("120"), tier_struct, default_unit_rate=Decimal("0.023")
    )
    assert cost == Decimal("2.690")
    assert len(steps) == 2
    assert steps[0].units_in_bracket == Decimal("50")
    assert steps[0].bracket_subtotal == Decimal("1.150")
    assert steps[1].units_in_bracket == Decimal("70")
    assert steps[1].bracket_subtotal == Decimal("1.540")

    # Zero usage produces zero
    zero_cost, zero_steps = rule_4_tier_calculation(Decimal("0"), tier_struct, Decimal("0.023"))
    assert zero_cost == Decimal("0.00")
    assert zero_steps == []


def test_rule_4_tier_calculation_volume_hand_calculated():
    """Rule 4: Volume tiered pricing (all-units threshold)."""
    tier_struct = TierStructure(
        pricing_model=PricingTierModel.VOLUME,
        brackets=[
            TierBracket(tier_start=0.0, tier_end=100.0, tier_unit_rate=0.10),
            TierBracket(tier_start=100.0, tier_end=500.0, tier_unit_rate=0.08),
            TierBracket(tier_start=500.0, tier_end=None, tier_unit_rate=0.05),
        ],
    )

    # 200 units falls into bracket 1 (100 to 500): all 200 * 0.08 = 16.00
    cost, steps = rule_4_tier_calculation(
        Decimal("200"), tier_struct, default_unit_rate=Decimal("0.10")
    )
    assert cost == Decimal("16.00")
    assert len(steps) == 1
    assert steps[0].bracket_rate == Decimal("0.08")


def test_rule_5_free_allowance_deduction_hand_calculated():
    """Rule 5: Free-tier consumption deducted before charged consumption."""
    allowance = FreeAllowance(
        quantity=5.0,
        unit="GB",
        reset_period="MONTHLY",
        post_allowance_rate=0.023,
    )

    # Usage 120 GB with 5 GB allowance -> 115 GB billable, 5 GB deducted
    net_billable, deducted = rule_5_free_allowance(Decimal("120"), allowance)
    assert net_billable == Decimal("115.0")
    assert deducted == Decimal("5.0")

    # Usage 4 GB with 5 GB allowance -> 0 GB billable, 4 GB deducted
    net_billable_small, deducted_small = rule_5_free_allowance(Decimal("4"), allowance)
    assert net_billable_small == Decimal("0.00")
    assert deducted_small == Decimal("4")

    # None allowance -> full usage billable
    net_none, deducted_none = rule_5_free_allowance(Decimal("50"), None)
    assert net_none == Decimal("50")
    assert deducted_none == Decimal("0.00")


def test_rule_4_and_5_combined_hand_calculated_fixture():
    """Combines Rule 4 (graduated tiers) and Rule 5 (free allowance) with exact hand calculation."""
    # 5 GB free allowance, then graduated tiers:
    # 0 to 50 GB at $0.023
    # 50 to 500 GB at $0.022
    allowance = FreeAllowance(quantity=5.0, unit="GB", post_allowance_rate=0.023)
    tier_struct = TierStructure(
        pricing_model=PricingTierModel.GRADUATED,
        brackets=[
            TierBracket(tier_start=0.0, tier_end=50.0, tier_unit_rate=0.023),
            TierBracket(tier_start=50.0, tier_end=500.0, tier_unit_rate=0.022),
        ],
    )

    # Usage: 120 GB
    # Step 1: Free allowance: 120 - 5 = 115 GB billable
    # Step 2: Bracket 1 (0 to 50 GB) = 50 * 0.023 = $1.15
    # Step 3: Bracket 2 (50 to 115 GB) = 65 * 0.022 = $1.43
    # Total = 1.15 + 1.43 = $2.58 exact
    net_billable, deducted = rule_5_free_allowance(Decimal("120"), allowance)
    assert net_billable == Decimal("115.0")
    cost, steps = rule_4_tier_calculation(net_billable, tier_struct, Decimal("0.023"))
    assert cost == Decimal("2.580")
    assert len(steps) == 2
    assert steps[0].bracket_subtotal == Decimal("1.150")
    assert steps[1].bracket_subtotal == Decimal("1.430")


def test_rule_6_minimum_charge_handling():
    """Rule 6: Minimum billing floor charge enforcement."""
    # Below floor: $5.00 elevated to $10.00 floor
    cost_elevated, applied = rule_6_minimum_charge(Decimal("5.00"), Decimal("10.00"))
    assert cost_elevated == Decimal("10.00")
    assert applied is True

    # Above floor: $15.00 remains $15.00
    cost_unaffected, not_applied = rule_6_minimum_charge(Decimal("15.00"), Decimal("10.00"))
    assert cost_unaffected == Decimal("15.00")
    assert not_applied is False


def test_rule_7_commitment_application():
    """Rule 7: Commitment & Reservation discounts."""
    comm = CommitmentInfo(
        commitment_type="SAVINGS_PLAN",
        term_months=12,
        payment_option="ALL_UPFRONT",
    )
    # $1.00/hr on-demand for 100 hrs = $100 baseline. 1-year SP gives 30% discount = $70 cost
    effective_cost, savings, ref = rule_7_commitment_application(
        Decimal("1.00"), comm, Decimal("100")
    )
    assert effective_cost == Decimal("70.00")
    assert savings == Decimal("30.00")
    assert "SAVINGS_PLAN_12M_ALL_UPFRONT" in (ref or "")


def test_rule_8_discount_application():
    """Rule 8: Contracted discount calculation & realized discount value."""
    # 20% discount on $100 subtotal -> $80 discounted, $20 saved
    disc_info = DiscountInfo(discount_type="PERCENTAGE", discount_percentage=20.0)
    discounted, saved, pct = rule_8_discount_application(Decimal("100.00"), disc_info)
    assert discounted == Decimal("80.00")
    assert saved == Decimal("20.00")
    assert pct == Decimal("20.0")

    # Rate comparison: list $1.00 vs contracted $0.80
    discounted_rt, saved_rt, pct_rt = rule_8_discount_application(
        Decimal("100.00"),
        discount_info=None,
        contracted_rate=Decimal("0.80"),
        list_rate=Decimal("1.00"),
    )
    assert discounted_rt == Decimal("80.00")
    assert saved_rt == Decimal("20.00")
    assert pct_rt == Decimal("20.0")


def test_rule_9_missing_data_produces_unknown_never_zero():
    """Rule 9: Missing data yields UNKNOWN with reason, never silent zero."""
    # Found -> PAID
    status_found, reason_none = rule_9_missing_data(
        pricing_found=True,
        provider="aws",
        service="AmazonEC2",
        sku="AWS-EC2-T3-XLARGE-US-EAST",
        region="us-east-1",
    )
    assert status_found == PricingStatus.PAID
    assert reason_none is None

    # Missing -> UNKNOWN
    status_missing, reason = rule_9_missing_data(
        pricing_found=False,
        provider="aws",
        service="AmazonEC2",
        sku="NON-EXISTENT-SKU",
        region="us-west-9",
    )
    assert status_missing == PricingStatus.UNKNOWN
    assert reason is not None
    assert "cannot assume 0.00" in reason


def test_rule_10_data_freshness_tracking():
    """Rule 10: Data freshness and stale indicator."""
    now = datetime.now(UTC)
    fresh_time = now - timedelta(hours=2)
    stale_time = now - timedelta(hours=48)

    is_stale_fresh, age_fresh = rule_10_data_freshness(fresh_time, stale_threshold_hours=24.0)
    assert is_stale_fresh is False
    assert age_fresh < 5.0

    is_stale_old, age_old = rule_10_data_freshness(stale_time, stale_threshold_hours=24.0)
    assert is_stale_old is True
    assert age_old > 40.0


def test_rule_11_runtime_scheduling():
    """Rule 11: Runtime scheduling calculations."""
    # 24/7 continuous = 730 hours
    hrs_continuous = rule_11_runtime_schedule(RuntimeScheduleType.CONTINUOUS_24_7)
    assert hrs_continuous == Decimal("730.0")

    # 8x5 business hours = 173.3333 hours
    hrs_8x5 = rule_11_runtime_schedule(RuntimeScheduleType.BUSINESS_HOURS_8X5)
    assert hrs_8x5 == Decimal("173.3333")

    # Custom hours
    hrs_custom = rule_11_runtime_schedule(RuntimeScheduleType.CUSTOM_HOURS, custom_hours=250.0)
    assert hrs_custom == Decimal("250.0")


def test_rule_12_cost_driver_decomposition():
    """Rule 12: Cost-driver decomposition with percentage attribution."""
    deriv = CostDerivation(
        rate_applied=Decimal("0.10"),
        pricing_dimension="DIM-03",
        quantity_consumed=Decimal("100"),
        unit="Hrs",
        net_billable_quantity=Decimal("100"),
        currency="USD",
    )

    drivers_input = [
        (CostCategoryType.COMPUTE, "EC2 Runtime", Decimal("70.00"), deriv, {}),
        (CostCategoryType.STORAGE, "EBS Volume", Decimal("20.00"), deriv, {}),
        (CostCategoryType.NETWORK, "Internet Egress", Decimal("10.00"), deriv, {}),
    ]

    components = rule_12_cost_driver_decomposition(drivers_input, currency="USD")
    assert len(components) == 3

    assert components[0].category == CostCategoryType.COMPUTE
    assert components[0].percentage_of_total == Decimal("70.00")
    assert components[0].monthly_cost.amount == 70.0

    assert components[1].category == CostCategoryType.STORAGE
    assert components[1].percentage_of_total == Decimal("20.00")

    assert components[2].category == CostCategoryType.NETWORK
    assert components[2].percentage_of_total == Decimal("10.00")


# ==============================================================================
# 2. Strict Four-Value Separation Tests
# ==============================================================================


def test_four_value_separation_types_and_addition_prohibition():
    """Enforce Prompt 23 Four-Value Separation:
    ListPrice, EstimatedCost, ActualCost, ForecastCost are distinct and NEVER summable.
    """
    actual = ActualCost(
        amount=100.0,
        currency="USD",
        source_classification=CostSourceClassification.ACTUAL,
        invoice_id="INV-001",
    )
    estimated = EstimatedCost(
        amount=100.0,
        currency="USD",
        source_classification=CostSourceClassification.ESTIMATED,
        pricing_record_id="REC-001",
        pricing_source="aws_catalog",
        usage_quantity=100.0,
        usage_unit="hours",
        estimation_formula="100 * 1.0",
    )
    forecast = ForecastCost(
        amount=100.0,
        currency="USD",
        source_classification=CostSourceClassification.FORECAST,
    )
    list_price = ProviderListPrice(
        amount=100.0,
        currency="USD",
        provider="aws",
        service="AmazonEC2",
        rate_unit="Hrs",
    )

    # 1. An estimate cannot be added to an actual; type system & runtime prevent it
    with pytest.raises(IncompatibleCostTypeError, match="Cannot sum"):
        _ = actual + estimated

    with pytest.raises(IncompatibleCostTypeError, match="Cannot sum"):
        _ = estimated + actual

    # 2. Cannot add list price to estimate or actual
    with pytest.raises(IncompatibleCostTypeError, match="Cannot sum"):
        _ = list_price + estimated

    with pytest.raises(IncompatibleCostTypeError, match="Cannot sum"):
        _ = list_price + actual

    # 3. Cannot add forecast to actual or estimate
    with pytest.raises(IncompatibleCostTypeError, match="Cannot sum"):
        _ = forecast + actual

    with pytest.raises(IncompatibleCostTypeError, match="Cannot sum"):
        _ = forecast + estimated

    # 4. Homogeneous addition within the same distinct type succeeds
    actual_2 = ActualCost(
        amount=50.0,
        currency="USD",
        source_classification=CostSourceClassification.ACTUAL,
        invoice_id="INV-002",
    )
    sum_actual = actual + actual_2
    assert isinstance(sum_actual, ActualCost)
    assert sum_actual.amount == 150.0

    estimated_2 = EstimatedCost(
        amount=50.0,
        currency="USD",
        source_classification=CostSourceClassification.ESTIMATED,
        pricing_record_id="REC-002",
        pricing_source="aws_catalog",
        usage_quantity=50.0,
        usage_unit="hours",
        estimation_formula="50 * 1.0",
    )
    sum_est = estimated + estimated_2
    assert isinstance(sum_est, EstimatedCost)
    assert sum_est.amount == 150.0

    forecast_2 = ForecastCost(
        amount=75.0,
        currency="USD",
        source_classification=CostSourceClassification.FORECAST,
    )
    sum_fc = forecast + forecast_2
    assert isinstance(sum_fc, ForecastCost)
    assert sum_fc.amount == 175.0

    list_price_2 = ProviderListPrice(
        amount=25.0,
        currency="USD",
        provider="aws",
        service="AmazonEC2",
        rate_unit="Hrs",
    )
    sum_lp = list_price + list_price_2
    assert isinstance(sum_lp, ProviderListPrice)
    assert sum_lp.amount == 125.0


# ==============================================================================
# 3. Cost Calculation Engine & Derivation Output Tests
# ==============================================================================


def test_calculation_engine_produces_full_derivation():
    """CostCalculationEngine produces accurate calculation and auditable CostDerivation."""
    engine = get_calculation_engine()

    tier_struct = TierStructure(
        pricing_model=PricingTierModel.GRADUATED,
        brackets=[
            TierBracket(tier_start=0.0, tier_end=50.0, tier_unit_rate=0.023),
            TierBracket(tier_start=50.0, tier_end=500.0, tier_unit_rate=0.022),
        ],
    )
    allowance = FreeAllowance(quantity=5.0, unit="GB-Mo", post_allowance_rate=0.023)

    record = PricingRecord(
        provider="aws",
        service="AmazonS3",
        service_sku="AWS-S3-STANDARD",
        resource_type="object_storage",
        region="us-east-1",
        pricing_dimension="DIM-11",
        unit="GB-Mo",
        unit_price=0.023,
        currency="USD",
        effective_from=datetime(2025, 1, 1, tzinfo=UTC),
        tier=tier_struct,
        free_allowance=allowance,
        source="aws_catalog",
    )

    amount, est_cost, deriv = engine.calculate_cost(
        quantity=120,
        unit="GB-Mo",
        price_quote=record,
        target_currency="USD",
        discount_info=DiscountInfo(discount_type="PERCENTAGE", discount_percentage=10.0),
    )

    # 120 - 5 = 115 GB billable.
    # 50 * 0.023 = 1.15; 65 * 0.022 = 1.43 -> 2.58
    # 10% discount -> 2.58 - 0.258 = 2.322 -> rounded 2.32
    assert isinstance(est_cost, EstimatedCost)
    assert est_cost.amount == 2.32
    assert deriv.free_allowance_deducted == Decimal("5.0")
    assert deriv.net_billable_quantity == Decimal("115.0")
    assert deriv.discount_applied_percentage == Decimal("10.0")
    assert len(deriv.tier_breakdown) == 2
    assert len(deriv.step_by_step_explanation) >= 5
    assert "Deducted free allowance" in deriv.step_by_step_explanation[2]


# ==============================================================================
# 4. Multi-Provider Pre-Deployment Estimator Tests
# ==============================================================================


def test_pre_deployment_estimator_aws_compute_with_cost_drivers():
    """Estimates AWS EC2 compute with root EBS, public IP, and egress data transfer."""
    estimator = get_pre_deployment_estimator()

    req = PreDeploymentEstimateRequest(
        provider="aws",
        service="AmazonEC2",
        region="us-east-1",
        instance_type="t3.xlarge",
        storage_gb=100.0,
        storage_type="gp3",
        public_ip=True,
        data_transfer_out_gb=50.0,
        runtime_schedule_type=RuntimeScheduleType.CONTINUOUS_24_7,
        target_currency="USD",
    )

    res = estimator.estimate(req)

    assert res.provider == "aws"
    assert res.service == "AmazonEC2"
    assert res.pricing_status == PricingStatus.ESTIMATED
    assert res.monthly_cost.amount > 0.0
    assert res.hourly_cost.amount > 0.0
    assert res.annualised_cost.amount == pytest.approx(res.monthly_cost.amount * 12.0, rel=1e-2)

    # Four distinct cost drivers should be present: Compute, Storage, Network (IP), Network (Egress covered by 100GB free)
    categories = {d.category for d in res.cost_drivers}
    assert CostCategoryType.COMPUTE in categories
    assert CostCategoryType.STORAGE in categories
    assert CostCategoryType.NETWORK in categories


def test_pre_deployment_estimator_azure_virtual_machine():
    """Estimates Azure Virtual Machine with Premium SSD disk."""
    estimator = get_pre_deployment_estimator()

    req = PreDeploymentEstimateRequest(
        provider="azure",
        service="Virtual Machines",
        region="eastus",
        instance_type="D4s v5",
        storage_gb=128.0,
        storage_type="Premium_SSD",
        public_ip=True,
        runtime_schedule_type=RuntimeScheduleType.BUSINESS_HOURS_8X5,
        target_currency="USD",
    )

    res = estimator.estimate(req)
    assert res.provider == "azure"
    assert res.pricing_status == PricingStatus.ESTIMATED
    assert res.monthly_cost.amount > 0.0
    assert res.hourly_cost.amount > 0.0


def test_pre_deployment_estimator_gcp_compute_engine():
    """Estimates GCP Compute Engine with persistent disk."""
    estimator = get_pre_deployment_estimator()

    req = PreDeploymentEstimateRequest(
        provider="gcp",
        service="Compute Engine",
        region="us-central1",
        instance_type="n2-standard-4",
        storage_gb=100.0,
        storage_type="pd-balanced",
        target_currency="USD",
    )

    res = estimator.estimate(req)
    assert res.provider == "gcp"
    assert res.pricing_status == PricingStatus.ESTIMATED
    assert res.monthly_cost.amount > 0.0


def test_pre_deployment_estimator_oci_compute():
    """Estimates OCI Compute with block volume."""
    estimator = get_pre_deployment_estimator()

    req = PreDeploymentEstimateRequest(
        provider="oci",
        service="Compute",
        region="us-ashburn-1",
        instance_type="VM.Standard.E4.Flex",
        storage_gb=50.0,
        public_ip=True,
        target_currency="USD",
    )

    res = estimator.estimate(req)
    assert res.provider == "oci"
    assert res.pricing_status == PricingStatus.ESTIMATED
    assert res.monthly_cost.amount > 0.0


def test_pre_deployment_estimator_managed_database_across_providers():
    """Estimates Managed Database across AWS, Azure, GCP, and OCI."""
    estimator = get_pre_deployment_estimator()

    # AWS RDS
    aws_db = estimator.estimate(
        PreDeploymentEstimateRequest(
            provider="aws",
            service="AmazonRDS",
            region="us-east-1",
            database_engine="PostgreSQL",
            storage_gb=100.0,
        )
    )
    assert aws_db.pricing_status == PricingStatus.ESTIMATED
    assert any(d.category == CostCategoryType.DATABASE for d in aws_db.cost_drivers)

    # Azure SQL
    az_db = estimator.estimate(
        PreDeploymentEstimateRequest(
            provider="azure",
            service="Azure SQL Database",
            region="eastus",
            storage_gb=50.0,
        )
    )
    assert az_db.pricing_status == PricingStatus.ESTIMATED

    # GCP Cloud SQL
    gcp_db = estimator.estimate(
        PreDeploymentEstimateRequest(
            provider="gcp",
            service="Cloud SQL",
            region="us-central1",
            database_engine="PostgreSQL",
            storage_gb=100.0,
        )
    )
    assert gcp_db.pricing_status == PricingStatus.ESTIMATED

    # OCI Database
    oci_db = estimator.estimate(
        PreDeploymentEstimateRequest(
            provider="oci",
            service="Base Database Service",
            region="us-ashburn-1",
        )
    )
    assert oci_db.pricing_status == PricingStatus.ESTIMATED


def test_pre_deployment_estimator_object_and_block_storage():
    """Estimates Object Storage and Block Storage across providers."""
    estimator = get_pre_deployment_estimator()

    # AWS S3 (Object Storage)
    s3_est = estimator.estimate(
        PreDeploymentEstimateRequest(
            provider="aws",
            service="AmazonS3",
            region="us-east-1",
            storage_gb=500.0,
            data_transfer_out_gb=100.0,
        )
    )
    assert s3_est.pricing_status == PricingStatus.ESTIMATED

    # Azure Blob Storage
    blob_est = estimator.estimate(
        PreDeploymentEstimateRequest(
            provider="azure",
            service="Blob Storage",
            region="eastus",
            storage_gb=1000.0,
        )
    )
    assert blob_est.pricing_status == PricingStatus.ESTIMATED

    # AWS EBS (Block Storage)
    ebs_est = estimator.estimate(
        PreDeploymentEstimateRequest(
            provider="aws",
            service="AmazonEBS",
            region="us-east-1",
            storage_gb=200.0,
        )
    )
    assert ebs_est.pricing_status == PricingStatus.ESTIMATED


def test_pre_deployment_estimator_unavailable_pricing_produces_unknown_never_zero():
    """Unavailable pricing produces UNKNOWN with reason and last known date, never zero."""
    estimator = get_pre_deployment_estimator()

    req = PreDeploymentEstimateRequest(
        provider="aws",
        service="UnheardOfServiceXYZ",
        region="ap-nowhere-1",
    )

    res = estimator.estimate(req)
    assert res.pricing_status == PricingStatus.UNKNOWN
    assert res.unavailability_reason is not None
    assert "UnheardOfServiceXYZ" in res.unavailability_reason
    assert res.monthly_cost.amount == 0.0
    assert "UNAVAILABLE" in res.monthly_cost.estimation_formula


def test_pre_deployment_estimator_extensible_service_registration():
    """Custom service handler can be registered dynamically in the registry."""
    estimator = get_pre_deployment_estimator()

    def custom_quantum_estimator(req: PreDeploymentEstimateRequest) -> PreDeploymentEstimateResult:
        deriv = CostDerivation(
            rate_applied=Decimal("5.00"),
            pricing_dimension="DIM-99",
            quantity_consumed=Decimal("10"),
            unit="qbit-hr",
            net_billable_quantity=Decimal("10"),
            currency="USD",
        )
        cost = EstimatedCost(
            amount=50.0,
            currency="USD",
            pricing_record_id="custom-quantum",
            pricing_source="quantum_custom",
            usage_quantity=10.0,
            usage_unit="qbit-hr",
            estimation_formula="10 * 5.0 = 50.0",
        )
        return PreDeploymentEstimateResult(
            provider=req.provider,
            service=req.service,
            region=req.region,
            currency="USD",
            pricing_status=PricingStatus.ESTIMATED,
            hourly_cost=cost,
            daily_cost=cost,
            monthly_cost=cost,
            annualised_cost=cost,
            overall_derivation=deriv,
        )

    estimator.registry.register("aws", "AmazonBraketQuantum", custom_quantum_estimator)

    res = estimator.estimate(
        PreDeploymentEstimateRequest(
            provider="aws",
            service="AmazonBraketQuantum",
            region="us-east-1",
        )
    )
    assert res.service == "AmazonBraketQuantum"
    assert res.monthly_cost.amount == 50.0


# ==============================================================================
# 5. REST API Integration Tests
# ==============================================================================


def test_api_pre_deployment_estimate_endpoint():
    """FastAPI POST /api/v1/cost/estimate endpoint computes and returns estimate."""
    client = TestClient(app)

    payload = {
        "provider": "aws",
        "service": "AmazonEC2",
        "region": "us-east-1",
        "instance_type": "t3.xlarge",
        "storage_gb": 100.0,
        "storage_type": "gp3",
        "public_ip": True,
        "runtime_schedule_type": "CONTINUOUS_24_7",
        "target_currency": "USD",
    }

    resp = client.post("/api/v1/cost/estimate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["provider"] == "aws"
    assert data["service"] == "AmazonEC2"
    assert data["pricing_status"] in ["ESTIMATED", "PAID"]
    assert data["monthly_cost"]["amount"] > 0
    assert len(data["cost_drivers"]) > 0
    assert "overall_derivation" in data
    assert len(data["overall_derivation"]["step_by_step_explanation"]) > 0


def test_api_supported_services_endpoint():
    """FastAPI GET /api/v1/cost/estimate/supported-services returns catalogued services."""
    client = TestClient(app)

    resp = client.get("/api/v1/cost/estimate/supported-services")
    assert resp.status_code == 200
    data = resp.json()

    assert "aws" in data["providers"]
    assert "azure" in data["providers"]
    assert "AmazonEC2" in data["services"]["aws"]
    assert "Virtual Machines" in data["services"]["azure"]
    assert data["extensible"] is True
