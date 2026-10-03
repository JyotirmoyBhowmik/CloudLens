"""Domain Models for Hierarchy Explorer, Inventory, and Search (Prompt 38).

Enforces:
- FR-107: Multi-attribute inventory filtering across provider, account, region, type, status, tag, and owner.
- FR-580: Global search across resources, services, scopes, applications, budgets, owners, connectors, policies, alerts.
- FR-581: Boolean logic: AND across filter types, OR within multi-selects.
- FR-582: URL-synchronizable filter state.
- FR-583: Saved, named, and shareable custom views.
- FR-584: Reactive count preview before full dataset loads.
- FR-585: Scope-safe search: never disclose existence or names of entities outside user scope grants.
- NFR-003: Sub-500ms response targets.
- 6 Lateral Lenses: Application, Cost Centre, Environment, Owner, Region, Tag, and Provider Hierarchy.
- Tree roll-up: aggregate cost, budget utilisation, and worst child threshold state at every node.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HierarchyLevel(StrEnum):
    """Canonical levels in cloud hierarchy navigation model (BBP Section 16.3)."""

    PROVIDER = "PROVIDER"
    ORGANISATION = "ORGANISATION"
    GROUP = "GROUP"
    BILLING_BOUNDARY = "BILLING_BOUNDARY"
    SUB_GROUP = "SUB_GROUP"
    SERVICE = "SERVICE"
    RESOURCE = "RESOURCE"


class LateralLensType(StrEnum):
    """Six alternative lateral entry points into estate (Prompt 38)."""

    PROVIDER_HIERARCHY = "PROVIDER_HIERARCHY"
    APPLICATION = "APPLICATION"
    COST_CENTRE = "COST_CENTRE"
    ENVIRONMENT = "ENVIRONMENT"
    OWNER = "OWNER"
    REGION = "REGION"
    TAG = "TAG"


class HierarchyNode(BaseModel):
    """Recursive node in hierarchy tree with roll-up aggregates and worst-child state."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Unique node ID")
    name: str = Field(..., description="Display title of node")
    level: HierarchyLevel = Field(..., description="Structural level")
    lens_type: LateralLensType = Field(default=LateralLensType.PROVIDER_HIERARCHY)
    provider: str | None = Field(default=None, description="Cloud provider if applicable")
    native_type: str | None = Field(
        default=None, description="Native term (e.g. ManagementGroup, OU, Folder, Compartment)"
    )
    scope_id: str | None = Field(default=None, description="Bound scope ID for RBAC evaluation")

    # Aggregate Roll-ups (BBP Section 16.3)
    aggregate_cost: Decimal = Field(
        default=Decimal("0.00"), description="Total rolled-up spend across all descendants"
    )
    budget_amount: Decimal = Field(
        default=Decimal("0.00"), description="Allocated budget at this node"
    )
    budget_utilisation_pct: Decimal = Field(
        default=Decimal("0.00"), description="Utilisation ratio"
    )
    worst_child_threshold_state: str = Field(
        default="NORMAL", description="NORMAL, WARNING, or CRITICAL"
    )

    direct_resource_count: int = Field(default=0, ge=0)
    total_descendant_resource_count: int = Field(default=0, ge=0)
    child_count: int = Field(default=0, ge=0)
    children: list[HierarchyNode] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HierarchyDetailPane(BaseModel):
    """Detailed view for selected hierarchy node."""

    node_id: str
    name: str
    lens_type: LateralLensType
    level: HierarchyLevel
    provider: str | None = None
    native_type: str | None = None
    aggregate_cost: Decimal
    budget_amount: Decimal
    budget_utilisation_pct: Decimal
    threshold_state: str
    direct_resources: list[InventoryResource35] = Field(default_factory=list)
    top_contributing_services: list[dict[str, Any]] = Field(default_factory=list)
    breadcrumbs: list[str] = Field(default_factory=list)


# ==============================================================================
# Canonical 35-Field Inventory Record (API-019 / BBP Section 16)
# ==============================================================================


class InventoryResource35(BaseModel):
    """Canonical 35-field inventory resource model."""

    model_config = ConfigDict(populate_by_name=True)

    # 1-5 Identification & Ownership
    id: str
    tenant_id: str
    scope_id: str
    native_id: str
    name: str

    # 6-10 Classification & Architecture
    provider: str
    service_id: str
    service_name: str
    service_category: str
    resource_type_id: str

    # 11-15 Type & Region
    resource_type: str
    region_id: str
    region_name: str
    availability_zone: str | None = None
    pricing_status: str  # FREE, PAID, CONDITIONAL

    # 16-20 Runtime & Tags
    runtime_state: str  # RUNNING, STOPPED, DEALLOCATED, TERMINATED
    lifecycle_status: str = Field(default="ACTIVE")
    tags: list[dict[str, Any]] = Field(default_factory=list)
    application_id: str | None = None
    application_name: str | None = None

    # 21-25 Organizational Boundaries
    environment_id: str | None = None
    environment_name: str | None = None
    owner_id: str | None = None
    owner_name: str | None = None  # May be "Unowned"
    owner_email: str | None = None

    # 26-30 Financial Alignment
    cost_center_id: str | None = None
    cost_center_name: str | None = None
    business_unit_id: str | None = None
    business_unit_name: str | None = None
    project_id: str | None = None

    # 31-35 Financial Values & Timestamps
    project_name: str | None = None
    monthly_cost: Decimal = Field(default=Decimal("0.00"))
    currency: str = Field(default="USD")
    last_synced_at: datetime
    created_at: datetime


class BulkAssignmentRequest(BaseModel):
    """Bulk update of curated metadata (FR-108, Prompt 38)."""

    resource_ids: list[str] = Field(..., min_length=1, description="List of target resource IDs")
    owner_name: str | None = Field(default=None, description="New owner name or 'Unowned'")
    owner_email: str | None = Field(default=None, description="New owner email")
    application_name: str | None = Field(default=None, description="Target application name")
    environment_name: str | None = Field(default=None, description="Target environment name")
    cost_center: str | None = Field(default=None, description="Target cost centre code")


class BulkAssignmentResponse(BaseModel):
    """Result of bulk curated assignment."""

    updated_count: int
    modified_fields: list[str]
    applied_at: datetime


# ==============================================================================
# Filter & Query Models (FR-107, FR-581, FR-584)
# ==============================================================================


class TagFilter(BaseModel):
    """Tag filter supporting existence check or specific key-value matching."""

    key: str
    value: str | None = None
    operator: str = Field(default="eq")  # eq, ne, exists, not_exists


class InventoryFilterQuery(BaseModel):
    """Structured multi-attribute inventory filter parameters."""

    providers: list[str] | None = None
    billing_boundaries: list[str] | None = None
    scope_subtrees: list[str] | None = None
    services: list[str] | None = None
    categories: list[str] | None = None
    resource_types: list[str] | None = None
    regions: list[str] | None = None
    zones: list[str] | None = None
    applications: list[str] | None = None
    projects: list[str] | None = None
    environments: list[str] | None = None
    owners: list[str] | None = None  # May include "Unowned"
    cost_centers: list[str] | None = None
    business_units: list[str] | None = None
    tag_filters: list[TagFilter] | None = None
    min_cost: Decimal | None = None
    max_cost: Decimal | None = None
    budget_states: list[str] | None = None
    threshold_states: list[str] | None = None
    runtime_states: list[str] | None = None
    lifecycle_statuses: list[str] | None = None
    search: str | None = None


class FilterCountPreview(BaseModel):
    """Reactive count preview before full result pagination loads (FR-584)."""

    matching_count: int
    total_spend: Decimal
    currency: str = Field(default="USD")
    counts_by_provider: dict[str, int] = Field(default_factory=dict)
    counts_by_environment: dict[str, int] = Field(default_factory=dict)


class SavedInventoryView(BaseModel):
    """Saved, named custom filter configuration (FR-583)."""

    id: str
    name: str
    user_id: str
    filters: dict[str, Any]
    selected_columns: list[str] = Field(default_factory=list)
    is_shared: bool = Field(default=False)
    created_at: datetime


# ==============================================================================
# Scope-Safe Global Search (FR-580, FR-585)
# ==============================================================================


class GlobalSearchItem(BaseModel):
    """Indexed search result across 9 entity types."""

    id: str
    entity_type: (
        str  # RESOURCE, SERVICE, SCOPE, APPLICATION, BUDGET, OWNER, CONNECTOR, POLICY, ALERT
    )
    identifier: str
    title: str
    subtitle: str
    provider: str | None = None
    scope_id: str
    rank_score: float = Field(
        default=0.5, description="1.0 for exact identifier match, lower for fuzzy/prefix"
    )
    deep_link: str


class GlobalSearchResponse(BaseModel):
    """Scope-safe global search result envelope."""

    query: str
    total_matches: int
    results: list[GlobalSearchItem]
    is_scope_restricted: bool
