"""Comprehensive Acceptance Tests for Governance Mock Data Extension (Prompt 47B).

Validates:
- Quotas across all 4 simulator profiles exercising all headroom states (Warning, Normal, Critical/Lead Time, Not Supported, Manual).
- Provisioning requests in all workflow states, estimate accuracy tracking across 3 periods, emergency bypass, and unapproved deployment detection.
- Remediation tasks across all 11 states and false-resolved verification reopening.
- Showback statements across 3 BUs over 2 periods with dispute ($14,200), acceptance, unallocated ($6,500), and restatements.
- Approver inbox covering all request types, inaction escalation, and out-of-office delegation.
- Forward demo data: Commitments (Prompt 58), Budget Planning (Prompt 57), Analytical Extracts (Prompt 56), MDM Gaps & Imports (Prompts 45/53).
- Mandate M3 compliance: ScreenVerifier audits S-01 to S-27 with 100% meaningful data.
- REST API endpoint GET /api/v1/system/demo/screens/verify.
- All 11 named demo scenarios loadable in a single action.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.config.tenant_settings import TenantSettingsStore
from domain.demo.models import DemoScenario
from domain.demo.screen_verifier import ScreenVerifier
from domain.demo.service import DemoModeService
from domain.models.enums import (
    QuotaHeadroomState,
    TaskState,
    WorkflowRequestType,
)
from domain.remediation.service import get_remediation_service
from domain.synthetic.mock_generator import DeterministicMockEstateGenerator
from domain.tenant.context import TenantContext


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient instance."""
    return TestClient(app)


@pytest.fixture
def demo_service() -> DemoModeService:
    """Isolated DemoModeService instance with seed 42."""
    tenant_store = TenantSettingsStore()
    generator = DeterministicMockEstateGenerator(seed=42)
    return DemoModeService(tenant_store=tenant_store, generator=generator)


class TestGovernanceMockDataExtension:
    """Validates Prompt 47B acceptance criteria for governance mock data extension."""

    def test_quota_headroom_states_and_profiles(self, demo_service: DemoModeService):
        """Quotas across all 4 simulator profiles cover all headroom states including lead-time breach and manual."""
        tenant_id = "T-DEMO-QUOTA"
        demo_service.enable_demo_mode(
            tenant_id=tenant_id, scenario=DemoScenario.QUOTA_EXHAUSTION_APPROACHING
        )
        estate = demo_service.get_estate(tenant_id)
        assert estate is not None
        assert estate.governance is not None

        quotas = estate.governance.quotas
        assert len(quotas) >= 8

        # 4 simulator profiles represented
        providers = {
            q["provider"].value.upper()
            if hasattr(q["provider"], "value")
            else str(q["provider"]).upper()
            for q in quotas
        }
        assert {"AWS", "AZURE", "GCP", "OCI"}.issubset(providers)

        # Headroom states covered
        headroom_states = {q["status"] for q in quotas}
        assert QuotaHeadroomState.NORMAL in headroom_states
        assert QuotaHeadroomState.WARNING in headroom_states
        assert QuotaHeadroomState.CRITICAL in headroom_states
        assert QuotaHeadroomState.NOT_SUPPORTED in headroom_states

        # Not Supported profile has null limit
        not_supported = [q for q in quotas if q["status"] == QuotaHeadroomState.NOT_SUPPORTED]
        assert len(not_supported) >= 1
        assert not_supported[0]["limit_value"] is None

        # Critical profile has predicted exhaustion inside 14-day vendor lead time
        critical = [q for q in quotas if q["status"] == QuotaHeadroomState.CRITICAL]
        assert len(critical) >= 1
        assert critical[0]["predicted_exhaustion_date"] is not None
        assert critical[0]["lead_time_days"] == 14

        # Manual limit present with mandatory manual note
        manual_quotas = [q for q in quotas if q.get("is_manual") is True]
        assert len(manual_quotas) >= 1
        assert manual_quotas[0]["manual_source_note"] != ""

    def test_provisioning_requests_and_actual_tracking(self, demo_service: DemoModeService):
        """Provisioning requests exercise all workflow states, actual tracking, and unapproved deployments."""
        tenant_id = "T-DEMO-GATE"
        demo_service.enable_demo_mode(
            tenant_id=tenant_id, scenario=DemoScenario.PROVISIONING_GATE_DECISION
        )
        estate = demo_service.get_estate(tenant_id)
        assert estate is not None
        assert estate.governance is not None

        requests = estate.governance.provisioning_requests
        assert len(requests) >= 8

        # States covered
        states = {r["status"] for r in requests}
        assert "DRAFT" in states
        assert "SUBMITTED" in states
        assert "IN_REVIEW" in states
        assert "APPROVED" in states
        assert "REJECTED" in states
        assert "BYPASSED" in states
        assert "LINKED_TO_RESOURCE" in states

        # 1 Approved request linked to an inventoried resource with 3 periods of actual cost
        trackings = estate.governance.estimate_actual_trackings
        assert len(trackings) >= 1
        sample_tracking = trackings[0]
        assert len(sample_tracking["periods_tracked"]) == 3
        assert sample_tracking["latest_variance_pct"] is not None

        # 1 Emergency bypassed request with BypassRecord
        bypassed_reqs = [r for r in requests if r["status"] == "BYPASSED"]
        assert len(bypassed_reqs) >= 1
        assert bypassed_reqs[0]["bypass_details"] is not None

        # 1 Unapproved deployment in gated scope with finding
        findings = estate.governance.unapproved_findings
        assert len(findings) >= 1
        assert findings[0]["governance_exception_id"] != ""
        assert findings[0]["resource_id"] != ""

    def test_remediation_tasks_across_11_states(self, demo_service: DemoModeService):
        """Remediation tasks cover all 11 lifecycle states and various sources."""
        tenant_id = "T-DEMO-TASKS"
        demo_service.enable_demo_mode(
            tenant_id=tenant_id, scenario=DemoScenario.REMEDIATION_CLEANUP_SPRINT
        )
        estate = demo_service.get_estate(tenant_id)
        assert estate is not None
        assert estate.governance is not None

        tasks = estate.governance.remediation_tasks
        assert len(tasks) >= 11

        task_states = {t["state"] for t in tasks}
        expected_states = {
            TaskState.OPEN,
            TaskState.ASSIGNED,
            TaskState.IN_PROGRESS,
            TaskState.BLOCKED,
            TaskState.AWAITING_VERIFICATION,
            TaskState.RESOLVED,
            TaskState.VERIFIED,
            TaskState.CLOSED,
            TaskState.REJECTED,
            TaskState.DEFERRED,
            TaskState.DUPLICATE,
        }
        for st in expected_states:
            assert st in task_states or st.value in task_states

        # Closed tasks have closure code
        closed_tasks = [
            t for t in tasks if t["state"] in {TaskState.CLOSED, TaskState.CLOSED.value}
        ]
        assert len(closed_tasks) >= 1
        assert closed_tasks[0]["closure_code"] is not None

    def test_false_resolved_task_reopens_on_verification(self, demo_service: DemoModeService):
        """False-resolved task (task-demo-false-resolved) demonstrably reopens upon automated verification."""
        tenant_id = "T-DEMO-FALSE-RES"
        demo_service.enable_demo_mode(
            tenant_id=tenant_id, scenario=DemoScenario.REMEDIATION_CLEANUP_SPRINT
        )

        tc = TenantContext(tenant_id=tenant_id, user_id="system-verifier", roles=["SUPER_ADMIN"])
        rem_service = get_remediation_service()

        task = rem_service.get_task("task-demo-false-resolved", tenant_context=tc)
        assert task.state == TaskState.RESOLVED

        # Execute automated verification
        reopened_task, result = rem_service.verify_task(
            "task-demo-false-resolved", actor="system-verifier", tenant_context=tc
        )

        assert result.is_cleared is False
        assert reopened_task.state == TaskState.OPEN
        assert any("VERIFICATION_FAILED_REOPENED" in h.action for h in reopened_task.history)

    def test_showback_statements_multi_bu_and_disputes(self, demo_service: DemoModeService):
        """Showback statements cover 3 BUs over 2 periods, $14,200 dispute, $6,500 unallocated, and restatement v2."""
        tenant_id = "T-DEMO-STMT"
        demo_service.enable_demo_mode(tenant_id=tenant_id, scenario=DemoScenario.SHOWBACK_DISPUTE)
        estate = demo_service.get_estate(tenant_id)
        assert estate is not None
        assert estate.governance is not None

        statements = estate.governance.showback_statements
        assert len(statements) >= 3

        # Scopes covered: Retail, Commercial, Digital
        scope_codes = {s["scope_code"] for s in statements}
        assert {"BU-RETAIL", "BU-COMMERCIAL", "BU-DIGITAL"}.issubset(scope_codes)

        # Disputed line statement has $14,200 dispute
        disputes = estate.governance.statement_disputes
        assert len(disputes) >= 1
        dispute = disputes[0]
        assert Decimal(str(dispute["disputed_amount"])) == Decimal("14200.00")
        assert dispute["status"] == "IN_REVIEW"

        # Explicit unallocated cost present
        unallocated_stmts = [s for s in statements if Decimal(str(s["unallocated_cost"])) > 0]
        assert len(unallocated_stmts) >= 1
        assert Decimal(str(unallocated_stmts[0]["unallocated_cost"])) == Decimal("6500.00")

        # Restatement v2 present with retroactive adjustments
        adjustments = estate.governance.statement_adjustments
        assert len(adjustments) >= 1
        assert adjustments[0]["original_statement_id"] == "stmt-retail-2026-08"

    def test_approver_inbox_escalation_and_delegation(self, demo_service: DemoModeService):
        """Workflow approver inbox covers diverse request types, 1 escalated for inaction, 1 delegated."""
        tenant_id = "T-DEMO-WF"
        demo_service.enable_demo_mode(
            tenant_id=tenant_id, scenario=DemoScenario.PROVISIONING_GATE_DECISION
        )
        estate = demo_service.get_estate(tenant_id)
        assert estate is not None
        assert estate.governance is not None

        workflows = estate.governance.workflow_requests
        assert len(workflows) >= 8

        # Canonical types covered
        wf_types = {w["request_type"] for w in workflows}
        assert (
            WorkflowRequestType.BUDGET_APPROVAL.value in wf_types
            or WorkflowRequestType.BUDGET_APPROVAL in wf_types
        )
        assert (
            WorkflowRequestType.PROVISIONING_REQUEST.value in wf_types
            or WorkflowRequestType.PROVISIONING_REQUEST in wf_types
        )
        assert (
            WorkflowRequestType.POLICY_EXEMPTION.value in wf_types
            or WorkflowRequestType.POLICY_EXEMPTION in wf_types
        )

        # Escalation for inaction
        escalated = [w for w in workflows if w["id"] == "wf-req-escalated-08"]
        assert len(escalated) == 1
        assert escalated[0]["is_escalated"] is True

        # Out-of-office delegation
        delegated = [w for w in workflows if w["id"] == "wf-req-delegated-09"]
        assert len(delegated) == 1
        decision = delegated[0]["stages"][0]["decisions"][0]
        assert decision["on_behalf_of"] == "user-finops-admin@cloudlens.internal"

    def test_commitments_planning_and_extracts(self, demo_service: DemoModeService):
        """Forward demo data for Prompts 56, 57, 58 is populated."""
        tenant_id = "T-DEMO-FWD"
        demo_service.enable_demo_mode(tenant_id=tenant_id)
        estate = demo_service.get_estate(tenant_id)
        assert estate is not None
        gov = estate.governance
        assert gov is not None

        # Prompt 58 commitments
        assert len(gov.commitments) >= 4
        assert any(c.in_renewal_window for c in gov.commitments)
        assert any(c.is_over_committed for c in gov.commitments)

        # Prompt 57 budget planning
        assert gov.budget_planning is not None
        assert gov.budget_planning.top_down_target > Decimal("0")
        assert len(gov.budget_planning.submissions) >= 2

        # Prompt 56 analytical extracts
        assert len(gov.analytical_extract_runs) >= 4
        assert any(r.format == "PARQUET" for r in gov.analytical_extract_runs)

        # Prompts 45 & 53 MDM gaps and bulk import history
        assert len(gov.master_data_gaps) >= 3
        assert len(gov.import_jobs) >= 2

    def test_screen_verifier_all_27_screens_mandate_m3(self, demo_service: DemoModeService):
        """ScreenVerifier audits S-01 to S-27 ensuring 100% Mandate M3 compliance."""
        tenant_id = "T-DEMO-M3"
        demo_service.enable_demo_mode(tenant_id=tenant_id)
        estate = demo_service.get_estate(tenant_id)
        assert estate is not None

        verifier = ScreenVerifier()
        report = verifier.verify_all_screens(tenant_id=tenant_id, estate=estate)

        assert report.total_screens == 27
        assert report.passed_screens == 27
        assert report.failed_screens == 0
        assert report.is_m3_compliant is True

        screen_codes = [s.screen_code for s in report.screens]
        assert len(screen_codes) == 27
        for i in range(1, 28):
            expected_code = f"S-{i:02d}"
            assert expected_code in screen_codes

        for screen in report.screens:
            assert screen.has_meaningful_data is True
            assert screen.record_count > 0
            assert screen.highlight_metric != ""
            assert screen.sample_identifier != "N/A"

    def test_screens_verify_api_endpoint(self, client: TestClient):
        """GET /api/v1/system/demo/screens/verify returns 200 with full M3 compliance."""
        response = client.get("/api/v1/system/demo/screens/verify?tenant_id=T-DEMO-API")
        assert response.status_code == 200
        data = response.json()

        assert data["total_screens"] == 27
        assert data["passed_screens"] == 27
        assert data["failed_screens"] == 0
        assert data["is_m3_compliant"] is True
        assert len(data["screens"]) == 27

    def test_all_11_demo_scenarios_loadable(self, demo_service: DemoModeService):
        """All 11 named demo scenarios can be loaded via single action."""
        tenant_id = "T-DEMO-SCENARIOS"
        assert len(DemoScenario) == 11

        for sc in DemoScenario:
            info = demo_service.load_scenario(tenant_id=tenant_id, scenario=sc)
            assert info.scenario == sc
            assert info.title != ""
            status = demo_service.get_status(tenant_id)
            assert status.is_demo_mode is True
            assert status.active_scenario == str(sc)
