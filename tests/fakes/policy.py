"""In-memory fake policy repository for test suites."""

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


class InMemoryPolicyRepository:
    """In-memory implementation of PolicyRepository for unit testing."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._policies: dict[tuple[str, str], PolicyDefinition] = {}
        self._policy_history: dict[tuple[str, str, int], PolicyDefinition] = {}
        self._findings: dict[tuple[str, str], PolicyFinding] = {}
        self._exemptions: dict[tuple[str, str], PolicyExemption] = {}

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> PolicyDefinition | None:
        return self.get_policy(entity_id, tenant_context=tenant_context)

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PolicyDefinition]:
        enabled_only = bool(filter_params.get("enabled_only")) if isinstance(filter_params, dict) else False
        category = filter_params.get("category") if isinstance(filter_params, dict) else None
        res = self.list_policies(tenant_context=tenant_context, enabled_only=enabled_only, category=category)
        return res[offset : offset + limit]

    def save(self, entity: PolicyDefinition, *, tenant_context: TenantContext) -> PolicyDefinition:
        return self.save_policy(entity, tenant_context=tenant_context)

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self.delete_policy(entity_id, tenant_context=tenant_context)

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return (tenant_context.tenant_id, entity_id) in self._policies

    def save_policy(
        self, policy: PolicyDefinition, *, tenant_context: TenantContext
    ) -> PolicyDefinition:
        t_id = tenant_context.tenant_id
        self._policies[(t_id, policy.id)] = policy.model_copy()
        self._policy_history[(t_id, policy.id, policy.version)] = policy.model_copy()
        return policy

    def get_policy(
        self, policy_id: str, *, tenant_context: TenantContext
    ) -> PolicyDefinition | None:
        p = self._policies.get((tenant_context.tenant_id, policy_id))
        return p.model_copy() if p else None

    def get_policy_version(
        self, policy_id: str, version: int, *, tenant_context: TenantContext
    ) -> PolicyDefinition | None:
        p = self._policy_history.get((tenant_context.tenant_id, policy_id, version))
        return p.model_copy() if p else None

    def list_policies(
        self,
        *,
        tenant_context: TenantContext,
        enabled_only: bool = False,
        category: PolicyCategory | None = None,
    ) -> list[PolicyDefinition]:
        t_id = tenant_context.tenant_id
        results = [p.model_copy() for (t, _), p in self._policies.items() if t == t_id]
        if enabled_only:
            results = [p for p in results if p.enabled]
        if category:
            results = [p for p in results if p.category == category]
        results.sort(key=lambda p: (not p.enabled, p.id))
        return results

    def delete_policy(self, policy_id: str, *, tenant_context: TenantContext) -> bool:
        return bool(self._policies.pop((tenant_context.tenant_id, policy_id), None))

    def save_finding(
        self, finding: PolicyFinding, *, tenant_context: TenantContext
    ) -> PolicyFinding:
        self._findings[(tenant_context.tenant_id, finding.id)] = finding.model_copy()
        return finding

    def get_finding(
        self, finding_id: str, *, tenant_context: TenantContext
    ) -> PolicyFinding | None:
        f = self._findings.get((tenant_context.tenant_id, finding_id))
        return f.model_copy() if f else None

    def find_open_finding(
        self,
        entity_id: str,
        policy_id: str,
        policy_version: int | None = None,
        *,
        tenant_context: TenantContext,
    ) -> PolicyFinding | None:
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
    ) -> list[PolicyFinding]:
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

    def count_findings(
        self,
        *,
        tenant_context: TenantContext,
        status: FindingLifecycleStatus | None = None,
    ) -> int:
        items = self.list_findings(tenant_context=tenant_context, status=status)
        return len(items)

    def delete_finding(
        self, finding_id: str, *, tenant_context: TenantContext
    ) -> bool:
        return bool(self._findings.pop((tenant_context.tenant_id, finding_id), None))

    def save_exemption(
        self, exemption: PolicyExemption, *, tenant_context: TenantContext
    ) -> PolicyExemption:
        self._exemptions[(tenant_context.tenant_id, exemption.id)] = exemption.model_copy()
        return exemption

    def get_exemption(
        self, exemption_id: str, *, tenant_context: TenantContext
    ) -> PolicyExemption | None:
        e = self._exemptions.get((tenant_context.tenant_id, exemption_id))
        return e.model_copy() if e else None

    def list_exemptions(
        self,
        *,
        tenant_context: TenantContext,
        policy_id: str | None = None,
        entity_id: str | None = None,
        active_only: bool = False,
    ) -> list[PolicyExemption]:
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
        return bool(self._exemptions.pop((tenant_context.tenant_id, exemption_id), None))
