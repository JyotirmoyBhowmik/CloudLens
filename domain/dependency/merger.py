"""Edge Merge Engine & Conflict Resolution Engine (Prompt 32).

Enforces BBP Section 24:
1. "A discovered edge never silently overwrites a manual edge. Conflicts are surfaced
   for human resolution with both versions visible."
2. A manually created edge persists through subsequent discovery runs and is labelled Manual.
3. Discovered edge confirming a manual edge updates last_seen without stripping the Manual label.
4. Surfaced conflicts store both manual_version and discovered_version with explicit resolution workflows.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid

from domain.dependency.models import (
    ConflictResolveRequest,
    DependencyEdge,
    EdgeConflict,
)
from domain.dependency.repository import DependencyRepository
from domain.models.enums import (
    ConflictResolutionAction,
    EdgeStatus,
    RelationshipType,
)
from domain.models.exceptions import (
    DependencyConflictException,
    DependencyEdgeNotFoundException,
)
from domain.tenant.context import TenantContext, require_tenant_context

logger = logging.getLogger(__name__)


class EdgeMergeEngine:
    """Manages merging discovered and imported edges against existing manual/curated edges."""

    def __init__(self, repository: DependencyRepository) -> None:
        self.repository = repository

    def merge_candidate_edge(
        self, candidate: DependencyEdge, *, tenant_context: TenantContext
    ) -> tuple[DependencyEdge, EdgeConflict | None]:
        """Merges a newly discovered or imported candidate edge against existing edges.

        Rules:
        - Never silently overwrite a manual edge.
        - If matching manual edge exists: update last_seen, keep provenance MANUAL.
        - If conflicting manual edge exists: surface conflict with both versions visible.
        - If existing edge is discovered: update last_seen and attributes.
        - If no existing edge: persist candidate as ACTIVE.
        """
        tc = require_tenant_context(tenant_context)
        now = dt.datetime.now(dt.UTC)

        # 1. Look for existing edge between identical source and target
        exact_match = self.repository.find_edge(
            source_id=candidate.source_ref.entity_id,
            target_id=candidate.target_ref.entity_id,
            tenant_context=tc,
        )

        if exact_match is not None:
            # Case 1A: Exact match on a manual edge
            if exact_match.is_manual:
                if exact_match.relationship_type == candidate.relationship_type:
                    # Discovered edge confirms the manual edge!
                    # Rule: A manually created edge persists through subsequent discovery runs and is labelled Manual.
                    exact_match.last_seen = now
                    exact_match.add_history(
                        action="DISCOVERY_CONFIRMED",
                        actor_id=candidate.provenance.rule_id or "discovery-engine",
                        note=f"Discovered edge confirmed manual relationship '{candidate.relationship_type.value}'.",
                    )
                    saved = self.repository.save_edge(exact_match, tenant_context=tc)
                    logger.info(
                        f"Discovery confirmed existing manual edge '{saved.id}' [Source: {saved.source_ref.entity_id}, Target: {saved.target_ref.entity_id}]. Label remains Manual."
                    )
                    return saved, None
                else:
                    # Conflicting relationship type between same entities
                    return self._surface_conflict(
                        manual_edge=exact_match,
                        discovered_edge=candidate,
                        reason=(
                            f"Discovered relationship type '{candidate.relationship_type.value}' "
                            f"conflicts with manual assertion '{exact_match.relationship_type.value}'."
                        ),
                        tenant_context=tc,
                    )

            # Case 1B: Exact match on an existing discovered or imported edge
            else:
                exact_match.last_seen = now
                exact_match.confidence = candidate.confidence
                exact_match.criticality = candidate.criticality
                if candidate.billing_attributes:
                    exact_match.billing_attributes = candidate.billing_attributes
                if exact_match.status == EdgeStatus.STALE:
                    exact_match.status = EdgeStatus.ACTIVE
                    exact_match.add_history(
                        action="STALE_REVIVED",
                        actor_id=candidate.provenance.rule_id or "discovery-engine",
                        to_status=EdgeStatus.ACTIVE.value,
                        note="Stale edge revived upon re-observation.",
                    )
                saved = self.repository.save_edge(exact_match, tenant_context=tc)
                return saved, None

        # 2. Look for existing edges where the same source has a single-target relationship
        # that contradicts the candidate (e.g. PARENT_CHILD or PRIMARY APPLICATION_DEPENDENCY)
        single_target_types = {
            RelationshipType.PARENT_CHILD,
            RelationshipType.APPLICATION_DEPENDENCY,
        }
        if candidate.relationship_type in single_target_types:
            existing_edges = self.repository.list_edges(
                source_id=candidate.source_ref.entity_id,
                relationship_type=candidate.relationship_type,
                tenant_context=tc,
            )
            for existing in existing_edges:
                if (
                    existing.is_manual
                    and existing.target_ref.entity_id != candidate.target_ref.entity_id
                ):
                    # Conflict: Manual says parent/app is X, discovered says parent/app is Y!
                    return self._surface_conflict(
                        manual_edge=existing,
                        discovered_edge=candidate,
                        reason=(
                            f"Discovered target '{candidate.target_ref.entity_id}' conflicts with "
                            f"manually asserted target '{existing.target_ref.entity_id}' for {candidate.relationship_type.value}."
                        ),
                        tenant_context=tc,
                    )

        # 3. No existing conflicting or exact edge: Persist discovered edge
        candidate.first_seen = candidate.first_seen or now
        candidate.last_seen = now
        candidate.effective_from = candidate.effective_from or now
        candidate.status = EdgeStatus.ACTIVE
        candidate.add_history(
            action="DISCOVERED",
            actor_id=candidate.provenance.rule_id or "discovery-engine",
            to_status=EdgeStatus.ACTIVE.value,
            note=f"Discovered via {candidate.provenance.layer.value if candidate.provenance.layer else 'unknown layer'}.",
        )
        saved = self.repository.save_edge(candidate, tenant_context=tc)
        return saved, None

    def _surface_conflict(
        self,
        manual_edge: DependencyEdge,
        discovered_edge: DependencyEdge,
        reason: str,
        *,
        tenant_context: TenantContext,
    ) -> tuple[DependencyEdge, EdgeConflict]:
        """Creates a surfaced conflict, marks edge status, and preserves both versions."""
        tc = require_tenant_context(tenant_context)
        now = dt.datetime.now(dt.UTC)
        conflict_id = f"conf-{uuid.uuid4().hex[:10]}"

        # Save candidate edge with status CONFLICT
        discovered_edge.status = EdgeStatus.CONFLICT
        discovered_edge.conflict_id = conflict_id
        discovered_edge.last_seen = now
        discovered_edge.add_history(
            action="CONFLICT_SURFACED",
            actor_id=discovered_edge.provenance.rule_id or "discovery-engine",
            to_status=EdgeStatus.CONFLICT.value,
            note=reason,
        )
        saved_discovered = self.repository.save_edge(discovered_edge, tenant_context=tc)

        # Flag existing manual edge with conflict status
        manual_edge.status = EdgeStatus.CONFLICT
        manual_edge.conflict_id = conflict_id
        manual_edge.add_history(
            action="CONFLICT_SURFACED",
            actor_id="system-merger",
            to_status=EdgeStatus.CONFLICT.value,
            note=f"Conflict surfaced with discovered edge '{saved_discovered.id}': {reason}",
        )
        self.repository.save_edge(manual_edge, tenant_context=tc)

        # Build conflict record with both serialized payloads
        conflict = EdgeConflict(
            conflict_id=conflict_id,
            tenant_id=tc.tenant_id,
            source_ref=manual_edge.source_ref,
            manual_edge_id=manual_edge.id,
            discovered_edge_id=saved_discovered.id,
            manual_version=manual_edge.model_dump(mode="json"),
            discovered_version=saved_discovered.model_dump(mode="json"),
            conflict_reason=reason,
            detected_at=now,
            is_resolved=False,
        )
        saved_conflict = self.repository.save_conflict(conflict, tenant_context=tc)

        logger.warning(
            f"SURFACED CONFLICT [{conflict_id}]: {reason}. Manual edge '{manual_edge.id}' protected."
        )
        return saved_discovered, saved_conflict

    def resolve_conflict(
        self,
        conflict_id: str,
        req: ConflictResolveRequest,
        actor_id: str,
        *,
        tenant_context: TenantContext,
    ) -> EdgeConflict:
        """Executes human resolution of a surfaced conflict."""
        tc = require_tenant_context(tenant_context)
        conflict = self.repository.get_conflict(conflict_id, tenant_context=tc)
        if not conflict:
            raise DependencyConflictException(conflict_id, "Conflict record not found.")

        if conflict.is_resolved:
            raise DependencyConflictException(conflict_id, "Conflict is already resolved.")

        now = dt.datetime.now(dt.UTC)
        manual_edge = self.repository.get_edge(conflict.manual_edge_id, tenant_context=tc)
        discovered_edge = self.repository.get_edge(conflict.discovered_edge_id, tenant_context=tc)

        if not manual_edge:
            raise DependencyEdgeNotFoundException(conflict.manual_edge_id)

        if req.resolution_action == ConflictResolutionAction.KEEP_MANUAL:
            # Keep manual: Restore manual edge to ACTIVE, mark discovered as SUPERSEDED
            manual_edge.status = EdgeStatus.ACTIVE
            manual_edge.conflict_id = None
            manual_edge.add_history(
                action="CONFLICT_RESOLVED_KEEP_MANUAL",
                actor_id=actor_id,
                from_status=EdgeStatus.CONFLICT.value,
                to_status=EdgeStatus.ACTIVE.value,
                note=f"Human resolved conflict by keeping manual assertion: {req.resolution_notes}",
            )
            self.repository.save_edge(manual_edge, tenant_context=tc)

            if discovered_edge:
                discovered_edge.status = EdgeStatus.SUPERSEDED
                discovered_edge.effective_to = now
                discovered_edge.add_history(
                    action="CONFLICT_SUPERSEDED",
                    actor_id=actor_id,
                    from_status=EdgeStatus.CONFLICT.value,
                    to_status=EdgeStatus.SUPERSEDED.value,
                    note=f"Discovered edge superseded in favor of manual edge: {req.resolution_notes}",
                )
                self.repository.save_edge(discovered_edge, tenant_context=tc)

        elif req.resolution_action == ConflictResolutionAction.ACCEPT_DISCOVERED:
            # Accept discovered: Supersede manual edge, activate discovered edge
            manual_edge.status = EdgeStatus.SUPERSEDED
            manual_edge.effective_to = now
            manual_edge.add_history(
                action="CONFLICT_RESOLVED_ACCEPTED_DISCOVERED",
                actor_id=actor_id,
                from_status=EdgeStatus.CONFLICT.value,
                to_status=EdgeStatus.SUPERSEDED.value,
                note=f"Human resolved conflict by accepting discovered edge: {req.resolution_notes}",
            )
            self.repository.save_edge(manual_edge, tenant_context=tc)

            if discovered_edge:
                discovered_edge.status = EdgeStatus.ACTIVE
                discovered_edge.conflict_id = None
                discovered_edge.add_history(
                    action="CONFLICT_RESOLVED_ACTIVATED",
                    actor_id=actor_id,
                    from_status=EdgeStatus.CONFLICT.value,
                    to_status=EdgeStatus.ACTIVE.value,
                    note=f"Activated discovered edge after conflict resolution: {req.resolution_notes}",
                )
                self.repository.save_edge(discovered_edge, tenant_context=tc)

        elif req.resolution_action == ConflictResolutionAction.MERGE:
            # Merge: Apply desired attributes to manual edge, keep it as MANUAL, supersede discovered
            if req.merged_criticality:
                manual_edge.criticality = req.merged_criticality
            if req.merged_direction:
                manual_edge.direction = req.merged_direction
            if req.merged_billing:
                manual_edge.billing_attributes = req.merged_billing

            manual_edge.status = EdgeStatus.ACTIVE
            manual_edge.conflict_id = None
            manual_edge.add_history(
                action="CONFLICT_RESOLVED_MERGED",
                actor_id=actor_id,
                from_status=EdgeStatus.CONFLICT.value,
                to_status=EdgeStatus.ACTIVE.value,
                note=f"Human merged attributes into manual edge: {req.resolution_notes}",
            )
            self.repository.save_edge(manual_edge, tenant_context=tc)

            if discovered_edge:
                discovered_edge.status = EdgeStatus.SUPERSEDED
                discovered_edge.effective_to = now
                discovered_edge.add_history(
                    action="CONFLICT_SUPERSEDED_BY_MERGE",
                    actor_id=actor_id,
                    from_status=EdgeStatus.CONFLICT.value,
                    to_status=EdgeStatus.SUPERSEDED.value,
                    note=f"Discovered edge merged into manual edge: {req.resolution_notes}",
                )
                self.repository.save_edge(discovered_edge, tenant_context=tc)

        # Update conflict record
        conflict.is_resolved = True
        conflict.resolved_by = actor_id
        conflict.resolved_at = now
        conflict.resolution_action = req.resolution_action
        conflict.resolution_notes = req.resolution_notes
        return self.repository.save_conflict(conflict, tenant_context=tc)
