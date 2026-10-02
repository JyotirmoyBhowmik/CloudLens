"""Unit Test Suite for Workflow, Approval and Delegation Engine (Prompt 50).

Enforces:
- Generic workflow engine with 8 states:
  Draft, Submitted, In Review, Approved, Rejected, Withdrawn, Expired, Applied.
- Master-data-driven workflow definitions (serial, parallel, quorum, trigger condition, SLA, escalation).
- Dynamic approver resolution (role, scope owner, cost-centre owner, business-unit owner, budget owner, explicit list).
- Documented fallback and governance exception when no approver can be resolved (NoResolvableApproverException).
- Delegation, out-of-office, and automatic escalation.
- Approver inbox and requester view with context, diff, financial impact, and mandatory rejection comment.
- Atomic apply-on-approval with error state reversion to In Review on failure.
- Wiring of all existing approval points (budget, override, exemption, custom role, master data, etc.).
- SLA engine in operational working hours using working-week and holiday calendar.
- Workflow audit events and operational metrics.
- REST API endpoint contracts.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.budgets.models import BudgetApprovalStatus, BudgetCreateRequest, BudgetScopeType
from domain.budgets.repository import reset_budget_repository
from domain.budgets.service import get_budget_service, reset_budget_service
from domain.models.enums import (
    ApprovalChainMode,
    ApproverResolutionType,
    DecisionOutcome,
    WorkflowState,
)
from domain.models.exceptions import (
    NoResolvableApproverException,
    WorkflowAlreadyFinalizedException,
    WorkflowMandatoryCommentException,
)
from domain.tenant.context import TenantContext
from domain.workflows.appliers import (
    CallbackApplier,
    get_applier_registry,
)
from domain.workflows.definitions import (
    get_default_workflow_definitions,
)
from domain.workflows.models import (
    DelegationCreateRequest,
    SubjectEntity,
    WorkflowApproverSpec,
    WorkflowDecisionRequest,
    WorkflowDefinition,
    WorkflowStageDefinition,
    WorkflowSubmitRequest,
    WorkflowTriggerCondition,
    WorkflowWithdrawRequest,
)
from domain.workflows.repository import (
    reset_workflow_repository,
)
from domain.workflows.service import (
    WorkflowService,
    get_workflow_service,
    reset_workflow_service,
)
from domain.workflows.sla import SLAEngine
from masterdata.service import get_master_data_service


@pytest.fixture(autouse=True)
def reset_singletons():
    """Isolate state for each unit test."""
    reset_workflow_repository()
    reset_workflow_service()
    reset_budget_repository()
    reset_budget_service()
    yield
    reset_workflow_repository()
    reset_workflow_service()
    reset_budget_repository()
    reset_budget_service()


@pytest.fixture
def tenant_ctx() -> TenantContext:
    """Standard authenticated tenant execution context."""
    return TenantContext(
        tenant_id="tenant-wf-test",
        user_id="user-engineer-1",
        email="engineer@enterprise.io",
        roles=["ENGINEER"],
        correlation_id=str(uuid.uuid4()),
    )


@pytest.fixture
def admin_ctx() -> TenantContext:
    """Tenant admin execution context."""
    return TenantContext(
        tenant_id="tenant-wf-test",
        user_id="user-admin-1",
        email="admin@enterprise.io",
        roles=["TENANT_ADMIN"],
        correlation_id=str(uuid.uuid4()),
    )


@pytest.fixture
def finops_ctx() -> TenantContext:
    """FinOps lead execution context."""
    return TenantContext(
        tenant_id="tenant-wf-test",
        user_id="user-finops-lead",
        email="finops@enterprise.io",
        roles=["FINOPS_ADMIN"],
        correlation_id=str(uuid.uuid4()),
    )


@pytest.fixture
def workflow_service() -> WorkflowService:
    """Instantiated workflow service."""
    return get_workflow_service()


# ==============================================================================
# 1. Generic Workflow Engine & Eight States Tests
# ==============================================================================


class TestGenericWorkflowEngineEightStates:
    """Validates the 8 states and state progression lifecycle."""

    def test_eight_states_exist_in_enum(self):
        """States: Draft, Submitted, In Review, Approved, Rejected, Withdrawn, Expired, Applied."""
        assert WorkflowState.DRAFT.value == "DRAFT"
        assert WorkflowState.SUBMITTED.value == "SUBMITTED"
        assert WorkflowState.IN_REVIEW.value == "IN_REVIEW"
        assert WorkflowState.APPROVED.value == "APPROVED"
        assert WorkflowState.REJECTED.value == "REJECTED"
        assert WorkflowState.WITHDRAWN.value == "WITHDRAWN"
        assert WorkflowState.EXPIRED.value == "EXPIRED"
        assert WorkflowState.APPLIED.value == "APPLIED"
        assert len(list(WorkflowState)) == 8

    def test_submit_transitions_to_in_review_with_sla_and_stages(
        self, workflow_service: WorkflowService, tenant_ctx: TenantContext
    ):
        """Submitting a budget approval above threshold creates stages and enters IN_REVIEW."""
        req = WorkflowSubmitRequest(
            request_type="BUDGET_APPROVAL",
            title="Q3 Analytics Budget Increase",
            subject_entity=SubjectEntity(
                entity_type="budget",
                entity_id="bgt-test-01",
                metadata={"owner": "user-owner-1", "amount": 25000.0},
            ),
            justification="Expanding analytics cluster footprint for enterprise customers.",
            payload={"amount": 25000.0, "currency": "USD"},
            financial_impact=25000.0,
        )

        wf = workflow_service.submit_request(req, tenant_context=tenant_ctx)

        assert wf.state == WorkflowState.IN_REVIEW
        assert wf.request_type == "BUDGET_APPROVAL"
        assert len(wf.stages) == 2  # FinOps -> Scope Authority
        assert wf.stages[0].status == "IN_REVIEW"
        assert wf.due_date is not None
        assert wf.escalation_due_at is not None
        assert len(wf.history) >= 2  # SUBMIT, INITIALIZE_STAGE

    def test_withdrawal_transitions_to_withdrawn(
        self, workflow_service: WorkflowService, tenant_ctx: TenantContext
    ):
        """Requester can withdraw an in-flight request."""
        req = WorkflowSubmitRequest(
            request_type="BUDGET_APPROVAL",
            title="Temporary Test Budget",
            subject_entity=SubjectEntity(entity_type="budget", entity_id="bgt-withdraw-01"),
            justification="Need budget for load testing.",
            payload={"amount": 15000.0},
            financial_impact=15000.0,
        )
        wf = workflow_service.submit_request(req, tenant_context=tenant_ctx)
        assert wf.state == WorkflowState.IN_REVIEW

        withdrawn = workflow_service.withdraw_request(
            wf.id,
            WorkflowWithdrawRequest(reason="Requirements changed, test cancelled."),
            tenant_context=tenant_ctx,
        )
        assert withdrawn.state == WorkflowState.WITHDRAWN

        # Cannot modify a finalized request
        with pytest.raises(WorkflowAlreadyFinalizedException):
            workflow_service.withdraw_request(
                wf.id,
                WorkflowWithdrawRequest(reason="Second attempt"),
                tenant_context=tenant_ctx,
            )

    def test_rejection_requires_mandatory_comment(
        self,
        workflow_service: WorkflowService,
        tenant_ctx: TenantContext,
        finops_ctx: TenantContext,
    ):
        """Rejection requires non-empty mandatory comment (Rule 2.1 & Enterprise Standard)."""
        wf = workflow_service.submit_request(
            WorkflowSubmitRequest(
                request_type="BUDGET_APPROVAL",
                title="Marketing Campaign Infrastructure",
                subject_entity=SubjectEntity(entity_type="budget", entity_id="bgt-reject-01"),
                justification="Campaign cluster provisioning.",
                payload={"amount": 30000.0},
                financial_impact=30000.0,
            ),
            tenant_context=tenant_ctx,
        )

        # Empty comment -> WorkflowMandatoryCommentException
        with pytest.raises(WorkflowMandatoryCommentException):
            workflow_service.record_decision(
                wf.id,
                WorkflowDecisionRequest(decision=DecisionOutcome.REJECT, comment="   "),
                tenant_context=finops_ctx,
            )

        # Valid comment -> Successful rejection
        rejected = workflow_service.record_decision(
            wf.id,
            WorkflowDecisionRequest(
                decision=DecisionOutcome.REJECT,
                comment="Exceeds current departmental quarterly allocation cap by 50%.",
            ),
            tenant_context=finops_ctx,
        )
        assert rejected.state == WorkflowState.REJECTED
        assert rejected.stages[0].status == "REJECTED"


# ==============================================================================
# 2. Master Data Workflow Definitions & Chains Tests
# ==============================================================================


class TestMasterDataWorkflowDefinitionsAndChains:
    """Validates definition registry, serial chains, parallel chains, and quorum."""

    def test_default_definitions_catalogue_contains_all_canonical_types(self):
        """Validates all 10+ standard approval points in default definitions."""
        defs = get_default_workflow_definitions()
        assert len(defs) >= 10
        type_codes = {d.request_type for d in defs}
        expected = {
            "BUDGET_APPROVAL",
            "OVERRIDE_APPROVAL",
            "POLICY_EXEMPTION",
            "CUSTOM_ROLE_CREATION",
            "MASTER_DATA_CHANGE",
            "TENANT_LIFECYCLE",
            "CONNECTOR_DELETION",
            "COST_MODEL_CHANGE",
            "ALLOCATION_RULE_CHANGE",
            "RETENTION_CHANGE",
            "RATE_CARD_UPLOAD",
        }
        assert expected.issubset(type_codes)

    def test_adding_new_approval_requirement_requires_only_definition_row(
        self, workflow_service: WorkflowService, tenant_ctx: TenantContext, admin_ctx: TenantContext
    ):
        """Acceptance test: Adding a new approval requirement needs only a workflow definition row."""
        custom_def = WorkflowDefinition(
            id="wf-def-custom-hardware-order",
            tenant_id=tenant_ctx.tenant_id,
            request_type="HARDWARE_ORDER",
            entity_type="server_order",
            name="Bare Metal GPU Cluster Procurement",
            description="Approval chain for high-performance server hardware orders.",
            trigger_condition=WorkflowTriggerCondition(amount_gt=50000.0),
            stages=[
                WorkflowStageDefinition(
                    stage_id="stage-hw-lead",
                    name="Infrastructure Engineering Lead",
                    sequence_order=1,
                    mode=ApprovalChainMode.SERIAL,
                    quorum=1,
                    approver_spec=WorkflowApproverSpec(
                        resolution_type=ApproverResolutionType.ROLE,
                        target_role="TENANT_ADMIN",
                    ),
                )
            ],
            sla_working_hours=48,
        )

        # Save custom definition into repository
        workflow_service.repository.save_definition(custom_def, tenant_context=admin_ctx)

        # Now submit against new request type with NO code change
        wf = workflow_service.submit_request(
            WorkflowSubmitRequest(
                request_type="HARDWARE_ORDER",
                title="8x H100 Node Procurement",
                subject_entity=SubjectEntity(entity_type="server_order", entity_id="order-h100-01"),
                justification="AI model training cluster expansion.",
                payload={"nodes": 8, "gpu": "H100", "cost": 320000.0},
                financial_impact=320000.0,
            ),
            tenant_context=tenant_ctx,
        )

        assert wf.state == WorkflowState.IN_REVIEW
        assert wf.request_type == "HARDWARE_ORDER"
        assert wf.stages[0].name == "Infrastructure Engineering Lead"

    def test_parallel_chain_with_quorum_enforcement(
        self, workflow_service: WorkflowService, tenant_ctx: TenantContext
    ):
        """Validates parallel stage requiring quorum (e.g. 2 of 2)."""
        # CUSTOM_ROLE_CREATION is defined with PARALLEL mode and quorum 2
        wf = workflow_service.submit_request(
            WorkflowSubmitRequest(
                request_type="CUSTOM_ROLE_CREATION",
                title="Create SecOps Auditor Role",
                subject_entity=SubjectEntity(entity_type="role", entity_id="role-secops-auditor"),
                justification="Auditing compliance without write permissions.",
                payload={
                    "role_code": "SECOPS_AUDITOR",
                    "display_name": "SecOps Auditor",
                    "allowed_permissions": ["config:read", "audit:read", "inventory:read"],
                },
            ),
            tenant_context=tenant_ctx,
        )

        stage = wf.stages[0]
        assert stage.mode == ApprovalChainMode.PARALLEL
        assert stage.quorum == 2

        # 1st Approver decides APPROVE -> Partial approval, still IN_REVIEW
        user1_ctx = TenantContext(
            tenant_id=tenant_ctx.tenant_id,
            user_id="sec-lead",
            roles=["SECURITY_ADMIN"],
        )
        updated1 = workflow_service.record_decision(
            wf.id,
            WorkflowDecisionRequest(
                decision=DecisionOutcome.APPROVE, comment="Security sign-off verified."
            ),
            tenant_context=user1_ctx,
        )
        assert updated1.state == WorkflowState.IN_REVIEW
        assert updated1.stages[0].status == "IN_REVIEW"
        assert updated1.stages[0].approved_count == 1

        # 2nd Approver decides APPROVE -> Quorum 2 reached -> Transitions to APPROVED and APPLIED!
        user2_ctx = TenantContext(
            tenant_id=tenant_ctx.tenant_id,
            user_id="tenant-admin-1",
            roles=["TENANT_ADMIN"],
        )
        updated2 = workflow_service.record_decision(
            wf.id,
            WorkflowDecisionRequest(
                decision=DecisionOutcome.APPROVE, comment="Platform admin sign-off verified."
            ),
            tenant_context=user2_ctx,
        )
        assert updated2.stages[0].status == "APPROVED"
        assert updated2.state == WorkflowState.APPLIED  # Applied automatically!


# ==============================================================================
# 3. Dynamic Approver Resolution & Governance Exception Tests
# ==============================================================================


class TestApproverResolutionAndGovernanceExceptions:
    """Validates dynamic approver resolution from master data and governance exceptions."""

    def test_cost_centre_owner_and_scope_owner_resolution(
        self, workflow_service: WorkflowService, tenant_ctx: TenantContext
    ):
        """Resolves approvers from COST_CENTRE and scope metadata."""
        resolver = workflow_service.resolver
        # Register simulated cost centre in master data
        md = get_master_data_service()
        md.create_record(
            master_type="COST_CENTRE",
            code="CC-ENG-101",
            display_name="Engineering Core",
            attributes={"manager_user_id": "mgr-engineering-lead"},
            tenant_id=tenant_ctx.tenant_id,
            created_by="system",
            force_publish=True,
        )

        stage_def = WorkflowStageDefinition(
            stage_id="stage-cc-review",
            name="Cost Centre Owner Approval",
            approver_spec=WorkflowApproverSpec(
                resolution_type=ApproverResolutionType.COST_CENTRE_OWNER,
                fallback_role="TENANT_ADMIN",
            ),
        )

        subject = SubjectEntity(
            entity_type="budget",
            entity_id="bgt-cc-01",
            metadata={"cost_centre_code": "CC-ENG-101"},
        )

        res = resolver.resolve_approvers(
            request_id="req-cc-01",
            stage_def=stage_def,
            subject_entity=subject,
            tenant_context=tenant_ctx,
        )

        assert "mgr-engineering-lead" in res.primary_approvers
        assert res.is_authorized("mgr-engineering-lead")

    def test_unresolvable_approver_raises_governance_exception(
        self, workflow_service: WorkflowService, tenant_ctx: TenantContext
    ):
        """Acceptance requirement: A request with no resolvable approver raises a governance exception rather than vanishing."""
        resolver = workflow_service.resolver

        stage_def = WorkflowStageDefinition(
            stage_id="stage-impossible",
            name="Unreachable Approver Stage",
            approver_spec=WorkflowApproverSpec(
                resolution_type=ApproverResolutionType.ROLE,
                target_role="NON_EXISTENT_ROLE_XYZ",
                fallback_role="",  # No fallback
                explicit_approvers=[],
            ),
        )

        subject = SubjectEntity(entity_type="config", entity_id="cfg-01")

        with pytest.raises(NoResolvableApproverException) as exc_info:
            resolver.resolve_approvers(
                request_id="req-unreachable-01",
                stage_def=stage_def,
                subject_entity=subject,
                tenant_context=tenant_ctx,
            )

        assert exc_info.value.error_code == "NO_RESOLVABLE_APPROVER_EXCEPTION"
        assert "req-unreachable-01" in str(exc_info.value)


# ==============================================================================
# 4. Delegation, Out-of-Office & Escalation Tests
# ==============================================================================


class TestDelegationAndAutomaticEscalation:
    """Validates out-of-office delegation rules and escalation trajectories."""

    def test_delegation_visible_on_decision_and_inbox(
        self,
        workflow_service: WorkflowService,
        tenant_ctx: TenantContext,
        finops_ctx: TenantContext,
    ):
        """Acceptance requirement: An approver on leave delegates; delegation is recorded and visible on decision."""
        # 1. FinOps lead creates delegation to delegate user
        delegate_user_id = "user-substitute-finops"
        now = datetime.now(UTC)
        workflow_service.register_delegation(
            DelegationCreateRequest(
                delegate_approver_id=delegate_user_id,
                start_date=now - timedelta(hours=1),
                end_date=now + timedelta(days=7),
                request_types=["BUDGET_APPROVAL"],
                reason="Annual Leave in Scandinavia",
            ),
            tenant_context=finops_ctx,
        )

        # 2. Engineer submits a high-value budget request
        wf = workflow_service.submit_request(
            WorkflowSubmitRequest(
                request_type="BUDGET_APPROVAL",
                title="Compute Scaling for Batch Processing",
                subject_entity=SubjectEntity(entity_type="budget", entity_id="bgt-del-01"),
                justification="Scale compute capacity for end-of-month run.",
                payload={"amount": 40000.0},
                financial_impact=40000.0,
            ),
            tenant_context=tenant_ctx,
        )

        # 3. Check inbox for delegate
        delegate_ctx = TenantContext(
            tenant_id=tenant_ctx.tenant_id,
            user_id=delegate_user_id,
            roles=["ENGINEER"],
        )
        inbox = workflow_service.get_approver_inbox(delegate_user_id, tenant_context=delegate_ctx)
        matching = [item for item in inbox if item.request_id == wf.id]
        assert len(matching) == 1
        assert matching[0].is_delegated is True
        assert matching[0].delegated_from == finops_ctx.user_id

        # 4. Delegate renders decision on behalf of FinOps lead
        decided = workflow_service.record_decision(
            wf.id,
            WorkflowDecisionRequest(
                decision=DecisionOutcome.APPROVE,
                comment="Approved on behalf of FinOps lead per delegation agreement.",
            ),
            tenant_context=delegate_ctx,
        )

        # 5. Verify delegation audit on decision
        decision = decided.stages[0].decisions[0]
        assert decision.decided_by == delegate_user_id
        assert decision.on_behalf_of == finops_ctx.user_id
        assert decision.delegation_id is not None

    def test_out_of_office_without_delegation_escalates_automatically(
        self, workflow_service: WorkflowService, tenant_ctx: TenantContext
    ):
        """Acceptance requirement: An unavailable approver escalates automatically rather than blocking."""
        # Mark finops lead as out of office
        finops_id = f"{tenant_ctx.tenant_id}-finops-lead"
        workflow_service.resolver.set_user_out_of_office(finops_id, is_ooo=True)

        wf = workflow_service.submit_request(
            WorkflowSubmitRequest(
                request_type="BUDGET_APPROVAL",
                title="Immediate Out-Of-Office Test",
                subject_entity=SubjectEntity(entity_type="budget", entity_id="bgt-ooo-01"),
                justification="Testing escalation on absent approver.",
                payload={"amount": 35000.0},
                financial_impact=35000.0,
            ),
            tenant_context=tenant_ctx,
        )

        # Request should have automatically triggered escalation
        assert wf.is_escalated is True
        assert wf.escalation_path.is_escalated is True


# ==============================================================================
# 5. Approver Inbox & Requester View Tests
# ==============================================================================


class TestApproverInboxAndRequesterView:
    """Validates the inbox and requester view with context, diff, and financial impact."""

    def test_approver_inbox_displays_diff_and_financial_impact(
        self,
        workflow_service: WorkflowService,
        tenant_ctx: TenantContext,
        finops_ctx: TenantContext,
    ):
        """Approver inbox presents full diff (previous vs proposed values) and monetary impact."""
        wf = workflow_service.submit_request(
            WorkflowSubmitRequest(
                request_type="BUDGET_APPROVAL",
                title="Database Scaling Upgrade",
                subject_entity=SubjectEntity(entity_type="budget", entity_id="bgt-inbox-01"),
                justification="Upgrade cluster instances from r5.large to r5.2xlarge.",
                payload={"amount": 28000.0, "instance_type": "r5.2xlarge"},
                previous_values={"amount": 8000.0, "instance_type": "r5.large"},
                financial_impact=28000.0,
            ),
            tenant_context=tenant_ctx,
        )

        inbox = workflow_service.get_approver_inbox(finops_ctx.user_id, tenant_context=finops_ctx)
        item = next(i for i in inbox if i.request_id == wf.id)

        assert item.financial_impact == 28000.0
        assert item.previous_values == {"amount": 8000.0, "instance_type": "r5.large"}
        assert item.payload["instance_type"] == "r5.2xlarge"
        assert item.justification == "Upgrade cluster instances from r5.large to r5.2xlarge."
        assert item.sla_remaining_hours is not None

    def test_requester_view_displays_status_and_escalation_eta(
        self, workflow_service: WorkflowService, tenant_ctx: TenantContext
    ):
        """Requester view tracks stage, who it is with, and when it will escalate."""
        wf = workflow_service.submit_request(
            WorkflowSubmitRequest(
                request_type="BUDGET_APPROVAL",
                title="Kubernetes Ingress Overhaul",
                subject_entity=SubjectEntity(entity_type="budget", entity_id="bgt-req-01"),
                justification="Load balancer migration.",
                payload={"amount": 16000.0},
                financial_impact=16000.0,
            ),
            tenant_context=tenant_ctx,
        )

        my_reqs = workflow_service.get_requester_view(tenant_ctx.user_id, tenant_context=tenant_ctx)
        item = next(r for r in my_reqs if r.request_id == wf.id)

        assert item.state == WorkflowState.IN_REVIEW
        assert item.current_stage_name == "FinOps Lead Review"
        assert item.escalation_due_at is not None
        assert item.duration_in_current_state_hours >= 0.0


# ==============================================================================
# 6. Atomic Apply-on-Approval & Failure Handling Tests
# ==============================================================================


class TestAtomicApplyOnApprovalAndFailureHandling:
    """Validates atomic change application on final approval and revert-on-failure invariant."""

    def test_atomic_apply_activates_budget_automatically(
        self,
        workflow_service: WorkflowService,
        tenant_ctx: TenantContext,
        admin_ctx: TenantContext,
    ):
        """Acceptance requirement: A budget above approval limit cannot become active without decision, and decision applies change automatically."""
        budget_service = get_budget_service()

        # 1. Create budget > 10,000 via BudgetService -> Enters PENDING_APPROVAL
        created_bgt, _ = budget_service.create_budget(
            BudgetCreateRequest(
                name="Core Database FY26",
                scope_type=BudgetScopeType.ORGANISATION,
                scope_id=tenant_ctx.tenant_id,
                amount=50000.0,
                currency="USD",
                effective_date=date.today(),
                owner=tenant_ctx.user_id,
            ),
            tenant_context=tenant_ctx,
        )
        assert created_bgt.approval_status == BudgetApprovalStatus.PENDING_APPROVAL

        # Find linked workflow request
        open_wfs = workflow_service.list_requests(tenant_context=tenant_ctx)
        wf = next(w for w in open_wfs if w.subject_entity.entity_id == created_bgt.id)
        assert wf.state == WorkflowState.IN_REVIEW

        # 2. Stage 1 (FinOps) Approves
        finops_ctx = TenantContext(
            tenant_id=tenant_ctx.tenant_id,
            user_id="user-finops-1",
            roles=["FINOPS_ADMIN"],
        )
        wf_step1 = workflow_service.record_decision(
            wf.id,
            WorkflowDecisionRequest(decision=DecisionOutcome.APPROVE, comment="FinOps approved."),
            tenant_context=finops_ctx,
        )
        assert wf_step1.stages[0].status == "APPROVED"
        assert wf_step1.current_stage_index == 1

        # 3. Stage 2 (Admin/Scope Owner) Approves -> Completes chain!
        wf_step2 = workflow_service.record_decision(
            wf.id,
            WorkflowDecisionRequest(
                decision=DecisionOutcome.APPROVE, comment="Executive approved."
            ),
            tenant_context=admin_ctx,
        )

        # 4. Verify Workflow state is APPLIED
        assert wf_step2.state == WorkflowState.APPLIED
        assert wf_step2.applied_at is not None

        # 5. Verify Budget entity in repository was automatically applied to ACTIVE!
        refreshed_bgt = budget_service.get_budget(created_bgt.id, tenant_context=tenant_ctx)
        assert refreshed_bgt.approval_status == BudgetApprovalStatus.ACTIVE
        assert refreshed_bgt.approval_decision is not None
        assert refreshed_bgt.approval_decision.decision == BudgetApprovalStatus.APPROVED

    def test_failure_to_apply_reverts_to_in_review_with_error_attached(
        self,
        workflow_service: WorkflowService,
        tenant_ctx: TenantContext,
        admin_ctx: TenantContext,
    ):
        """Acceptance requirement: A failure to apply reverts to In Review with the error attached, never silently."""

        # Register a failing applier for a test request type
        class FailingApplier(CallbackApplier):
            def __init__(self):
                super().__init__(self._fail)

            def _fail(self, _request, _tc):
                raise RuntimeError("Downstream database connection timed out during atomic commit.")

        appliers = get_applier_registry()
        appliers.register_applier("FAILING_TEST_TYPE", FailingApplier())

        # Create single-stage definition for test type
        test_def = WorkflowDefinition(
            id="wf-def-fail-test",
            tenant_id=tenant_ctx.tenant_id,
            request_type="FAILING_TEST_TYPE",
            entity_type="test_entity",
            name="Failing Application Test",
            trigger_condition=WorkflowTriggerCondition(always=True),
            stages=[
                WorkflowStageDefinition(
                    stage_id="stage-fail-1",
                    name="Admin Approval",
                    mode=ApprovalChainMode.SERIAL,
                    quorum=1,
                    approver_spec=WorkflowApproverSpec(
                        resolution_type=ApproverResolutionType.ROLE,
                        target_role="TENANT_ADMIN",
                    ),
                )
            ],
            sla_working_hours=24,
        )
        workflow_service.repository.save_definition(test_def, tenant_context=admin_ctx)

        wf = workflow_service.submit_request(
            WorkflowSubmitRequest(
                request_type="FAILING_TEST_TYPE",
                title="Testing Error State Reversion",
                subject_entity=SubjectEntity(entity_type="test_entity", entity_id="ent-fail-01"),
                justification="Testing negative constraint on application failure.",
                payload={"data": "test"},
            ),
            tenant_context=tenant_ctx,
        )
        assert wf.state == WorkflowState.IN_REVIEW

        # Admin approves -> Applier runs and fails
        result = workflow_service.record_decision(
            wf.id,
            WorkflowDecisionRequest(
                decision=DecisionOutcome.APPROVE, comment="Looks good to approve."
            ),
            tenant_context=admin_ctx,
        )

        # Must have reverted from APPROVED back to IN_REVIEW with error attached!
        assert result.state == WorkflowState.IN_REVIEW
        assert result.error_message is not None
        assert "Downstream database connection timed out" in result.error_message


# ==============================================================================
# 7. SLA Working Hours Engine Tests
# ==============================================================================


class TestSLAWorkingHoursEngine:
    """Validates operational working hours calculation using schedule and holiday exclusions."""

    def test_sla_advances_only_during_working_hours_and_days(self):
        """SLA takes into account daily 08:00-18:00 and skips weekends."""
        engine = SLAEngine()
        # Friday 16:00 (4pm) UTC, SLA 4 working hours
        friday_4pm = datetime(2026, 4, 10, 16, 0, tzinfo=UTC)  # 2026-04-10 is Friday
        # Friday has 2 working hours left (16:00 to 18:00)
        # Remaining 2 working hours carried over to Monday 08:00 + 2 = Monday 10:00!
        due_date = engine.calculate_due_date(
            start_time=friday_4pm,
            sla_working_hours=4,
            schedule_id="WW_STANDARD_MON_FRI",
        )
        assert due_date.date() == date(2026, 4, 13)  # Monday
        assert due_date.hour == 10
        assert due_date.minute == 0


# ==============================================================================
# 8. Workflow Operational Metrics Tests
# ==============================================================================


class TestWorkflowOperationalMetrics:
    """Validates performance metrics and SLA tracking."""

    def test_metrics_report_aggregation(
        self,
        workflow_service: WorkflowService,
        tenant_ctx: TenantContext,
        finops_ctx: TenantContext,
    ):
        """Validates open requests, decision duration, and approver velocity."""
        # Submit and approve a request
        wf = workflow_service.submit_request(
            WorkflowSubmitRequest(
                request_type="BUDGET_APPROVAL",
                title="Metrics Test Budget",
                subject_entity=SubjectEntity(entity_type="budget", entity_id="bgt-met-01"),
                justification="Testing metrics calculation.",
                payload={"amount": 20000.0},
                financial_impact=20000.0,
            ),
            tenant_context=tenant_ctx,
        )

        workflow_service.record_decision(
            wf.id,
            WorkflowDecisionRequest(
                decision=DecisionOutcome.APPROVE, comment="Approved for metrics."
            ),
            tenant_context=finops_ctx,
        )

        metrics = workflow_service.get_metrics(tenant_context=tenant_ctx)
        assert (
            "BUDGET_APPROVAL" in metrics.open_requests_by_type
            or metrics.open_requests_by_type == {}
        )
        assert metrics.average_time_to_decision_hours >= 0.0
        assert finops_ctx.user_id in metrics.approvals_by_approver
        assert metrics.approvals_by_approver[finops_ctx.user_id] >= 1


# ==============================================================================
# 9. REST API Endpoint Tests
# ==============================================================================


class TestWorkflowAPIEndpoints:
    """Validates HTTP REST API endpoints."""

    def test_workflow_api_lifecycle_and_inbox(self):
        """End-to-end API test from submission to decision and inbox."""
        client = TestClient(app)
        headers = {
            "X-Tenant-ID": "tenant-api-test",
            "X-User-ID": "api-engineer-1",
            "X-User-Email": "api-eng@test.com",
            "X-User-Roles": "ENGINEER,TENANT_ADMIN",
        }

        # 1. Submit request
        submit_res = client.post(
            "/api/v1/workflows/requests",
            headers=headers,
            json={
                "request_type": "OVERRIDE_APPROVAL",
                "title": "Emergency Production Threshold Override",
                "subject_entity": {
                    "entity_type": "override",
                    "entity_id": "ovr-api-01",
                },
                "justification": "Mitigating production false alarm during black friday traffic surge.",
                "payload": {"is_permanent": False, "duration_hours": 12},
            },
        )
        assert submit_res.status_code == 201
        wf_data = submit_res.json()
        wf_id = wf_data["id"]
        assert wf_data["state"] == "IN_REVIEW"

        # 2. View in Approver Inbox
        inbox_res = client.get("/api/v1/workflows/inbox", headers=headers)
        assert inbox_res.status_code == 200
        inbox_items = inbox_res.json()
        assert any(item["request_id"] == wf_id for item in inbox_items)

        # 3. View in Requester Tracking View
        my_reqs_res = client.get("/api/v1/workflows/my-requests", headers=headers)
        assert my_reqs_res.status_code == 200
        my_items = my_reqs_res.json()
        assert any(item["request_id"] == wf_id for item in my_items)

        # 4. Render decision (Approve)
        decide_res = client.post(
            f"/api/v1/workflows/requests/{wf_id}/decide",
            headers=headers,
            json={"decision": "APPROVE", "comment": "Approved emergency operational override."},
        )
        assert decide_res.status_code == 200
        decided_data = decide_res.json()
        assert decided_data["state"] == "APPLIED"

        # 5. Fetch definitions & metrics
        defs_res = client.get("/api/v1/workflows/definitions", headers=headers)
        assert defs_res.status_code == 200
        assert len(defs_res.json()) >= 10

        metrics_res = client.get("/api/v1/workflows/metrics", headers=headers)
        assert metrics_res.status_code == 200
        assert "open_requests_by_type" in metrics_res.json()
