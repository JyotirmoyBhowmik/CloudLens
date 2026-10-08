"""In-memory test fake for DependencyRepository (Prompt P07 / Prompt 32)."""

from __future__ import annotations

import copy
import datetime as dt
import logging

from domain.dependency.models import DependencyEdge, EdgeConflict
from domain.models.enums import EdgeStatus, RelationshipType
from domain.tenant.context import TenantContext, require_tenant_context

logger = logging.getLogger(__name__)


class InMemoryDependencyRepository:
    """Thread-safe tenant-partitioned repository fake for dependency graph edges and conflicts."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._edges: dict[str, dict[str, DependencyEdge]] = {}
        self._conflicts: dict[str, dict[str, EdgeConflict]] = {}
        self._history: dict[str, dict[str, list[DependencyEdge]]] = {}

    def _get_tenant_edges(self, tenant_id: str) -> dict[str, DependencyEdge]:
        if tenant_id not in self._edges:
            self._edges[tenant_id] = {}
        return self._edges[tenant_id]

    def _get_tenant_conflicts(self, tenant_id: str) -> dict[str, EdgeConflict]:
        if tenant_id not in self._conflicts:
            self._conflicts[tenant_id] = {}
        return self._conflicts[tenant_id]

    def _get_tenant_history(self, tenant_id: str) -> dict[str, list[DependencyEdge]]:
        if tenant_id not in self._history:
            self._history[tenant_id] = {}
        return self._history[tenant_id]

    def save_edge(self, edge: DependencyEdge, *, tenant_context: TenantContext) -> DependencyEdge:
        tc = require_tenant_context(tenant_context)
        t_edges = self._get_tenant_edges(tc.tenant_id)
        t_history = self._get_tenant_history(tc.tenant_id)

        if edge.id in t_edges:
            existing = t_edges[edge.id]
            if edge.id not in t_history:
                t_history[edge.id] = []
            t_history[edge.id].append(copy.deepcopy(existing))

        t_edges[edge.id] = copy.deepcopy(edge)
        return copy.deepcopy(edge)

    def get_edge(self, edge_id: str, *, tenant_context: TenantContext) -> DependencyEdge | None:
        tc = require_tenant_context(tenant_context)
        t_edges = self._get_tenant_edges(tc.tenant_id)
        edge = t_edges.get(edge_id)
        return copy.deepcopy(edge) if edge else None

    def find_edge(
        self,
        source_id: str,
        target_id: str,
        relationship_type: RelationshipType | None = None,
        *,
        tenant_context: TenantContext,
    ) -> DependencyEdge | None:
        tc = require_tenant_context(tenant_context)
        t_edges = self._get_tenant_edges(tc.tenant_id)
        for edge in t_edges.values():
            if edge.source_ref.entity_id == source_id and edge.target_ref.entity_id == target_id:
                if relationship_type is None or edge.relationship_type == relationship_type:
                    return copy.deepcopy(edge)
        return None

    def list_edges(
        self,
        *,
        tenant_context: TenantContext,
        status: EdgeStatus | None = None,
        relationship_type: RelationshipType | None = None,
        as_of: dt.datetime | None = None,
        source_id: str | None = None,
        target_id: str | None = None,
        include_history: bool = False,
        include_deleted: bool = False,
        limit: int = 1000,
    ) -> list[DependencyEdge]:
        tc = require_tenant_context(tenant_context)
        t_edges = self._get_tenant_edges(tc.tenant_id)
        results: list[DependencyEdge] = []

        if as_of is not None:
            candidates: list[DependencyEdge] = list(t_edges.values())
            t_history = self._get_tenant_history(tc.tenant_id)
            for hist_list in t_history.values():
                candidates.extend(hist_list)

            matched_by_id: dict[str, DependencyEdge] = {}
            for cand in candidates:
                if cand.effective_from <= as_of:
                    if cand.effective_to is None or cand.effective_to > as_of:
                        existing = matched_by_id.get(cand.id)
                        if existing is None or cand.effective_from >= existing.effective_from:
                            matched_by_id[cand.id] = cand

            results = list(matched_by_id.values())
        else:
            results = list(t_edges.values())

        if status is not None:
            results = [e for e in results if e.status == status]
        elif as_of is None and not include_history and not include_deleted:
            results = [
                e for e in results if e.status not in (EdgeStatus.DELETED, EdgeStatus.SUPERSEDED)
            ]

        if relationship_type is not None:
            results = [e for e in results if e.relationship_type == relationship_type]

        if source_id is not None:
            results = [e for e in results if e.source_ref.entity_id == source_id]

        if target_id is not None:
            results = [e for e in results if e.target_ref.entity_id == target_id]

        results.sort(key=lambda x: x.last_seen, reverse=True)
        return [copy.deepcopy(e) for e in results[:limit]]

    def get_edge_history(
        self, edge_id: str, *, tenant_context: TenantContext
    ) -> list[DependencyEdge]:
        tc = require_tenant_context(tenant_context)
        t_history = self._get_tenant_history(tc.tenant_id)
        versions = t_history.get(edge_id, [])
        t_edges = self._get_tenant_edges(tc.tenant_id)
        current = t_edges.get(edge_id)
        combined = list(versions)
        if current:
            combined.append(current)
        combined.sort(key=lambda x: x.effective_from)
        return [copy.deepcopy(v) for v in combined]

    def delete_edge(
        self, edge_id: str, *, tenant_context: TenantContext, hard: bool = False
    ) -> bool:
        tc = require_tenant_context(tenant_context)
        t_edges = self._get_tenant_edges(tc.tenant_id)
        edge = t_edges.get(edge_id)
        if not edge:
            return False

        if hard:
            del t_edges[edge_id]
            return True

        now = dt.datetime.now(dt.UTC)
        edge.status = EdgeStatus.DELETED
        edge.effective_to = now
        edge.add_history(
            action="DELETED",
            actor_id=tenant_context.user_id or "system",
            to_status=EdgeStatus.DELETED.value,
            note="Edge marked deleted",
        )
        self.save_edge(edge, tenant_context=tc)
        return True

    def save_conflict(
        self, conflict: EdgeConflict, *, tenant_context: TenantContext
    ) -> EdgeConflict:
        tc = require_tenant_context(tenant_context)
        t_conflicts = self._get_tenant_conflicts(tc.tenant_id)
        t_conflicts[conflict.conflict_id] = copy.deepcopy(conflict)
        return copy.deepcopy(conflict)

    def get_conflict(
        self, conflict_id: str, *, tenant_context: TenantContext
    ) -> EdgeConflict | None:
        tc = require_tenant_context(tenant_context)
        t_conflicts = self._get_tenant_conflicts(tc.tenant_id)
        conf = t_conflicts.get(conflict_id)
        return copy.deepcopy(conf) if conf else None

    def list_conflicts(
        self, *, tenant_context: TenantContext, unresolved_only: bool = True
    ) -> list[EdgeConflict]:
        tc = require_tenant_context(tenant_context)
        t_conflicts = self._get_tenant_conflicts(tc.tenant_id)
        results = list(t_conflicts.values())
        if unresolved_only:
            results = [c for c in results if not c.is_resolved]
        results.sort(key=lambda x: x.detected_at, reverse=True)
        return [copy.deepcopy(c) for c in results]
