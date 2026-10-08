"""Policy Engine Repository (Prompt 30, Prompt 13 Item 84, Prompt P07).

Enforces:
- Prompt 13 Item 84: Mandatory non-empty TenantContext on every public repository method.
- Pattern P1 & P4: Protocol contract and PostgreSQL RLS persistence via SqlPolicyRepository.
- Policies (definitions from master data), findings, and exemptions.
- Strict SQL aggregation for findings counts (SELECT COUNT(*)), zero hard-coded counts.
- Production startup guard verifying no in-memory repositories in staging/production.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
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


@runtime_checkable
class PolicyRepository(Protocol):
    """Authoritative repository protocol for policies, findings, and exemptions."""

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> PolicyDefinition | None: ...
    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PolicyDefinition]: ...
    def save(self, entity: PolicyDefinition, *, tenant_context: TenantContext) -> PolicyDefinition: ...
    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool: ...
    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool: ...
    def save_policy(
        self, policy: PolicyDefinition, *, tenant_context: TenantContext
    ) -> PolicyDefinition: ...
    def get_policy(
        self, policy_id: str, *, tenant_context: TenantContext
    ) -> PolicyDefinition | None: ...
    def get_policy_version(
        self, policy_id: str, version: int, *, tenant_context: TenantContext
    ) -> PolicyDefinition | None: ...
    def list_policies(
        self,
        *,
        tenant_context: TenantContext,
        enabled_only: bool = False,
        category: PolicyCategory | None = None,
    ) -> list[PolicyDefinition]: ...
    def delete_policy(self, policy_id: str, *, tenant_context: TenantContext) -> bool: ...
    def save_finding(
        self, finding: PolicyFinding, *, tenant_context: TenantContext
    ) -> PolicyFinding: ...
    def get_finding(
        self, finding_id: str, *, tenant_context: TenantContext
    ) -> PolicyFinding | None: ...
    def find_open_finding(
        self,
        entity_id: str,
        policy_id: str,
        policy_version: int | None = None,
        *,
        tenant_context: TenantContext,
    ) -> PolicyFinding | None: ...
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
    ) -> list[PolicyFinding]: ...
    def count_findings(
        self,
        *,
        tenant_context: TenantContext,
        status: FindingLifecycleStatus | None = None,
    ) -> int: ...
    def delete_finding(
        self, finding_id: str, *, tenant_context: TenantContext
    ) -> bool: ...
    def save_exemption(
        self, exemption: PolicyExemption, *, tenant_context: TenantContext
    ) -> PolicyExemption: ...
    def get_exemption(
        self, exemption_id: str, *, tenant_context: TenantContext
    ) -> PolicyExemption | None: ...
    def list_exemptions(
        self,
        *,
        tenant_context: TenantContext,
        policy_id: str | None = None,
        entity_id: str | None = None,
        active_only: bool = False,
    ) -> list[PolicyExemption]: ...
    def delete_exemption(self, exemption_id: str, *, tenant_context: TenantContext) -> bool: ...


class SqlPolicyRepository:
    """PostgreSQL production implementation with RLS enforcement."""

    is_in_memory: bool = False

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    def _row_to_policy(self, row: Any) -> PolicyDefinition:
        m = dict(row._mapping)
        raw = m.get("policy_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return PolicyDefinition.model_validate(raw)
        return PolicyDefinition(
            id=m["id"],
            name=m["name"],
            description=m.get("description", ""),
            rule_type=m["rule_type"],
            category=PolicyCategory(m.get("category", "COST_OPTIMIZATION")),
            severity=PolicySeverity(m["severity"]),
            parameters=m.get("parameters") or {},
            enabled=m.get("enabled", True),
            version=m.get("version", 1),
            created_at=m["created_at"],
            updated_at=m.get("updated_at") or m["created_at"],
        )

    def _row_to_finding(self, row: Any) -> PolicyFinding:
        m = dict(row._mapping)
        raw = m.get("finding_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return PolicyFinding.model_validate(raw)
        return PolicyFinding.model_validate(m)

    def _row_to_exemption(self, row: Any) -> PolicyExemption:
        m = dict(row._mapping)
        raw = m.get("exemption_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return PolicyExemption.model_validate(raw)
        return PolicyExemption.model_validate(m)

    # --------------------------------------------------------------------------
    # Policy CRUD
    # --------------------------------------------------------------------------

    async def get_policy_async(
        self, policy_id: str, *, tenant_context: TenantContext
    ) -> PolicyDefinition | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM policies WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": policy_id, "tid": tenant_context.tenant_id},
            )
            row = res.first()
            return self._row_to_policy(row) if row else None

    def get_policy(
        self, policy_id: str, *, tenant_context: TenantContext
    ) -> PolicyDefinition | None:
        return self._run_async(self.get_policy_async(policy_id, tenant_context=tenant_context))

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> PolicyDefinition | None:
        return self.get_policy(entity_id, tenant_context=tenant_context)

    async def get_policy_version_async(
        self, policy_id: str, version: int, *, tenant_context: TenantContext
    ) -> PolicyDefinition | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM policy_history WHERE policy_id = :pid AND version = :ver AND tenant_id = :tid LIMIT 1;"),
                {"pid": policy_id, "ver": version, "tid": tenant_context.tenant_id},
            )
            row = res.first()
            return self._row_to_policy(row) if row else None

    def get_policy_version(
        self, policy_id: str, version: int, *, tenant_context: TenantContext
    ) -> PolicyDefinition | None:
        return self._run_async(self.get_policy_version_async(policy_id, version, tenant_context=tenant_context))

    async def save_policy_async(
        self, policy: PolicyDefinition, *, tenant_context: TenantContext
    ) -> PolicyDefinition:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            tid = tenant_context.tenant_id
            payload_json = json.dumps(policy.model_dump(mode="json"))

            # 1. Upsert active policy
            query = text("""
                INSERT INTO policies (
                    id, tenant_id, name, rule_type, severity, parameters, created_at,
                    updated_at, version, policy_payload
                ) VALUES (
                    :id, :tid, :name, :rule_type, :severity, CAST(:params AS jsonb), :created_at,
                    NOW(), :version, CAST(:payload AS jsonb)
                )
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    rule_type = EXCLUDED.rule_type,
                    severity = EXCLUDED.severity,
                    parameters = EXCLUDED.parameters,
                    updated_at = NOW(),
                    version = EXCLUDED.version,
                    policy_payload = EXCLUDED.policy_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": policy.id,
                    "tid": tid,
                    "name": policy.name,
                    "rule_type": str(getattr(policy, "rule_type", getattr(policy, "category", "DECLARATIVE"))),
                    "severity": policy.severity.value if hasattr(policy.severity, "value") else str(policy.severity),
                    "params": json.dumps(getattr(policy, "parameters", {})),
                    "created_at": policy.created_at,
                    "version": policy.version,
                    "payload": payload_json,
                },
            )

            # 2. Immutable version history snapshot
            hist_query = text("""
                INSERT INTO policy_history (id, tenant_id, policy_id, version, policy_payload, created_at)
                VALUES (:id, :tid, :pid, :ver, CAST(:payload AS jsonb), NOW())
                ON CONFLICT (tenant_id, policy_id, version) DO UPDATE SET
                    policy_payload = EXCLUDED.policy_payload;
            """)
            await sess.execute(
                hist_query,
                {
                    "id": f"{policy.id}-v{policy.version}",
                    "tid": tid,
                    "pid": policy.id,
                    "ver": policy.version,
                    "payload": payload_json,
                },
            )

            await sess.commit()
            return policy

    def save_policy(
        self, policy: PolicyDefinition, *, tenant_context: TenantContext
    ) -> PolicyDefinition:
        return self._run_async(self.save_policy_async(policy, tenant_context=tenant_context))

    def save(self, entity: PolicyDefinition, *, tenant_context: TenantContext) -> PolicyDefinition:
        return self.save_policy(entity, tenant_context=tenant_context)

    async def list_policies_async(
        self,
        *,
        tenant_context: TenantContext,
        enabled_only: bool = False,
        category: PolicyCategory | None = None,
    ) -> list[PolicyDefinition]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sql = "SELECT * FROM policies WHERE tenant_id = :tid"
            params: dict[str, Any] = {"tid": tenant_context.tenant_id}
            res = await sess.execute(text(sql), params)
            rows = res.fetchall()

            # If tenant has no custom policies, seed definitions from master data
            if not rows:
                from masterdata.service import get_master_data_service
                md_service = get_master_data_service()
                md_records = md_service.list_records("POLICY", tenant_id=tenant_context.tenant_id)
                if md_records:
                    seeded: list[PolicyDefinition] = []
                    for rec in md_records:
                        attrs = rec.attributes
                        pol = PolicyDefinition(
                            id=rec.code,
                            name=rec.display_name,
                            description=rec.description,
                            rule_type=attrs.get("rule_type", "CUSTOM"),
                            category=PolicyCategory(attrs.get("category", "COST_OPTIMIZATION")),
                            severity=PolicySeverity(attrs.get("severity", "MEDIUM")),
                            parameters=attrs.get("parameters", {}),
                            enabled=attrs.get("enabled", True),
                            version=1,
                        )
                        await self.save_policy_async(pol, tenant_context=tenant_context)
                        seeded.append(pol)
                    rows_seeded = seeded
                    if enabled_only:
                        rows_seeded = [p for p in rows_seeded if p.enabled]
                    if category:
                        rows_seeded = [p for p in rows_seeded if p.category == category]
                    rows_seeded.sort(key=lambda p: (not p.enabled, p.id))
                    return rows_seeded

            results = [self._row_to_policy(r) for r in rows]
            if enabled_only:
                results = [p for p in results if p.enabled]
            if category:
                results = [p for p in results if p.category == category]
            results.sort(key=lambda p: (not p.enabled, p.id))
            return results

    def list_policies(
        self,
        *,
        tenant_context: TenantContext,
        enabled_only: bool = False,
        category: PolicyCategory | None = None,
    ) -> list[PolicyDefinition]:
        return self._run_async(
            self.list_policies_async(
                tenant_context=tenant_context, enabled_only=enabled_only, category=category
            )
        )

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

    async def delete_policy_async(self, policy_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("DELETE FROM policies WHERE id = :id AND tenant_id = :tid;"),
                {"id": policy_id, "tid": tenant_context.tenant_id},
            )
            await sess.commit()
            return res.rowcount > 0

    def delete_policy(self, policy_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_policy_async(policy_id, tenant_context=tenant_context))

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self.delete_policy(entity_id, tenant_context=tenant_context)

    async def exists_async(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT 1 FROM policies WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": entity_id, "tid": tenant_context.tenant_id},
            )
            return res.first() is not None

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.exists_async(entity_id, tenant_context=tenant_context))

    # --------------------------------------------------------------------------
    # Findings Operations
    # --------------------------------------------------------------------------

    async def save_finding_async(
        self, finding: PolicyFinding, *, tenant_context: TenantContext
    ) -> PolicyFinding:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            tid = tenant_context.tenant_id
            query = text("""
                INSERT INTO policy_findings (
                    id, tenant_id, policy_id, entity_id, lifecycle_status, severity,
                    category, mode, finding_payload, created_at, last_evaluated_at
                ) VALUES (
                    :id, :tid, :pid, :eid, :st, :sev, :cat, :mode, CAST(:payload AS jsonb),
                    :created_at, :last_eval
                )
                ON CONFLICT (id) DO UPDATE SET
                    lifecycle_status = EXCLUDED.lifecycle_status,
                    severity = EXCLUDED.severity,
                    last_evaluated_at = EXCLUDED.last_evaluated_at,
                    finding_payload = EXCLUDED.finding_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": finding.id,
                    "tid": tid,
                    "pid": finding.policy_id,
                    "eid": finding.entity_id,
                    "st": finding.lifecycle_status.value if hasattr(finding.lifecycle_status, "value") else str(finding.lifecycle_status),
                    "sev": finding.severity.value if hasattr(finding.severity, "value") else str(finding.severity),
                    "cat": finding.category.value if hasattr(finding.category, "value") else str(finding.category),
                    "mode": finding.mode.value if hasattr(finding.mode, "value") else str(finding.mode),
                    "payload": json.dumps(finding.model_dump(mode="json")),
                    "created_at": getattr(finding, "created_at", finding.first_detected_at),
                    "last_eval": finding.last_evaluated_at,
                },
            )
            await sess.commit()
            return finding

    def save_finding(
        self, finding: PolicyFinding, *, tenant_context: TenantContext
    ) -> PolicyFinding:
        return self._run_async(self.save_finding_async(finding, tenant_context=tenant_context))

    async def get_finding_async(
        self, finding_id: str, *, tenant_context: TenantContext
    ) -> PolicyFinding | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM policy_findings WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": finding_id, "tid": tenant_context.tenant_id},
            )
            row = res.first()
            return self._row_to_finding(row) if row else None

    def get_finding(
        self, finding_id: str, *, tenant_context: TenantContext
    ) -> PolicyFinding | None:
        return self._run_async(self.get_finding_async(finding_id, tenant_context=tenant_context))

    async def find_open_finding_async(
        self,
        entity_id: str,
        policy_id: str,
        policy_version: int | None = None,
        *,
        tenant_context: TenantContext,
    ) -> PolicyFinding | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("""
                    SELECT * FROM policy_findings
                    WHERE tenant_id = :tid AND entity_id = :eid AND policy_id = :pid
                      AND lifecycle_status = 'OPEN'
                    ORDER BY last_evaluated_at DESC
                    LIMIT 1;
                """),
                {"tid": tenant_context.tenant_id, "eid": entity_id, "pid": policy_id},
            )
            row = res.first()
            if not row:
                return None
            finding = self._row_to_finding(row)
            if policy_version is not None and finding.policy_version != policy_version:
                return None
            return finding

    def find_open_finding(
        self,
        entity_id: str,
        policy_id: str,
        policy_version: int | None = None,
        *,
        tenant_context: TenantContext,
    ) -> PolicyFinding | None:
        return self._run_async(
            self.find_open_finding_async(
                entity_id, policy_id, policy_version, tenant_context=tenant_context
            )
        )

    async def list_findings_async(
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
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sql = "SELECT * FROM policy_findings WHERE tenant_id = :tid"
            params: dict[str, Any] = {"tid": tenant_context.tenant_id}
            if status:
                sql += " AND lifecycle_status = :st"
                params["st"] = status.value if hasattr(status, "value") else str(status)
            if severity:
                sql += " AND severity = :sev"
                params["sev"] = severity.value if hasattr(severity, "value") else str(severity)
            if category:
                sql += " AND category = :cat"
                params["cat"] = category.value if hasattr(category, "value") else str(category)
            if mode:
                sql += " AND mode = :mode"
                params["mode"] = mode.value if hasattr(mode, "value") else str(mode)
            if policy_id:
                sql += " AND policy_id = :pid"
                params["pid"] = policy_id
            if entity_id:
                sql += " AND entity_id = :eid"
                params["eid"] = entity_id

            sql += " ORDER BY last_evaluated_at DESC;"
            res = await sess.execute(text(sql), params)
            rows = res.fetchall()
            return [self._row_to_finding(r) for r in rows]

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
        return self._run_async(
            self.list_findings_async(
                tenant_context=tenant_context,
                status=status,
                severity=severity,
                category=category,
                mode=mode,
                policy_id=policy_id,
                entity_id=entity_id,
            )
        )

    async def count_findings_async(
        self,
        *,
        tenant_context: TenantContext,
        status: FindingLifecycleStatus | None = None,
    ) -> int:
        """Executes direct SQL SELECT COUNT(*) on policy_findings (Mandate P07)."""
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sql = "SELECT COUNT(*) FROM policy_findings WHERE tenant_id = :tid"
            params: dict[str, Any] = {"tid": tenant_context.tenant_id}
            if status:
                sql += " AND lifecycle_status = :st"
                params["st"] = status.value if hasattr(status, "value") else str(status)
            res = await sess.execute(text(sql), params)
            row = res.first()
            return int(row[0]) if row else 0

    def count_findings(
        self,
        *,
        tenant_context: TenantContext,
        status: FindingLifecycleStatus | None = None,
    ) -> int:
        return self._run_async(self.count_findings_async(tenant_context=tenant_context, status=status))

    async def delete_finding_async(
        self, finding_id: str, *, tenant_context: TenantContext
    ) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("DELETE FROM policy_findings WHERE id = :id AND tenant_id = :tid;"),
                {"id": finding_id, "tid": tenant_context.tenant_id},
            )
            await sess.commit()
            return (res.rowcount or 0) > 0

    def delete_finding(
        self, finding_id: str, *, tenant_context: TenantContext
    ) -> bool:
        return self._run_async(self.delete_finding_async(finding_id, tenant_context=tenant_context))

    # --------------------------------------------------------------------------
    # Exemptions Operations
    # --------------------------------------------------------------------------

    async def save_exemption_async(
        self, exemption: PolicyExemption, *, tenant_context: TenantContext
    ) -> PolicyExemption:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            tid = tenant_context.tenant_id
            query = text("""
                INSERT INTO policy_exemptions (
                    id, tenant_id, policy_id, entity_id, is_active, expires_at,
                    exemption_payload, created_at
                ) VALUES (
                    :id, :tid, :pid, :eid, :active, :exp, CAST(:payload AS jsonb), :created_at
                )
                ON CONFLICT (id) DO UPDATE SET
                    is_active = EXCLUDED.is_active,
                    expires_at = EXCLUDED.expires_at,
                    exemption_payload = EXCLUDED.exemption_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": exemption.id,
                    "tid": tid,
                    "pid": exemption.policy_id,
                    "eid": exemption.entity_id,
                    "active": exemption.is_active(),
                    "exp": exemption.expires_at,
                    "payload": json.dumps(exemption.model_dump(mode="json")),
                    "created_at": exemption.created_at,
                },
            )
            await sess.commit()
            return exemption

    def save_exemption(
        self, exemption: PolicyExemption, *, tenant_context: TenantContext
    ) -> PolicyExemption:
        return self._run_async(self.save_exemption_async(exemption, tenant_context=tenant_context))

    async def get_exemption_async(
        self, exemption_id: str, *, tenant_context: TenantContext
    ) -> PolicyExemption | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("SELECT * FROM policy_exemptions WHERE id = :id AND tenant_id = :tid LIMIT 1;"),
                {"id": exemption_id, "tid": tenant_context.tenant_id},
            )
            row = res.first()
            return self._row_to_exemption(row) if row else None

    def get_exemption(
        self, exemption_id: str, *, tenant_context: TenantContext
    ) -> PolicyExemption | None:
        return self._run_async(self.get_exemption_async(exemption_id, tenant_context=tenant_context))

    async def list_exemptions_async(
        self,
        *,
        tenant_context: TenantContext,
        policy_id: str | None = None,
        entity_id: str | None = None,
        active_only: bool = False,
    ) -> list[PolicyExemption]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sql = "SELECT * FROM policy_exemptions WHERE tenant_id = :tid"
            params: dict[str, Any] = {"tid": tenant_context.tenant_id}
            if policy_id:
                sql += " AND policy_id = :pid"
                params["pid"] = policy_id
            if entity_id:
                sql += " AND entity_id = :eid"
                params["eid"] = entity_id
            if active_only:
                sql += " AND is_active = TRUE AND expires_at > NOW()"
            sql += " ORDER BY expires_at DESC;"
            res = await sess.execute(text(sql), params)
            rows = res.fetchall()
            return [self._row_to_exemption(r) for r in rows]

    def list_exemptions(
        self,
        *,
        tenant_context: TenantContext,
        policy_id: str | None = None,
        entity_id: str | None = None,
        active_only: bool = False,
    ) -> list[PolicyExemption]:
        return self._run_async(
            self.list_exemptions_async(
                tenant_context=tenant_context,
                policy_id=policy_id,
                entity_id=entity_id,
                active_only=active_only,
            )
        )

    async def delete_exemption_async(self, exemption_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            res = await sess.execute(
                text("DELETE FROM policy_exemptions WHERE id = :id AND tenant_id = :tid;"),
                {"id": exemption_id, "tid": tenant_context.tenant_id},
            )
            await sess.commit()
            return res.rowcount > 0

    def delete_exemption(self, exemption_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_exemption_async(exemption_id, tenant_context=tenant_context))


# Singleton instance & factory
_policy_repository_instance: PolicyRepository | None = None


def get_policy_repository() -> PolicyRepository:
    """Returns singleton PolicyRepository with production startup guard."""
    global _policy_repository_instance
    if _policy_repository_instance is None:
        _policy_repository_instance = SqlPolicyRepository()
        verify_persistence_startup_guard(_policy_repository_instance)
    return _policy_repository_instance


def reset_policy_repository(repo: PolicyRepository | None = None) -> None:
    """Resets singleton PolicyRepository for testing."""
    global _policy_repository_instance
    _policy_repository_instance = repo
