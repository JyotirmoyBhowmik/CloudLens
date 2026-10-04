"""Test Suite for Resource Lifecycle and Decommissioning (Prompt 59).

Tests:
- Full 10-state lifecycle state machine with configured transitions.
- Mandatory cross-team dependency impact check blocking approval if unacknowledged.
- Staged soak window with stopped-but-not-deleted surfacing ongoing storage cost.
- Cost-stop verification from actual billing catching lingering charges.
- Retention obligation check blocking deletion until satisfied by named officer.
- Orphan/residue detection with costed tasks.
- Decommissioning programme view with progress, projected, and realised savings.
- Read-only safety guard: CloudLens never touches provider delete APIs.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from domain.lifecycle.exceptions import (
    CostStopVerificationFailureException,
    InvalidLifecycleTransitionException,
    RetentionObligationUnsatisfiedException,
    UnacknowledgedDependencyException,
)
from domain.lifecycle.models import (
    LifecycleState,
    OrphanResourceType,
    RetentionObligation,
)
from domain.lifecycle.service import LifecycleService
from domain.models.enums import (
    TaskCategory,
    TaskPriority,
    WorkflowRequestType,
    WorkflowState,
)
from domain.remediation.service import RemediationService
from domain.tenant.context import TenantContext
from domain.workflows.service import WorkflowService


class TestLifecycleDecommissioningSuite:
    """Rigorous verification of Prompt 59 resource lifecycle and decommissioning."""

    @pytest.fixture
    def tenant_context(self) -> TenantContext:
        return TenantContext(
            tenant_id="tenant-lifecycle-corp",
            user_id="sre-lead@acme.corp",
            roles={"CLOUD_ADMIN", "FINOPS_ADMIN"},
        )

    @pytest.fixture
    def service(self) -> LifecycleService:
        return LifecycleService()

    @pytest.fixture
    def remediation_service(self) -> RemediationService:
        return RemediationService()

    @pytest.fixture
    def workflow_service(self) -> WorkflowService:
        return WorkflowService()

    def test_ten_state_lifecycle_transitions_and_illegal_rejections(
        self, service: LifecycleService, tenant_context: TenantContext
    ) -> None:
        """Configured permitted transitions succeed; illegal transitions are strictly rejected."""
        # 1. Register in REQUESTED state
        res = service.register_resource(
            resource_id="res-vm-001",
            tenant_id=tenant_context.tenant_id,
            owner_team="TEAM_CORE_BANKING",
            service_type="VIRTUAL_MACHINE",
            monthly_run_rate=Decimal("1200.00"),
            storage_cost_rate=Decimal("80.00"),
            initial_state=LifecycleState.REQUESTED,
        )

        # Illegal skip: REQUESTED -> DELETED must fail
        with pytest.raises(InvalidLifecycleTransitionException):
            service.transition_state("res-vm-001", LifecycleState.DELETED, "actor-admin")

        # Legal path: REQUESTED -> PROVISIONED -> ACTIVE -> IDLE_CANDIDATE
        service.transition_state("res-vm-001", LifecycleState.PROVISIONED, "actor-admin")
        assert res.current_state == LifecycleState.PROVISIONED

        service.transition_state("res-vm-001", LifecycleState.ACTIVE, "actor-admin")
        assert res.current_state == LifecycleState.ACTIVE

        service.transition_state("res-vm-001", LifecycleState.IDLE_CANDIDATE, "finops-scanner")
        assert res.current_state == LifecycleState.IDLE_CANDIDATE

    def test_mandatory_dependency_impact_check_blocks_approval_without_cross_team_acknowledgement(
        self, service: LifecycleService, tenant_context: TenantContext
    ) -> None:
        """A decommissioning proposal lists every dependent and requires acknowledgement from any dependent owned by another team."""
        res = service.register_resource(
            resource_id="res-db-customer",
            tenant_id=tenant_context.tenant_id,
            owner_team="TEAM_DATABASE",
            service_type="RELATIONAL_DATABASE",
            monthly_run_rate=Decimal("3500.00"),
            initial_state=LifecycleState.ACTIVE,
        )

        # Inbound dependency from a DIFFERENT team (TEAM_PAYMENTS depends on this DB)
        service.add_inbound_dependency(
            resource_id="res-db-customer",
            dependency_id="dep-pay-db",
            dependent_resource_id="res-pay-gateway",
            dependency_type="DATABASE_CALL",
            dependent_owner_team="TEAM_PAYMENTS",
            confidence=Decimal("0.98"),
        )

        # Propose decommissioning
        req = service.submit_decommissioning_request(
            resource_ids=["res-db-customer"],
            proposing_actor="db-lead@acme.corp",
            proposer_team="TEAM_DATABASE",
            justification="Database migration to serverless completed",
            intended_date=dt.datetime.now(dt.UTC) + dt.timedelta(days=14),
        )
        assert res.current_state == LifecycleState.DECOMMISSION_PROPOSED

        # Attempting approval while cross-team dependency is unacknowledged MUST FAIL
        with pytest.raises(UnacknowledgedDependencyException) as exc_info:
            service.approve_decommissioning_request(req.request_id, approver_id="cloud-lead@acme.corp")
        assert "TEAM_PAYMENTS" in str(exc_info.value)
        assert res.current_state == LifecycleState.DECOMMISSION_PROPOSED

        # Explicit cross-team owner sign-off
        service.acknowledge_dependency(
            resource_id="res-db-customer",
            dependency_id="dep-pay-db",
            acknowledged_by="payments-owner@acme.corp",
        )

        # Now approval succeeds
        service.approve_decommissioning_request(req.request_id, approver_id="cloud-lead@acme.corp")
        assert res.current_state == LifecycleState.DECOMMISSION_APPROVED
        assert req.is_approved is True

    def test_staged_soak_window_and_surfacing_stopped_resources(
        self, service: LifecycleService, tenant_context: TenantContext
    ) -> None:
        """A resource stopped and never deleted is surfaced with its ongoing cost."""
        now = dt.datetime.now(dt.UTC)
        res = service.register_resource(
            resource_id="res-cluster-abandoned",
            tenant_id=tenant_context.tenant_id,
            owner_team="TEAM_ANALYTICS",
            service_type="KUBERNETES_CLUSTER",
            monthly_run_rate=Decimal("5000.00"),
            storage_cost_rate=Decimal("450.00"), # Lingering EBS storage charges
            initial_state=LifecycleState.DECOMMISSION_APPROVED,
        )

        # Transition to STOPPED 20 days ago (past the 14-day soak window)
        res.stopped_at = now - dt.timedelta(days=20)
        res.current_state = LifecycleState.STOPPED

        surfaced = service.surface_stopped_resources(
            tenant_id=tenant_context.tenant_id,
            max_soak_days=14,
            as_of=now,
        )

        assert len(surfaced) == 1
        assert surfaced[0].resource_id == "res-cluster-abandoned"
        assert surfaced[0].days_in_stopped_state >= 20
        assert surfaced[0].ongoing_storage_cost == Decimal("450.00")

    def test_cost_stop_verification_from_actual_billing(
        self, service: LifecycleService, tenant_context: TenantContext
    ) -> None:
        """A resource deleted but still incurring cost raises an exception."""
        res = service.register_resource(
            resource_id="res-zombie-vm",
            tenant_id=tenant_context.tenant_id,
            owner_team="TEAM_LEGACY",
            service_type="VIRTUAL_MACHINE",
            monthly_run_rate=Decimal("800.00"),
            initial_state=LifecycleState.DELETED,
        )

        # If billing continues after deletion date, raise exception
        with pytest.raises(CostStopVerificationFailureException) as exc_info:
            service.verify_cost_stop(
                resource_id="res-zombie-vm",
                post_deletion_billing_amount=Decimal("125.50"),
            )
        assert "$125.50" in str(exc_info.value)
        assert res.current_state == LifecycleState.DELETED

        # When billing has ceased ($0.00), resource transitions to RETIRED
        service.verify_cost_stop(
            resource_id="res-zombie-vm",
            post_deletion_billing_amount=Decimal("0.00"),
        )
        assert res.current_state == LifecycleState.RETIRED

    def test_retention_obligation_blocks_deletion_until_confirmed_satisfied(
        self, service: LifecycleService, tenant_context: TenantContext
    ) -> None:
        """A resource with an unsatisfied retention obligation cannot proceed to deletion."""
        now = dt.datetime.now(dt.UTC)
        obligation = RetentionObligation(
            retention_basis="SEC-Rule-17a-4 / Financial Records",
            mandatory_until=now + dt.timedelta(days=365),
            is_satisfied=False,
        )

        res = service.register_resource(
            resource_id="res-storage-sec-archive",
            tenant_id=tenant_context.tenant_id,
            owner_team="TEAM_COMPLIANCE",
            service_type="OBJECT_STORAGE",
            initial_state=LifecycleState.STOPPED,
            retention_obligation=obligation,
        )

        # Transitioning to PENDING_DELETION while obligation is unsatisfied MUST FAIL
        with pytest.raises(RetentionObligationUnsatisfiedException) as exc_info:
            service.transition_state("res-storage-sec-archive", LifecycleState.PENDING_DELETION, "sre-lead")
        assert "SEC-Rule-17a-4" in str(exc_info.value)

        # Named compliance officer signs off
        service.satisfy_retention_obligation(
            resource_id="res-storage-sec-archive",
            compliance_officer_id="officer-sarah@acme.corp",
            notes="Data exported to cold WORM archive in compliance with statutory policy.",
        )

        # Now deletion proceeds cleanly
        service.transition_state("res-storage-sec-archive", LifecycleState.PENDING_DELETION, "sre-lead")
        assert res.current_state == LifecycleState.PENDING_DELETION

        service.transition_state("res-storage-sec-archive", LifecycleState.DELETED, "sre-lead")
        assert res.current_state == LifecycleState.DELETED

    def test_orphan_and_residue_detection(
        self, service: LifecycleService, tenant_context: TenantContext
    ) -> None:
        """Detects orphaned residue left behind after incomplete decommission."""
        candidates = [
            {
                "resource_id": "vol-orphan-001",
                "residue_type": "UNATTACHED_DISK",
                "associated_scope": "BU_RETAIL",
                "monthly_waste_cost": Decimal("180.00"),
            },
            {
                "resource_id": "eip-unused-002",
                "residue_type": "UNUSED_IP_ADDRESS",
                "associated_scope": "BU_WEALTH",
                "monthly_waste_cost": Decimal("36.50"),
            },
        ]

        detected = service.detect_orphan_residue(tenant_context.tenant_id, candidates)
        assert len(detected) == 2
        assert detected[0].residue_type == OrphanResourceType.UNATTACHED_DISK
        assert detected[0].monthly_waste_cost == Decimal("180.00")
        assert detected[1].residue_type == OrphanResourceType.UNUSED_IP_ADDRESS

    def test_realised_saving_credited_from_actuals_never_estimate(
        self, service: LifecycleService, tenant_context: TenantContext
    ) -> None:
        """Completed decommissioning credits a verified saving computed from billing, not from estimate."""
        res = service.register_resource(
            resource_id="res-monolith-01",
            tenant_id=tenant_context.tenant_id,
            owner_team="TEAM_LEGACY",
            service_type="COMPUTE",
            monthly_run_rate=Decimal("10000.00"),
            initial_state=LifecycleState.DELETED,
        )

        # Actual billing month before was $9,850.00. Month after is $120.00
        realised = service.credit_realised_saving(
            resource_id="res-monolith-01",
            actual_billing_before=Decimal("9850.00"),
            actual_billing_after=Decimal("120.00"),
            tenant_context=tenant_context,
        )
        assert realised == Decimal("9730.00")
        assert realised != res.monthly_run_rate  # Based on actuals ($9,730.00), not estimate ($10,000.00)

    def test_decommissioning_programme_view(
        self, service: LifecycleService, tenant_context: TenantContext
    ) -> None:
        """Decommissioning programme view aggregates multiple resources."""
        service.register_resource(
            resource_id="r1",
            tenant_id=tenant_context.tenant_id,
            owner_team="TEAM_A",
            service_type="COMPUTE",
            monthly_run_rate=Decimal("2000.00"),
            initial_state=LifecycleState.DELETED,
        )
        service.register_resource(
            resource_id="r2",
            tenant_id=tenant_context.tenant_id,
            owner_team="TEAM_A",
            service_type="DATABASE",
            monthly_run_rate=Decimal("4000.00"),
            initial_state=LifecycleState.ACTIVE,
        )

        prog = service.create_programme(
            tenant_context=tenant_context,
            name="DC Exit 2027",
            description="Complete retirement of on-prem mirrored resources",
            target_completion_date=dt.datetime.now(dt.UTC) + dt.timedelta(days=90),
            resource_ids=["r1", "r2"],
        )

        view = service.get_programme_view(prog.programme_id)
        assert view.total_resources == 2
        assert view.projected_monthly_savings == Decimal("6000.00")
        assert view.realised_monthly_savings == Decimal("2000.00")
        assert view.state_breakdown["DELETED"] == 1
        assert view.state_breakdown["ACTIVE"] == 1

    def test_decommissioning_request_routed_through_workflow_engine(
        self,
        service: LifecycleService,
        tenant_context: TenantContext,
        workflow_service: WorkflowService,
    ) -> None:
        """Decommissioning request is routed through Prompt 50 workflow engine with resources and savings."""
        r1 = service.register_resource(
            resource_id="res-wf-app-01",
            tenant_id=tenant_context.tenant_id,
            owner_team="TEAM_FINANCE",
            service_type="VIRTUAL_MACHINE",
            monthly_run_rate=Decimal("1500.00"),
            initial_state=LifecycleState.ACTIVE,
        )
        r2 = service.register_resource(
            resource_id="res-wf-db-02",
            tenant_id=tenant_context.tenant_id,
            owner_team="TEAM_FINANCE",
            service_type="RELATIONAL_DATABASE",
            monthly_run_rate=Decimal("3500.00"),
            initial_state=LifecycleState.ACTIVE,
        )

        req = service.submit_decommissioning_request(
            resource_ids=["res-wf-app-01", "res-wf-db-02"],
            proposing_actor="finance-dev@acme.corp",
            proposer_team="TEAM_FINANCE",
            justification="Quarterly cleanup of superseded ledger reporting cluster",
            intended_date=dt.datetime.now(dt.UTC) + dt.timedelta(days=14),
            workflow_service=workflow_service,
            tenant_context=tenant_context,
        )

        assert req.workflow_request_id is not None
        assert req.estimated_monthly_saving == Decimal("5000.00")
        assert r1.current_state == LifecycleState.DECOMMISSION_PROPOSED
        assert r2.current_state == LifecycleState.DECOMMISSION_PROPOSED

        # Verify WorkflowRequest in Prompt 50 engine
        wf_req = workflow_service.repository.get(
            req.workflow_request_id, tenant_context=tenant_context
        )
        assert wf_req is not None
        assert wf_req.state == WorkflowState.IN_REVIEW
        assert wf_req.financial_impact == 5000.0
        assert wf_req.request_type == WorkflowRequestType.DECOMMISSIONING_REQUEST.value
        assert "Decommissioning Request" in wf_req.title

    def test_cost_stop_verification_failure_creates_remediation_task_and_raises_exception(
        self,
        service: LifecycleService,
        tenant_context: TenantContext,
        remediation_service: RemediationService,
    ) -> None:
        """When cost continues post deletion, cost-stop verification creates an assigned task and raises exception."""
        res = service.register_resource(
            resource_id="res-lingering-storage",
            tenant_id=tenant_context.tenant_id,
            owner_team="TEAM_INFRA",
            service_type="OBJECT_STORAGE",
            monthly_run_rate=Decimal("600.00"),
            initial_state=LifecycleState.DELETED,
        )

        with pytest.raises(CostStopVerificationFailureException) as exc_info:
            service.verify_cost_stop(
                resource_id="res-lingering-storage",
                post_deletion_billing_amount=Decimal("320.00"),
                remediation_service=remediation_service,
                tenant_context=tenant_context,
            )
        assert "$320.00" in str(exc_info.value)
        assert res.cost_stop_task_id is not None

        # Verify assigned task in RemediationService
        task = remediation_service.repository.get(
            res.cost_stop_task_id, tenant_context=tenant_context
        )
        assert task is not None
        assert task.assignee_id == "TEAM_INFRA"
        assert task.estimated_saving == 320.0
        assert task.category == TaskCategory.RECONCILIATION_VARIANCE
        assert "Cost-Stop Verification Failure" in task.title

    def test_orphan_residue_detection_creates_costed_remediation_tasks(
        self,
        service: LifecycleService,
        tenant_context: TenantContext,
        remediation_service: RemediationService,
    ) -> None:
        """Detected orphaned residue items generate costed tasks in Prompt 51 engine."""
        candidates = [
            {
                "resource_id": "vol-orphan-ebs",
                "residue_type": "UNATTACHED_DISK",
                "associated_scope": "BU_RETAIL",
                "monthly_waste_cost": Decimal("240.00"),
                "owner_id": "storage-lead@acme.corp",
            },
            {
                "resource_id": "snap-sourceless-001",
                "residue_type": "ORPHAN_SNAPSHOT",
                "associated_scope": "BU_WEALTH",
                "monthly_waste_cost": Decimal("75.00"),
                "owner_id": "backup-admin@acme.corp",
            },
        ]

        items = service.detect_orphan_residue(
            tenant_id=tenant_context.tenant_id,
            residue_candidates=candidates,
            remediation_service=remediation_service,
            tenant_context=tenant_context,
        )

        assert len(items) == 2
        assert items[0].task_created_id is not None
        assert items[1].task_created_id is not None

        # Verify task 1 in remediation repository
        task1 = remediation_service.repository.get(
            items[0].task_created_id, tenant_context=tenant_context
        )
        assert task1 is not None
        assert task1.estimated_saving == 240.0
        assert task1.priority == TaskPriority.HIGH
        assert task1.category == TaskCategory.IDLE_RESOURCE

        # Verify task 2 in remediation repository
        task2 = remediation_service.repository.get(
            items[1].task_created_id, tenant_context=tenant_context
        )
        assert task2 is not None
        assert task2.estimated_saving == 75.0

    def test_realised_saving_credited_into_prompt_51_ledger(
        self,
        service: LifecycleService,
        tenant_context: TenantContext,
        remediation_service: RemediationService,
    ) -> None:
        """Decommissioning records verified saving into Prompt 51 realised-saving ledger from actuals."""
        service.register_resource(
            resource_id="res-bigdata-spark",
            tenant_id=tenant_context.tenant_id,
            owner_team="TEAM_DATA_PLATFORM",
            service_type="BIG_DATA_CLUSTER",
            monthly_run_rate=Decimal("12000.00"),
            initial_state=LifecycleState.DELETED,
        )

        # Before = $11,800.00, After = $0.00
        realised = service.credit_realised_saving(
            resource_id="res-bigdata-spark",
            actual_billing_before=Decimal("11800.00"),
            actual_billing_after=Decimal("0.00"),
            tenant_context=tenant_context,
            remediation_service=remediation_service,
        )
        assert realised == Decimal("11800.00")

        # Verify entry in RealisedSavingLedger
        report = remediation_service.ledger.get_savings_report(tenant_context=tenant_context)
        assert report.total_realised_saving == 11800.0
        assert "TEAM_DATA_PLATFORM" in report.savings_by_team
        assert report.savings_by_team["TEAM_DATA_PLATFORM"] == 11800.0

    def test_master_data_lifecycle_state_model_introspection(
        self, service: LifecycleService
    ) -> None:
        """Full 10-state lifecycle model exposes permitted transitions and configured evidence gates."""
        model = service.get_lifecycle_state_model()
        assert len(model["states"]) == 10
        assert "REQUESTED" in model["states"]
        assert "ACTIVE" in model["states"]
        assert "DECOMMISSION_PROPOSED" in model["states"]
        assert "DECOMMISSION_APPROVED" in model["states"]
        assert "STOPPED" in model["states"]
        assert "PENDING_DELETION" in model["states"]
        assert "DELETED" in model["states"]
        assert "RETIRED" in model["states"]

        assert "DECOMMISSION_APPROVED" in model["evidence_requirements"]
        assert "cross-team dependency" in model["evidence_requirements"]["DECOMMISSION_APPROVED"].lower()

    def test_dependency_provenance_and_confidence(
        self, service: LifecycleService, tenant_context: TenantContext
    ) -> None:
        """Inbound dependencies retain provenance source and confidence metrics."""
        service.register_resource(
            resource_id="res-app-svc",
            tenant_id=tenant_context.tenant_id,
            owner_team="TEAM_APP",
            service_type="CONTAINER_SERVICE",
            monthly_run_rate=Decimal("800.00"),
        )
        dep = service.add_inbound_dependency(
            resource_id="res-app-svc",
            dependency_id="dep-api-gateway",
            dependent_resource_id="res-gw-ingress",
            dependency_type="NETWORK_FLOW",
            dependent_owner_team="TEAM_NETWORKING",
            confidence=Decimal("0.95"),
            provenance="PROMPT_32_FLOW_LOGS",
        )
        assert dep.provenance == "PROMPT_32_FLOW_LOGS"
        assert dep.confidence == Decimal("0.95")
        assert dep.is_cross_team is True
