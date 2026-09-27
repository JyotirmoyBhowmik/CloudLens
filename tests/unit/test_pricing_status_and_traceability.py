"""Unit Tests for Pricing Status Engine, Source Traceability, and Cost Source Segregation (Prompt 21).

Enforces all Prompt 21 acceptance criteria and enterprise constraints:
- AC 1: A pricing statement cannot be produced without a source reference and effective date.
- AC 2: A bare 'Free' cannot be emitted by the status engine or composer.
- AC 3: An estimated cost and an actual cost cannot be summed accidentally (enforced by type and operator overload).
- AC 4: A stale pricing value is flagged with its last known retrieval date and computed staleness.
- AC 5: All seven pricing statuses are reachable and verified:
  FREE, FREE TIER, CONDITIONAL FREE, PAID, ESTIMATED, UNKNOWN, NOT APPLICABLE.
- AC 6: Information-panel content model produces complete structured payload for Prompt 40.
- AC 7: API endpoints /status/evaluate, /statement/compose, and /panel/{sku_or_id} function correctly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.cloudlens_api.main import app
from domain.models.enums import PricingStatus
from domain.models.exceptions import (
    IncompatibleCostTypeError,
    MissingTraceabilityException,
    UndefendedFreeStatusException,
)
from domain.pricing.cost_sources import (
    ActualCost,
    BlendedCostSummary,
    CachedCost,
    EstimatedCost,
    ForecastCost,
    ManualCost,
    UnavailableCost,
)
from domain.pricing.information_panel import (
    InformationPanelBuilder,
    PricingInformationPanel,
)
from domain.pricing.models import (
    CommitmentInfo,
    DiscountInfo,
    FreeAllowance,
    PricingRecord,
    PricingTierModel,
    TierBracket,
    TierStructure,
)
from domain.pricing.service import get_pricing_service, reset_pricing_service
from domain.pricing.statement_composer import (
    PricingStatement,
    PricingStatementComposer,
)
from domain.pricing.status_engine import (
    PricingStatusClassification,
    PricingStatusEngine,
)
from domain.pricing.traceability import (
    DataClassType,
    FreshnessIndicator,
    SourceTraceability,
)


@pytest.fixture(autouse=True)
def fresh_pricing_service():
    """Reset the singleton pricing service before each test."""
    reset_pricing_service()
    yield
    reset_pricing_service()


@pytest.fixture
def sample_traceability() -> SourceTraceability:
    return SourceTraceability(
        pricing_source="aws_price_list_api",
        source_url="https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/index.json",
        retrieval_timestamp=datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC),
        region="us-east-1",
        currency="USD",
        effective_date=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def ec2_paid_record() -> PricingRecord:
    return PricingRecord(
        provider="aws",
        service="AmazonEC2",
        service_sku="t3.medium-on-demand",
        resource_type="compute_instance",
        region="us-east-1",
        pricing_dimension="DIM-03",
        unit="Hrs",
        unit_price=0.0416,
        currency="USD",
        effective_from=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
        source="aws_price_list_bulk",
        source_url="https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/index.json",
        retrieved_at=datetime.now(UTC),
    )


# ==============================================================================
# 1. Acceptance Criterion 1 & Rule 161: Source Traceability Discipline
# ==============================================================================


def test_source_traceability_requires_source_and_url():
    """AC 1: A pricing statement cannot be produced without source reference and effective date."""
    with pytest.raises((MissingTraceabilityException, ValidationError)):
        SourceTraceability(
            pricing_source="",  # Empty source
            source_url="https://aws.amazon.com/pricing/",
            region="us-east-1",
            currency="USD",
            effective_date=datetime(2026, 1, 1, tzinfo=UTC),
        )

    with pytest.raises((MissingTraceabilityException, ValidationError)):
        SourceTraceability(
            pricing_source="aws_pricing",
            source_url="",  # Empty URL
            region="us-east-1",
            currency="USD",
            effective_date=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_pricing_statement_without_traceability_raises_exception(ec2_paid_record):
    """AC 1: Record lacking source URL cannot produce a defensible pricing statement."""
    invalid_record = ec2_paid_record.model_copy(update={"source_url": ""})

    with pytest.raises(
        MissingTraceabilityException, match="lacks required source reference or source URL"
    ):
        PricingStatementComposer.compose_statement_for_record(invalid_record)


# ==============================================================================
# 2. Acceptance Criterion 2 & Rule 159: Bare 'Free' Strictly Prohibited
# ==============================================================================


def test_bare_free_statement_raises_undefended_free_exception(ec2_paid_record, sample_traceability):
    """AC 2: Emitting a bare 'Free' string or empty condition is strictly prohibited."""
    # 1. Composer raises UndefendedFreeStatusException when condition is empty or 'Free'
    with pytest.raises(UndefendedFreeStatusException):
        PricingStatementComposer.compose_free_statement(
            ec2_paid_record, free_condition="", traceability=sample_traceability
        )

    with pytest.raises(UndefendedFreeStatusException):
        PricingStatementComposer.compose_free_statement(
            ec2_paid_record, free_condition="Free", traceability=sample_traceability
        )

    with pytest.raises(UndefendedFreeStatusException):
        PricingStatementComposer.compose_free_statement(
            ec2_paid_record, free_condition="none", traceability=sample_traceability
        )

    # 2. Direct model instantiation validates bare statements
    with pytest.raises((UndefendedFreeStatusException, ValidationError)):
        PricingStatement(
            text="Free.",
            status=PricingStatus.FREE,
            conditions=["Condition: active tier"],
            traceability=sample_traceability,
        )

    with pytest.raises((UndefendedFreeStatusException, ValidationError)):
        PricingStatement(
            text="Service is completely free for all users.",
            status=PricingStatus.FREE,
            conditions=[],  # Empty conditions
            traceability=sample_traceability,
        )


def test_status_engine_rejects_bare_free_classification(ec2_paid_record, sample_traceability):
    """AC 2: PricingStatusClassification rejects bare 'Free' statement or empty conditions."""
    free_rec = ec2_paid_record.model_copy(
        update={"unit_price": 0.0, "attributes": {"is_free": True}}
    )

    # Engine evaluate rejects empty free condition
    with pytest.raises(UndefendedFreeStatusException):
        PricingStatusEngine.evaluate(record=free_rec, free_condition="")

    with pytest.raises((UndefendedFreeStatusException, ValidationError)):
        PricingStatusClassification(
            status=PricingStatus.FREE,
            conditions=[],  # Empty
            statement="Free: Always free under terms",
            rule_id="RULE-TEST",
            traceability=sample_traceability,
        )


# ==============================================================================
# 3. Item 159: Statement Composer Formats & Number Provenance
# ==============================================================================


def test_statement_composer_free_allowance_sentences(sample_traceability):
    """Item 159: Sentence structure follows standard formats and uses numbers strictly from catalogue."""
    # Format A: requests
    lambda_record = PricingRecord(
        provider="aws",
        service="AWSLambda",
        service_sku="lambda-requests",
        resource_type="serverless_function",
        region="us-east-1",
        pricing_dimension="DIM-03",
        unit="Requests",
        unit_price=0.0000002,
        free_allowance=FreeAllowance(
            quantity=1000000.0,
            unit="Requests",
            reset_period="MONTHLY",
            post_allowance_rate=0.0000002,
        ),
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        source="aws_price_list",
        source_url="https://aws.amazon.com/lambda/pricing/",
    )
    stmt = PricingStatementComposer.compose_free_allowance_statement(
        lambda_record, sample_traceability
    )
    assert stmt.status == PricingStatus.FREE_TIER
    assert (
        "Free for 1e+06 Requests (monthly) with additional requests billed at 2e-07 USD per Requests."
        in stmt.text
    )
    assert any("1e+06 Requests" in c for c in stmt.conditions)
    assert any("2e-07 USD" in c for c in stmt.conditions)

    # Format B: capacity / hours
    dynamo_record = PricingRecord(
        provider="aws",
        service="DynamoDB",
        service_sku="dynamodb-storage",
        resource_type="database_table",
        region="us-east-1",
        pricing_dimension="DIM-03",
        unit="GB-Mo",
        unit_price=0.25,
        free_allowance=FreeAllowance(
            quantity=25.0,
            unit="GB-Mo",
            reset_period="MONTHLY",
            post_allowance_rate=0.25,
        ),
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        source="aws_price_list",
        source_url="https://aws.amazon.com/dynamodb/pricing/",
    )
    stmt2 = PricingStatementComposer.compose_free_allowance_statement(
        dynamo_record, sample_traceability
    )
    assert (
        "Free up to 25 GB-Mo (monthly) with charges of 0.25 USD per GB-Mo beyond it." in stmt2.text
    )


def test_statement_composer_conditional_free_sentence(sample_traceability):
    """Item 159: 'No separate service charge but dependent services may incur charges'."""
    cloudformation_record = PricingRecord(
        provider="aws",
        service="CloudFormation",
        service_sku="cf-template-engine",
        resource_type="template_engine",
        region="us-east-1",
        pricing_dimension="DIM-03",
        unit="Usage",
        unit_price=0.0,
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        source="aws_price_list",
        source_url="https://aws.amazon.com/cloudformation/pricing/",
    )
    stmt = PricingStatementComposer.compose_conditional_free_statement(
        record=cloudformation_record,
        prerequisite_condition="standard resource deployment",
        dependent_services=["EC2", "EBS", "RDS"],
        traceability=sample_traceability,
    )
    assert stmt.status == PricingStatus.CONDITIONAL_FREE
    assert (
        "No separate service charge (standard resource deployment), but dependent services (EC2, EBS, RDS) may incur charges."
        in stmt.text
    )


def test_statement_composer_tiered_paid_sentence(sample_traceability):
    """Item 159: Tiered pricing statement displays starting and graduation rates."""
    s3_tiered_record = PricingRecord(
        provider="aws",
        service="AmazonS3",
        service_sku="s3-standard-storage",
        resource_type="object_storage",
        region="us-east-1",
        pricing_dimension="DIM-03",
        unit="GB-Mo",
        unit_price=0.023,
        tier=TierStructure(
            pricing_model=PricingTierModel.GRADUATED,
            brackets=[
                TierBracket(tier_start=0.0, tier_end=51200.0, tier_unit_rate=0.023),
                TierBracket(tier_start=51200.0, tier_end=512000.0, tier_unit_rate=0.022),
                TierBracket(tier_start=512000.0, tier_end=None, tier_unit_rate=0.021),
            ],
        ),
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        source="aws_price_list",
        source_url="https://aws.amazon.com/s3/pricing/",
    )
    stmt = PricingStatementComposer.compose_paid_statement(s3_tiered_record, sample_traceability)
    assert stmt.status == PricingStatus.PAID
    assert (
        "Tiered pricing starting at 0.023 USD per GB-Mo graduating to 0.021 USD per GB-Mo."
        in stmt.text
    )


# ==============================================================================
# 4. Acceptance Criterion 3 & Item 160: Cost Source Classification & Type Safety
# ==============================================================================


def test_actual_and_estimated_cost_cannot_be_summed_directly():
    """AC 3: An estimated cost and an actual cost cannot be summed accidentally — enforced by type."""
    actual = ActualCost(
        amount=150.75,
        currency="USD",
        invoice_id="INV-2026-03-001",
        billing_period="2026-03",
    )
    estimated = EstimatedCost(
        amount=50.25,
        currency="USD",
        pricing_record_id="rec-123",
        pricing_source="aws_pricing_bulk",
        usage_quantity=744.0,
        usage_unit="Hrs",
        estimation_formula="744 hrs * 0.0675 USD/hr",
    )

    # Adding actual to estimated must raise IncompatibleCostTypeError
    with pytest.raises(IncompatibleCostTypeError, match="Cannot sum ActualCost with EstimatedCost"):
        _ = actual + estimated

    # Adding estimated to actual must raise IncompatibleCostTypeError
    with pytest.raises(IncompatibleCostTypeError, match="Cannot sum EstimatedCost with ActualCost"):
        _ = estimated + actual


def test_actual_cost_cannot_be_added_to_primitive_or_incompatible():
    """AC 3: ActualCost cannot be added to a primitive float or integer."""
    actual = ActualCost(amount=100.0, currency="USD")

    with pytest.raises(IncompatibleCostTypeError):
        _ = actual + 50.0

    with pytest.raises(IncompatibleCostTypeError):
        _ = 50.0 + actual


def test_actual_cost_summation_with_matching_currency():
    """Two ActualCosts with matching currencies sum correctly."""
    a1 = ActualCost(amount=100.0, currency="USD", invoice_id="INV-1")
    a2 = ActualCost(amount=50.5, currency="USD", invoice_id="INV-2")

    total = a1 + a2
    assert isinstance(total, ActualCost)
    assert total.amount == 150.5
    assert total.currency == "USD"
    assert total.is_actual is True
    assert total.is_estimate is False


def test_actual_cost_summation_currency_mismatch():
    """ActualCosts with different currencies cannot be summed directly."""
    a_usd = ActualCost(amount=100.0, currency="USD")
    a_eur = ActualCost(amount=100.0, currency="EUR")

    with pytest.raises(IncompatibleCostTypeError, match="Currency mismatch"):
        _ = a_usd + a_eur


def test_blended_cost_summary_keeps_categories_segregated():
    """Item 160: BlendedCostSummary aggregates distinct subtotals without conflating actual and estimated."""
    actual = ActualCost(amount=1000.0, currency="USD")
    estimated = EstimatedCost(
        amount=250.0,
        currency="USD",
        pricing_record_id="rec-1",
        pricing_source="catalogue",
        usage_quantity=10.0,
        usage_unit="Units",
        estimation_formula="10 * 25 USD",
    )
    forecast = ForecastCost(amount=1200.0, currency="USD", forecast_horizon_days=30)
    manual = ManualCost(
        amount=50.0, currency="USD", entered_by="admin", justification="Special adjustment"
    )
    cached = CachedCost(
        amount=75.0,
        currency="USD",
        original_retrieved_at=datetime(2026, 3, 1, tzinfo=UTC),
        cache_age_hours=12.5,
    )
    unavailable = UnavailableCost(currency="USD", reason="Missing meter export")

    items = [actual, estimated, forecast, manual, cached, unavailable]
    summary = BlendedCostSummary.from_items(items, currency="USD")

    assert summary.actual_subtotal == 1000.0
    assert summary.estimated_subtotal == 250.0
    assert summary.forecast_subtotal == 1200.0
    assert summary.manual_subtotal == 50.0
    assert summary.cached_subtotal == 75.0
    assert summary.has_unavailable_items is True
    assert summary.unavailable_count == 1
    # Check that there is NO single total field combining actual + estimated
    assert not hasattr(summary, "total_cost")


# ==============================================================================
# 5. Acceptance Criterion 4 & Item 162: Data Freshness Discipline
# ==============================================================================


def test_freshness_indicator_dynamic_staleness_computation():
    """AC 4: Stale pricing value is flagged with its last known retrieval date and computed staleness."""
    now = datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

    # 1. Fresh pricing record (retrieved 2 days ago, threshold is 168 hours = 7 days)
    fresh_time = now - timedelta(days=2)
    fresh_ind = FreshnessIndicator.compute(
        retrieved_at=fresh_time,
        data_class=DataClassType.PRICING,
        as_of=now,
    )
    assert fresh_ind.is_stale is False
    assert fresh_ind.age_hours == 48.0
    assert fresh_ind.last_known_retrieval_date == fresh_time

    # 2. Stale pricing record (retrieved 10 days ago, threshold is 168 hours)
    stale_time = now - timedelta(days=10)
    stale_ind = FreshnessIndicator.compute(
        retrieved_at=stale_time,
        data_class=DataClassType.PRICING,
        as_of=now,
    )
    assert stale_ind.is_stale is True
    assert stale_ind.age_hours == 240.0
    assert stale_ind.last_known_retrieval_date == stale_time

    # 3. Inventory staleness threshold (threshold is 6.0 hours)
    inv_retrieved = now - timedelta(hours=8)
    inv_ind = FreshnessIndicator.compute(
        retrieved_at=inv_retrieved,
        data_class=DataClassType.INVENTORY,
        as_of=now,
    )
    assert inv_ind.is_stale is True
    assert inv_ind.staleness_threshold_hours == 6.0


# ==============================================================================
# 6. Acceptance Criterion 5 & Item 158: All Seven Statuses Reachable & Verified
# ==============================================================================


def test_reachability_all_seven_pricing_statuses(ec2_paid_record):
    """AC 5: All seven statuses are reachable and verified by tests."""
    # 1. NOT_APPLICABLE: Structural or non-billable construct
    res_na = PricingStatusEngine.evaluate(
        record=None,
        resource_type="resource_group",
    )
    assert res_na.status == PricingStatus.NOT_APPLICABLE
    assert "RULE-PSE-07-NOT-APPLICABLE" in res_na.rule_id
    assert any("organizational or metadata construct" in c for c in res_na.conditions)

    # 2. UNKNOWN: SKU missing or unmapped in catalogue (STRICT: NEVER defaulted to free or zero)
    res_unk = PricingStatusEngine.evaluate(
        record=None,
        resource_type="custom_database_cluster",
    )
    assert res_unk.status == PricingStatus.UNKNOWN
    assert "RULE-PSE-06-UNKNOWN" in res_unk.rule_id
    assert any("Never defaulted to Free or Zero" in c for c in res_unk.conditions)

    # 3. ESTIMATED: Explicit algorithmic surrogate estimation
    res_est = PricingStatusEngine.evaluate(
        record=ec2_paid_record,
        is_estimated=True,
    )
    assert res_est.status == PricingStatus.ESTIMATED
    assert "RULE-PSE-05-ESTIMATED" in res_est.rule_id
    assert res_est.statement.startswith("Estimated:")

    # 4. FREE TIER: Included free allowance with overage rates
    lambda_record = PricingRecord(
        provider="aws",
        service="AWSLambda",
        service_sku="lambda-requests",
        resource_type="serverless_function",
        region="us-east-1",
        pricing_dimension="DIM-03",
        unit="Requests",
        unit_price=0.0000002,
        free_allowance=FreeAllowance(
            quantity=1000000.0,
            unit="Requests",
            reset_period="MONTHLY",
            post_allowance_rate=0.0000002,
        ),
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        source="aws_price_list",
        source_url="https://aws.amazon.com/lambda/pricing/",
    )
    res_ft = PricingStatusEngine.evaluate(record=lambda_record)
    assert res_ft.status == PricingStatus.FREE_TIER
    assert "RULE-PSE-02-FREE-TIER" in res_ft.rule_id

    # 5. CONDITIONAL FREE: No separate service charge, dependent services incur charges
    cf_record = PricingRecord(
        provider="aws",
        service="CloudFormation",
        service_sku="cf-engine",
        resource_type="template_engine",
        region="us-east-1",
        pricing_dimension="DIM-03",
        unit="Usage",
        unit_price=0.0,
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        source="aws_price_list",
        source_url="https://aws.amazon.com/cloudformation/pricing/",
    )
    res_cf = PricingStatusEngine.evaluate(
        record=cf_record,
        dependent_services=["EC2", "EBS"],
    )
    assert res_cf.status == PricingStatus.CONDITIONAL_FREE
    assert "RULE-PSE-03-CONDITIONAL-FREE" in res_cf.rule_id

    # 6. FREE: Explicitly free under stated defensible conditions
    iam_record = PricingRecord(
        provider="aws",
        service="IAM",
        service_sku="iam-core",
        resource_type="identity_access_management",
        region="us-east-1",
        pricing_dimension="DIM-03",
        unit="Usage",
        unit_price=0.0,
        effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        source="aws_price_list",
        source_url="https://aws.amazon.com/iam/pricing/",
    )
    res_free = PricingStatusEngine.evaluate(
        record=iam_record,
        free_condition="Included with AWS account at no charge under standard subscription terms",
    )
    assert res_free.status == PricingStatus.FREE
    assert "RULE-PSE-01-FREE" in res_free.rule_id
    assert (
        "Free: Included with AWS account at no charge under standard subscription terms."
        in res_free.statement
    )

    # 7. PAID: Standard billable unit rate
    res_paid = PricingStatusEngine.evaluate(record=ec2_paid_record)
    assert res_paid.status == PricingStatus.PAID
    assert "RULE-PSE-04-PAID" in res_paid.rule_id


def test_status_engine_rejects_free_without_conditions_on_free_service(ec2_paid_record):
    """AC 2: Status engine rejects classifying unit_price=0.0 as FREE if conditions are empty."""
    iam_record = ec2_paid_record.model_copy(
        update={
            "unit_price": 0.0,
            "attributes": {"is_free": True, "free_condition": ""},
        }
    )
    with pytest.raises(UndefendedFreeStatusException):
        PricingStatusEngine.evaluate(record=iam_record, free_condition="")


# ==============================================================================
# 7. Item 163 & Prompt 40: Information-Panel Content Model
# ==============================================================================


def test_information_panel_builder_comprehensive_payload(ec2_paid_record):
    """Item 163: Information panel builder creates complete 20+ field structured payload."""
    rec_with_discount = ec2_paid_record.model_copy(
        update={
            "discount_info": DiscountInfo(
                discount_percentage=15.0,
                contract_reference="EA-ENTERPRISE-2026",
            ),
            "commitment_info": CommitmentInfo(
                commitment_type="SAVINGS_PLAN",
                term_months=36,
            ),
        }
    )

    actual = ActualCost(amount=30.36, currency="USD")
    panel = InformationPanelBuilder.build_from_record(
        record=rec_with_discount,
        resource_id="i-0123456789abcdef0",
        cost_breakdown=[actual],
    )

    assert isinstance(panel, PricingInformationPanel)
    assert panel.resource_id == "i-0123456789abcdef0"
    assert panel.service == "AmazonEC2"
    assert panel.service_sku == "t3.medium-on-demand"
    assert panel.pricing_model == "On-Demand"
    assert panel.region == "us-east-1"
    assert panel.unit_rate == 0.0416
    assert panel.monthly_estimate == round(0.0416 * 730.0, 2)
    assert panel.pricing_status == PricingStatus.PAID
    assert len(panel.pricing_status_conditions) > 0
    assert "Billed at 0.0416 USD per Hrs." in panel.pricing_statement
    assert panel.currency == "USD"
    assert panel.billing_unit == "Hrs"
    assert panel.discount_applicability == "15% discount applied via EA-ENTERPRISE-2026."
    assert panel.commitment_applicability == "Eligible for SAVINGS_PLAN (36-month term)."
    assert panel.source_traceability.pricing_source == "aws_price_list_bulk"
    assert panel.freshness.is_stale is False
    assert len(panel.caveats) >= 3
    assert len(panel.related_metrics) >= 4
    assert len(panel.cost_breakdown) == 1
    assert isinstance(panel.cost_breakdown[0], ActualCost)


# ==============================================================================
# 8. API Route Endpoints: /status/evaluate, /statement/compose, /panel/{sku_or_id}
# ==============================================================================


def test_api_status_evaluate_endpoint(ec2_paid_record):
    """API endpoint /api/v1/pricing/status/evaluate computes status with stored conditions."""
    service = get_pricing_service()
    service.ingest_price_record(ec2_paid_record)

    client = TestClient(app)

    # 1. Existing paid record
    response = client.post(
        "/api/v1/pricing/status/evaluate",
        json={
            "provider": "aws",
            "service_sku": "t3.medium-on-demand",
            "region": "us-east-1",
            "pricing_dimension": "DIM-03",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PAID"
    assert "0.0416" in data["statement"]
    assert len(data["conditions"]) > 0

    # 2. Unknown SKU (Never defaulted to Free or Zero)
    response_unk = client.post(
        "/api/v1/pricing/status/evaluate",
        json={
            "provider": "aws",
            "service_sku": "nonexistent-sku-xyz",
            "region": "us-east-1",
            "pricing_dimension": "DIM-03",
        },
    )
    assert response_unk.status_code == 200
    data_unk = response_unk.json()
    assert data_unk["status"] == "UNKNOWN"
    assert "Not defaulted to free" in data_unk["statement"]


def test_api_statement_compose_endpoint(ec2_paid_record):
    """API endpoint /api/v1/pricing/statement/compose composes condition-grounded statements."""
    service = get_pricing_service()
    service.ingest_price_record(ec2_paid_record)

    client = TestClient(app)

    response = client.post(
        "/api/v1/pricing/statement/compose",
        json={
            "provider": "aws",
            "service_sku": "t3.medium-on-demand",
            "region": "us-east-1",
            "pricing_dimension": "DIM-03",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PAID"
    assert "Billed at 0.0416 USD per Hrs." in data["text"]
    assert data["traceability"]["pricing_source"] == "aws_price_list_bulk"


def test_api_panel_endpoint(ec2_paid_record):
    """API endpoint /api/v1/pricing/panel/{sku_or_id} returns structured information panel."""
    service = get_pricing_service()
    stored_rec, _ = service.ingest_price_record(ec2_paid_record)

    client = TestClient(app)

    response = client.get(
        f"/api/v1/pricing/panel/{stored_rec.service_sku}?provider=aws&region=us-east-1&dimension=DIM-03"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "AmazonEC2"
    assert data["unit_rate"] == 0.0416
    assert data["pricing_status"] == "PAID"
    assert "caveats" in data
    assert "related_metrics" in data
    assert "freshness" in data
    assert data["freshness"]["is_stale"] is False
