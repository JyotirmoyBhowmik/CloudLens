"""Unit and Integration Tests for Showback, Chargeback Statements and Cost Allocation Packs (Prompt 52).

Enforces:
1. Statement generation across scopes (Business Unit, Cost Centre, Application, Project, Team).
2. Budget variance calculation, status, and parameterized narrative phrasing from template.
3. Prior period comparison, movement calculation, and largest driver explanations.
4. Mandatory visible apportionment basis on shared-service lines:
   Hard Rule: "Do not apportion shared cost without showing the basis."
5. Period close cycle: DRAFT -> IN_REVIEW (review window) -> FINALISED (immutability).
   Hard Rule: "Do not alter a finalised statement in place."
6. Restatement adjustments: non-destructive versioning, line-level deltas, and audit trail.
7. Line dispute path routed through workflow engine with 48h SLA and documented reallocations.
8. Formal recipient acceptance and executive outstanding-acceptance reporting.
9. Showback vs Chargeback distinction:
   Hard Rule: "Do not present showback as chargeback."
   Phase 2 chargeback gating.
10. Multi-currency presentation with FX rate and rate date disclosure.
11. Allocation transparency view with winning rule, contributing resources, and permissioned charge line drill-through.
12. Multi-format distribution (Markdown, CSV, JSON, HTML) and delivery simulation.
13. Complete REST API endpoints coverage via TestClient.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.models.enums import DecisionOutcome
from domain.models.exceptions import (
    FinalisedStatementModificationForbiddenException,
    MissingApportionmentBasisException,
    StatementAlreadyFinalisedException,
    StatementDisputeException,
)
from domain.statements.models import (
    BudgetVarianceStatus,
    DisputeStatus,
    ExportFormat,
    MovementDirection,
    RecipientScopeType,
    SharedServiceApportionmentItem,
    StatementLifecycleStatus,
    StatementMode,
)
from domain.statements.service import (
    StatementService,
    get_statement_service,
    reset_statement_service,
)
from domain.tenant.context import TenantContext

# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture(autouse=True)
def clean_statement_service():
    """Reset repository and service singleton between tests."""
    reset_statement_service()
    yield
    reset_statement_service()


@pytest.fixture
def tenant_admin_context() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-showback-01",
        user_id="usr-cfo-showback",
        email="cfo@company.com",
        roles=["GLOBAL_ADMIN", "FINANCIAL_DETAIL"],
        correlation_id="corr-stmt-test-01",
        is_superuser=True,
    )


@pytest.fixture
def bu_owner_context() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-showback-01",
        user_id="usr-retail-lead",
        email="retail-lead@company.com",
        roles=["SCOPE:BU-RETAIL"],
        correlation_id="corr-stmt-test-02",
        is_superuser=False,
    )


@pytest.fixture
def statement_service() -> StatementService:
    return get_statement_service()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# 1. Statement Generation Across Recipient Scopes
# ==============================================================================


def test_generate_statement_across_all_recipient_scopes(
    statement_service: StatementService, tenant_admin_context: TenantContext
):
    """Verify statement generator produces valid showback statements across all 5 recipient scope types."""
    scopes = [
        (RecipientScopeType.BUSINESS_UNIT, "BU-RETAIL", "Retail Business Unit"),
        (RecipientScopeType.COST_CENTRE, "CC-4401", "Engineering Platform Cost Centre"),
        (RecipientScopeType.APPLICATION, "APP-CHECKOUT", "E-Commerce Checkout App"),
        (RecipientScopeType.PROJECT, "PRJ-MIGRATION", "Cloud Migration Project"),
        (RecipientScopeType.TEAM, "TEAM-SRE", "Site Reliability Engineering Team"),
    ]

    for scope_type, scope_code, scope_name in scopes:
        stmt = statement_service.generate_statement(
            period="2026-09",
            scope_type=scope_type,
            scope_code=scope_code,
            scope_name=scope_name,
            recipient_owner_id="usr-owner-01",
            recipient_owner_email="owner@company.com",
            tenant_context=tenant_admin_context,
            custom_budget=50000.0,
        )

        assert stmt.statement_id.endswith(f"-2026-09-{scope_code.lower()}-v1")
        assert stmt.scope_type == scope_type
        assert stmt.scope_code == scope_code
        assert stmt.scope_name == scope_name
        assert stmt.period == "2026-09"
        assert stmt.version == 1
        assert stmt.status == StatementLifecycleStatus.DRAFT
        assert stmt.mode == StatementMode.SHOWBACK
        assert stmt.total_allocated_cost > Decimal("0.00")
        assert stmt.direct_allocated_cost > Decimal("0.00")
        assert stmt.shared_service_apportioned_cost > Decimal("0.00")
        assert stmt.total_allocated_cost == (
            stmt.direct_allocated_cost + stmt.shared_service_apportioned_cost
        )

        # 4 Breakdowns present
        assert len(stmt.provider_breakdown) >= 1
        assert len(stmt.category_breakdown) >= 1
        assert len(stmt.application_breakdown) >= 1
        assert len(stmt.environment_breakdown) >= 1

        # Check provider shares sum to direct allocated cost share
        provider_shares_sum = sum(p.share_percentage for p in stmt.provider_breakdown)
        expected_direct_share = (stmt.direct_allocated_cost / stmt.total_allocated_cost) * Decimal(
            "100.0"
        )
        assert abs(provider_shares_sum - expected_direct_share) <= Decimal("0.5")


# ==============================================================================
# 2. Budget Performance & Phrasing
# ==============================================================================


def test_budget_variance_and_phrasing(
    statement_service: StatementService, tenant_admin_context: TenantContext
):
    """Verify budget comparison calculation and dynamic template phrasing."""
    # Under budget
    stmt_under = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-UNDER",
        tenant_context=tenant_admin_context,
        custom_budget=100000.0,
    )
    assert stmt_under.budget_status == BudgetVarianceStatus.ON_TRACK
    assert stmt_under.budget_variance_amount < Decimal("0.00")
    assert "headroom" in stmt_under.budget_commentary.lower()

    # Exceeded budget
    stmt_over = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-OVER",
        tenant_context=tenant_admin_context,
        custom_budget=5000.0,
    )
    assert stmt_over.budget_status == BudgetVarianceStatus.EXCEEDED
    assert stmt_over.budget_variance_amount > Decimal("0.00")
    assert "overage" in stmt_over.budget_commentary.lower()

    # Unbudgeted
    stmt_unbudgeted = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-NOBUDGET",
        tenant_context=tenant_admin_context,
        custom_budget=0.0,
    )
    assert stmt_unbudgeted.budget_status == BudgetVarianceStatus.UNBUDGETED


# ==============================================================================
# 3. Prior Period Comparison & Largest Movements
# ==============================================================================


def test_prior_period_comparison_and_largest_movements(
    statement_service: StatementService, tenant_admin_context: TenantContext
):
    """Verify month-over-month shifts and narrative explanations."""
    stmt = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-GROWTH",
        tenant_context=tenant_admin_context,
        prior_period_cost=30000.0,
    )
    assert stmt.prior_period == "2026-08"
    assert stmt.prior_period_cost == Decimal("30000.00")
    assert stmt.movement_direction in (
        MovementDirection.UP,
        MovementDirection.DOWN,
        MovementDirection.FLAT,
    )
    assert len(stmt.largest_movements) >= 1

    top_m = stmt.largest_movements[0]
    assert top_m.item_name
    assert top_m.delta_amount != Decimal("0.00")
    assert len(top_m.narrative_explanation) > 10


# ==============================================================================
# 4. Mandatory Visible Basis for Shared Costs (Hard Rule)
# ==============================================================================


def test_shared_service_apportionment_requires_visible_basis(
    statement_service: StatementService, tenant_admin_context: TenantContext
):
    """Enforces Hard Rule: 'Do not apportion shared cost without showing the basis.'"""
    stmt = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-SHARED",
        tenant_context=tenant_admin_context,
    )

    assert len(stmt.shared_service_apportionments) >= 1
    for appo in stmt.shared_service_apportionments:
        assert appo.shared_service_name
        assert appo.apportioned_amount > Decimal("0.00")
        assert appo.allocation_rule_id
        # Explicit visible basis is mandatory
        assert appo.apportionment_basis
        assert len(appo.apportionment_basis.strip()) >= 5

    # Enforce validation failure if basis is empty or whitespace
    with pytest.raises(MissingApportionmentBasisException):
        SharedServiceApportionmentItem(
            shared_service_id="k8s-shared",
            shared_service_name="Shared Kubernetes Cluster",
            provider="AWS",
            source_total_cost=Decimal("10000.00"),
            apportioned_amount=Decimal("2500.00"),
            apportionment_percentage=Decimal("25.0"),
            allocation_rule_id="RULE-SPLIT-01",
            allocation_rule_name="CPU/RAM Split",
            apportionment_basis="   ",  # Invalid empty/whitespace basis
        )


# ==============================================================================
# 5. Period Close Cycle & Finalised Immutability (Hard Rule)
# ==============================================================================


def test_period_close_cycle_and_finalisation(
    statement_service: StatementService,
    tenant_admin_context: TenantContext,
):
    """Verify DRAFT -> IN_REVIEW (review window) -> FINALISED lifecycle."""
    stmt = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-CYCLE",
        tenant_context=tenant_admin_context,
    )
    assert stmt.status == StatementLifecycleStatus.DRAFT

    # Circulate
    circulated = statement_service.circulate_statement(
        stmt.statement_id, review_window_days=7, tenant_context=tenant_admin_context
    )
    assert circulated.status == StatementLifecycleStatus.IN_REVIEW
    assert circulated.circulated_at is not None
    assert circulated.review_deadline is not None

    # Finalise
    finalised = statement_service.finalise_statement(
        stmt.statement_id, tenant_context=tenant_admin_context
    )
    assert finalised.status == StatementLifecycleStatus.FINALISED
    assert finalised.finalised_at is not None

    # Cannot re-finalise
    with pytest.raises(StatementAlreadyFinalisedException):
        statement_service.finalise_statement(stmt.statement_id, tenant_context=tenant_admin_context)


def test_hard_rule_finalised_statement_in_place_mutation_forbidden(
    statement_service: StatementService, tenant_admin_context: TenantContext
):
    """Enforces Hard Rule: 'Do not alter a finalised statement in place.'"""
    stmt = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-LOCKED",
        tenant_context=tenant_admin_context,
    )
    statement_service.finalise_statement(stmt.statement_id, tenant_context=tenant_admin_context)

    # Calling assert_modifiable must raise FinalisedStatementModificationForbiddenException
    finalised = statement_service.get_statement(
        stmt.statement_id, tenant_context=tenant_admin_context
    )
    with pytest.raises(FinalisedStatementModificationForbiddenException) as exc_info:
        statement_service.cycle_engine.assert_modifiable(finalised)
    assert finalised.statement_id in str(exc_info.value)


# ==============================================================================
# 6. Restatement Adjustments
# ==============================================================================


def test_restatement_adjustment_emits_versioned_statement(
    statement_service: StatementService, tenant_admin_context: TenantContext
):
    """Verify post-finalisation restatement produces versioned adjustment without in-place mutation."""
    orig_stmt = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-ADJUST",
        tenant_context=tenant_admin_context,
    )
    statement_service.finalise_statement(
        orig_stmt.statement_id, tenant_context=tenant_admin_context
    )

    initial_total = orig_stmt.total_allocated_cost

    # Apply restatement adjustment
    adj_deltas = [
        {
            "line_id": "srv-k8s-platform",
            "description": "Shared Kubernetes cluster billing correction",
            "original_amount": 1000.0,
            "adjustment_delta": -250.0,
            "reason": "Over-allocation of node hours corrected by platform team",
        },
        {
            "line_id": "srv-s3-backup",
            "description": "Glacier archive retrieval fee addition",
            "original_amount": 500.0,
            "adjustment_delta": 100.0,
            "reason": "Late-arriving AWS invoice line item",
        },
    ]

    adj_stmt, adj_record = statement_service.process_restatement_adjustment(
        orig_stmt.statement_id,
        adjustment_deltas=adj_deltas,
        restatement_reason="Audit true-up of shared platform node hours and late invoice lines",
        tenant_context=tenant_admin_context,
    )

    # Verify original statement is now SUPERSEDED
    reloaded_orig = statement_service.get_statement(
        orig_stmt.statement_id, tenant_context=tenant_admin_context
    )
    assert reloaded_orig.status == StatementLifecycleStatus.SUPERSEDED

    # Verify new adjusted statement
    assert adj_stmt.version == 2
    assert adj_stmt.supersedes_statement_id == orig_stmt.statement_id
    assert adj_stmt.status == StatementLifecycleStatus.ADJUSTED
    assert adj_stmt.total_allocated_cost == (initial_total - Decimal("150.00"))

    # Verify adjustment record
    assert adj_record.original_statement_id == orig_stmt.statement_id
    assert adj_record.adjusted_statement_id == adj_stmt.statement_id
    assert adj_record.adjustment_total == Decimal("-150.00")
    assert len(adj_record.lines) == 2


# ==============================================================================
# 7. Dispute Path & Workflow Resolution
# ==============================================================================


def test_dispute_workflow_and_reallocation_audit(
    statement_service: StatementService,
    bu_owner_context: TenantContext,
    tenant_admin_context: TenantContext,
):
    """Verify queried statement line routes to workflow engine and resolved dispute emits reallocation."""
    stmt = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-RETAIL",
        tenant_context=bu_owner_context,
    )

    # 1. Raise dispute
    dispute = statement_service.raise_dispute(
        stmt.statement_id,
        line_id="srv-k8s-platform",
        line_description="Platform K8s Cluster Share",
        disputed_amount=2500.0,
        proposed_amount=1500.0,
        reason="Retail team did not utilize the machine learning GPU nodepool allocated here.",
        tenant_context=bu_owner_context,
    )

    assert dispute.dispute_id.startswith("dsp-2026-09-")
    assert dispute.status == DisputeStatus.SUBMITTED
    assert dispute.disputed_amount == Decimal("2500.00")
    assert dispute.sla_deadline is not None

    # Statement lifecycle moves to DISPUTED
    stmt_updated = statement_service.get_statement(
        stmt.statement_id, tenant_context=bu_owner_context
    )
    assert stmt_updated.status == StatementLifecycleStatus.DISPUTED

    # 2. Resolve dispute with approval
    resolved, realloc = statement_service.resolve_dispute(
        dispute.dispute_id,
        decision=DecisionOutcome.APPROVE,
        resolution_notes="GPU nodes were correctly provisioned for BU-DATA, not BU-RETAIL. Crediting $1,000.",
        target_reallocation_scope="BU-DATA",
        tenant_context=tenant_admin_context,
    )

    assert resolved.status == DisputeStatus.RESOLVED_ACCEPTED
    assert realloc is not None
    assert realloc.source_scope_code == "BU-RETAIL"
    assert realloc.target_scope_code == "BU-DATA"
    assert realloc.reallocated_amount == Decimal("1000.00")


def test_dispute_validation_errors(
    statement_service: StatementService, bu_owner_context: TenantContext
):
    """Verify invalid dispute inputs are rejected."""
    stmt = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-RETAIL",
        tenant_context=bu_owner_context,
    )

    # Empty reason
    with pytest.raises(StatementDisputeException):
        statement_service.raise_dispute(
            stmt.statement_id,
            line_id="srv-test",
            line_description="Test",
            disputed_amount=100.0,
            proposed_amount=0.0,
            reason="   ",
            tenant_context=bu_owner_context,
        )

    # Negative amount
    with pytest.raises(StatementDisputeException):
        statement_service.raise_dispute(
            stmt.statement_id,
            line_id="srv-test",
            line_description="Test",
            disputed_amount=-50.0,
            proposed_amount=0.0,
            reason="Invalid amount test",
            tenant_context=bu_owner_context,
        )


# ==============================================================================
# 8. Formal Acceptance & Outstanding Reports
# ==============================================================================


def test_formal_acceptance_and_outstanding_compliance_report(
    statement_service: StatementService,
    tenant_admin_context: TenantContext,
):
    """Verify recipient acceptance sign-off and executive outstanding report."""
    # Stmt 1: Accepted
    s1 = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-FINANCE",
        tenant_context=tenant_admin_context,
    )
    statement_service.circulate_statement(s1.statement_id, tenant_context=tenant_admin_context)
    statement_service.accept_statement(
        s1.statement_id, notes="Approved by Finance Director", tenant_context=tenant_admin_context
    )

    # Stmt 2: Circulated but not accepted
    s2 = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-MARKETING",
        tenant_context=tenant_admin_context,
    )
    statement_service.circulate_statement(s2.statement_id, tenant_context=tenant_admin_context)

    # Report
    rep = statement_service.get_outstanding_acceptance_report(
        period="2026-09", tenant_context=tenant_admin_context
    )

    assert rep.total_statements_issued == 2
    assert rep.total_accepted == 1
    assert rep.total_outstanding == 1
    assert rep.acceptance_rate_percentage == Decimal("50.0")
    assert len(rep.items) == 1
    assert rep.items[0].scope_code == "BU-MARKETING"


# ==============================================================================
# 9. Showback vs Chargeback & Phase 2 Flag Gating
# ==============================================================================


def test_showback_mode_and_phase_2_chargeback_gating(
    statement_service: StatementService, tenant_admin_context: TenantContext
):
    """Enforces Hard Rule: 'Do not present showback as chargeback.'"""
    stmt = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-SHOWBACK",
        tenant_context=tenant_admin_context,
        enable_chargeback_phase2=False,
    )

    assert stmt.mode == StatementMode.SHOWBACK
    assert "SHOWBACK STATEMENT — FOR INTERNAL MANAGEMENT INFORMATION ONLY" in stmt.showback_banner
    assert stmt.chargeback_fields.is_enabled is False
    assert stmt.chargeback_fields.journal_reference is None

    # Phase 2 enabled explicitly
    stmt_p2 = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-CHARGEBACK",
        tenant_context=tenant_admin_context,
        enable_chargeback_phase2=True,
    )
    assert stmt_p2.mode == StatementMode.CHARGEBACK
    assert stmt_p2.chargeback_fields.is_enabled is True
    assert stmt_p2.chargeback_fields.journal_reference is not None


# ==============================================================================
# 10. Multi-Currency Presentation & Disclosure
# ==============================================================================


def test_multi_currency_presentation_and_disclosure(
    statement_service: StatementService, tenant_admin_context: TenantContext
):
    """Verify target presentation currency conversion and exchange rate disclosure."""
    stmt_eur = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-EUROPE",
        target_currency="EUR",
        tenant_context=tenant_admin_context,
    )

    assert stmt_eur.currency == "EUR"
    assert stmt_eur.currency_disclosure.base_currency == "USD"
    assert stmt_eur.currency_disclosure.presentation_currency == "EUR"
    assert stmt_eur.currency_disclosure.exchange_rate > Decimal("0.0")
    assert stmt_eur.currency_disclosure.rate_type != ""


# ==============================================================================
# 11. Allocation Transparency View (Permissioned Drill-Through)
# ==============================================================================


def test_allocation_transparency_permissioned_drill_through(
    statement_service: StatementService,
    bu_owner_context: TenantContext,
    tenant_admin_context: TenantContext,
):
    """Verify allocation line drill-through: redacting charge lines if lacking financial-detail permission."""
    stmt = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-RETAIL",
        tenant_context=tenant_admin_context,
    )

    # 1. Unprivileged user (bu_owner lacks FINANCIAL_DETAIL role)
    view_redacted = statement_service.get_allocation_transparency(
        stmt.statement_id,
        line_id="AWS",
        tenant_context=bu_owner_context,
    )
    assert view_redacted.winning_rule_id
    assert len(view_redacted.contributing_resources) >= 1
    assert view_redacted.financial_detail_permitted is False
    assert len(view_redacted.charge_lines) == 0
    assert view_redacted.disclosure_message is not None
    assert "financial-detail permission" in view_redacted.disclosure_message

    # 2. Privileged user (tenant_admin has FINANCIAL_DETAIL role and is superuser)
    view_full = statement_service.get_allocation_transparency(
        stmt.statement_id,
        line_id="AWS",
        tenant_context=tenant_admin_context,
    )
    assert view_full.financial_detail_permitted is True
    assert len(view_full.charge_lines) >= 1
    assert view_full.disclosure_message is None
    assert view_full.charge_lines[0].unit_price > Decimal("0.00")


# ==============================================================================
# 12. Multi-Format Export & Distribution
# ==============================================================================


def test_multi_format_export_and_distribution(
    statement_service: StatementService, tenant_admin_context: TenantContext, tmp_path
):
    """Verify Markdown, CSV, JSON, and HTML exports plus object storage write."""
    statement_service.distribution_engine.base_storage_path = tmp_path

    stmt = statement_service.generate_statement(
        period="2026-09",
        scope_code="BU-EXPORT",
        tenant_context=tenant_admin_context,
    )

    # Markdown
    md = statement_service.export_statement(
        stmt.statement_id, format=ExportFormat.MARKDOWN, tenant_context=tenant_admin_context
    )
    assert f"# {stmt.scope_name} — Cost Showback Statement" in md
    assert "SHOWBACK STATEMENT — FOR INTERNAL MANAGEMENT INFORMATION ONLY" in md
    assert "## 3. Shared-Service Apportionments (With Explicit Basis)" in md

    # CSV
    csv_text = statement_service.export_statement(
        stmt.statement_id, format=ExportFormat.CSV, tenant_context=tenant_admin_context
    )
    assert "Section,ItemKey,ItemName,Amount,Currency,BasisOrRule,Status" in csv_text
    assert "SharedApportionment" in csv_text

    # JSON
    json_text = statement_service.export_statement(
        stmt.statement_id, format=ExportFormat.JSON, tenant_context=tenant_admin_context
    )
    assert f'"{stmt.statement_id}"' in json_text

    # HTML
    html_text = statement_service.export_statement(
        stmt.statement_id, format=ExportFormat.HTML, tenant_context=tenant_admin_context
    )
    assert "<html><body><pre>" in html_text

    # Delivery to Storage & Email simulation
    dist_res = statement_service.distribute_statement(
        stmt.statement_id, channels=["OBJECT_STORAGE", "EMAIL"], tenant_context=tenant_admin_context
    )
    assert "storage_path_md" in dist_res
    assert "email_dispatch" in dist_res
    assert dist_res["email_dispatch"]["recipient_to"] == stmt.recipient_owner_email


# ==============================================================================
# 13. REST API Surface Integration via TestClient
# ==============================================================================


def test_rest_api_statement_lifecycle_and_endpoints(client: TestClient):
    """Full REST API integration test across all statement endpoints."""
    headers = {
        "X-Tenant-ID": "tenant-api-01",
        "X-User-ID": "usr-admin",
        "X-User-Roles": "GLOBAL_ADMIN,FINANCIAL_DETAIL",
    }

    # 1. Generate Statement
    gen_payload = {
        "period": "2026-09",
        "scope_type": "BUSINESS_UNIT",
        "scope_code": "BU-API",
        "scope_name": "API Integration Business Unit",
        "recipient_owner_id": "usr-api-owner",
        "recipient_owner_email": "api-owner@company.com",
        "target_currency": "USD",
        "custom_budget": 85000.0,
    }
    gen_res = client.post("/api/v1/statements/generate", json=gen_payload, headers=headers)
    assert gen_res.status_code == 201
    stmt_data = gen_res.json()
    statement_id = stmt_data["statement_id"]
    assert stmt_data["status"] == "DRAFT"

    # 2. List Statements
    list_res = client.get("/api/v1/statements?period=2026-09", headers=headers)
    assert list_res.status_code == 200
    assert list_res.json()["total_count"] >= 1

    # 3. Get Single Statement
    get_res = client.get(f"/api/v1/statements/{statement_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["statement_id"] == statement_id

    # 4. Circulate Statement
    circ_res = client.post(
        f"/api/v1/statements/{statement_id}/circulate",
        json={"review_window_days": 5},
        headers=headers,
    )
    assert circ_res.status_code == 200
    assert circ_res.json()["status"] == "IN_REVIEW"

    # 5. Finalise Statement
    fin_res = client.post(
        f"/api/v1/statements/{statement_id}/finalize",
        json={"notes": "Period close confirmed"},
        headers=headers,
    )
    assert fin_res.status_code == 200
    assert fin_res.json()["status"] == "FINALISED"

    # 6. Restatement Adjustment
    adj_payload = {
        "restatement_reason": "Correcting cross-account network egress allocation",
        "adjustment_deltas": [
            {
                "line_id": "net-egress-shared",
                "description": "Egress correction",
                "original_amount": 500.0,
                "adjustment_delta": -120.0,
                "reason": "Traffic attributed to central transit gateway instead",
            }
        ],
    }
    adj_res = client.post(
        f"/api/v1/statements/{statement_id}/adjust",
        json=adj_payload,
        headers=headers,
    )
    assert adj_res.status_code == 200
    adj_data = adj_res.json()
    new_stmt_id = adj_data["statement_id"]
    assert adj_data["version"] == 2
    assert adj_data["status"] == "ADJUSTED"

    # 7. Raise Dispute on Line
    disp_payload = {
        "line_id": "srv-k8s-platform",
        "line_description": "Shared Kubernetes Platform",
        "disputed_amount": 450.0,
        "proposed_amount": 200.0,
        "reason": "Non-production namespace included in production statement allocation",
    }
    disp_res = client.post(
        f"/api/v1/statements/{new_stmt_id}/disputes",
        json=disp_payload,
        headers=headers,
    )
    assert disp_res.status_code == 201
    dispute_id = disp_res.json()["dispute_id"]

    # 8. List Disputes
    list_disp_res = client.get(f"/api/v1/statements/{new_stmt_id}/disputes", headers=headers)
    assert list_disp_res.status_code == 200
    assert len(list_disp_res.json()) >= 1

    # 9. Resolve Dispute
    resolve_payload = {
        "decision": "APPROVED",
        "resolution_notes": "Agreed: Dev namespace moved to CC-INNOVATION",
        "target_reallocation_scope": "CC-INNOVATION",
    }
    res_disp_res = client.post(
        f"/api/v1/statements/{new_stmt_id}/disputes/{dispute_id}/resolve",
        json=resolve_payload,
        headers=headers,
    )
    assert res_disp_res.status_code == 200
    assert res_disp_res.json()["status"] == "RESOLVED_ACCEPTED"

    # 10. Accept Statement
    acc_res = client.post(
        f"/api/v1/statements/{new_stmt_id}/accept",
        json={"notes": "Accepted post-adjustment"},
        headers=headers,
    )
    assert acc_res.status_code == 200
    assert acc_res.json()["status"] == "ACCEPTED"

    # 11. Allocation Transparency Drill-Through
    trans_res = client.get(
        f"/api/v1/statements/{new_stmt_id}/lines/AWS/transparency",
        headers=headers,
    )
    assert trans_res.status_code == 200
    assert trans_res.json()["financial_detail_permitted"] is True
    assert len(trans_res.json()["charge_lines"]) >= 1

    # 12. Export Endpoint
    exp_res = client.get(
        f"/api/v1/statements/{new_stmt_id}/export?format=MARKDOWN",
        headers=headers,
    )
    assert exp_res.status_code == 200
    assert "text/markdown" in exp_res.headers["content-type"]

    # 13. Distribute Endpoint
    dist_res = client.post(
        f"/api/v1/statements/{new_stmt_id}/distribute",
        headers=headers,
    )
    assert dist_res.status_code == 200
    assert "email_dispatch" in dist_res.json()

    # 14. Outstanding Acceptance Report
    rep_res = client.get(
        "/api/v1/statements/reports/outstanding-acceptance?period=2026-09",
        headers=headers,
    )
    assert rep_res.status_code == 200
    assert rep_res.json()["period"] == "2026-09"

    # 15. Templates Catalogue
    tpl_res = client.get("/api/v1/statements/templates", headers=headers)
    assert tpl_res.status_code == 200
    assert len(tpl_res.json()) >= 3
