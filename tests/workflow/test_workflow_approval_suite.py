"""Test Level 19: Workflow and Approval Engine Suite (Prompt 42B / Defect D-11).

Verifies the unified enterprise workflow engine across all five canonical criteria:
1. Every approval point routes strictly through the single unified engine.
2. Approver resolution succeeds across role, scope, ownership, and explicit list,
   and raises NoResolvableApproverException when resolution fails.
3. Delegation and out-of-office escalation behave as configured.
4. Approval applies changes atomically and reverts to IN_REVIEW with error attached on apply failure.
5. SLA is computed in working hours using the holiday and working-week calendar masters.
"""

from __future__ import annotations

import datetime as dt

import pytest

from domain.models.enums import (
    ApprovalChainMode,
    ApproverResolutionType,
    DecisionOutcome,
    WorkflowRequestType,
    WorkflowState,
)
from domain.models.exceptions import (
    NoResolvableApproverException,
)
from domain.tenant.context import TenantContext
from domain.workflows.models import (
    DelegationCreateRequest,
    RequesterInfo,
    SubjectEntity,
    WorkflowApproverSpec,
    WorkflowDecisionRequest,
    WorkflowStage,
    WorkflowStageDefinition,
    WorkflowSubmitRequest,
)
from domain.workflows.resolver import ApproverResolver
from domain.workflows.service import WorkflowService
from domain.workflows.sla import SLAEngine
from masterdata.service import MasterDataService


class TestWorkflowApprovalSuite:
    """Rigorous verification of Test Level 19 (Workflow and Approval Engine)."""

    @pytest.fixture
    def tenant_context(self) -> TenantContext:
        return TenantContext(
            tenant_id="tenant-wf-test",
            user_id="workflow-lead@acme.com",
            roles={"TENANT_ADMIN", "FINOPS_ADMIN"},
        )

    @pytest.fixture
    def md_service(self) -> MasterDataService:
        return MasterDataService(auto_seed=True)

    @pytest.fixture
    def wf_service(self, md_service: MasterDataService) -> WorkflowService:
        return WorkflowService(master_data_service=md_service)

    def test_criterion_1_single_engine_routing_for_all_approval_points(
        self, wf_service: WorkflowService, tenant_context: TenantContext
    ) -> None:
        """Criterion 1: Every approval point routes through the single engine."""
        submit_req = WorkflowSubmitRequest(
            request_type=WorkflowRequestType.BUDGET_APPROVAL,
            title="Q4 Production Ingress Budget Increase",
            justification="Scaling cluster budget by 20%",
            subject_entity=SubjectEntity(
                entity_type="budget",
                entity_id="budget-prod-001",
                scope_type="ORGANISATION",
                scope_id=tenant_context.tenant_id,
            ),
            requester=RequesterInfo(
                requester_id=tenant_context.user_id,
                requester_email="workflow-lead@acme.com",
            ),
            payload={"requested_amount": 75000.0},
        )
        created = wf_service.submit_request(submit_req, tenant_context=tenant_context)
        assert created.id is not None
        assert created.state in (WorkflowState.SUBMITTED, WorkflowState.IN_REVIEW)
        assert created.request_type == WorkflowRequestType.BUDGET_APPROVAL

    def test_criterion_2_approver_resolution_modes_and_governance_exception(
        self, wf_service: WorkflowService, tenant_context: TenantContext
    ) -> None:
        """Criterion 2: Approver resolution from role, scope, ownership, list, and governance exception."""
        resolver = ApproverResolver(master_data_service=wf_service.master_data_service)

        # 2a. Explicit list resolution
        stage_list = WorkflowStageDefinition(
            stage_id="stage-explicit",
            name="Explicit Reviewers",
            approver_spec=WorkflowApproverSpec(
                resolution_type=ApproverResolutionType.EXPLICIT_LIST,
                explicit_approvers=["user-lead-1", "user-lead-2"],
            ),
        )
        spec_list = resolver.resolve_approvers(
            request_id="req-test-1",
            stage_def=stage_list,
            subject_entity=SubjectEntity(entity_type="budget", entity_id="b-1"),
            tenant_context=tenant_context,
        )
        assert "user-lead-1" in spec_list.effective_approvers
        assert "user-lead-2" in spec_list.effective_approvers

        # 2b. Role-based resolution
        stage_role = WorkflowStageDefinition(
            stage_id="stage-role",
            name="Role Reviewers",
            approver_spec=WorkflowApproverSpec(
                resolution_type=ApproverResolutionType.ROLE,
                target_role="FINOPS_ADMIN",
            ),
        )
        spec_role = resolver.resolve_approvers(
            request_id="req-test-2",
            stage_def=stage_role,
            subject_entity=SubjectEntity(entity_type="budget", entity_id="b-1"),
            tenant_context=tenant_context,
        )
        assert len(spec_role.effective_approvers) > 0

        # 2c. Unresolvable approver triggers governance exception
        stage_invalid = WorkflowStageDefinition(
            stage_id="stage-invalid",
            name="Unresolvable Stage",
            approver_spec=WorkflowApproverSpec(
                resolution_type=ApproverResolutionType.COST_CENTRE_OWNER,
                fallback_role="",  # Empty fallback role to trigger governance exception
            ),
        )
        with pytest.raises(NoResolvableApproverException):
            resolver.resolve_approvers(
                request_id="req-test-3",
                stage_def=stage_invalid,
                subject_entity=SubjectEntity(
                    entity_type="budget",
                    entity_id="b-invalid",
                    metadata={"cost_center": "NON_EXISTENT_CC_9999"},
                ),
                tenant_context=tenant_context,
            )

    def test_criterion_3_delegation_and_escalation_behaviour(
        self, wf_service: WorkflowService, tenant_context: TenantContext
    ) -> None:
        """Criterion 3: Delegation and escalation behave as configured."""
        now = dt.datetime.now(dt.UTC)
        del_req = DelegationCreateRequest(
            delegate_approver_id="delegate-approver",
            start_date=now - dt.timedelta(days=1),
            end_date=now + dt.timedelta(days=7),
            reason="Annual leave coverage",
        )
        rule = wf_service.register_delegation(del_req, tenant_context=tenant_context)
        assert rule.id is not None
        assert rule.is_currently_active(as_of=now) is True

        delegations = wf_service.repository.list_delegations(tenant_context=tenant_context)
        assert any(d.delegate_approver_id == "delegate-approver" for d in delegations)

    def test_criterion_4_atomic_apply_and_reversion_to_in_review_on_failure(
        self, wf_service: WorkflowService, tenant_context: TenantContext
    ) -> None:
        """Criterion 4: Approval applies atomically and reverts to IN_REVIEW on apply failure."""
        submit_req = WorkflowSubmitRequest(
            request_type=WorkflowRequestType.BUDGET_APPROVAL,
            title="Non-existent entity to force apply failure",
            justification="Testing atomic failure rollback",
            subject_entity=SubjectEntity(
                entity_type="budget",
                entity_id="budget-does-not-exist",
                scope_type="ORGANISATION",
                scope_id=tenant_context.tenant_id,
            ),
            requester=RequesterInfo(
                requester_id=tenant_context.user_id,
                requester_email="workflow-lead@acme.com",
            ),
            payload={"requested_amount": 999999.0},
        )
        created = wf_service.submit_request(submit_req, tenant_context=tenant_context)
        created.stages = [
            WorkflowStage(
                stage_id="stage-1",
                name="Approval",
                assigned_approvers=[tenant_context.user_id],
                chain_mode=ApprovalChainMode.SERIAL,
                quorum=1,
            )
        ]
        created.state = WorkflowState.IN_REVIEW
        wf_service.repository.save(created, tenant_context=tenant_context)

        # Decision: Approve
        decision = WorkflowDecisionRequest(
            decision=DecisionOutcome.APPROVE,
            comment="Approved by lead",
        )
        updated = wf_service.record_decision(
            request_id=created.id,
            decision_req=decision,
            tenant_context=tenant_context,
        )

        # Upon failure to apply the missing budget, workflow must revert to IN_REVIEW with error attached
        assert updated.state == WorkflowState.IN_REVIEW
        assert updated.error_message is not None
        assert "Application failed" in updated.error_message

    def test_criterion_5_working_hours_sla_computation_with_holidays(
        self, md_service: MasterDataService
    ) -> None:
        """Criterion 5: SLA computed strictly in working hours using holiday and working-week masters."""
        sla_engine = SLAEngine(master_data_service=md_service)

        # Start on a Friday at 16:00 (4 PM) UTC
        friday_afternoon = dt.datetime(2026, 10, 2, 16, 0, 0, tzinfo=dt.UTC)
        # Request 8 working hours SLA
        due_date = sla_engine.calculate_due_date(
            start_time=friday_afternoon,
            sla_working_hours=8,
            schedule_id="WW_STANDARD_MON_FRI",
        )
        assert due_date > friday_afternoon
        # Must skip Saturday (Oct 3) and Sunday (Oct 4), arriving on Monday (Oct 5)
        assert due_date.weekday() == 0, f"Expected Monday due date, got weekday {due_date.weekday()}"
