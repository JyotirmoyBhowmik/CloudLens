"""Tenant-Scoped Repository for Remediation Tasks, Savings Ledger, and Creation Rules (Prompt 51).

Enforces:
- Prompt 13 Item 84: 100% TenantContext validation across all repository operations.
- Tenant isolation per BBP Section 41 and SEC-015.
- Mechanical scoping and audit integrity.
"""

from __future__ import annotations

import builtins
import logging
import threading
from typing import Any

from domain.models.enums import TaskSource
from domain.remediation.models import (
    RealisedSavingEntry,
    RemediationTask,
    TaskCreationRule,
)
from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository

logger = logging.getLogger(__name__)


class RemediationRepository(TenantAwareRepository[RemediationTask]):
    """Thread-safe, tenant-isolated repository for remediation tasks and realised savings."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # Key: (tenant_id, task_id) -> RemediationTask
        self._tasks: dict[tuple[str, str], RemediationTask] = {}
        # Key: (tenant_id, saving_id) -> RealisedSavingEntry
        self._savings: dict[tuple[str, str], RealisedSavingEntry] = {}
        # Key: (tenant_id or "SYSTEM", source_code) -> TaskCreationRule
        self._rules: dict[tuple[str, str], TaskCreationRule] = {}

    # ==========================================================================
    # 1. RemediationTask CRUD (TenantAwareRepository Implementation)
    # ==========================================================================

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> RemediationTask | None:
        """Retrieves a single remediation task by ID within tenant boundary."""
        self._validate_tenant_context(tenant_context)
        with self._lock:
            task = self._tasks.get((tenant_context.tenant_id, entity_id))
            return task.model_copy(deep=True) if task else None

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
        """Lists remediation tasks belonging strictly to the tenant with optional filtering."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id

        with self._lock:
            items = [t for (tid, _), t in self._tasks.items() if tid == t_id]

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

            if filters:
                if "state" in filters and filters["state"]:
                    st = filters["state"]
                    items = [t for t in items if t.state == st or t.state.value == str(st)]
                if "category" in filters and filters["category"]:
                    cat = filters["category"]
                    items = [t for t in items if t.category == cat or t.category.value == str(cat)]
                if "priority" in filters and filters["priority"]:
                    prio = filters["priority"]
                    items = [
                        t for t in items if t.priority == prio or t.priority.value == str(prio)
                    ]
                if "assignee_id" in filters and filters["assignee_id"]:
                    items = [t for t in items if t.assignee_id == filters["assignee_id"]]
                if "source" in filters and filters["source"]:
                    src = filters["source"]
                    items = [t for t in items if t.source == src or t.source.value == str(src)]

            # Sort latest first
            items.sort(key=lambda t: t.created_at, reverse=True)
            page = items[offset : offset + limit]
            return [t.model_copy(deep=True) for t in page]

    def save(self, entity: RemediationTask, *, tenant_context: TenantContext) -> RemediationTask:
        """Saves or updates a remediation task, enforcing tenant ownership."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id

        entity.tenant_id = t_id
        with self._lock:
            self._tasks[(t_id, entity.id)] = entity.model_copy(deep=True)
            return entity.model_copy(deep=True)

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Removes a remediation task within the tenant boundary."""
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, entity_id)
            if key in self._tasks:
                del self._tasks[key]
                return True
            return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Checks if a remediation task exists within the tenant context."""
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return (tenant_context.tenant_id, entity_id) in self._tasks

    # ==========================================================================
    # 2. Entity & Alert Indexes
    # ==========================================================================

    def get_by_subject(
        self, entity_type: str, entity_id: str, *, tenant_context: TenantContext
    ) -> builtins.list[RemediationTask]:
        """Retrieves all tasks targeting a specific subject entity."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        with self._lock:
            return [
                t.model_copy(deep=True)
                for (tid, _), t in self._tasks.items()
                if tid == t_id
                and t.subject_entity.entity_type == entity_type
                and t.subject_entity.entity_id == entity_id
            ]

    def get_by_alert_id(
        self, alert_id: str, *, tenant_context: TenantContext
    ) -> RemediationTask | None:
        """Retrieves the task linked to a given alert ID."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        with self._lock:
            for (tid, _), t in self._tasks.items():
                if tid == t_id and t.alert_id == alert_id:
                    return t.model_copy(deep=True)
            return None

    def get_by_finding_id(
        self, finding_id: str, *, tenant_context: TenantContext
    ) -> RemediationTask | None:
        """Retrieves the task linked to a given policy finding ID."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        with self._lock:
            for (tid, _), t in self._tasks.items():
                if tid == t_id and t.finding_id == finding_id:
                    return t.model_copy(deep=True)
            return None

    # ==========================================================================
    # 3. Realised-Saving Ledger Persistence
    # ==========================================================================

    def save_saving_entry(
        self, entry: RealisedSavingEntry, *, tenant_context: TenantContext
    ) -> RealisedSavingEntry:
        """Appends an empirical realised saving entry into the tenant ledger."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        entry.tenant_id = t_id
        with self._lock:
            self._savings[(t_id, entry.id)] = entry.model_copy(deep=True)
            return entry.model_copy(deep=True)

    def list_saving_entries(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[RealisedSavingEntry]:
        """Returns all realised saving records for the tenant."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        with self._lock:
            return [
                entry.model_copy(deep=True)
                for (tid, _), entry in self._savings.items()
                if tid == t_id
            ]

    # ==========================================================================
    # 4. Master Data Creation Rules
    # ==========================================================================

    def get_creation_rule(
        self, source_code: str | TaskSource, *, tenant_context: TenantContext
    ) -> TaskCreationRule | None:
        """Retrieves task creation rule by source, resolving tenant override over default."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        sc = source_code.value if hasattr(source_code, "value") else str(source_code)
        with self._lock:
            if (t_id, sc.upper()) in self._rules:
                return self._rules[(t_id, sc.upper())].model_copy(deep=True)
            if ("SYSTEM", sc.upper()) in self._rules:
                return self._rules[("SYSTEM", sc.upper())].model_copy(deep=True)
            return None

    def list_creation_rules(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[TaskCreationRule]:
        """Lists active task creation rules for the tenant."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        with self._lock:
            rules_by_code: dict[str, TaskCreationRule] = {}
            # Global defaults first
            for (scope, sc), r in self._rules.items():
                if scope == "SYSTEM":
                    rules_by_code[sc] = r.model_copy(deep=True)
            # Tenant overrides second
            for (scope, sc), r in self._rules.items():
                if scope == t_id:
                    rules_by_code[sc] = r.model_copy(deep=True)
            return builtins.list(rules_by_code.values())

    def save_creation_rule(
        self, rule: TaskCreationRule, *, tenant_context: TenantContext
    ) -> TaskCreationRule:
        """Stores a tenant-scoped or global task creation rule."""
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        with self._lock:
            self._rules[(t_id, rule.source_code.value.upper())] = rule.model_copy(deep=True)
            return rule.model_copy(deep=True)


# Global singleton instance for in-memory operation & testing
_GLOBAL_REMEDIATION_REPOSITORY: RemediationRepository | None = None
_REPO_LOCK = threading.Lock()


def get_remediation_repository() -> RemediationRepository:
    """Returns the singleton instance of RemediationRepository."""
    global _GLOBAL_REMEDIATION_REPOSITORY
    with _REPO_LOCK:
        if _GLOBAL_REMEDIATION_REPOSITORY is None:
            _GLOBAL_REMEDIATION_REPOSITORY = RemediationRepository()
        return _GLOBAL_REMEDIATION_REPOSITORY


def reset_remediation_repository() -> None:
    """Resets the singleton instance (for clean test isolation)."""
    global _GLOBAL_REMEDIATION_REPOSITORY
    with _REPO_LOCK:
        _GLOBAL_REMEDIATION_REPOSITORY = None
