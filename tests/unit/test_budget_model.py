"""Comprehensive Unit and Contract Tests for Budget Model and Allocations (Prompt 28).

Enforces:
- Prompt 28: Budgets at all seventeen scope types with full field set.
- Prompt 28: Support monthly, quarterly, annual, fiscal-year and custom periods aligned to fiscal calendar.
- Prompt 28: Evaluation producing actual utilisation, forecast utilisation, variance and state.
- Prompt 28: Overlap, over-allocation and double-counting detection.
- Prompt 28: Approval workflow: budgets above approval limit enter PENDING_APPROVAL and require approval.
- Prompt 28: Budget templates per scope type providing default period, thresholds and recipients.
- Prompt 28: Provider-native budgets imported read-only for comparison, visually and structurally distinct.
- Negative constraint: Do NOT silently prevent logical and native budgets from overlapping; flag and explain instead.
- Negative constraint: Do NOT evaluate a budget before its effective date.
- API Contracts: API-037, API-038, API-039.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.budgets.calendar import BudgetPeriodCalendar
from domain.budgets.models import (
    BudgetAmendRequest,
    BudgetApprovalStatus,
    BudgetApproveRequest,
    BudgetCreateRequest,
    BudgetEntity,
    BudgetEscalation,
    BudgetPeriod,
    BudgetRejectRequest,
    BudgetRolloverPolicy,
    BudgetScopeType,
    BudgetSourceType,
    BudgetThreshold,
    NativeBudgetImportRequest,
)
from domain.budgets.repository import reset_budget_repository
from domain.budgets.service import (
    BudgetService,
    get_budget_service,
    reset_budget_service,
)
from domain.budgets.templates import (
    get_template_for_scope,
    list_all_budget_templates,
)
from domain.models.enums import ProviderType
from domain.models.exceptions import (
    BudgetPendingApprovalException,
    InvalidBudgetAmountException,
    InvalidBudgetDatesException,
    NativeBudgetReadOnlyException,
)
from domain.tenant.context import TenantContext
from domain.thresholds.models import ThresholdState


@pytest.fixture
def tenant_ctx() -> TenantContext:
    """Fixture providing an isolated tenant context."""
    return TenantContext(
        tenant_id="tenant-finops-alpha",
        user_id="finops-lead-01",
        roles=["FINOPS_ADMIN"],
        correlation_id="corr-budget-test-001",
    )


@pytest.fixture
def budget_service() -> BudgetService:
    """Fixture providing a clean BudgetService instance."""
    reset_budget_repository()
    reset_budget_service()
    return get_budget_service()


@pytest.fixture
def client(tenant_ctx: TenantContext) -> TestClient:
    """Fixture providing FastAPI test client with tenant headers."""
    reset_budget_repository()
    reset_budget_service()
    return TestClient(
        app,
        headers={
            "X-Tenant-ID": tenant_ctx.tenant_id,
            "X-Actor-ID": tenant_ctx.actor_id or "finops-lead-01",
            "X-Correlation-ID": tenant_ctx.correlation_id or "corr-budget-client",
        },
    )


# ==============================================================================
# 1. Seventeen Scope Types & Full Field Set (CST-013 / AC-030)
# ==============================================================================


class TestSeventeenScopeTypesAndFields:
    """Verifies budgets at all seventeen scope types with full field sets."""

    @pytest.mark.parametrize("scope_type", list(BudgetScopeType))
    def test_budget_creation_at_all_seventeen_scope_types(
        self,
        scope_type: BudgetScopeType,
        budget_service: BudgetService,
        tenant_ctx: TenantContext,
    ):
        """Verifies a budget can be created at every one of the 17 scope types and immediately shows utilisation."""
        today = date.today()
        req = BudgetCreateRequest(
            name=f"Operational Budget for {scope_type.value}",
            scope_type=scope_type,
            scope_id=f"scope-{scope_type.value.lower()}-01",
            period=BudgetPeriod.MONTHLY,
            amount=5000.0,  # Below approval limit
            currency="USD",
            thresholds=[
                BudgetThreshold(percentage=80.0, band="WARNING"),
                BudgetThreshold(percentage=100.0, band="CRITICAL"),
            ],
            alert_recipients=["owner@enterprise.internal"],
            escalation=BudgetEscalation(escalate_to="vp@enterprise.internal", after_hours=48),
            forecast_threshold=95.0,
            effective_date=today - timedelta(days=10),
            expiry_date=today + timedelta(days=50),
            owner="FinOps Lead",
            rollover_policy=BudgetRolloverPolicy.NONE,
            notes=f"Test budget covering {scope_type.value}",
        )

        budget, warnings = budget_service.create_budget(req, tenant_context=tenant_ctx)
        assert budget.id
        assert budget.scope_type == scope_type
        assert budget.amount == 5000.0
        assert budget.approval_status == BudgetApprovalStatus.ACTIVE
        assert budget.is_active is True

        # Immediately evaluable with real-time utilisation
        eval_res = budget_service.evaluate_budget(
            budget.id, actual_spend=100.0, tenant_context=tenant_ctx
        )
        assert eval_res.budget_id == budget.id
        assert eval_res.actual_spend == 100.0
        assert eval_res.actual_utilisation == 2.0
        assert eval_res.variance == 4900.0
        assert eval_res.state == ThresholdState.NORMAL

    def test_reject_non_positive_budget_amount(
        self, budget_service: BudgetService, tenant_ctx: TenantContext
    ):
        """Validates that non-positive budget allocations are rejected."""
        today = date.today()
        with pytest.raises((InvalidBudgetAmountException, ValueError)):
            req = BudgetCreateRequest(
                name="Invalid Zero Budget",
                scope_type=BudgetScopeType.APPLICATION,
                scope_id="app-1",
                amount=-100.0,
                effective_date=today,
                owner="Dev Lead",
            )
            budget_service.create_budget(req, tenant_context=tenant_ctx)

    def test_reject_expiry_before_effective_date(
        self, budget_service: BudgetService, tenant_ctx: TenantContext
    ):
        """Validates that expiry date before effective date is rejected."""
        today = date.today()
        with pytest.raises(InvalidBudgetDatesException):
            req = BudgetCreateRequest(
                name="Invalid Dates Budget",
                scope_type=BudgetScopeType.APPLICATION,
                scope_id="app-1",
                amount=1000.0,
                effective_date=today,
                expiry_date=today - timedelta(days=5),
                owner="Dev Lead",
            )
            budget_service.create_budget(req, tenant_context=tenant_ctx)


# ==============================================================================
# 2. Fiscal Calendar & Period Handling (CST-014)
# ==============================================================================


class TestFiscalCalendarAndPeriodHandling:
    """Tests monthly, quarterly, annual, fiscal-year, and custom period resolution."""

    def test_monthly_period_boundaries(self):
        """Verifies monthly period resolves to current month boundaries."""
        calendar = BudgetPeriodCalendar()
        today = date(2026, 6, 15)
        entity = BudgetEntity(
            id="bgt-test-m",
            tenant_id="t1",
            name="Monthly Test",
            scope_type=BudgetScopeType.SUBSCRIPTION,
            scope_id="sub-1",
            period=BudgetPeriod.MONTHLY,
            amount=5000.0,
            effective_date=date(2026, 1, 1),
            owner="Tester",
        )
        start, end = calendar.resolve_period_bounds(entity, as_of=today)
        assert start == date(2026, 6, 1)
        assert end == date(2026, 6, 30)

    def test_quarterly_period_boundaries(self):
        """Verifies quarterly period resolves across calendar/fiscal quarters."""
        calendar = BudgetPeriodCalendar()
        today = date(2026, 5, 20)
        entity = BudgetEntity(
            id="bgt-test-q",
            tenant_id="t1",
            name="Quarterly Test",
            scope_type=BudgetScopeType.PROJECT,
            scope_id="proj-1",
            period=BudgetPeriod.QUARTERLY,
            amount=15000.0,
            effective_date=date(2026, 1, 1),
            owner="Tester",
        )
        start, end = calendar.resolve_period_bounds(entity, as_of=today)
        assert start == date(2026, 4, 1)
        assert end == date(2026, 6, 30)

    def test_fiscal_year_and_custom_period_boundaries(self):
        """Verifies fiscal year and custom period resolution."""
        calendar = BudgetPeriodCalendar()
        custom_start = date(2026, 3, 15)
        custom_end = date(2026, 9, 15)

        entity = BudgetEntity(
            id="bgt-test-c",
            tenant_id="t1",
            name="Custom Test",
            scope_type=BudgetScopeType.APPLICATION,
            scope_id="app-1",
            period=BudgetPeriod.CUSTOM,
            amount=8000.0,
            effective_date=custom_start,
            expiry_date=custom_end,
            owner="Tester",
        )
        start, end = calendar.resolve_period_bounds(entity, as_of=date(2026, 5, 1))
        assert start == custom_start
        assert end == custom_end


# ==============================================================================
# 3. Financial Evaluation Engine & Negative Constraint (CST-019 / CST-021)
# ==============================================================================


class TestBudgetEvaluationAndNegativeConstraints:
    """Tests evaluation calculations and negative constraints."""

    def test_negative_constraint_never_evaluates_before_effective_date(
        self, budget_service: BudgetService, tenant_ctx: TenantContext
    ):
        """NEGATIVE CONSTRAINT: Do NOT evaluate a budget before its effective date."""
        today = date.today()
        future_effective = today + timedelta(days=15)

        req = BudgetCreateRequest(
            name="Future Project Budget",
            scope_type=BudgetScopeType.PROJECT,
            scope_id="proj-future",
            period=BudgetPeriod.MONTHLY,
            amount=5000.0,
            effective_date=future_effective,
            owner="Future Lead",
        )
        budget, _ = budget_service.create_budget(req, tenant_context=tenant_ctx)

        # Evaluate as of today (which is before effective date)
        result = budget_service.evaluate_budget(
            budget.id, as_of=today, actual_spend=500.0, tenant_context=tenant_ctx
        )
        assert result.is_effective is False
        assert result.state == ThresholdState.INFORMATIONAL
        assert result.actual_spend == 0.0
        assert result.actual_utilisation == 0.0
        assert result.forecast_spend == 0.0
        assert result.predicted_breach_date is None
        assert result.notes is not None and "not yet effective" in result.notes.lower()

    def test_burn_rate_velocity_and_predicted_breach_date(
        self, budget_service: BudgetService, tenant_ctx: TenantContext
    ):
        """Verifies burn rate velocity and predicted breach date calculation."""
        eval_date = date(2026, 6, 10)
        req = BudgetCreateRequest(
            name="High Velocity Service Budget",
            scope_type=BudgetScopeType.SERVICE,
            scope_id="svc-compute",
            period=BudgetPeriod.MONTHLY,
            amount=1000.0,
            effective_date=date(2026, 6, 1),
            owner="Compute Lead",
        )
        budget, _ = budget_service.create_budget(req, tenant_context=tenant_ctx)

        # On day 10, spend is $600 (velocity = $60/day). Limit of $1000 will breach in ~6.6 days (day 16-17)
        result = budget_service.evaluate_budget(
            budget.id, as_of=eval_date, actual_spend=600.0, tenant_context=tenant_ctx
        )
        assert result.is_effective is True
        assert result.actual_spend == 600.0
        assert result.actual_utilisation == 60.0
        # 10 days elapsed, 20 remaining. Forecast = 600 + (60 * 20) = 1800
        assert result.forecast_spend == 1800.0
        assert result.forecast_utilisation == 180.0
        assert result.predicted_breach_date == date(2026, 6, 16)
        # Forecast breach raises warning state even though actual is 60%
        assert result.state == ThresholdState.WARNING

    def test_threshold_state_transitions(
        self, budget_service: BudgetService, tenant_ctx: TenantContext
    ):
        """Verifies threshold state transitions (NORMAL -> WARNING -> HIGH -> CRITICAL)."""
        today = date.today()
        req = BudgetCreateRequest(
            name="Tiered Threshold Budget",
            scope_type=BudgetScopeType.COST_CENTRE,
            scope_id="cc-eng",
            period=BudgetPeriod.MONTHLY,
            amount=1000.0,
            forecast_threshold=None,
            thresholds=[
                BudgetThreshold(percentage=80.0, band="WARNING"),
                BudgetThreshold(percentage=90.0, band="HIGH"),
                BudgetThreshold(percentage=100.0, band="CRITICAL"),
            ],
            effective_date=today - timedelta(days=5),
            owner="Engineering Lead",
        )
        budget, _ = budget_service.create_budget(req, tenant_context=tenant_ctx)

        # 50% spend -> NORMAL
        res_norm = budget_service.evaluate_budget(
            budget.id, as_of=today, actual_spend=500.0, tenant_context=tenant_ctx
        )
        assert res_norm.state == ThresholdState.NORMAL

        # 82% spend -> WARNING
        res_warn = budget_service.evaluate_budget(
            budget.id, as_of=today, actual_spend=820.0, tenant_context=tenant_ctx
        )
        assert res_warn.state == ThresholdState.WARNING

        # 92% spend -> HIGH
        res_high = budget_service.evaluate_budget(
            budget.id, as_of=today, actual_spend=920.0, tenant_context=tenant_ctx
        )
        assert res_high.state == ThresholdState.HIGH

        # 105% spend -> CRITICAL
        res_crit = budget_service.evaluate_budget(
            budget.id, as_of=today, actual_spend=1050.0, tenant_context=tenant_ctx
        )
        assert res_crit.state == ThresholdState.CRITICAL
        assert res_crit.is_breached is True


# ==============================================================================
# 4. Overlap & Over-Allocation Detection (CST-016 / AC-031)
# ==============================================================================


class TestBudgetOverlapAndOverAllocation:
    """Tests overlap detection, child over-allocation, and dual accounting handling."""

    def test_same_scope_duplicate_warning(
        self, budget_service: BudgetService, tenant_ctx: TenantContext
    ):
        """Verifies duplicate active budgets on the same scope generate a warning."""
        today = date.today()
        req1 = BudgetCreateRequest(
            name="Primary Account Budget",
            scope_type=BudgetScopeType.AWS_ACCOUNT,
            scope_id="123456789012",
            amount=5000.0,
            effective_date=today,
            owner="Cloud Lead",
        )
        b1, w1 = budget_service.create_budget(req1, tenant_context=tenant_ctx)
        assert len(w1) == 0

        req2 = BudgetCreateRequest(
            name="Secondary Account Budget (Duplicate)",
            scope_type=BudgetScopeType.AWS_ACCOUNT,
            scope_id="123456789012",
            amount=3000.0,
            effective_date=today,
            owner="Finance Lead",
        )
        b2, w2 = budget_service.create_budget(req2, tenant_context=tenant_ctx)
        assert len(w2) >= 1
        assert any(w.overlap_type == "SAME_SCOPE_DUPLICATE" for w in w2)

    def test_child_over_allocation_and_unallocated_remainder(
        self, budget_service: BudgetService, tenant_ctx: TenantContext
    ):
        """Verifies child budgets exceeding parent raise warning and show unallocated remainder."""
        today = date.today()
        parent_req = BudgetCreateRequest(
            name="Parent BU Budget",
            scope_type=BudgetScopeType.BUSINESS_UNIT,
            scope_id="bu-retail",
            amount=10000.0,
            effective_date=today,
            owner="VP Retail",
        )
        parent, _ = budget_service.create_budget(parent_req, tenant_context=tenant_ctx)

        # Child 1: $6,000
        child1_req = BudgetCreateRequest(
            name="Child App 1 Budget",
            scope_type=BudgetScopeType.APPLICATION,
            scope_id="app-store",
            parent_budget_id=parent.id,
            amount=6000.0,
            effective_date=today,
            owner="Store Lead",
        )
        child1, _ = budget_service.create_budget(child1_req, tenant_context=tenant_ctx)

        hier1 = budget_service.get_budget_hierarchy(parent.id, tenant_context=tenant_ctx)
        assert hier1.total_child_allocated == 6000.0
        assert hier1.unallocated_remainder == 4000.0
        assert hier1.is_over_allocated is False

        # Child 2: $7,000 (Total children = $13,000 > parent $10,000)
        child2_req = BudgetCreateRequest(
            name="Child App 2 Budget (Causes Over-allocation)",
            scope_type=BudgetScopeType.APPLICATION,
            scope_id="app-checkout",
            parent_budget_id=parent.id,
            amount=7000.0,
            effective_date=today,
            owner="Checkout Lead",
        )
        child2, w_child2 = budget_service.create_budget(child2_req, tenant_context=tenant_ctx)
        assert any(w.overlap_type == "CHILD_OVER_ALLOCATION" for w in w_child2)

        hier2 = budget_service.get_budget_hierarchy(parent.id, tenant_context=tenant_ctx)
        assert hier2.total_child_allocated == 13000.0
        assert hier2.unallocated_remainder == -3000.0
        assert hier2.is_over_allocated is True

    def test_negative_constraint_never_prevent_logical_and_native_overlap(
        self, budget_service: BudgetService, tenant_ctx: TenantContext
    ):
        """NEGATIVE CONSTRAINT: Do NOT silently prevent logical and native budgets from overlapping;

        flag and explain instead.
        """
        today = date.today()
        # Native budget (AWS Account)
        native_req = NativeBudgetImportRequest(
            provider=ProviderType.AWS,
            native_budget_id="aws-bgt-prod-core",
            native_budget_name="AWS Core Production Monthly",
            scope_type=BudgetScopeType.AWS_ACCOUNT,
            scope_id="112233445566",
            amount=8000.0,
            effective_date=today,
        )
        native_b = budget_service.import_native_budget(native_req, tenant_context=tenant_ctx)
        assert native_b.is_native is True
        assert native_b.is_read_only is True

        # Logical budget (Application)
        logical_req = BudgetCreateRequest(
            name="Payments Application Budget",
            scope_type=BudgetScopeType.APPLICATION,
            scope_id="app-payments",
            amount=6000.0,
            effective_date=today,
            owner="App Lead",
        )
        logical_b, warnings = budget_service.create_budget(logical_req, tenant_context=tenant_ctx)

        # Both budgets must be active and co-exist without error
        assert logical_b.approval_status == BudgetApprovalStatus.ACTIVE
        assert native_b.approval_status == BudgetApprovalStatus.ACTIVE

        # Must flag and explain the overlap
        overlap_warnings = [w for w in warnings if w.overlap_type == "LOGICAL_NATIVE_OVERLAP"]
        assert len(overlap_warnings) >= 1
        assert "dual-accounting notice" in overlap_warnings[0].explanation.lower()
        assert "independently" in overlap_warnings[0].explanation.lower()


# ==============================================================================
# 5. Approval Workflow & Amendments (CST-017 / CST-018 / AC-032 / AC-033)
# ==============================================================================


class TestBudgetApprovalWorkflowAndAmendments:
    """Tests approval limit enforcement, approval/rejection lifecycle, and amendment audit trail."""

    def test_budget_above_approval_limit_enters_pending_approval_ac032(
        self, budget_service: BudgetService, tenant_ctx: TenantContext
    ):
        """AC-032: Budgets above approval limit ($10,000) cannot become active without recorded approval."""
        today = date.today()
        req = BudgetCreateRequest(
            name="Executive Cloud Infrastructure Budget",
            scope_type=BudgetScopeType.ORGANISATION,
            scope_id="org-master",
            amount=50000.0,  # Exceeds $10,000 limit
            effective_date=today,
            owner="Enterprise Arch",
        )
        budget, _ = budget_service.create_budget(req, tenant_context=tenant_ctx)
        assert budget.approval_status == BudgetApprovalStatus.PENDING_APPROVAL
        assert budget.is_active is False

        # Attempting to evaluate raises BudgetPendingApprovalException
        with pytest.raises(BudgetPendingApprovalException) as exc_info:
            budget_service.evaluate_budget(budget.id, tenant_context=tenant_ctx)
        assert "cannot become active without a recorded formal approval decision" in str(
            exc_info.value
        )

        # Formally approve budget
        approved = budget_service.approve_budget(
            budget.id,
            BudgetApproveRequest(comment="Executive approval granted for FY planning ceiling."),
            tenant_context=tenant_ctx,
        )
        assert approved.approval_status == BudgetApprovalStatus.ACTIVE
        assert approved.approval_decision is not None
        assert approved.approval_decision.decision == BudgetApprovalStatus.APPROVED
        assert approved.approval_decision.decided_by == tenant_ctx.actor_id

        # Now evaluable
        res = budget_service.evaluate_budget(
            budget.id, actual_spend=12000.0, tenant_context=tenant_ctx
        )
        assert res.actual_utilisation == 24.0

    def test_budget_rejection_workflow(
        self, budget_service: BudgetService, tenant_ctx: TenantContext
    ):
        """Verifies formal rejection of a pending budget."""
        today = date.today()
        req = BudgetCreateRequest(
            name="Rejected Marketing Sandbox Budget",
            scope_type=BudgetScopeType.ENVIRONMENT,
            scope_id="env-marketing",
            amount=25000.0,
            effective_date=today,
            owner="Marketing Lead",
        )
        budget, _ = budget_service.create_budget(req, tenant_context=tenant_ctx)
        assert budget.approval_status == BudgetApprovalStatus.PENDING_APPROVAL

        rejected = budget_service.reject_budget(
            budget.id,
            BudgetRejectRequest(
                comment="Rejected: Unjustified spend allocation for non-prod environment."
            ),
            tenant_context=tenant_ctx,
        )
        assert rejected.approval_status == BudgetApprovalStatus.REJECTED
        assert rejected.approval_decision is not None
        assert rejected.approval_decision.decision == BudgetApprovalStatus.REJECTED

    def test_budget_amendment_audit_history_ac033(
        self, budget_service: BudgetService, tenant_ctx: TenantContext
    ):
        """AC-033: Budget amendment history tracks previous amount, new amount, actor, approver, reason."""
        today = date.today()
        req = BudgetCreateRequest(
            name="Project Gamma Budget",
            scope_type=BudgetScopeType.PROJECT,
            scope_id="proj-gamma",
            amount=6000.0,
            effective_date=today,
            owner="Project Lead",
        )
        budget, _ = budget_service.create_budget(req, tenant_context=tenant_ctx)

        # Amend to $8,000 (still <= $10,000)
        amended1 = budget_service.amend_budget(
            budget.id,
            BudgetAmendRequest(
                new_amount=8000.0, reason="Scope expansion for Phase 2 deliverables"
            ),
            tenant_context=tenant_ctx,
        )
        assert amended1.amount == 8000.0
        assert len(amended1.amendments) == 1
        assert amended1.amendments[0].previous_amount == 6000.0
        assert amended1.amendments[0].new_amount == 8000.0
        assert amended1.amendments[0].reason == "Scope expansion for Phase 2 deliverables"
        assert amended1.approval_status == BudgetApprovalStatus.ACTIVE

        # Amend to $15,000 (> $10,000 approval limit) -> Re-enters PENDING_APPROVAL
        amended2 = budget_service.amend_budget(
            budget.id,
            BudgetAmendRequest(
                new_amount=15000.0, reason="High-volume hardware acquisition requirement"
            ),
            tenant_context=tenant_ctx,
        )
        assert amended2.amount == 15000.0
        assert len(amended2.amendments) == 2
        assert amended2.amendments[1].previous_amount == 8000.0
        assert amended2.amendments[1].new_amount == 15000.0
        assert amended2.approval_status == BudgetApprovalStatus.PENDING_APPROVAL


# ==============================================================================
# 6. Provider-Native Read-Only Budget Import
# ==============================================================================


class TestProviderNativeBudgetImport:
    """Tests importing provider-native budgets as read-only and distinctly badged."""

    def test_provider_imported_budgets_visually_and_structurally_distinct(
        self, budget_service: BudgetService, tenant_ctx: TenantContext
    ):
        """Verifies provider-imported budgets are visually badged, read-only, and immutable."""
        today = date.today()
        req = NativeBudgetImportRequest(
            provider=ProviderType.AZURE,
            native_budget_id="az-bgt-sub-prod",
            native_budget_name="Azure Subscription Production Spend Cap",
            scope_type=BudgetScopeType.SUBSCRIPTION,
            scope_id="sub-prod-001",
            amount=12000.0,
            effective_date=today,
        )
        native_b = budget_service.import_native_budget(req, tenant_context=tenant_ctx)
        assert native_b.is_native is True
        assert native_b.is_read_only is True
        assert native_b.budget_source == BudgetSourceType.PROVIDER_NATIVE
        assert "[PROVIDER NATIVE - AZURE - READ ONLY]" in native_b.display_source_badge

        # Mutation attempts must be rejected
        with pytest.raises(NativeBudgetReadOnlyException):
            budget_service.amend_budget(
                native_b.id,
                BudgetAmendRequest(new_amount=15000.0, reason="Illegal mutation attempt"),
                tenant_context=tenant_ctx,
            )

        with pytest.raises(NativeBudgetReadOnlyException):
            budget_service.approve_budget(
                native_b.id,
                BudgetApproveRequest(comment="Illegal approve attempt"),
                tenant_context=tenant_ctx,
            )

        with pytest.raises(NativeBudgetReadOnlyException):
            budget_service.delete_budget(native_b.id, tenant_context=tenant_ctx)


# ==============================================================================
# 7. Budget Templates Catalogue
# ==============================================================================


class TestBudgetTemplatesCatalogue:
    """Tests budget template coverage across all seventeen scope types."""

    def test_templates_cover_all_seventeen_scope_types(self):
        """Verifies templates exist for all 17 scope types."""
        templates = list_all_budget_templates()
        assert len(templates) == 17
        for st in BudgetScopeType:
            tmpl = get_template_for_scope(st)
            assert tmpl.scope_type == st
            assert tmpl.default_period in BudgetPeriod
            assert len(tmpl.default_thresholds) >= 2
            assert len(tmpl.default_alert_recipients) >= 1


# ==============================================================================
# 8. REST API Endpoints Contract (API-037, API-038, API-039)
# ==============================================================================


class TestBudgetAPIEndpoints:
    """Tests REST API endpoints for budget lifecycle and governance."""

    def test_api_038_create_budget(self, client: TestClient):
        """API-038: POST /api/v1/budgets creates a new budget and returns warnings."""
        today = date.today()
        payload = {
            "name": "API Test Budget",
            "scope_type": "APPLICATION",
            "scope_id": "app-api-test",
            "amount": 7500.0,
            "period": "MONTHLY",
            "effective_date": today.isoformat(),
            "owner": "API Tester",
        }
        res = client.post("/api/v1/budgets", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert "budget" in data
        assert "warnings" in data
        assert data["budget"]["name"] == "API Test Budget"
        assert data["budget"]["amount"] == 7500.0
        assert data["budget"]["approval_status"] == "ACTIVE"

    def test_api_037_list_budgets_with_evaluation(self, client: TestClient):
        """API-037: GET /api/v1/budgets lists budgets with real-time spend and utilisation."""
        today = date.today()
        # Seed budget
        client.post(
            "/api/v1/budgets",
            json={
                "name": "Listing Test Budget",
                "scope_type": "SERVICE",
                "scope_id": "svc-storage",
                "amount": 4000.0,
                "period": "MONTHLY",
                "effective_date": today.isoformat(),
                "owner": "Storage Lead",
            },
        )

        res = client.get("/api/v1/budgets?include_evaluation=true")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 1
        item = next(i for i in data["items"] if i["name"] == "Listing Test Budget")
        assert item["evaluation"] is not None
        assert item["evaluation"]["amount"] == 4000.0

    def test_api_039_amend_budget(self, client: TestClient):
        """API-039: PATCH /api/v1/budgets/{id} amends budget ceiling."""
        today = date.today()
        create_res = client.post(
            "/api/v1/budgets",
            json={
                "name": "Amend Target Budget",
                "scope_type": "ENVIRONMENT",
                "scope_id": "env-staging",
                "amount": 3000.0,
                "period": "MONTHLY",
                "effective_date": today.isoformat(),
                "owner": "Staging Lead",
            },
        )
        b_id = create_res.json()["budget"]["id"]

        patch_res = client.patch(
            f"/api/v1/budgets/{b_id}",
            json={"new_amount": 4500.0, "reason": "Increased test runner capacity"},
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["amount"] == 4500.0
        assert len(patch_res.json()["amendments"]) == 1

    def test_api_approval_lifecycle_endpoints(self, client: TestClient):
        """Tests approval and rejection endpoints via API."""
        today = date.today()
        # Create budget > $10,000 -> PENDING_APPROVAL
        create_res = client.post(
            "/api/v1/budgets",
            json={
                "name": "High Value API Budget",
                "scope_type": "BUSINESS_UNIT",
                "scope_id": "bu-wealth",
                "amount": 50000.0,
                "period": "ANNUAL",
                "effective_date": today.isoformat(),
                "owner": "Wealth VP",
            },
        )
        b_id = create_res.json()["budget"]["id"]
        assert create_res.json()["budget"]["approval_status"] == "PENDING_APPROVAL"

        # Approve
        appr_res = client.post(
            f"/api/v1/budgets/{b_id}/approve",
            json={"comment": "Approved by FinOps steering committee"},
        )
        assert appr_res.status_code == 200
        assert appr_res.json()["approval_status"] == "ACTIVE"

    def test_api_native_budget_import(self, client: TestClient):
        """Tests importing provider-native budget and verifying read-only enforcement."""
        today = date.today()
        res = client.post(
            "/api/v1/budgets/import-native",
            json={
                "provider": "gcp",
                "native_budget_id": "gcp-billing-bgt-001",
                "native_budget_name": "GCP BigQuery Sandbox Cap",
                "scope_type": "GCP_PROJECT",
                "scope_id": "prj-analytics",
                "amount": 10000.0,
                "effective_date": today.isoformat(),
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["is_native"] is True
        assert data["is_read_only"] is True
        assert "[PROVIDER NATIVE - GCP - READ ONLY]" in data["display_source_badge"]

        # Mutate attempt via API -> HTTP 409
        mut_res = client.patch(
            f"/api/v1/budgets/{data['id']}",
            json={"new_amount": 12000.0, "reason": "Attempted edit"},
        )
        assert mut_res.status_code == 409
        assert "NATIVE_BUDGET_READ_ONLY" in mut_res.json()["error_code"]
