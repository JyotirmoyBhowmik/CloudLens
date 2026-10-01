"""Unit and Contract Tests for Cost Reconciliation, Variance Classification, and Executive Trust (Prompt 24).

Enforces:
- Prompt 24 Item 1 & BBP Section 12 (BP-17): Authoritative period comparison with finalisation lag guard.
- Prompt 24 Item 2: Deterministic variance classification taxonomy.
- Prompt 24 Item 3: Explicit framing rule: presents both figures and classification without editorialising.
- Prompt 24 Item 4: Configurable per-provider tolerance with PASS/FAILED and investigation item on failure.
- Prompt 24 Item 5: Executive dashboard trust indicator (never suppressed on failure).
- Prompt 24 Item 6: Separate comparison of estimated cost against actual billed cost.
- Prompt 24 Item 7: Retain reconciliation history so the trend in variance is visible over time.
- Prompt 24 Strict Negative Constraints:
  * Do not adjust ingested cost data to force a match.
  * Do not suppress a failed reconciliation from the dashboard.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.cost.models import FocusCostFact
from domain.cost.reconciliation import (
    CostReconciliationEngine,
    EstimationBias,
    ExecutiveTrustStatus,
    InvestigationPriority,
    InvestigationStatus,
    ReconciliationRepository,
    ReconciliationStatus,
    RunReconciliationRequest,
    VarianceClassification,
)
from domain.cost.repository import CostFactRepository
from domain.models.base import ProvenanceRecord
from domain.models.enums import ChargeCategory, CostSourceType, ServiceCategory
from domain.models.exceptions import (
    ReconciliationAdjustmentForbiddenException,
    ReconciliationPeriodNotClosedException,
)
from domain.models.measures import FinancialMeasure, QuantityMeasure
from domain.tenant.context import TenantContext


@pytest.fixture
def tenant_ctx() -> TenantContext:
    return TenantContext(tenant_id="tenant-recon-prod")


@pytest.fixture
def other_tenant_ctx() -> TenantContext:
    return TenantContext(tenant_id="tenant-recon-other")


@pytest.fixture
def cost_repo() -> CostFactRepository:
    return CostFactRepository()


@pytest.fixture
def recon_repo() -> ReconciliationRepository:
    return ReconciliationRepository()


@pytest.fixture
def recon_engine(
    recon_repo: ReconciliationRepository, cost_repo: CostFactRepository
) -> CostReconciliationEngine:
    return CostReconciliationEngine(reconciliation_repo=recon_repo, cost_repo=cost_repo)


def _seed_cost_fact(
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
    billing_period: str,
    scope_id: str,
    provider: str,
    service_id: str,
    billed_amount: Decimal,
    effective_amount: Decimal | None = None,
) -> FocusCostFact:
    """Helper to seed a valid FOCUS cost fact."""
    year, month = map(int, billing_period.split("-"))
    start_dt = datetime(year, month, 1, 0, 0, 0, tzinfo=UTC)
    end_dt = datetime(year, month, 28, 23, 59, 59, tzinfo=UTC)
    start_d = date(year, month, 1)
    end_d = date(year, month, 28)

    fact = FocusCostFact(
        id=f"fact-{uuid.uuid4().hex[:8]}",
        tenant_id=tenant_ctx.tenant_id,
        scope_id=scope_id,
        provider=provider,
        service_id=service_id,
        service_name=service_id,
        service_category=ServiceCategory.COMPUTE,
        charge_category=ChargeCategory.USAGE,
        charge_period_start=start_dt,
        charge_period_end=end_dt,
        billing_period_start=start_d,
        billing_period_end=end_d,
        billing_currency="USD",
        charge_subcategory="OnDemand",
        cost_source=CostSourceType.INVOICE,
        pricing_quantity=QuantityMeasure.of(Decimal("100.0")),
        billed_cost=FinancialMeasure.of(billed_amount),
        effective_cost=FinancialMeasure.of(effective_amount or billed_amount),
        source_provenance=ProvenanceRecord(source_system="test-seed"),
    )
    cost_repo.save(fact, tenant_context=tenant_ctx)
    return fact


# ==============================================================================
# Prompt 24 Item 1: Period Finalisation & Reconciliation Execution
# ==============================================================================


def test_reconciliation_finalisation_lag_guard(
    recon_engine: CostReconciliationEngine,
    tenant_ctx: TenantContext,
) -> None:
    """Period close plus finalisation lag guard rejects reconciliation before provider has finalized."""
    # A future or current month like 2026-12 should fail finalisation lag
    req = RunReconciliationRequest(
        billing_period="2026-12",
        provider="aws",
        scope_id="acc-prod-101",
        provider_authoritative_total=Decimal("1500.00"),
        bypass_lag_check=False,
    )
    with pytest.raises(ReconciliationPeriodNotClosedException) as exc_info:
        recon_engine.run_reconciliation(req, tenant_context=tenant_ctx)

    assert exc_info.value.billing_period == "2026-12"
    assert exc_info.value.provider == "aws"
    assert "not yet finalized" in str(exc_info.value.message)


def test_reconciliation_bypass_lag_check_executes(
    recon_engine: CostReconciliationEngine,
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
) -> None:
    """bypass_lag_check allows backfills and test executions for unclosed periods."""
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-03",
        scope_id="acc-prod-101",
        provider="aws",
        service_id="AmazonEC2",
        billed_amount=Decimal("1000.00"),
    )
    req = RunReconciliationRequest(
        billing_period="2026-03",
        provider="aws",
        scope_id="acc-prod-101",
        provider_authoritative_total=Decimal("1000.00"),
        bypass_lag_check=True,
    )
    report = recon_engine.run_reconciliation(req, tenant_context=tenant_ctx)

    assert report.status == ReconciliationStatus.PASS
    assert report.platform_total == Decimal("1000.00")
    assert report.provider_total == Decimal("1000.00")
    assert report.absolute_variance == Decimal("0.00")
    assert report.classification == VarianceClassification.WITHIN_TOLERANCE


# ==============================================================================
# Prompt 24 Item 4: Tolerance Evaluation (PASS vs FAILED)
# ==============================================================================


def test_reconciliation_pass_within_absolute_tolerance(
    recon_engine: CostReconciliationEngine,
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
) -> None:
    """Discrepancy within absolute tolerance ($5.00) passes reconciliation."""
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-01",
        scope_id="acc-prod-101",
        provider="aws",
        service_id="AmazonEC2",
        billed_amount=Decimal("1002.50"),
    )
    req = RunReconciliationRequest(
        billing_period="2026-01",
        provider="aws",
        scope_id="acc-prod-101",
        provider_authoritative_total=Decimal("1000.00"),
        bypass_lag_check=True,
    )
    report = recon_engine.run_reconciliation(req, tenant_context=tenant_ctx)

    assert report.status == ReconciliationStatus.PASS
    assert report.absolute_variance == Decimal("2.50")
    assert report.classification == VarianceClassification.WITHIN_TOLERANCE
    assert report.investigation_item_id is None


def test_reconciliation_pass_within_percentage_tolerance(
    recon_engine: CostReconciliationEngine,
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
) -> None:
    """Discrepancy within percentage tolerance (0.5%) passes even if absolute variance > $5.00 on large spend."""
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-01",
        scope_id="acc-enterprise",
        provider="azure",
        service_id="Virtual Machines",
        billed_amount=Decimal("100200.00"),
    )
    req = RunReconciliationRequest(
        billing_period="2026-01",
        provider="azure",
        scope_id="acc-enterprise",
        provider_authoritative_total=Decimal("100000.00"),  # $200 variance is 0.20%, within 0.50%
        bypass_lag_check=True,
    )
    report = recon_engine.run_reconciliation(req, tenant_context=tenant_ctx)

    assert report.status == ReconciliationStatus.PASS
    assert report.percentage_variance == Decimal("0.20")
    assert report.classification == VarianceClassification.WITHIN_TOLERANCE


def test_reconciliation_failed_beyond_tolerance_creates_investigation(
    recon_engine: CostReconciliationEngine,
    recon_repo: ReconciliationRepository,
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
) -> None:
    """Variance exceeding both absolute and percentage tolerances marks report FAILED and creates investigation item."""
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-01",
        scope_id="acc-fail-1",
        provider="aws",
        service_id="AmazonRDS",
        billed_amount=Decimal("5000.00"),
    )
    req = RunReconciliationRequest(
        billing_period="2026-01",
        provider="aws",
        scope_id="acc-fail-1",
        provider_authoritative_total=Decimal("4500.00"),  # $500 variance is 11.11%
        bypass_lag_check=True,
    )
    report = recon_engine.run_reconciliation(req, tenant_context=tenant_ctx)

    assert report.status == ReconciliationStatus.FAILED
    assert report.absolute_variance == Decimal("500.00")
    assert report.percentage_variance == Decimal("11.11")
    assert report.investigation_item_id is not None

    # Check investigation item was created and persisted in repository
    inv_item = recon_repo.get_investigation_item(
        report.investigation_item_id, tenant_context=tenant_ctx
    )
    assert inv_item is not None
    assert inv_item.report_id == report.id
    assert inv_item.provider == "aws"
    assert inv_item.variance_amount == Decimal("500.00")
    assert inv_item.priority == InvestigationPriority.CRITICAL  # >= 5%
    assert inv_item.status == InvestigationStatus.OPEN


# ==============================================================================
# Prompt 24 Item 2: Deterministic Variance Classification Taxonomy
# ==============================================================================


def test_variance_classification_credit(
    recon_engine: CostReconciliationEngine,
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
) -> None:
    """Unallocated invoice-level credits classify variance as CREDIT."""
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-01",
        scope_id="acc-credit-1",
        provider="gcp",
        service_id="Compute Engine",
        billed_amount=Decimal("1000.00"),
    )
    req = RunReconciliationRequest(
        billing_period="2026-01",
        provider="gcp",
        scope_id="acc-credit-1",
        provider_authoritative_total=Decimal("850.00"),  # delta is $150
        unallocated_credits=Decimal("150.00"),
        bypass_lag_check=True,
    )
    report = recon_engine.run_reconciliation(req, tenant_context=tenant_ctx)

    assert report.status == ReconciliationStatus.FAILED
    assert report.classification == VarianceClassification.CREDIT
    assert "invoice-level credit" in (report.classification_details or "")


def test_variance_classification_tax(
    recon_engine: CostReconciliationEngine,
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
) -> None:
    """Invoice-assessed sales tax/VAT classifies variance as TAX."""
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-01",
        scope_id="acc-tax-1",
        provider="aws",
        service_id="AmazonEC2",
        billed_amount=Decimal("1000.00"),
    )
    req = RunReconciliationRequest(
        billing_period="2026-01",
        provider="aws",
        scope_id="acc-tax-1",
        provider_authoritative_total=Decimal("1080.00"),  # $80 tax
        assessed_taxes=Decimal("80.00"),
        bypass_lag_check=True,
    )
    report = recon_engine.run_reconciliation(req, tenant_context=tenant_ctx)

    assert report.status == ReconciliationStatus.FAILED
    assert report.classification == VarianceClassification.TAX
    assert "jurisdictional tax" in (report.classification_details or "")


def test_variance_classification_missing_scope(
    recon_engine: CostReconciliationEngine,
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
) -> None:
    """Unlinked member account or subscription on invoice classifies variance as MISSING_SCOPE."""
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-01",
        scope_id="sub-core",
        provider="azure",
        service_id="Virtual Machines",
        billed_amount=Decimal("1000.00"),
    )
    req = RunReconciliationRequest(
        billing_period="2026-01",
        provider="azure",
        scope_id="sub-core",
        provider_authoritative_total=Decimal("1400.00"),
        unlinked_scopes=["sub-sandbox-999"],
        bypass_lag_check=True,
    )
    report = recon_engine.run_reconciliation(req, tenant_context=tenant_ctx)

    assert report.status == ReconciliationStatus.FAILED
    assert report.classification == VarianceClassification.MISSING_SCOPE
    assert "sub-sandbox-999" in (report.classification_details or "")


def test_variance_classification_unrecognised_charge(
    recon_engine: CostReconciliationEngine,
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
) -> None:
    """Uncatalogued charge items classify variance as UNRECOGNISED_CHARGE."""
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-01",
        scope_id="oci-tenancy-1",
        provider="oci",
        service_id="Compute",
        billed_amount=Decimal("500.00"),
    )
    req = RunReconciliationRequest(
        billing_period="2026-01",
        provider="oci",
        scope_id="oci-tenancy-1",
        provider_authoritative_total=Decimal("650.00"),
        unrecognised_charges=Decimal("150.00"),
        bypass_lag_check=True,
    )
    report = recon_engine.run_reconciliation(req, tenant_context=tenant_ctx)

    assert report.status == ReconciliationStatus.FAILED
    assert report.classification == VarianceClassification.UNRECOGNISED_CHARGE


def test_variance_classification_pricing_mismatch(
    recon_engine: CostReconciliationEngine,
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
) -> None:
    """Rate card contract discrepancy classifies variance as PRICING_MISMATCH."""
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-01",
        scope_id="acc-rate-test",
        provider="aws",
        service_id="AmazonS3",
        billed_amount=Decimal("500.00"),
    )
    req = RunReconciliationRequest(
        billing_period="2026-01",
        provider="aws",
        scope_id="acc-rate-test",
        provider_authoritative_total=Decimal("580.00"),
        rate_mismatch_amount=Decimal("80.00"),
        bypass_lag_check=True,
    )
    report = recon_engine.run_reconciliation(req, tenant_context=tenant_ctx)

    assert report.status == ReconciliationStatus.FAILED
    assert report.classification == VarianceClassification.PRICING_MISMATCH


def test_variance_classification_data_freshness_gap(
    recon_engine: CostReconciliationEngine,
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
) -> None:
    """In-flight sync or pending data freshness gap classifies variance as DATA_FRESHNESS_GAP."""
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-01",
        scope_id="acc-sync-gap",
        provider="aws",
        service_id="AmazonEC2",
        billed_amount=Decimal("500.00"),
    )
    req = RunReconciliationRequest(
        billing_period="2026-01",
        provider="aws",
        scope_id="acc-sync-gap",
        provider_authoritative_total=Decimal("900.00"),
        is_sync_in_flight=True,
        bypass_lag_check=True,
    )
    report = recon_engine.run_reconciliation(req, tenant_context=tenant_ctx)

    assert report.status == ReconciliationStatus.FAILED
    assert report.classification == VarianceClassification.DATA_FRESHNESS_GAP


def test_variance_classification_amortisation_basis_difference(
    recon_engine: CostReconciliationEngine,
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
) -> None:
    """Discrepancy between cash-flow billed vs amortised accrual classifies as AMORTISATION_BASIS_DIFFERENCE."""
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-01",
        scope_id="acc-ri-1",
        provider="aws",
        service_id="AmazonEC2",
        billed_amount=Decimal("1200.00"),  # Full upfront fee on cash basis
        effective_amount=Decimal("100.00"),  # Amortised monthly accrual
    )
    req = RunReconciliationRequest(
        billing_period="2026-01",
        provider="aws",
        scope_id="acc-ri-1",
        provider_authoritative_total=Decimal("100.00"),  # Provider report was on amortised basis
        bypass_lag_check=True,
    )
    report = recon_engine.run_reconciliation(req, tenant_context=tenant_ctx)

    assert report.status == ReconciliationStatus.FAILED
    assert report.classification == VarianceClassification.AMORTISATION_BASIS_DIFFERENCE


# ==============================================================================
# Prompt 24 Item 3: Explicit Framing Rule
# ==============================================================================


def test_explicit_framing_rule_non_editorialised(
    recon_engine: CostReconciliationEngine,
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
) -> None:
    """Explicit framing rule: presents both figures and classification without editorialising."""
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-01",
        scope_id="acc-frame",
        provider="aws",
        service_id="AmazonEC2",
        billed_amount=Decimal("1050.00"),
    )
    req = RunReconciliationRequest(
        billing_period="2026-01",
        provider="aws",
        scope_id="acc-frame",
        provider_authoritative_total=Decimal("1000.00"),
        bypass_lag_check=True,
    )
    report = recon_engine.run_reconciliation(req, tenant_context=tenant_ctx)

    # Acceptance: "The report does not assert which figure is correct; it presents both and classifies the difference."
    stmt = report.framing_statement
    assert "Platform normalised FOCUS total is 1050.00 USD" in stmt
    assert "Provider authoritative billed total is 1000.00 USD" in stmt
    assert "Reconciliation variance is +50.00 USD" in stmt
    assert (
        "Both figures are recorded objectively as reported without presumption of inaccuracy."
        in stmt
    )


# ==============================================================================
# Prompt 24 Item 5: Executive Dashboard Trust Indicator (Single Most Important Number)
# ==============================================================================


def test_executive_trust_indicator_calculation(
    recon_engine: CostReconciliationEngine,
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
) -> None:
    """Surfaces executive adoption trust metric with transparent match rate."""
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-01",
        scope_id="acc-prod",
        provider="aws",
        service_id="AmazonEC2",
        billed_amount=Decimal("10000.00"),
    )
    # 1. First period: perfect match
    recon_engine.run_reconciliation(
        RunReconciliationRequest(
            billing_period="2026-01",
            provider="aws",
            scope_id="acc-prod",
            provider_authoritative_total=Decimal("10000.00"),
            bypass_lag_check=True,
        ),
        tenant_context=tenant_ctx,
    )

    trust = recon_engine.compute_executive_trust_indicator(tenant_context=tenant_ctx)
    assert trust.trust_score_pct == Decimal("100.00")
    assert trust.status == ExecutiveTrustStatus.EXCELLENT
    assert trust.reconciliation_pass_count == 1
    assert trust.reconciliation_fail_count == 0
    assert trust.is_suppressed is False


def test_executive_trust_indicator_never_suppresses_failures(
    recon_engine: CostReconciliationEngine,
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
) -> None:
    """STRICT: Negative constraint: 'Do not suppress a failed reconciliation from the dashboard.'"""
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-01",
        scope_id="acc-prod",
        provider="aws",
        service_id="AmazonEC2",
        billed_amount=Decimal("10000.00"),
    )
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-02",
        scope_id="acc-prod",
        provider="aws",
        service_id="AmazonEC2",
        billed_amount=Decimal("8000.00"),
    )

    # Run period 1 (PASS)
    recon_engine.run_reconciliation(
        RunReconciliationRequest(
            billing_period="2026-01",
            provider="aws",
            scope_id="acc-prod",
            provider_authoritative_total=Decimal("10000.00"),
            bypass_lag_check=True,
        ),
        tenant_context=tenant_ctx,
    )

    # Run period 2 (FAIL: $8000 platform vs $10000 provider => $2000 variance)
    recon_engine.run_reconciliation(
        RunReconciliationRequest(
            billing_period="2026-02",
            provider="aws",
            scope_id="acc-prod",
            provider_authoritative_total=Decimal("10000.00"),
            bypass_lag_check=True,
        ),
        tenant_context=tenant_ctx,
    )

    trust = recon_engine.compute_executive_trust_indicator(tenant_context=tenant_ctx)

    # Strict check: Never suppressed!
    assert trust.is_suppressed is False
    assert trust.reconciliation_pass_count == 1
    assert trust.reconciliation_fail_count == 1
    assert trust.active_investigations_count == 1
    # Total spend = 20000.00, total variance = 2000.00 => 90% match
    assert trust.trust_score_pct == Decimal("90.00")
    assert trust.status == ExecutiveTrustStatus.NEEDS_ATTENTION


# ==============================================================================
# Prompt 24 Item 6: Estimate vs Actual Accuracy Comparison
# ==============================================================================


def test_estimate_vs_actual_accuracy_evaluation(
    recon_engine: CostReconciliationEngine,
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
) -> None:
    """Separate comparison of estimated cost against actual billed cost."""
    # Seed actual costs for two services
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-01",
        scope_id="acc-eval",
        provider="aws",
        service_id="AmazonEC2",
        billed_amount=Decimal("1000.00"),
    )
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2026-01",
        scope_id="acc-eval",
        provider="aws",
        service_id="AmazonRDS",
        billed_amount=Decimal("500.00"),
    )

    estimates = [
        {
            "service_id": "AmazonEC2",
            "estimated_cost": "1020.00",  # 2% error => ACCURATE
            "assumptions_summary": "m5.large 730 hrs",
        },
        {
            "service_id": "AmazonRDS",
            "estimated_cost": "700.00",  # 40% error => OVER_ESTIMATED
            "assumptions_summary": "db.m5.large Multi-AZ",
        },
    ]

    report = recon_engine.evaluate_estimate_vs_actual(
        billing_period="2026-01",
        estimates=estimates,
        tenant_context=tenant_ctx,
    )

    assert report.billing_period == "2026-01"
    assert report.total_actual == Decimal("1500.00")
    assert report.total_estimated == Decimal("1720.00")
    assert report.items_count == 2

    # Check item level
    ec2_item = next(i for i in report.items if i.service_id == "AmazonEC2")
    assert ec2_item.bias == EstimationBias.ACCURATE
    assert ec2_item.percentage_error == Decimal("2.00")

    rds_item = next(i for i in report.items if i.service_id == "AmazonRDS")
    assert rds_item.bias == EstimationBias.OVER_ESTIMATED
    assert rds_item.percentage_error == Decimal("40.00")

    # MAPE is (2 + 40) / 2 = 21.00%
    assert report.mape_pct == Decimal("21.00")
    assert report.overall_bias == EstimationBias.OVER_ESTIMATED


# ==============================================================================
# Prompt 24 Item 7: Historical Trends
# ==============================================================================


def test_reconciliation_history_trend_tracking(
    recon_engine: CostReconciliationEngine,
    cost_repo: CostFactRepository,
    tenant_ctx: TenantContext,
) -> None:
    """Multi-period reconciliation history tracks variance trend direction."""
    # Period 1: High variance
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2025-11",
        scope_id="scope-trend",
        provider="aws",
        service_id="AmazonEC2",
        billed_amount=Decimal("1200.00"),
    )
    recon_engine.run_reconciliation(
        RunReconciliationRequest(
            billing_period="2025-11",
            provider="aws",
            scope_id="scope-trend",
            provider_authoritative_total=Decimal("1000.00"),  # $200 variance
            bypass_lag_check=True,
        ),
        tenant_context=tenant_ctx,
    )

    # Period 2: Low variance (improving)
    _seed_cost_fact(
        cost_repo,
        tenant_ctx,
        billing_period="2025-12",
        scope_id="scope-trend",
        provider="aws",
        service_id="AmazonEC2",
        billed_amount=Decimal("1005.00"),
    )
    recon_engine.run_reconciliation(
        RunReconciliationRequest(
            billing_period="2025-12",
            provider="aws",
            scope_id="scope-trend",
            provider_authoritative_total=Decimal("1000.00"),  # $5 variance
            bypass_lag_check=True,
        ),
        tenant_context=tenant_ctx,
    )

    history = recon_engine.get_reconciliation_history_trend(
        tenant_context=tenant_ctx,
        provider="aws",
        scope_id="scope-trend",
    )

    assert history.total_periods_evaluated == 2
    assert len(history.reports) == 2
    assert history.trend_direction == "IMPROVING"


# ==============================================================================
# Prompt 24 Negative Constraints: Anti-Fudging Guard
# ==============================================================================


def test_anti_fudging_guard_prohibits_cost_adjustments(
    recon_engine: CostReconciliationEngine,
    tenant_ctx: TenantContext,
) -> None:
    """STRICT: Negative constraint: 'Do not adjust ingested cost data to force a match.'"""
    with pytest.raises(ReconciliationAdjustmentForbiddenException) as exc_info:
        recon_engine.adjust_cost_data_for_match("fact-target-123", tenant_context=tenant_ctx)

    assert exc_info.value.cost_fact_id == "fact-target-123"
    assert "strictly prohibited" in str(exc_info.value.message)


# ==============================================================================
# API Contract Tests (FastAPI TestClient)
# ==============================================================================


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_api_reconciliation_workflow(client: TestClient) -> None:
    """End-to-end API verification for Prompt 24 reconciliation endpoints."""
    headers = {"X-Tenant-ID": "tenant-recon-api", "X-User-Role": "FINOPS_ADMIN"}

    # 1. Run reconciliation via API
    run_payload = {
        "billing_period": "2026-02",
        "provider": "aws",
        "scope_id": "acc-api-test",
        "provider_authoritative_total": "5000.00",
        "bypass_lag_check": True,
        "currency": "USD",
    }
    run_resp = client.post("/api/v1/cost/reconciliation/run", json=run_payload, headers=headers)
    assert run_resp.status_code == 200, run_resp.text
    report_data = run_resp.json()
    report_id = report_data["id"]
    assert report_data["status"] == "FAILED"  # No platform facts seeded => $5000 variance

    # 2. Get report by ID
    get_resp = client.get(f"/api/v1/cost/reconciliation/reports/{report_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == report_id

    # 3. List reports
    list_resp = client.get("/api/v1/cost/reconciliation/reports?provider=aws", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    # 4. Get executive trust indicator
    trust_resp = client.get("/api/v1/cost/reconciliation/executive-trust", headers=headers)
    assert trust_resp.status_code == 200
    trust_data = trust_resp.json()
    assert trust_data["is_suppressed"] is False
    assert trust_data["reconciliation_fail_count"] >= 1

    # 5. List and update investigation items
    inv_resp = client.get("/api/v1/cost/reconciliation/investigations", headers=headers)
    assert inv_resp.status_code == 200
    inv_items = inv_resp.json()
    assert len(inv_items) >= 1
    item_id = inv_items[0]["id"]

    patch_resp = client.patch(
        f"/api/v1/cost/reconciliation/investigations/{item_id}",
        json={"status": "INVESTIGATING", "notes": "Auditor reviewing missing CUR files."},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "INVESTIGATING"

    # 6. Evaluate estimate vs actual
    eval_resp = client.post(
        "/api/v1/cost/reconciliation/estimate-vs-actual/evaluate",
        json={
            "billing_period": "2026-02",
            "estimates": [
                {
                    "service_id": "AmazonEC2",
                    "estimated_cost": "250.00",
                    "assumptions_summary": "t3.medium",
                }
            ],
        },
        headers=headers,
    )
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["total_estimated"] == "250.00"

    # 7. Attempt forbidden cost fact adjustment (Anti-fudging check)
    fudge_resp = client.post(
        "/api/v1/cost/reconciliation/adjust-fact",
        json={"cost_fact_id": "fact-999", "adjusted_amount": "5000.00"},
        headers=headers,
    )
    assert fudge_resp.status_code == 422
    assert fudge_resp.json()["error_code"] == "RECONCILIATION_ADJUSTMENT_FORBIDDEN"
