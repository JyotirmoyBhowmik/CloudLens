"""Tenant-Scoped Repository for Remediation Tasks, Savings Ledger, and Creation Rules (Prompt 51, Prompt P07).

Enforces:
- Prompt 13 Item 84: 100% TenantContext validation across all repository operations.
- Tenant isolation per BBP Section 41 and SEC-015 via PostgreSQL RLS.
- Protocol + SqlRemediationRepository per docs/persistence-pattern.md.
- Production startup guard verifying no in-memory repositories in staging/production.
"""

from __future__ import annotations

import builtins
import datetime as dt
import json
import logging
import threading
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from domain.models.enums import TaskSource
from domain.remediation.models import (
    RealisedSavingEntry,
    RemediationTask,
    TaskCreationRule,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


@runtime_checkable
class RemediationRepository(Protocol):
    """Authoritative repository protocol for remediation tasks and realised savings."""

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> RemediationTask | None: ...
    def list(
        self,
        *,
        tenant_context: TenantContext,
        state: Any = None,
        priority: Any = None,
        category: Any = None,
        assignee_id: str | None = None,
        source: Any = None,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
        **kwargs: Any,
    ) -> builtins.list[RemediationTask]: ...
    def save(self, entity: RemediationTask, *, tenant_context: TenantContext) -> RemediationTask: ...
    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool: ...
    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool: ...
    def get_by_subject(
        self, entity_type: str, entity_id: str, *, tenant_context: TenantContext
    ) -> builtins.list[RemediationTask]: ...
    def get_by_alert_id(
        self, alert_id: str, *, tenant_context: TenantContext
    ) -> RemediationTask | None: ...
    def get_by_finding_id(
        self, finding_id: str, *, tenant_context: TenantContext
    ) -> RemediationTask | None: ...
    def save_saving_entry(
        self, entry: RealisedSavingEntry, *, tenant_context: TenantContext
    ) -> RealisedSavingEntry: ...
    def list_saving_entries(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[RealisedSavingEntry]: ...
    def get_creation_rule(
        self, source_code: str | TaskSource, *, tenant_context: TenantContext
    ) -> TaskCreationRule | None: ...
    def list_creation_rules(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[TaskCreationRule]: ...
    def save_creation_rule(
        self, rule: TaskCreationRule, *, tenant_context: TenantContext
    ) -> TaskCreationRule: ...


class SqlRemediationRepository:
    """PostgreSQL production implementation with Row-Level Security enforcement."""

    is_in_memory: bool = False

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    def _row_to_task(self, row: Any) -> RemediationTask:
        m = dict(row._mapping)
        raw = m.get("task_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return RemediationTask.model_validate(raw)
        return RemediationTask.model_validate(m)

    def _row_to_saving(self, row: Any) -> RealisedSavingEntry:
        m = dict(row._mapping)
        raw = m.get("ledger_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return RealisedSavingEntry.model_validate(raw)
        return RealisedSavingEntry.model_validate(m)

    def _row_to_rule(self, row: Any) -> TaskCreationRule:
        m = dict(row._mapping)
        raw = m.get("rule_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "source_code" in raw:
            return TaskCreationRule.model_validate(raw)
        return TaskCreationRule.model_validate(m)

    # =========================================================================
    # Task Operations
    # =========================================================================

    async def get_async(self, entity_id: str, *, tenant_context: TenantContext) -> RemediationTask | None:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                SELECT * FROM remediation_tasks
                WHERE id = :id AND tenant_id = :tid
                LIMIT 1;
            """)
            res = await sess.execute(query, {"id": entity_id, "tid": tenant_context.tenant_id})
            row = res.fetchone()
            if not row:
                return None
            return self._row_to_task(row)

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> RemediationTask | None:
        return self._run_async(self.get_async(entity_id, tenant_context=tenant_context))

    async def list_async(
        self,
        *,
        tenant_context: TenantContext,
        state: Any = None,
        priority: Any = None,
        category: Any = None,
        assignee_id: str | None = None,
        source: Any = None,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
        **kwargs: Any,
    ) -> builtins.list[RemediationTask]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            sql = ["SELECT * FROM remediation_tasks WHERE tenant_id = :tid"]
            params: dict[str, Any] = {"tid": tenant_context.tenant_id}

            filters = (
                dict(filter_params) if (filter_params and isinstance(filter_params, dict)) else {}
            )
            if state is not None:
                filters["state"] = state
            if priority is not None:
                filters["priority"] = priority
            if category is not None:
                filters["category"] = category
            if assignee_id is not None:
                filters["assignee_id"] = assignee_id
            if source is not None:
                filters["source"] = source
            filters.update(kwargs)

            if "state" in filters and filters["state"]:
                st = filters["state"]
                sql.append("AND state = :state")
                params["state"] = st.value if hasattr(st, "value") else str(st)
            if "priority" in filters and filters["priority"]:
                prio = filters["priority"]
                sql.append("AND priority = :priority")
                params["priority"] = prio.value if hasattr(prio, "value") else str(prio)
            if "category" in filters and filters["category"]:
                cat = filters["category"]
                sql.append("AND category = :category")
                params["category"] = cat.value if hasattr(cat, "value") else str(cat)
            if "assignee_id" in filters and filters["assignee_id"]:
                sql.append("AND assignee_id = :assignee_id")
                params["assignee_id"] = str(filters["assignee_id"])

            sql.append("ORDER BY created_at DESC LIMIT :limit OFFSET :offset;")
            params["limit"] = limit
            params["offset"] = offset

            res = await sess.execute(text(" ".join(sql)), params)
            rows = res.fetchall()
            items = [self._row_to_task(r) for r in rows]

            if "source" in filters and filters["source"]:
                src = filters["source"]
                src_val = src.value if hasattr(src, "value") else str(src)
                items = [t for t in items if (t.source.value if hasattr(t.source, "value") else str(t.source)) == src_val]

            return items

    def list(
        self,
        *,
        tenant_context: TenantContext,
        state: Any = None,
        priority: Any = None,
        category: Any = None,
        assignee_id: str | None = None,
        source: Any = None,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
        **kwargs: Any,
    ) -> builtins.list[RemediationTask]:
        return self._run_async(
            self.list_async(
                tenant_context=tenant_context,
                state=state,
                priority=priority,
                category=category,
                assignee_id=assignee_id,
                source=source,
                filter_params=filter_params,
                limit=limit,
                offset=offset,
                **kwargs,
            )
        )

    async def save_async(self, entity: RemediationTask, *, tenant_context: TenantContext) -> RemediationTask:
        entity.tenant_id = tenant_context.tenant_id
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            state_val = entity.state.value if hasattr(entity.state, "value") else str(entity.state)
            priority_val = entity.priority.value if hasattr(entity.priority, "value") else str(entity.priority)
            cat_val = entity.category.value if hasattr(entity.category, "value") else str(entity.category)

            query = text("""
                INSERT INTO remediation_tasks (
                    id, tenant_id, title, state, priority, category, assignee_id,
                    task_payload, created_at, updated_at
                ) VALUES (
                    :id, :tid, :title, :state, :priority, :category, :assignee_id,
                    CAST(:payload AS JSONB), :created_at, :updated_at
                )
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    state = EXCLUDED.state,
                    priority = EXCLUDED.priority,
                    category = EXCLUDED.category,
                    assignee_id = EXCLUDED.assignee_id,
                    task_payload = EXCLUDED.task_payload,
                    updated_at = EXCLUDED.updated_at;
            """)
            await sess.execute(
                query,
                {
                    "id": entity.id,
                    "tid": tenant_context.tenant_id,
                    "title": entity.title,
                    "state": state_val,
                    "priority": priority_val,
                    "category": cat_val,
                    "assignee_id": entity.assignee_id,
                    "payload": json.dumps(entity.model_dump(mode="json")),
                    "created_at": entity.created_at,
                    "updated_at": entity.updated_at,
                },
            )
            await sess.commit()
            return entity

    def save(self, entity: RemediationTask, *, tenant_context: TenantContext) -> RemediationTask:
        return self._run_async(self.save_async(entity, tenant_context=tenant_context))

    async def delete_async(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("DELETE FROM remediation_tasks WHERE id = :id AND tenant_id = :tid;")
            res = await sess.execute(query, {"id": entity_id, "tid": tenant_context.tenant_id})
            await sess.commit()
            return (res.rowcount or 0) > 0

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.delete_async(entity_id, tenant_context=tenant_context))

    async def exists_async(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("SELECT 1 FROM remediation_tasks WHERE id = :id AND tenant_id = :tid LIMIT 1;")
            res = await sess.execute(query, {"id": entity_id, "tid": tenant_context.tenant_id})
            return res.fetchone() is not None

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        return self._run_async(self.exists_async(entity_id, tenant_context=tenant_context))

    async def get_by_subject_async(
        self, entity_type: str, entity_id: str, *, tenant_context: TenantContext
    ) -> builtins.list[RemediationTask]:
        all_tasks = await self.list_async(tenant_context=tenant_context, limit=1000)
        return [
            t for t in all_tasks
            if t.subject_entity.entity_type == entity_type and t.subject_entity.entity_id == entity_id
        ]

    def get_by_subject(
        self, entity_type: str, entity_id: str, *, tenant_context: TenantContext
    ) -> builtins.list[RemediationTask]:
        return self._run_async(
            self.get_by_subject_async(entity_type, entity_id, tenant_context=tenant_context)
        )

    async def get_by_alert_id_async(
        self, alert_id: str, *, tenant_context: TenantContext
    ) -> RemediationTask | None:
        all_tasks = await self.list_async(tenant_context=tenant_context, limit=1000)
        for t in all_tasks:
            if t.alert_id == alert_id:
                return t
        return None

    def get_by_alert_id(
        self, alert_id: str, *, tenant_context: TenantContext
    ) -> RemediationTask | None:
        return self._run_async(self.get_by_alert_id_async(alert_id, tenant_context=tenant_context))

    async def get_by_finding_id_async(
        self, finding_id: str, *, tenant_context: TenantContext
    ) -> RemediationTask | None:
        all_tasks = await self.list_async(tenant_context=tenant_context, limit=1000)
        for t in all_tasks:
            if t.finding_id == finding_id:
                return t
        return None

    def get_by_finding_id(
        self, finding_id: str, *, tenant_context: TenantContext
    ) -> RemediationTask | None:
        return self._run_async(self.get_by_finding_id_async(finding_id, tenant_context=tenant_context))

    # =========================================================================
    # Savings Ledger Operations
    # =========================================================================

    async def save_saving_entry_async(
        self, entry: RealisedSavingEntry, *, tenant_context: TenantContext
    ) -> RealisedSavingEntry:
        entry.tenant_id = tenant_context.tenant_id
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                INSERT INTO remediation_savings_ledger (
                    id, tenant_id, task_id, amount, currency, ledger_payload, recorded_at
                ) VALUES (
                    :id, :tid, :task_id, :amount, :currency, CAST(:payload AS JSONB), :recorded_at
                )
                ON CONFLICT (id) DO UPDATE SET
                    amount = EXCLUDED.amount,
                    currency = EXCLUDED.currency,
                    ledger_payload = EXCLUDED.ledger_payload;
            """)
            amt = getattr(entry, "realised_amount", getattr(entry, "amount", 0.0))
            rec_dt = getattr(entry, "verified_at", getattr(entry, "recorded_at", dt.datetime.now(dt.timezone.utc)))
            await sess.execute(
                query,
                {
                    "id": entry.id,
                    "tid": tenant_context.tenant_id,
                    "task_id": entry.task_id,
                    "amount": amt,
                    "currency": entry.currency,
                    "payload": json.dumps(entry.model_dump(mode="json")),
                    "recorded_at": rec_dt,
                },
            )
            await sess.commit()
            return entry

    def save_saving_entry(
        self, entry: RealisedSavingEntry, *, tenant_context: TenantContext
    ) -> RealisedSavingEntry:
        return self._run_async(self.save_saving_entry_async(entry, tenant_context=tenant_context))

    async def list_saving_entries_async(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[RealisedSavingEntry]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                SELECT * FROM remediation_savings_ledger
                WHERE tenant_id = :tid
                ORDER BY recorded_at DESC;
            """)
            res = await sess.execute(query, {"tid": tenant_context.tenant_id})
            rows = res.fetchall()
            return [self._row_to_saving(r) for r in rows]

    def list_saving_entries(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[RealisedSavingEntry]:
        return self._run_async(self.list_saving_entries_async(tenant_context=tenant_context))

    # =========================================================================
    # Creation Rules Operations
    # =========================================================================

    async def get_creation_rule_async(
        self, source_code: str | TaskSource, *, tenant_context: TenantContext
    ) -> TaskCreationRule | None:
        sc = source_code.value if hasattr(source_code, "value") else str(source_code)
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                SELECT * FROM remediation_rules
                WHERE tenant_id = :tid AND UPPER(source_code) = :sc
                LIMIT 1;
            """)
            res = await sess.execute(query, {"tid": tenant_context.tenant_id, "sc": sc.upper()})
            row = res.fetchone()
            if row:
                return self._row_to_rule(row)
            return None

    def get_creation_rule(
        self, source_code: str | TaskSource, *, tenant_context: TenantContext
    ) -> TaskCreationRule | None:
        return self._run_async(self.get_creation_rule_async(source_code, tenant_context=tenant_context))

    async def list_creation_rules_async(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[TaskCreationRule]:
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                SELECT * FROM remediation_rules
                WHERE tenant_id = :tid
                ORDER BY created_at ASC;
            """)
            res = await sess.execute(query, {"tid": tenant_context.tenant_id})
            rows = res.fetchall()
            return [self._row_to_rule(r) for r in rows]

    def list_creation_rules(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[TaskCreationRule]:
        return self._run_async(self.list_creation_rules_async(tenant_context=tenant_context))

    async def save_creation_rule_async(
        self, rule: TaskCreationRule, *, tenant_context: TenantContext
    ) -> TaskCreationRule:
        rule_id = getattr(rule, "id", f"rule-{rule.source_code.value.lower()}")
        async with get_tenant_session(tenant_context.tenant_id) as sess:
            query = text("""
                INSERT INTO remediation_rules (
                    id, tenant_id, source_code, name, rule_payload, created_at
                ) VALUES (
                    :id, :tid, :source_code, :name, CAST(:payload AS JSONB), NOW()
                )
                ON CONFLICT (id) DO UPDATE SET
                    source_code = EXCLUDED.source_code,
                    name = EXCLUDED.name,
                    rule_payload = EXCLUDED.rule_payload;
            """)
            await sess.execute(
                query,
                {
                    "id": rule_id,
                    "tid": tenant_context.tenant_id,
                    "source_code": rule.source_code.value.upper(),
                    "name": rule.name,
                    "payload": json.dumps(rule.model_dump(mode="json")),
                },
            )
            await sess.commit()
            return rule

    def save_creation_rule(
        self, rule: TaskCreationRule, *, tenant_context: TenantContext
    ) -> TaskCreationRule:
        return self._run_async(self.save_creation_rule_async(rule, tenant_context=tenant_context))


# Global singleton instance for repository operation
_GLOBAL_REMEDIATION_REPOSITORY: RemediationRepository | None = None
_REPO_LOCK = threading.Lock()


def get_remediation_repository() -> RemediationRepository:
    """Returns the singleton instance of RemediationRepository (SqlRemediationRepository by default)."""
    global _GLOBAL_REMEDIATION_REPOSITORY
    with _REPO_LOCK:
        if _GLOBAL_REMEDIATION_REPOSITORY is None:
            repo = SqlRemediationRepository()
            verify_persistence_startup_guard(repo)
            _GLOBAL_REMEDIATION_REPOSITORY = repo
        return _GLOBAL_REMEDIATION_REPOSITORY


def reset_remediation_repository(repo: RemediationRepository | None = None) -> None:
    """Resets the singleton instance (for clean test isolation)."""
    global _GLOBAL_REMEDIATION_REPOSITORY
    with _REPO_LOCK:
        _GLOBAL_REMEDIATION_REPOSITORY = repo
