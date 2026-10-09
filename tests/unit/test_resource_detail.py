"""Unit & Contract Tests for Resource Detail, Cost Exploration, Usage, Runtime & Investigation (Prompt 39).

Enforces:
- Master brief Section 29 (15 core questions answered explicitly for every resource).
- Master brief Section 51 (Cost detail, drivers, largest increases investigation).
- BBP Section 30.3 (Resource detail panels).
- BBP Section 31.3 (Cost explorer & change point investigation).
- Six distinct unblended cost values: current, actual, estimated, forecast, budget, variance.
- Strict cost driver decomposition invariant: sum of driver amounts strictly equals total spend.
- Telemetry gap discipline: missed telemetry rendered as NO_DATA, never as zero.
- Runtime schedule adherence, excess hours, and monetary valuation.
- Investigation view with change point discontinuity, contributing resources, changed dimensions, and inventory changes.
- Scope-masking discipline: 404 returned for out-of-scope resources.
- Financial detail permission gating for low-level charge lines.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.resource_detail.exceptions import (
    FinancialDetailAccessDeniedException,
    ResourceDetailNotFoundException,
)
from domain.resource_detail.models import (
    CostExplorerDimension,
    CostExplorerGranularity,
    CostExplorerQuery,
)
from domain.resource_detail.service import (
    ResourceDetailService,
    get_resource_detail_service,
)
from domain.tenant.context import TenantContext


@pytest.fixture(autouse=True)
def setup_test_repository():
    from domain.hierarchy.repository import reset_hierarchy_repository
    from domain.hierarchy.service import reset_hierarchy_service
    from tests.fakes.hierarchy import InMemoryHierarchyRepository, seed_test_hierarchy

    fake_repo = InMemoryHierarchyRepository()
    reset_hierarchy_repository(fake_repo)
    reset_hierarchy_service()
    seed_test_hierarchy(fake_repo, "default-tenant")
    yield
    reset_hierarchy_service()
    reset_hierarchy_repository()


@pytest.fixture
def service() -> ResourceDetailService:
    return get_resource_detail_service()


@pytest.fixture
def global_tenant_context() -> TenantContext:
    return TenantContext(
        tenant_id="default-tenant",
        user_id="finops-admin",
        scope_grants=["*"],
    )


@pytest.fixture
def restricted_scope_context() -> TenantContext:
    return TenantContext(
        tenant_id="default-tenant",
        user_id="dev-engineer",
        scope_grants=["sc-aws-dev-1"],
    )


@pytest.fixture
def restricted_viewer_context() -> TenantContext:
    return TenantContext(
        tenant_id="default-tenant",
        user_id="auditor-viewer",
        roles=["RESTRICTED_VIEWER"],
        scope_grants=["*"],
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def test_headers(make_auth_token) -> dict[str, str]:
    token = make_auth_token(
        tenant_id="default-tenant",
        user_id="admin",
        roles=["SUPERUSER"],
        permissions=["*"],
    )
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# 1. 15 Questions Completeness Tests (Section 29)
# ==============================================================================


def test_fifteen_questions_completeness(
    service: ResourceDetailService, global_tenant_context: TenantContext
):
    """Verifies that all 15 core questions are answered explicitly and non-emptily for all seeded resources."""
    test_resource_ids = ["res-aws-vm-01", "res-aws-rds-01", "res-az-sql-01", "res-az-vm-01"]

    for res_id in test_resource_ids:
        detail = service.get_resource_detail(res_id, global_tenant_context)
        q = detail.fifteen_questions

        assert q.q1_what_it_is, f"Q1 unanswered for {res_id}"
        assert q.q2_where, f"Q2 unanswered for {res_id}"
        assert q.q3_who_owns_it, f"Q3 unanswered for {res_id}"
        assert q.q4_what_it_does, f"Q4 unanswered for {res_id}"
        assert q.q5_how_connected, f"Q5 unanswered for {res_id}"
        assert q.q6_how_charged, f"Q6 unanswered for {res_id}"
        assert q.q7_whether_free, f"Q7 unanswered for {res_id}"
        assert q.q8_what_allowance, f"Q8 unanswered for {res_id}"
        assert q.q9_what_causes_charges, f"Q9 unanswered for {res_id}"
        assert q.q10_how_much_it_cost, f"Q10 unanswered for {res_id}"
        assert q.q11_expected_cost, f"Q11 unanswered for {res_id}"
        assert q.q12_budget, f"Q12 unanswered for {res_id}"
        assert q.q13_threshold_crossed, f"Q13 unanswered for {res_id}"
        assert q.q14_why_cost_changed, f"Q14 unanswered for {res_id}"
        assert q.q15_provider_info_support, f"Q15 unanswered for {res_id}"


# ==============================================================================
# 2. Six Distinct Unblended Cost Values & Invariants
# ==============================================================================


def test_unblended_six_cost_values_invariants(
    service: ResourceDetailService, global_tenant_context: TenantContext
):
    """Verifies that current, actual, estimated, forecast, budget, and variance are distinct unblended figures."""
    detail = service.get_resource_detail("res-aws-vm-01", global_tenant_context)
    c = detail.cost

    # Assert all 6 values are present and distinct
    assert c.current_cost == Decimal("142.50")
    assert c.actual_cost == Decimal("138.20")
    assert c.estimated_cost == Decimal("135.00")
    assert c.forecast_cost == Decimal("148.00")
    assert c.budget_amount == Decimal("150.00")
    assert c.variance == Decimal("-2.00")
    assert c.variance_status == "FAVOURABLE"

    # Math consistency: variance == forecast - budget
    assert c.variance == c.forecast_cost - c.budget_amount


def test_unblended_cost_unfavourable_variance(
    service: ResourceDetailService, global_tenant_context: TenantContext
):
    """Verifies unfavourable variance logic on budget breach (res-aws-rds-01)."""
    detail = service.get_resource_detail("res-aws-rds-01", global_tenant_context)
    c = detail.cost

    assert c.current_cost == Decimal("920.00")
    assert c.budget_amount == Decimal("700.00")
    assert c.forecast_cost == Decimal("950.00")
    assert c.variance == Decimal("250.00")
    assert c.variance_status == "UNFAVOURABLE"
    assert detail.threshold_state == "CRITICAL"


# ==============================================================================
# 3. Cost Driver Decomposition Invariant
# ==============================================================================


def test_cost_driver_decomposition_sum_equals_total_spend(
    service: ResourceDetailService, global_tenant_context: TenantContext
):
    """Strictly enforces that decomposed driver amounts sum to current spend."""
    test_resource_ids = ["res-aws-vm-01", "res-aws-rds-01", "res-az-sql-01", "res-az-vm-01"]

    for res_id in test_resource_ids:
        detail = service.get_resource_detail(res_id, global_tenant_context)
        sum_drivers = sum(d.amount for d in detail.cost_drivers)

        assert round(sum_drivers, 2) == round(detail.cost.current_cost, 2), (
            f"Decomposition sum ({sum_drivers}) does not match current cost ({detail.cost.current_cost}) for {res_id}"
        )
        assert detail.total_driver_amount == sum_drivers


# ==============================================================================
# 4. Pricing Panel Specification Tests
# ==============================================================================


def test_pricing_panel_specification_compliance(
    service: ResourceDetailService, global_tenant_context: TenantContext
):
    """Verifies all mandatory fields of the pricing panel."""
    detail = service.get_resource_detail("res-aws-vm-01", global_tenant_context)
    p = detail.pricing

    assert p.pricing_status == "PAID"
    assert p.pricing_model == "On-Demand"
    assert p.unit == "hour"
    assert p.unit_price > Decimal("0.00")
    assert p.free_tier_consumed_pct == Decimal("100.00")
    assert "AWS Price List" in p.pricing_source
    assert p.region == "us-east-1"
    assert p.currency == "USD"


# ==============================================================================
# 5. Usage Detail Gap Discipline Tests
# ==============================================================================


def test_usage_gap_discipline_no_data_never_zero(
    service: ResourceDetailService, global_tenant_context: TenantContext
):
    """Verifies telemetry gap discipline: missed points have value=None and is_gap=True (never 0)."""
    detail = service.get_resource_detail("res-aws-vm-01", global_tenant_context)
    usage = detail.usage

    assert usage.has_telemetry_gap is True
    gap_points = [pt for pt in usage.time_series if pt.is_gap]
    assert len(gap_points) >= 1

    for gap in gap_points:
        assert gap.value is None, "Telemetry gap value must be None, never 0.0"
        assert gap.gap_reason, "Explicit gap reason required"


# ==============================================================================
# 6. Runtime Adherence & Excess Valuation Tests
# ==============================================================================


def test_runtime_view_excess_hours_and_monetary_valuation(
    service: ResourceDetailService, global_tenant_context: TenantContext
):
    """Verifies schedule adherence, excess hours, and monetary excess valuation."""
    # Compliant resource
    vm_detail = service.get_resource_detail("res-aws-vm-01", global_tenant_context)
    assert vm_detail.runtime.adherence_status == "COMPLIANT"
    assert vm_detail.runtime.excess_hours == Decimal("0.00")
    assert vm_detail.runtime.excess_cost == Decimal("0.00")

    # Out-of-schedule resource with active exemption
    az_vm_detail = service.get_resource_detail("res-az-vm-01", global_tenant_context)
    assert az_vm_detail.runtime.adherence_status == "OUT_OF_SCHEDULE"
    assert az_vm_detail.runtime.excess_hours == Decimal("14.50")
    assert az_vm_detail.runtime.excess_cost == Decimal("4.83")
    assert len(az_vm_detail.runtime.active_exemptions) == 1
    assert az_vm_detail.runtime.active_exemptions[0].exemption_id == "ex-run-001"


# ==============================================================================
# 7. Cost Explorer Multi-Dimensional Grouping Tests
# ==============================================================================


def test_cost_explorer_multi_dimensional_grouping(
    service: ResourceDetailService, global_tenant_context: TenantContext
):
    """Verifies grouping across multiple dimensions (SERVICE, PROVIDER, ACCOUNT)."""
    dimensions = [
        CostExplorerDimension.SERVICE,
        CostExplorerDimension.PROVIDER,
        CostExplorerDimension.ACCOUNT,
        CostExplorerDimension.CHARGE_CATEGORY,
    ]

    for dim in dimensions:
        q = CostExplorerQuery(dimension=dim, granularity=CostExplorerGranularity.DAILY)
        resp = service.explore_costs(q, global_tenant_context)

        assert resp.dimension == dim
        assert resp.total_spend > Decimal("0.00")
        assert len(resp.groups) > 0
        assert len(resp.cost_drivers) > 0

        # Sum of group costs equals total spend
        group_sum = sum(g.total_cost for g in resp.groups)
        assert round(group_sum, 2) == round(resp.total_spend, 2)


def test_cost_explorer_period_comparison(
    service: ResourceDetailService, global_tenant_context: TenantContext
):
    """Verifies period comparison (PoP) calculation."""
    q = CostExplorerQuery(
        dimension=CostExplorerDimension.SERVICE,
        granularity=CostExplorerGranularity.DAILY,
        comparison_period="POP",
    )
    resp = service.explore_costs(q, global_tenant_context)

    assert resp.comparison_total_spend is not None
    assert resp.variance_pct is not None
    assert resp.variance_pct == Decimal("+8.70")


# ==============================================================================
# 8. Contributing Charge Lines & Financial Permission Tests
# ==============================================================================


def test_contributing_charge_lines_drill_through(
    service: ResourceDetailService, global_tenant_context: TenantContext
):
    """Verifies drill-through from group to itemized charge lines."""
    resp = service.get_contributing_charge_lines(
        group_id="res-aws-vm-01",
        dimension="SERVICE",
        tenant_context=global_tenant_context,
    )
    assert resp.total_count == 4
    assert resp.total_amount == Decimal("142.50")
    assert len(resp.items) == 4

    # Verify line items have financial details
    line = resp.items[0]
    assert line.quantity > Decimal("0.00")
    assert line.rate > Decimal("0.00")
    assert line.amount > Decimal("0.00")
    assert line.unit


def test_financial_detail_permission_denied_for_restricted_viewer(
    service: ResourceDetailService, restricted_viewer_context: TenantContext
):
    """Verifies that RESTRICTED_VIEWER is forbidden from viewing itemized financial charge lines."""
    with pytest.raises(FinancialDetailAccessDeniedException):
        service.get_contributing_charge_lines(
            group_id="res-aws-vm-01",
            dimension="SERVICE",
            tenant_context=restricted_viewer_context,
        )


# ==============================================================================
# 9. Investigation View Tests (Largest Increases)
# ==============================================================================


def test_investigate_largest_increases_rds_spike(
    service: ResourceDetailService, global_tenant_context: TenantContext
):
    """Verifies root cause diagnosis for RDS spend spike (+48.4%)."""
    rep = service.investigate_cost_increase("res-aws-rds-01", global_tenant_context)

    assert rep.increase_amount == Decimal("300.00")
    assert rep.increase_percentage == Decimal("48.39")
    assert rep.is_restatement is False

    # Highlighted change point
    change_points = [p for p in rep.daily_series if p.is_change_point]
    assert len(change_points) == 1
    assert change_points[0].note is not None

    # Contributing resources delta
    assert len(rep.contributing_resources) == 1
    assert rep.contributing_resources[0].resource_id == "res-aws-rds-01"
    assert rep.contributing_resources[0].delta_spend == Decimal("300.00")

    # Changed pricing dimensions
    assert len(rep.changed_pricing_dimensions) >= 2
    sku_change = next(d for d in rep.changed_pricing_dimensions if "SKU" in d.dimension_name)
    assert "db.r5.2xlarge" in sku_change.new_value

    # Inventory change event
    assert len(rep.inventory_changes) >= 1
    assert rep.inventory_changes[0].change_type == "RESIZED"


# ==============================================================================
# 10. Scope Masking Discipline Tests
# ==============================================================================


def test_scope_masking_discipline_raises_not_found(
    service: ResourceDetailService, restricted_scope_context: TenantContext
):
    """Verifies that requesting a production resource with dev-only scopes raises 404 (never disclosing existence)."""
    with pytest.raises(ResourceDetailNotFoundException):
        service.get_resource_detail("res-aws-vm-01", restricted_scope_context)


# ==============================================================================
# 11. API Integration Tests (FastAPI / TestClient)
# ==============================================================================


def test_api_get_resource_detail_success(client: TestClient, test_headers: dict[str, str]):
    """Tests GET /api/v1/resource-detail/{id} endpoint."""
    resp = client.get("/api/v1/resource-detail/res-aws-vm-01", headers=test_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["id"] == "res-aws-vm-01"
    assert data["provider"] == "AWS"
    assert data["cost"]["current_cost"] == "142.50"
    assert len(data["cost_drivers"]) == 4
    assert data["fifteen_questions"]["q1_what_it_is"]


def test_api_get_resource_detail_not_found(client: TestClient, test_headers: dict[str, str]):
    """Tests GET /api/v1/resource-detail/{id} for non-existent resource returns 404."""
    resp = client.get("/api/v1/resource-detail/res-non-existent-999", headers=test_headers)
    assert resp.status_code == 404


def test_api_post_explorer_success(client: TestClient, test_headers: dict[str, str]):
    """Tests POST /api/v1/resource-detail/explorer endpoint."""
    payload = {
        "dimension": "SERVICE",
        "granularity": "DAILY",
        "comparison_period": "POP",
        "filters": {},
    }
    resp = client.post("/api/v1/resource-detail/explorer", json=payload, headers=test_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["dimension"] == "SERVICE"
    assert len(data["groups"]) > 0
    assert float(data["total_spend"]) > 0.0


def test_api_get_charge_lines_success(client: TestClient, test_headers: dict[str, str]):
    """Tests GET /api/v1/resource-detail/explorer/charge-lines endpoint."""
    resp = client.get("/api/v1/resource-detail/explorer/charge-lines?group_id=res-aws-vm-01", headers=test_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_count"] == 4
    assert len(data["items"]) == 4


def test_api_investigate_cost_increase_success(client: TestClient, test_headers: dict[str, str]):
    """Tests GET /api/v1/resource-detail/investigate/{entity_id} endpoint."""
    resp = client.get("/api/v1/resource-detail/investigate/res-aws-rds-01", headers=test_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["entity_id"] == "res-aws-rds-01"
    assert float(data["increase_amount"]) == 300.00
    assert len(data["daily_series"]) == 7


def test_api_runtime_overview_success(client: TestClient, test_headers: dict[str, str]):
    """Tests GET /api/v1/resource-detail/runtime-overview endpoint."""
    resp = client.get("/api/v1/resource-detail/runtime-overview", headers=test_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_managed_resources"] > 0
    assert float(data["compliance_rate_pct"]) > 0.0
    assert float(data["total_excess_hours"]) == 14.50
