"""Master-Data-Driven Workflow Definitions Catalogue (Prompt 50).

Enforces:
- Workflow definitions as Master Data: request type, entity type, trigger conditions,
  approval chain (serial, parallel, quorum), SLA in working hours, escalation path,
  auto-approve conditions, and auto-reject on expiry.
- Zero code changes required to add a new approval requirement.
- Wires all ten canonical approval points:
  1. Budget above approval limit (BBP Section 22)
  2. Administrative and temporary overrides (BBP Section 32.3)
  3. Policy exemptions (BBP Section 34)
  4. Custom role creation (BBP Section 33)
  5. Master-data changes where registry requires approval (Prompt 45)
  6. Tenant creation and suspension
  7. Connector deletion
  8. Cost-model and allocation-rule changes
  9. Retention changes
  10. Negotiated rate-card upload
"""

from __future__ import annotations

from domain.models.enums import (
    ApprovalChainMode,
    ApproverResolutionType,
    WorkflowRequestType,
)
from domain.workflows.models import (
    WorkflowApproverSpec,
    WorkflowDefinition,
    WorkflowEscalationPath,
    WorkflowStageDefinition,
    WorkflowTriggerCondition,
)

# Canonical system workflow definitions
DEFAULT_WORKFLOW_DEFINITIONS: dict[str, WorkflowDefinition] = {
    # 1. Budget above approval limit ($10,000 default threshold)
    WorkflowRequestType.BUDGET_APPROVAL.value: WorkflowDefinition(
        id="wf-def-budget-approval",
        request_type=WorkflowRequestType.BUDGET_APPROVAL.value,
        entity_type="budget",
        name="High-Value Budget Approval Workflow",
        description="Formal approval chain required for cloud budgets exceeding the allocation approval ceiling.",
        trigger_condition=WorkflowTriggerCondition(amount_gt=10000.0),
        stages=[
            WorkflowStageDefinition(
                stage_id="stage-budget-finops",
                name="FinOps Lead Review",
                sequence_order=1,
                mode=ApprovalChainMode.SERIAL,
                quorum=1,
                approver_spec=WorkflowApproverSpec(
                    resolution_type=ApproverResolutionType.ROLE,
                    target_role="FINOPS_ADMIN",
                    fallback_role="TENANT_ADMIN",
                ),
            ),
            WorkflowStageDefinition(
                stage_id="stage-budget-exec",
                name="Budget Scope Authority Approval",
                sequence_order=2,
                mode=ApprovalChainMode.SERIAL,
                quorum=1,
                approver_spec=WorkflowApproverSpec(
                    resolution_type=ApproverResolutionType.SCOPE_OWNERSHIP,
                    fallback_role="TENANT_ADMIN",
                ),
            ),
        ],
        approval_mode=ApprovalChainMode.SERIAL,
        quorum=1,
        sla_working_hours=48,
        working_schedule_id="WW_STANDARD_MON_FRI",
        escalation_path=WorkflowEscalationPath(
            escalate_to_role="GLOBAL_ADMIN",
            escalate_after_hours=24,
        ),
        auto_reject_on_expiry=True,
    ),
    # 2. Administrative and temporary overrides
    WorkflowRequestType.OVERRIDE_APPROVAL.value: WorkflowDefinition(
        id="wf-def-override-approval",
        request_type=WorkflowRequestType.OVERRIDE_APPROVAL.value,
        entity_type="override",
        name="Governance & Operational Override Approval",
        description="Mandatory sign-off for temporary or permanent operational and threshold overrides.",
        trigger_condition=WorkflowTriggerCondition(always=True),
        stages=[
            WorkflowStageDefinition(
                stage_id="stage-override-security",
                name="Security & Compliance Review",
                sequence_order=1,
                mode=ApprovalChainMode.SERIAL,
                quorum=1,
                approver_spec=WorkflowApproverSpec(
                    resolution_type=ApproverResolutionType.ROLE,
                    target_role="SECURITY_ADMIN",
                    fallback_role="TENANT_ADMIN",
                ),
            )
        ],
        sla_working_hours=24,
        working_schedule_id="WW_STANDARD_MON_FRI",
        escalation_path=WorkflowEscalationPath(
            escalate_to_role="TENANT_ADMIN",
            escalate_after_hours=12,
        ),
        auto_reject_on_expiry=True,
    ),
    # 3. Policy exemptions
    WorkflowRequestType.POLICY_EXEMPTION.value: WorkflowDefinition(
        id="wf-def-policy-exemption",
        request_type=WorkflowRequestType.POLICY_EXEMPTION.value,
        entity_type="policy_exemption",
        name="Time-Boxed Policy Exemption Authorization",
        description="Formal sign-off for granting exceptions to platform governance guardrails.",
        trigger_condition=WorkflowTriggerCondition(always=True),
        stages=[
            WorkflowStageDefinition(
                stage_id="stage-exemption-gov",
                name="Governance Authority Review",
                sequence_order=1,
                mode=ApprovalChainMode.SERIAL,
                quorum=1,
                approver_spec=WorkflowApproverSpec(
                    resolution_type=ApproverResolutionType.ROLE,
                    target_role="SECURITY_ADMIN",
                    fallback_role="TENANT_ADMIN",
                ),
            )
        ],
        sla_working_hours=48,
        working_schedule_id="WW_STANDARD_MON_FRI",
        escalation_path=WorkflowEscalationPath(
            escalate_to_role="TENANT_ADMIN",
            escalate_after_hours=24,
        ),
        auto_reject_on_expiry=True,
    ),
    # 4. Custom role creation (BBP Section 33) - Parallel Quorum
    WorkflowRequestType.CUSTOM_ROLE_CREATION.value: WorkflowDefinition(
        id="wf-def-custom-role",
        request_type=WorkflowRequestType.CUSTOM_ROLE_CREATION.value,
        entity_type="role",
        name="Custom RBAC Role Composition Approval",
        description="Parallel dual-authorization by Security Admin and Tenant Admin.",
        trigger_condition=WorkflowTriggerCondition(always=True),
        stages=[
            WorkflowStageDefinition(
                stage_id="stage-role-dual-auth",
                name="Dual Security & Admin Sign-off",
                sequence_order=1,
                mode=ApprovalChainMode.PARALLEL,
                quorum=2,
                approver_spec=WorkflowApproverSpec(
                    resolution_type=ApproverResolutionType.ROLE,
                    target_role="SECURITY_ADMIN",
                    explicit_approvers=["sec-lead", "tenant-admin-1"],
                    fallback_role="TENANT_ADMIN",
                ),
            )
        ],
        approval_mode=ApprovalChainMode.PARALLEL,
        quorum=2,
        sla_working_hours=72,
        working_schedule_id="WW_STANDARD_MON_FRI",
        escalation_path=WorkflowEscalationPath(
            escalate_to_role="GLOBAL_ADMIN",
            escalate_after_hours=36,
        ),
        auto_reject_on_expiry=True,
    ),
    # 5. Master-data changes where registry requires approval (Prompt 45)
    WorkflowRequestType.MASTER_DATA_CHANGE.value: WorkflowDefinition(
        id="wf-def-master-data",
        request_type=WorkflowRequestType.MASTER_DATA_CHANGE.value,
        entity_type="master_data",
        name="Master Data Registry Mutation Approval",
        description="Data steward sign-off before publishing modified master records.",
        trigger_condition=WorkflowTriggerCondition(always=True),
        stages=[
            WorkflowStageDefinition(
                stage_id="stage-md-steward",
                name="Data Steward Review",
                sequence_order=1,
                mode=ApprovalChainMode.SERIAL,
                quorum=1,
                approver_spec=WorkflowApproverSpec(
                    resolution_type=ApproverResolutionType.ROLE,
                    target_role="FINOPS_ADMIN",
                    fallback_role="TENANT_ADMIN",
                ),
            )
        ],
        sla_working_hours=48,
        working_schedule_id="WW_STANDARD_MON_FRI",
        escalation_path=WorkflowEscalationPath(
            escalate_to_role="GLOBAL_ADMIN",
            escalate_after_hours=24,
        ),
        auto_reject_on_expiry=True,
    ),
    # 6. Tenant creation and suspension
    WorkflowRequestType.TENANT_LIFECYCLE.value: WorkflowDefinition(
        id="wf-def-tenant-lifecycle",
        request_type=WorkflowRequestType.TENANT_LIFECYCLE.value,
        entity_type="tenant",
        name="Tenant Lifecycle Sign-off",
        description="Global administration approval for tenant onboarding or suspension.",
        trigger_condition=WorkflowTriggerCondition(always=True),
        stages=[
            WorkflowStageDefinition(
                stage_id="stage-tenant-lifecycle",
                name="Platform Global Admin Sign-off",
                sequence_order=1,
                mode=ApprovalChainMode.SERIAL,
                quorum=1,
                approver_spec=WorkflowApproverSpec(
                    resolution_type=ApproverResolutionType.ROLE,
                    target_role="GLOBAL_ADMIN",
                    fallback_role="GLOBAL_ADMIN",
                ),
            )
        ],
        sla_working_hours=24,
        working_schedule_id="WW_STANDARD_MON_FRI",
        escalation_path=WorkflowEscalationPath(
            escalate_to_role="GLOBAL_ADMIN",
            escalate_after_hours=12,
        ),
        auto_reject_on_expiry=True,
    ),
    # 7. Connector deletion
    WorkflowRequestType.CONNECTOR_DELETION.value: WorkflowDefinition(
        id="wf-def-connector-deletion",
        request_type=WorkflowRequestType.CONNECTOR_DELETION.value,
        entity_type="connector",
        name="Cloud Connector Decommission Approval",
        description="Approval required before disconnecting telemetry and billing connectors.",
        trigger_condition=WorkflowTriggerCondition(always=True),
        stages=[
            WorkflowStageDefinition(
                stage_id="stage-connector-cloud-admin",
                name="Cloud Operations Lead Sign-off",
                sequence_order=1,
                mode=ApprovalChainMode.SERIAL,
                quorum=1,
                approver_spec=WorkflowApproverSpec(
                    resolution_type=ApproverResolutionType.ROLE,
                    target_role="CLOUD_ADMIN",
                    fallback_role="TENANT_ADMIN",
                ),
            )
        ],
        sla_working_hours=24,
        working_schedule_id="WW_STANDARD_MON_FRI",
        escalation_path=WorkflowEscalationPath(
            escalate_to_role="TENANT_ADMIN",
            escalate_after_hours=12,
        ),
        auto_reject_on_expiry=True,
    ),
    # 8. Cost-model change
    WorkflowRequestType.COST_MODEL_CHANGE.value: WorkflowDefinition(
        id="wf-def-cost-model",
        request_type=WorkflowRequestType.COST_MODEL_CHANGE.value,
        entity_type="cost_model",
        name="Cost Model Adjustment Approval",
        description="FinOps and Finance review for cost calculation formulas and amortization rules.",
        trigger_condition=WorkflowTriggerCondition(always=True),
        stages=[
            WorkflowStageDefinition(
                stage_id="stage-cost-finance",
                name="Finance Controller Sign-off",
                sequence_order=1,
                mode=ApprovalChainMode.SERIAL,
                quorum=1,
                approver_spec=WorkflowApproverSpec(
                    resolution_type=ApproverResolutionType.ROLE,
                    target_role="FINANCE_ADMIN",
                    fallback_role="TENANT_ADMIN",
                ),
            )
        ],
        sla_working_hours=48,
        working_schedule_id="WW_STANDARD_MON_FRI",
        escalation_path=WorkflowEscalationPath(
            escalate_to_role="TENANT_ADMIN",
            escalate_after_hours=24,
        ),
        auto_reject_on_expiry=True,
    ),
    # 9. Allocation-rule change
    WorkflowRequestType.ALLOCATION_RULE_CHANGE.value: WorkflowDefinition(
        id="wf-def-allocation-rule",
        request_type=WorkflowRequestType.ALLOCATION_RULE_CHANGE.value,
        entity_type="allocation_rule",
        name="Cost Allocation Rule Modification Approval",
        description="Review for business unit attribution and split-cost allocation rules.",
        trigger_condition=WorkflowTriggerCondition(always=True),
        stages=[
            WorkflowStageDefinition(
                stage_id="stage-alloc-finops",
                name="FinOps Governance Sign-off",
                sequence_order=1,
                mode=ApprovalChainMode.SERIAL,
                quorum=1,
                approver_spec=WorkflowApproverSpec(
                    resolution_type=ApproverResolutionType.ROLE,
                    target_role="FINOPS_ADMIN",
                    fallback_role="TENANT_ADMIN",
                ),
            )
        ],
        sla_working_hours=48,
        working_schedule_id="WW_STANDARD_MON_FRI",
        escalation_path=WorkflowEscalationPath(
            escalate_to_role="TENANT_ADMIN",
            escalate_after_hours=24,
        ),
        auto_reject_on_expiry=True,
    ),
    # 10. Retention change
    WorkflowRequestType.RETENTION_CHANGE.value: WorkflowDefinition(
        id="wf-def-retention-change",
        request_type=WorkflowRequestType.RETENTION_CHANGE.value,
        entity_type="retention_policy",
        name="Data Retention & Pruning Policy Alteration",
        description="Legal and compliance sign-off for reducing or extending data retention windows.",
        trigger_condition=WorkflowTriggerCondition(always=True),
        stages=[
            WorkflowStageDefinition(
                stage_id="stage-retention-security",
                name="Data Governance Officer Sign-off",
                sequence_order=1,
                mode=ApprovalChainMode.SERIAL,
                quorum=1,
                approver_spec=WorkflowApproverSpec(
                    resolution_type=ApproverResolutionType.ROLE,
                    target_role="SECURITY_ADMIN",
                    fallback_role="TENANT_ADMIN",
                ),
            )
        ],
        sla_working_hours=72,
        working_schedule_id="WW_STANDARD_MON_FRI",
        escalation_path=WorkflowEscalationPath(
            escalate_to_role="TENANT_ADMIN",
            escalate_after_hours=36,
        ),
        auto_reject_on_expiry=True,
    ),
    # 11. Negotiated rate-card upload
    WorkflowRequestType.RATE_CARD_UPLOAD.value: WorkflowDefinition(
        id="wf-def-rate-card",
        request_type=WorkflowRequestType.RATE_CARD_UPLOAD.value,
        entity_type="rate_card",
        name="Negotiated Enterprise Rate Card Approval",
        description="Procurement and commercial validation before applying custom negotiated discount matrices.",
        trigger_condition=WorkflowTriggerCondition(always=True),
        stages=[
            WorkflowStageDefinition(
                stage_id="stage-rate-procurement",
                name="Procurement Category Manager Sign-off",
                sequence_order=1,
                mode=ApprovalChainMode.SERIAL,
                quorum=1,
                approver_spec=WorkflowApproverSpec(
                    resolution_type=ApproverResolutionType.ROLE,
                    target_role="PROCUREMENT",
                    fallback_role="FINOPS_ADMIN",
                ),
            )
        ],
        sla_working_hours=48,
        working_schedule_id="WW_STANDARD_MON_FRI",
        escalation_path=WorkflowEscalationPath(
            escalate_to_role="TENANT_ADMIN",
            escalate_after_hours=24,
        ),
        auto_reject_on_expiry=True,
    ),
    # 12. Showback Statement Dispute (Prompt 52)
    WorkflowRequestType.STATEMENT_DISPUTE.value: WorkflowDefinition(
        id="wf-def-statement-dispute",
        request_type=WorkflowRequestType.STATEMENT_DISPUTE.value,
        entity_type="statement_dispute",
        name="Showback Statement Dispute Workflow",
        description="Formal review and dispute resolution workflow for queried cost allocation or showback statement line items.",
        trigger_condition=WorkflowTriggerCondition(always=True),
        stages=[
            WorkflowStageDefinition(
                stage_id="stage-dispute-finops",
                name="FinOps Cost Analyst Investigation",
                sequence_order=1,
                mode=ApprovalChainMode.SERIAL,
                quorum=1,
                approver_spec=WorkflowApproverSpec(
                    resolution_type=ApproverResolutionType.ROLE,
                    target_role="FINOPS_ADMIN",
                    fallback_role="TENANT_ADMIN",
                ),
            )
        ],
        sla_working_hours=48,
        working_schedule_id="WW_STANDARD_MON_FRI",
        escalation_path=WorkflowEscalationPath(
            escalate_to_role="FINANCE_DIRECTOR",
            escalate_after_hours=24,
        ),
        auto_reject_on_expiry=False,
    ),
    # 12. Cost-Aware Provisioning Gate (Prompt 55)
    WorkflowRequestType.PROVISIONING_REQUEST.value: WorkflowDefinition(
        id="wf-def-provisioning-request",
        request_type=WorkflowRequestType.PROVISIONING_REQUEST.value,
        entity_type="provisioning_request",
        name="Cost-Aware Provisioning Gate Approval Workflow",
        description="Pre-deployment evaluation and approval workflow for cloud resource provisioning against scope budget and quota headroom.",
        trigger_condition=WorkflowTriggerCondition(always=True),
        stages=[
            WorkflowStageDefinition(
                stage_id="stage-provisioning-gate-review",
                name="Scope Owner & FinOps Provisioning Gate Review",
                sequence_order=1,
                mode=ApprovalChainMode.SERIAL,
                quorum=1,
                approver_spec=WorkflowApproverSpec(
                    resolution_type=ApproverResolutionType.ROLE,
                    target_role="FINOPS_ADMIN",
                    fallback_role="TENANT_ADMIN",
                ),
            )
        ],
        sla_working_hours=24,
        working_schedule_id="WW_STANDARD_MON_FRI",
        escalation_path=WorkflowEscalationPath(
            escalate_to_role="FINANCE_DIRECTOR",
            escalate_after_hours=12,
        ),
        auto_reject_on_expiry=False,
    ),
}


def get_default_workflow_definitions() -> list[WorkflowDefinition]:
    """Returns full catalogue of default master data workflow definitions."""
    return list(DEFAULT_WORKFLOW_DEFINITIONS.values())


def get_default_workflow_definition_by_type(request_type: str) -> WorkflowDefinition | None:
    """Looks up default workflow definition by canonical request type code."""
    return DEFAULT_WORKFLOW_DEFINITIONS.get(request_type.strip().upper())
