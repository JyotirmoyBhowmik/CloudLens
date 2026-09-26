"""RBAC and Scope Grant Domain Models (Prompt 11).

Defines:
- Permission & RoleDefinition models (Item 70).
- ScopeGrant model across all eight scoping dimensions (Item 71).
- ResourceTarget and AuthorizationDecision for server-side evaluation (Item 71-72).
- Financial sensitivity and rate masking types (Item 73).
- DisclosureMetadata for aggregate access filtering (Item 74).
- AccessReviewRecord and AccessReviewReport (Item 75).
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from domain.models.base import CanonicalEntity
from domain.models.enums import FinancialSensitivity, GranteeType, GrantEffect


class Permission(CanonicalEntity):
    """Permission definition in the platform permission catalogue (Prompt 11 Item 70)."""

    code: str = Field(
        ..., description="Stable permission code (e.g. 'billing:read', 'config:write')"
    )
    display_name: str = Field(..., description="Human-readable title")
    description: str = Field(..., description="Detailed description of authority granted")
    domain: str = Field(
        ..., description="Functional domain (e.g. 'billing', 'inventory', 'config')"
    )
    action: str = Field(
        ..., description="Action within domain ('read', 'write', 'export', 'toggle', 'approve')"
    )
    is_system: bool = Field(default=True, description="True if standard shipped permission")


class RoleDefinition(CanonicalEntity):
    """Canonical built-in or custom RBAC role definition (Prompt 11 Item 70)."""

    code: str = Field(
        ..., description="Stable role machine key (e.g. 'GLOBAL_ADMIN', 'FINOPS_ADMIN')"
    )
    display_name: str = Field(..., description="Human-readable role name (e.g. 'Super Admin')")
    description: str = Field(..., description="Detailed purpose and responsibility of the role")
    is_built_in: bool = Field(default=False, description="True for nine platform shipped roles")
    allowed_permissions: list[str] = Field(
        default_factory=list, description="List of permission codes granted by this role"
    )
    tenant_id: str | None = Field(
        default=None, description="Tenant ID owning custom role, None for global built-in roles"
    )
    max_scope: str = Field(
        default="SCOPE", description="Maximum scope authority (PLATFORM, TENANT, SCOPE)"
    )
    requires_mfa: bool = Field(
        default=False, description="Whether this role mandates multi-factor auth"
    )


class ScopeGrant(CanonicalEntity):
    """Declarative scope grant mapping an identity or role to multidimensional boundaries (Prompt 11 Item 71).

    Enforces all eight canonical scoping dimensions:
    1. provider: Cloud provider code ('aws', 'azure', 'gcp', 'oci', or '*' for all).
    2. account/billing boundary: Specific cloud account, subscription, or billing account IDs.
    3. hierarchy subtree: Root node ID or path prefix, cascading to descendants.
    4. project/application: Project IDs and application codes.
    5. cost centre and business unit: Cost centre codes and business unit codes.
    6. financial data sensitivity: Visibility tier (FULL_FINANCIAL_DETAIL, COST_TOTALS_ONLY, NON_FINANCIAL).
    7. administrative: Scope applies to administrative / policy management capabilities.
    8. resource-level allow/deny exceptions: Explicit resource IDs included or excluded.
    """

    tenant_id: str = Field(..., description="Tenant boundary for scope grant")
    grantee_type: GranteeType = Field(..., description="USER or ROLE")
    grantee_id: str = Field(..., description="User ID or Role Code receiving grant")
    effect: GrantEffect = Field(default=GrantEffect.ALLOW, description="ALLOW or DENY")

    # Dimension 1: Cloud Provider
    providers: list[str] = Field(
        default_factory=list, description="Target provider codes or ['*'] for all"
    )

    # Dimension 2: Account / Billing Boundary
    account_ids: list[str] = Field(
        default_factory=list,
        description="Target cloud accounts, subscriptions, or billing boundary IDs",
    )

    # Dimension 3: Hierarchy Subtree (cascading to descendants)
    hierarchy_subtree_roots: list[str] = Field(
        default_factory=list,
        description="Hierarchy node IDs or paths acting as roots for subtree grant",
    )
    cascade_hierarchy: bool = Field(
        default=True,
        description="If True, grant cascades down to all descendants of hierarchy roots",
    )

    # Dimension 4: Project / Application
    project_ids: list[str] = Field(default_factory=list, description="Target project codes")
    application_ids: list[str] = Field(default_factory=list, description="Target application codes")

    # Dimension 5: Cost Centre and Business Unit
    cost_centre_ids: list[str] = Field(default_factory=list, description="Target cost centre codes")
    business_unit_ids: list[str] = Field(
        default_factory=list, description="Target business unit codes"
    )

    # Dimension 6: Financial Data Sensitivity
    financial_sensitivity: FinancialSensitivity = Field(
        default=FinancialSensitivity.FULL_FINANCIAL_DETAIL,
        description="Financial data visibility restriction for this scope grant",
    )

    # Dimension 7: Administrative Scoping
    is_administrative: bool = Field(
        default=False,
        description="Grant applies to administrative/governance operations within scope",
    )

    # Dimension 8: Resource-level allow/deny exceptions
    resource_exceptions: list[str] = Field(
        default_factory=list,
        description="Explicit resource IDs excluded (if effect=ALLOW) or included (if effect=DENY)",
    )

    created_by: str = Field(default="system", description="Principal creating the grant")
    description: str | None = Field(default=None, description="Audit reason or grant rationale")
    is_active: bool = Field(default=True, description="Active status")


class ResourceTarget(BaseModel):
    """Contextual metadata of an accessed resource or cost fact for scope evaluation."""

    resource_id: str | None = Field(default=None, description="Canonical or native resource ID")
    provider: str | None = Field(default=None, description="Cloud provider code")
    account_id: str | None = Field(
        default=None, description="Account, subscription, or compartment ID"
    )
    hierarchy_path: list[str] = Field(
        default_factory=list,
        description="Path of node IDs from root to current node (e.g. ['root', 'mg-prod', 'sub-1'])",
    )
    project_id: str | None = Field(default=None, description="Attributed project ID")
    application_id: str | None = Field(default=None, description="Attributed application code")
    cost_centre_id: str | None = Field(default=None, description="Attributed cost centre code")
    business_unit_id: str | None = Field(default=None, description="Attributed business unit code")
    is_financial: bool = Field(
        default=False, description="True if target carries financial metrics"
    )
    is_rate_detail: bool = Field(
        default=False, description="True if target carries unit rate or pricing detail"
    )
    is_administrative: bool = Field(
        default=False, description="True if operation is administrative/configuration"
    )


class AuthorizationDecision(BaseModel):
    """Result of evaluating permissions and scope grants for a request."""

    allowed: bool = Field(..., description="True if authorized, False otherwise")
    effect: GrantEffect = Field(..., description="ALLOW or DENY")
    reason: str = Field(..., description="Detailed explanation of authorization outcome")
    matched_grant_id: str | None = Field(
        default=None, description="ScopeGrant ID that determined the decision"
    )
    effective_financial_sensitivity: FinancialSensitivity = Field(
        default=FinancialSensitivity.FULL_FINANCIAL_DETAIL,
        description="Most restrictive financial data tier applicable to this context",
    )
    can_view_rates: bool = Field(
        default=True, description="True if user has permission to see unit rates and charge lines"
    )


class DisclosureMetadata(BaseModel):
    """Explicit disclosure structure reporting access-filtering on aggregates (Prompt 11 Item 74).

    The Disclosure Rule: when access control removes data from an aggregate,
    the response and the UI must say so. Silent filtering is a defect.
    """

    is_filtered: bool = Field(
        ..., description="True if any data was excluded by access control scope grants"
    )
    filtered_dimensions: list[str] = Field(
        default_factory=list,
        description="List of scoping dimensions that produced exclusions (e.g. ['business_unit'])",
    )
    hidden_count: int = Field(
        default=0, description="Exact count of items/records removed by access control"
    )
    total_unfiltered_count: int | None = Field(
        default=None, description="Total count prior to access filtering"
    )
    disclosure_notice: str | None = Field(
        default=None,
        description="User-facing notice explaining the access control filtering boundary",
    )


class FilteredAggregateResult(BaseModel):
    """Generic wrapper for aggregate data with mandatory disclosure metadata."""

    data: Any = Field(..., description="Filtered dataset or aggregate summary")
    disclosure: DisclosureMetadata = Field(
        ..., description="Access-filtering disclosure metadata (Item 74)"
    )


class AccessReviewRecord(BaseModel):
    """Individual user entry in the access review export (Prompt 11 Item 75)."""

    user_id: str
    email: str
    display_name: str | None
    status: str
    assigned_roles: list[str]
    effective_permissions: list[str]
    scope_grants: list[dict[str, Any]]
    last_sign_in_at: datetime | None
    created_at: datetime
    is_break_glass: bool


class AccessReviewReport(BaseModel):
    """Full access review audit report for a tenant (Prompt 11 Item 75)."""

    tenant_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_users: int
    records: list[AccessReviewRecord]
