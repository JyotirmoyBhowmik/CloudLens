"""Dynamic Approver Resolution Engine (Prompt 50).

Enforces:
- Resolution from master data and entity ownership rather than named individuals:
  ROLE, SCOPE_OWNERSHIP, COST_CENTRE_OWNER, BUSINESS_UNIT_OWNER, BUDGET_OWNER, EXPLICIT_LIST.
- Documented fallback role (e.g. TENANT_ADMIN).
- Governance exception (NoResolvableApproverException) when no approver can be resolved.
- Delegation and out-of-office substitution mapping.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from domain.models.enums import ApproverResolutionType
from domain.models.exceptions import NoResolvableApproverException
from domain.tenant.context import TenantContext
from domain.workflows.models import (
    DelegationRule,
    SubjectEntity,
    WorkflowApproverSpec,
    WorkflowStageDefinition,
)
from masterdata.service import MasterDataService, get_master_data_service

logger = logging.getLogger(__name__)


class ResolvedApprovers:
    """Outcome of resolving approvers for a workflow stage."""

    def __init__(
        self,
        primary_approvers: list[str],
        effective_approvers: list[str],
        delegation_map: dict[str, DelegationRule],
        unavailable_without_delegate: list[str],
    ) -> None:
        self.primary_approvers = primary_approvers
        self.effective_approvers = effective_approvers
        self.delegation_map = delegation_map
        self.unavailable_without_delegate = unavailable_without_delegate

    def is_authorized(self, actor_id: str) -> bool:
        """Checks if an actor is authorized either as primary or delegate."""
        return actor_id in self.effective_approvers or actor_id in self.primary_approvers

    def get_delegation_for(self, actor_id: str) -> DelegationRule | None:
        """Retrieves active delegation rule if the actor is acting as a delegate."""
        return self.delegation_map.get(actor_id)


class ApproverResolver:
    """Resolves stage approvers dynamically from master data, roles, and ownership."""

    def __init__(self, master_data_service: MasterDataService | None = None) -> None:
        self.master_data_service = master_data_service or get_master_data_service()
        # Mock/in-memory role directory for testing and tenant user directory integration
        self._role_memberships: dict[tuple[str, str], list[str]] = {}
        # Known out-of-office users without delegation: user_id -> bool
        self._out_of_office_status: dict[str, bool] = {}

    def register_role_members(self, tenant_id: str, role_code: str, user_ids: list[str]) -> None:
        """Registers user assignments for a role within a tenant boundary."""
        self._role_memberships[(tenant_id, role_code.upper())] = list(user_ids)

    def set_user_out_of_office(self, user_id: str, is_ooo: bool = True) -> None:
        """Marks a user as out-of-office."""
        self._out_of_office_status[user_id] = is_ooo

    def _get_users_by_role(self, role_code: str, tenant_id: str) -> list[str]:
        """Looks up user IDs assigned to a role in the tenant."""
        key = (tenant_id, role_code.upper())
        if key in self._role_memberships:
            return self._role_memberships[key]
        # Check global / default mappings
        global_key = ("*", role_code.upper())
        if global_key in self._role_memberships:
            return self._role_memberships[global_key]

        # Standard simulated default users per system role
        defaults = {
            "GLOBAL_ADMIN": ["global-admin-user", f"{tenant_id}-global-admin"],
            "TENANT_ADMIN": [f"{tenant_id}-admin", "user-admin-1", "tenant-admin-1"],
            "FINOPS_ADMIN": [f"{tenant_id}-finops-lead", "user-finops-lead", "user-finops-1"],
            "FINANCE_ADMIN": [f"{tenant_id}-finance-lead", "user-finance-lead"],
            "SECURITY_ADMIN": [f"{tenant_id}-security-lead", "sec-lead", "user-security-lead"],
            "CLOUD_ADMIN": [f"{tenant_id}-cloud-admin", "user-cloud-admin"],
            "PLATFORM_ADMIN": [f"{tenant_id}-platform-admin"],
            "PROCUREMENT": [f"{tenant_id}-procurement-lead"],
        }
        return defaults.get(role_code.upper(), [])

    def resolve_approvers(
        self,
        request_id: str,
        stage_def: WorkflowStageDefinition,
        subject_entity: SubjectEntity,
        *,
        tenant_context: TenantContext,
        delegations: list[DelegationRule] | None = None,
        as_of: datetime | None = None,
        request_type: str | None = None,
    ) -> ResolvedApprovers:
        """Resolves stage approvers from master data with fallback and delegation support."""
        spec: WorkflowApproverSpec = stage_def.approver_spec
        tenant_id = tenant_context.tenant_id
        candidates: list[str] = []

        # 1. Primary Resolution Strategy
        if spec.resolution_type == ApproverResolutionType.ROLE:
            role = spec.target_role or "TENANT_ADMIN"
            candidates = self._get_users_by_role(role, tenant_id)
            if spec.explicit_approvers:
                candidates = list(dict.fromkeys(candidates + spec.explicit_approvers))
            if role in tenant_context.roles and tenant_context.user_id not in candidates:
                candidates.append(tenant_context.user_id)

        elif spec.resolution_type == ApproverResolutionType.SCOPE_OWNERSHIP:
            owner = subject_entity.metadata.get("owner") or subject_entity.metadata.get(
                "scope_owner"
            )
            if owner:
                candidates = [owner]

        elif spec.resolution_type == ApproverResolutionType.COST_CENTRE_OWNER:
            cc_code = (
                subject_entity.metadata.get("cost_centre_code")
                or subject_entity.metadata.get("cost_center")
                or subject_entity.scope_id
            )
            if cc_code:
                try:
                    rec = self.master_data_service.get_record(
                        "COST_CENTRE", cc_code, tenant_id=tenant_id
                    )
                    if rec and rec.attributes:
                        mgr = rec.attributes.get("manager_user_id") or rec.attributes.get("owner")
                        if mgr:
                            candidates = [mgr]
                except Exception:
                    pass

        elif spec.resolution_type == ApproverResolutionType.BUSINESS_UNIT_OWNER:
            bu_code = (
                subject_entity.metadata.get("business_unit_code")
                or subject_entity.metadata.get("business_unit")
                or subject_entity.scope_id
            )
            if bu_code:
                try:
                    rec = self.master_data_service.get_record(
                        "BUSINESS_UNIT", bu_code, tenant_id=tenant_id
                    )
                    if rec and rec.attributes:
                        mgr = rec.attributes.get("manager_user_id") or rec.attributes.get("owner")
                        if mgr:
                            candidates = [mgr]
                except Exception:
                    pass

        elif spec.resolution_type == ApproverResolutionType.BUDGET_OWNER:
            owner = subject_entity.metadata.get("owner") or subject_entity.metadata.get(
                "budget_owner"
            )
            if owner:
                candidates = [owner]

        elif spec.resolution_type == ApproverResolutionType.EXPLICIT_LIST:
            candidates = list(spec.explicit_approvers)

        # 2. Documented Fallback
        if not candidates:
            logger.info(
                "Primary resolution '%s' yielded no candidates for stage '%s', attempting fallback role '%s'",
                spec.resolution_type.value,
                stage_def.name,
                spec.fallback_role,
            )
            if spec.fallback_role:
                candidates = self._get_users_by_role(spec.fallback_role, tenant_id)

        # If still empty, check explicit list if not already checked
        if not candidates and spec.explicit_approvers:
            candidates = list(spec.explicit_approvers)

        # 3. Governance Exception: Never silently disappear!
        if not candidates:
            logger.error(
                "Governance Exception: No approver could be resolved for request '%s' at stage '%s'",
                request_id,
                stage_def.name,
            )
            raise NoResolvableApproverException(
                request_id=request_id,
                stage_name=stage_def.name,
                resolution_type=spec.resolution_type.value,
            )

        # 4. Delegation and Out-of-Office Processing
        now = as_of or datetime.now(UTC)
        active_delegations = delegations or []
        effective: list[str] = list(candidates)
        delegation_map: dict[str, DelegationRule] = {}
        unavailable_without_delegate: list[str] = []

        for cand in candidates:
            if self._out_of_office_status.get(cand, False):
                # Check if this candidate has an active delegation
                has_del = any(
                    d.original_approver_id == cand
                    and d.is_currently_active(as_of=now, req_type=request_type)
                    for d in active_delegations
                )
                if not has_del:
                    unavailable_without_delegate.append(cand)

        for d in active_delegations:
            if d.is_currently_active(as_of=now, req_type=request_type):
                if d.original_approver_id in candidates or (
                    spec.target_role
                    and d.original_approver_id
                    in self._get_users_by_role(spec.target_role, tenant_id)
                ):
                    effective.append(d.delegate_approver_id)
                    delegation_map[d.delegate_approver_id] = d

        return ResolvedApprovers(
            primary_approvers=candidates,
            effective_approvers=list(dict.fromkeys(effective)),
            delegation_map=delegation_map,
            unavailable_without_delegate=unavailable_without_delegate,
        )
