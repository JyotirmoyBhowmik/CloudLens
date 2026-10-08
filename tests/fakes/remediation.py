"""In-memory test fake for RemediationRepository (Prompt P07 / Prompt 51)."""

from __future__ import annotations

import builtins
import threading
from typing import Any

from domain.models.enums import TaskSource
from domain.remediation.models import (
    RealisedSavingEntry,
    RemediationTask,
    TaskCreationRule,
)
from domain.tenant.context import TenantContext


class InMemoryRemediationRepository:
    """Thread-safe, in-memory repository fake for test environments."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[tuple[str, str], RemediationTask] = {}
        self._savings: dict[tuple[str, str], RealisedSavingEntry] = {}
        self._rules: dict[tuple[str, str], TaskCreationRule] = {}

    def _validate_tenant_context(self, tenant_context: TenantContext) -> None:
        if not tenant_context or not tenant_context.tenant_id:
            raise ValueError("Operation requires valid TenantContext with non-empty tenant_id.")

    def get(self, entity_id: str, *, tenant_context: TenantContext) -> RemediationTask | None:
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

            items.sort(key=lambda t: t.created_at, reverse=True)
            page = items[offset : offset + limit]
            return [t.model_copy(deep=True) for t in page]

    def save(self, entity: RemediationTask, *, tenant_context: TenantContext) -> RemediationTask:
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        entity.tenant_id = t_id
        with self._lock:
            self._tasks[(t_id, entity.id)] = entity.model_copy(deep=True)
            return entity.model_copy(deep=True)

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            key = (tenant_context.tenant_id, entity_id)
            if key in self._tasks:
                del self._tasks[key]
                return True
            return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        self._validate_tenant_context(tenant_context)
        with self._lock:
            return (tenant_context.tenant_id, entity_id) in self._tasks

    def get_by_subject(
        self, entity_type: str, entity_id: str, *, tenant_context: TenantContext
    ) -> builtins.list[RemediationTask]:
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
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        with self._lock:
            for (tid, _), t in self._tasks.items():
                if tid == t_id and t.finding_id == finding_id:
                    return t.model_copy(deep=True)
            return None

    def save_saving_entry(
        self, entry: RealisedSavingEntry, *, tenant_context: TenantContext
    ) -> RealisedSavingEntry:
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        entry.tenant_id = t_id
        with self._lock:
            self._savings[(t_id, entry.id)] = entry.model_copy(deep=True)
            return entry.model_copy(deep=True)

    def list_saving_entries(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[RealisedSavingEntry]:
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        with self._lock:
            return [
                entry.model_copy(deep=True)
                for (tid, _), entry in self._savings.items()
                if tid == t_id
            ]

    def get_creation_rule(
        self, source_code: str | TaskSource, *, tenant_context: TenantContext
    ) -> TaskCreationRule | None:
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
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        with self._lock:
            rules_by_code: dict[str, TaskCreationRule] = {}
            for (scope, sc), r in self._rules.items():
                if scope == "SYSTEM":
                    rules_by_code[sc] = r.model_copy(deep=True)
            for (scope, sc), r in self._rules.items():
                if scope == t_id:
                    rules_by_code[sc] = r.model_copy(deep=True)
            return builtins.list(rules_by_code.values())

    def save_creation_rule(
        self, rule: TaskCreationRule, *, tenant_context: TenantContext
    ) -> TaskCreationRule:
        self._validate_tenant_context(tenant_context)
        t_id = tenant_context.tenant_id
        with self._lock:
            self._rules[(t_id, rule.source_code.value.upper())] = rule.model_copy(deep=True)
            return rule.model_copy(deep=True)
