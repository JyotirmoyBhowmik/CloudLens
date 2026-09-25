"""Scope Entity, Single Self-Referencing Tree, and Materialized Hierarchy History.

Enforces Prompt 05 Items 31 & 37:
1. Scope entity as a single self-referencing tree carrying a canonical role and provider-native type.
2. Canonical roles: TENANT, ROOT_GROUP, GROUP, BILLING_BOUNDARY, SUB_GROUP, BILLING_ACCOUNT.
3. Map Azure Management Group, AWS Organizational Unit, GCP Folder, OCI Compartment onto GROUP
   while preserving each native type verbatim.
4. SUB_GROUP is legitimately absent for AWS and GCP — modeled as a valid state, not an error.
5. Scope_path materialized hierarchy and scope history table so historical cost stays attributable
   to the hierarchy that was in force at the time.
"""

import uuid
from datetime import UTC, datetime

from pydantic import Field

from domain.models.base import CanonicalEntity, ProvenanceRecord
from domain.models.enums import OriginType, ProviderType, ScopeAbsenceReason, ScopeRole
from domain.models.exceptions import HistoricalAttributionException, InvalidScopeHierarchyException


class ScopeHistory(CanonicalEntity):
    """SCD Type 2 record tracking materialized hierarchy lineage over time."""

    scope_id: str = Field(..., description="ID of the tracked Scope entity")
    tenant_id: str = Field(..., description="Organization tenant ID")
    parent_scope_id: str | None = Field(
        default=None, description="Parent scope ID during this window"
    )
    materialized_path: str = Field(
        ..., description="Materialized lineage path in force during this window"
    )
    canonical_role: ScopeRole = Field(..., description="Canonical role in force")
    native_id: str = Field(..., description="Provider native identifier")
    native_type: str = Field(..., description="Provider native type name")
    effective_from: datetime = Field(..., description="Start of validity interval in UTC")
    effective_to: datetime | None = Field(
        default=None,
        description="End of validity interval in UTC (None indicates currently active)",
    )
    change_reason: str = Field(
        default="INITIAL_DISCOVERY", description="Audit reason for hierarchy change"
    )


class Scope(CanonicalEntity):
    """Canonical Scope entity representing a node in the provider-agnostic organizational tree."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    name: str = Field(..., description="Human-readable scope name")
    canonical_role: ScopeRole = Field(..., description="Canonical hierarchy classification")
    provider: ProviderType = Field(..., description="Cloud provider or canonical boundary")
    native_type: str = Field(
        ...,
        description="Verbatim provider-native type name (e.g. 'ManagementGroup', 'OrganizationalUnit')",
    )
    native_id: str = Field(..., description="Verbatim provider-native identifier (ARN, OCID, URI)")
    parent_id: str | None = Field(
        default=None, description="Self-referencing parent scope identifier"
    )
    materialized_path: str = Field(
        default="", description="Hierarchical materialized path (e.g. '/tenant/root/group/sub')"
    )
    depth: int = Field(default=0, description="Tree depth level (0 for root)")
    is_sub_group_applicable: bool = Field(
        default=True,
        description="Whether SUB_GROUP role is applicable to this provider topology (False for AWS & GCP)",
    )
    sub_group_absence_reason: ScopeAbsenceReason | None = Field(
        default=None,
        description="Explicit reason when SUB_GROUP is absent (modeled as valid state per Prompt 05 Item 31)",
    )


class ScopeTree:
    """Manages the in-memory or persisted self-referencing Scope hierarchy and history tracking."""

    def __init__(self) -> None:
        self.scopes: dict[str, Scope] = {}
        self.history: list[ScopeHistory] = []

    def add_scope(self, scope: Scope, effective_time: datetime | None = None) -> Scope:
        """Adds a new scope to the tree, computing its materialized path and opening its history window."""
        t = effective_time or datetime.now(UTC)

        # Validate parent exists if specified
        if scope.parent_id:
            parent = self.scopes.get(scope.parent_id)
            if not parent:
                raise InvalidScopeHierarchyException(
                    f"Parent scope ID '{scope.parent_id}' does not exist."
                )
            scope.depth = parent.depth + 1
            scope.materialized_path = f"{parent.materialized_path}/{scope.id}"
        else:
            scope.depth = 0
            scope.materialized_path = f"/{scope.id}"

        # Model SUB_GROUP absence for AWS and GCP as valid state
        if scope.provider in (ProviderType.AWS, ProviderType.GCP):
            scope.is_sub_group_applicable = False
            scope.sub_group_absence_reason = ScopeAbsenceReason.NOT_APPLICABLE_TO_PROVIDER

        self.scopes[scope.id] = scope

        # Open initial SCD-2 history record
        hist = ScopeHistory(
            id=str(uuid.uuid4()),
            scope_id=scope.id,
            tenant_id=scope.tenant_id,
            parent_scope_id=scope.parent_id,
            materialized_path=scope.materialized_path,
            canonical_role=scope.canonical_role,
            native_id=scope.native_id,
            native_type=scope.native_type,
            effective_from=t,
            effective_to=None,
            change_reason="INITIAL_DISCOVERY",
            source_provenance=ProvenanceRecord(
                source_system=scope.provider.value,
                origin_type=OriginType.DISCOVERED,
                survives_rediscovery=True,
            ),
        )
        self.history.append(hist)
        return scope

    def reparent_scope(
        self,
        scope_id: str,
        new_parent_id: str,
        effective_time: datetime,
        reason: str = "REPARENTED",
    ) -> Scope:
        """Reparents a scope node, closing the prior history window and creating a new SCD-2 entry.

        Preserves historical attribution of prior cost per Prompt 05 Item 37 & Acceptance.
        """
        if scope_id not in self.scopes:
            raise InvalidScopeHierarchyException(f"Scope '{scope_id}' not found.")
        if new_parent_id not in self.scopes:
            raise InvalidScopeHierarchyException(f"Target parent '{new_parent_id}' not found.")

        # Circular reference check
        current_ancestor: str | None = new_parent_id
        while current_ancestor:
            if current_ancestor == scope_id:
                raise InvalidScopeHierarchyException(
                    f"Cannot reparent '{scope_id}' under '{new_parent_id}' as it would create a circular dependency."
                )
            ancestor_obj = self.scopes.get(current_ancestor)
            current_ancestor = ancestor_obj.parent_id if ancestor_obj else None

        scope = self.scopes[scope_id]
        new_parent = self.scopes[new_parent_id]

        # 1. Close existing active history record
        for h in self.history:
            if h.scope_id == scope_id and h.effective_to is None:
                h.effective_to = effective_time
                break

        # 2. Update current Scope entity
        scope.parent_id = new_parent_id
        scope.depth = new_parent.depth + 1
        scope.materialized_path = f"{new_parent.materialized_path}/{scope.id}"
        scope.updated_at = effective_time

        # 3. Create new active history record with updated materialized path
        new_hist = ScopeHistory(
            id=str(uuid.uuid4()),
            scope_id=scope.id,
            tenant_id=scope.tenant_id,
            parent_scope_id=scope.parent_id,
            materialized_path=scope.materialized_path,
            canonical_role=scope.canonical_role,
            native_id=scope.native_id,
            native_type=scope.native_type,
            effective_from=effective_time,
            effective_to=None,
            change_reason=reason,
            source_provenance=ProvenanceRecord(
                source_system=scope.provider.value,
                origin_type=OriginType.DERIVED,
                survives_rediscovery=True,
            ),
        )
        self.history.append(new_hist)

        # 4. Propagate path changes down to existing direct and indirect children
        self._recursively_reparent_children(scope.id, effective_time, reason)
        return scope

    def _recursively_reparent_children(
        self, parent_id: str, effective_time: datetime, reason: str
    ) -> None:
        parent = self.scopes[parent_id]
        for child_id, child in self.scopes.items():
            if child.parent_id == parent_id:
                for h in self.history:
                    if h.scope_id == child_id and h.effective_to is None:
                        h.effective_to = effective_time
                        break

                child.depth = parent.depth + 1
                child.materialized_path = f"{parent.materialized_path}/{child.id}"
                child.updated_at = effective_time

                child_hist = ScopeHistory(
                    id=str(uuid.uuid4()),
                    scope_id=child.id,
                    tenant_id=child.tenant_id,
                    parent_scope_id=parent_id,
                    materialized_path=child.materialized_path,
                    canonical_role=child.canonical_role,
                    native_id=child.native_id,
                    native_type=child.native_type,
                    effective_from=effective_time,
                    effective_to=None,
                    change_reason=f"CASCADE_{reason}",
                )
                self.history.append(child_hist)
                self._recursively_reparent_children(child.id, effective_time, reason)

    def resolve_scope_at(self, scope_id: str, point_in_time: datetime) -> ScopeHistory:
        """Point-in-time historical scope resolver.

        Returns the exact ScopeHistory record (and materialized path) that was active at point_in_time.
        """
        for h in self.history:
            if h.scope_id == scope_id:
                if h.effective_from <= point_in_time and (
                    h.effective_to is None or point_in_time < h.effective_to
                ):
                    return h

        raise HistoricalAttributionException(
            f"No historical scope lineage found for scope '{scope_id}' at timestamp {point_in_time.isoformat()}."
        )
