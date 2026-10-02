"""Policy Engine Repository (Prompt 30, Prompt 13 Item 84).

Enforces:
- Prompt 13 Item 84: Mandatory non-empty TenantContext on every public repository method.
- Versioned storage preserving historical policy definitions alongside current active definitions.
- Finding deduplication lookups for open findings matching (entity, policy, version).
"""

from __future__ import annotations

import builtins
import datetime as dt
from typing import Any

from domain.models.enums import (
    FindingLifecycleStatus,
    PolicyCategory,
    PolicyMode,
    PolicySeverity,
)
from domain.policy.models import (
    PolicyDefinition,
    PolicyExemption,
    PolicyFinding,
)
from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository


class PolicyRepository(TenantAwareRepository[PolicyDefinition]):
    """Thread-safe tenant-scoped repository for policies, findings, and exemptions."""

    def __init__(self) -> None:
        super().__init__()
        # Key: (tenant_id, policy_id) -> PolicyDefinition
        self._policies: dict[tuple[str, str], PolicyDefinition] = {}
        # Key: (tenant_id, policy_id, version) -> PolicyDefinition
        self._policy_history: dict[tuple[str, str, int], PolicyDefinition] = {}
        # Key: (tenant_id, finding_id) -> PolicyFinding
        self._findings: dict[tuple[str, str], PolicyFinding] = {}
        # Key: (tenant_id, exemption_id) -> PolicyExemption
        self._exemptions: dict[tuple[str, str], PolicyExemption] = {}

    # ==========================================================================
    # 0. Canonical TenantAwareRepository Protocol Implementation
    # ==========================================================================

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> PolicyDefinition | None:
        """Retrieves a single policy by ID within tenant boundary."""
        return self.get_policy(entity_id, tenant_context=tenant_context)

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[PolicyDefinition]:
        """Lists policies belonging strictly to the tenant with optional pagination."""
        enabled_only = (
            bool(filter_params.get("enabled_only")) if isinstance(filter_params, dict) else False
        )
        category = filter_params.get("category") if isinstance(filter_params, dict) else None
        results = self.list_policies(
            tenant_context=tenant_context,
            enabled_only=enabled_only,
            category=category,
        )
        return results[offset : offset + limit]

    def save(self, entity: PolicyDefinition, *, tenant_context: TenantContext) -> PolicyDefinition:
        """Persists or updates a policy definition."""
        return self.save_policy(entity, tenant_context=tenant_context)

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes a policy within tenant boundary."""
        return self.delete_policy(entity_id, tenant_context=tenant_context)

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Checks if a policy exists within tenant boundary."""
        self._validate_tenant_context(tenant_context)
        return (tenant_context.tenant_id, entity_id) in self._policies

    # ==========================================================================
    # 1. Policy CRUD & Version History Operations
    # ==========================================================================

    def save_policy(
        self, policy: PolicyDefinition, *, tenant_context: TenantContext
    ) -> PolicyDefinition:
        """Saves current policy and records immutable version snapshot."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id

        # Save current policy
        self._policies[(t_id, policy.id)] = policy.model_copy()
        # Save historical version snapshot
        self._policy_history[(t_id, policy.id, policy.version)] = policy.model_copy()
        return policy

    def get_policy(
        self, policy_id: str, *, tenant_context: TenantContext
    ) -> PolicyDefinition | None:
        """Retrieves the current active version of a policy."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        policy = self._policies.get((t_id, policy_id))
        return policy.model_copy() if policy else None

    def get_policy_version(
        self, policy_id: str, version: int, *, tenant_context: TenantContext
    ) -> PolicyDefinition | None:
        """Retrieves a specific historical version of a policy."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        policy = self._policy_history.get((t_id, policy_id, version))
        return policy.model_copy() if policy else None

    def list_policies(
        self,
        *,
        tenant_context: TenantContext,
        enabled_only: bool = False,
        category: PolicyCategory | None = None,
    ) -> builtins.list[PolicyDefinition]:
        """Lists all policies within the tenant scope."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id

        results = [p.model_copy() for (t, _), p in self._policies.items() if t == t_id]
        if enabled_only:
            results = [p for p in results if p.enabled]
        if category:
            results = [p for p in results if p.category == category]

        results.sort(key=lambda p: (not p.enabled, p.id))
        return results

    def delete_policy(self, policy_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes a policy and its active definitions."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        key = (t_id, policy_id)
        if key in self._policies:
            del self._policies[key]
            return True
        return False

    # ==========================================================================
    # 2. Finding Storage & Deduplication Operations
    # ==========================================================================

    def save_finding(
        self, finding: PolicyFinding, *, tenant_context: TenantContext
    ) -> PolicyFinding:
        """Stores or updates a policy finding."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        self._findings[(t_id, finding.id)] = finding.model_copy()
        return finding

    def get_finding(
        self, finding_id: str, *, tenant_context: TenantContext
    ) -> PolicyFinding | None:
        """Retrieves a single finding by ID."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        finding = self._findings.get((t_id, finding_id))
        return finding.model_copy() if finding else None

    def find_open_finding(
        self,
        entity_id: str,
        policy_id: str,
        policy_version: int | None = None,
        *,
        tenant_context: TenantContext,
    ) -> PolicyFinding | None:
        """Finds an existing OPEN finding for the same entity and policy (FR-744)."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id

        for (t, _), finding in self._findings.items():
            if (
                t == t_id
                and finding.entity_id == entity_id
                and finding.policy_id == policy_id
                and finding.lifecycle_status == FindingLifecycleStatus.OPEN
            ):
                if policy_version is not None and finding.policy_version != policy_version:
                    continue
                return finding.model_copy()
        return None

    def list_findings(
        self,
        *,
        tenant_context: TenantContext,
        status: FindingLifecycleStatus | None = None,
        severity: PolicySeverity | None = None,
        category: PolicyCategory | None = None,
        mode: PolicyMode | None = None,
        policy_id: str | None = None,
        entity_id: str | None = None,
    ) -> builtins.list[PolicyFinding]:
        """Lists findings with optional criteria filtering."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id

        results = [f.model_copy() for (t, _), f in self._findings.items() if t == t_id]
        if status:
            results = [f for f in results if f.lifecycle_status == status]
        if severity:
            results = [f for f in results if f.severity == severity]
        if category:
            results = [f for f in results if f.category == category]
        if mode:
            results = [f for f in results if f.mode == mode]
        if policy_id:
            results = [f for f in results if f.policy_id == policy_id]
        if entity_id:
            results = [f for f in results if f.entity_id == entity_id]

        results.sort(key=lambda f: f.last_evaluated_at, reverse=True)
        return results

    # ==========================================================================
    # 3. Policy Exemption Operations
    # ==========================================================================

    def save_exemption(
        self, exemption: PolicyExemption, *, tenant_context: TenantContext
    ) -> PolicyExemption:
        """Stores an operational policy exemption."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        self._exemptions[(t_id, exemption.id)] = exemption.model_copy()
        return exemption

    def get_exemption(
        self, exemption_id: str, *, tenant_context: TenantContext
    ) -> PolicyExemption | None:
        """Retrieves an exemption by ID."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        exemption = self._exemptions.get((t_id, exemption_id))
        return exemption.model_copy() if exemption else None

    def list_exemptions(
        self,
        *,
        tenant_context: TenantContext,
        policy_id: str | None = None,
        entity_id: str | None = None,
        active_only: bool = False,
    ) -> builtins.list[PolicyExemption]:
        """Lists policy exemptions with active/historical filtering."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        now = dt.datetime.now(dt.UTC)

        results = [e.model_copy() for (t, _), e in self._exemptions.items() if t == t_id]
        if policy_id:
            results = [e for e in results if e.policy_id == policy_id]
        if entity_id:
            results = [e for e in results if e.entity_id == entity_id]
        if active_only:
            results = [e for e in results if e.is_active(now)]

        results.sort(key=lambda e: e.expires_at, reverse=True)
        return results

    def delete_exemption(self, exemption_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes an exemption by ID."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        key = (t_id, exemption_id)
        if key in self._exemptions:
            del self._exemptions[key]
            return True
        return False

    # ==========================================================================
    # 4. Cleanup & Test Isolation
    # ==========================================================================

    def clear_tenant_data(self, *, tenant_context: TenantContext) -> None:
        """Clears all stored data for the specified tenant."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        for k_pol in [k for k in self._policies if k[0] == t_id]:
            del self._policies[k_pol]
        for k_hist in [k for k in self._policy_history if k[0] == t_id]:
            del self._policy_history[k_hist]
        for k_fnd in [k for k in self._findings if k[0] == t_id]:
            del self._findings[k_fnd]
        for k_exm in [k for k in self._exemptions if k[0] == t_id]:
            del self._exemptions[k_exm]

    def _clear_all_for_testing(self) -> None:
        """Internal helper for resetting singleton between test executions."""
        self._policies.clear()
        self._policy_history.clear()
        self._findings.clear()
        self._exemptions.clear()


# ==============================================================================
# Repository Singleton Factory
# ==============================================================================

_policy_repository_instance: PolicyRepository | None = None


def get_policy_repository() -> PolicyRepository:
    """Returns singleton PolicyRepository instance."""
    global _policy_repository_instance
    if _policy_repository_instance is None:
        _policy_repository_instance = PolicyRepository()
    return _policy_repository_instance


def reset_policy_repository() -> None:
    """Resets singleton PolicyRepository for test teardown."""
    global _policy_repository_instance
    if _policy_repository_instance is not None:
        _policy_repository_instance._clear_all_for_testing()
    _policy_repository_instance = None
