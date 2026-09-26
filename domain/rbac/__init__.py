"""CloudLens RBAC and Scope Grants Module (Prompt 11).

Provides:
- Permission & Role definitions for 9 built-in roles + custom roles.
- ScopeGrant model across all 8 dimensions with deny-over-allow evaluation.
- Rate masking & financial sensitivity separation.
- Filtered aggregates with explicit DisclosureMetadata.
- Access review audit report exports (JSON & CSV).
"""

from domain.rbac.catalogue import (
    CANONICAL_PERMISSIONS,
    ROLE_SYNONYMS,
    PermissionCatalogue,
    get_permission_catalogue,
)
from domain.rbac.evaluator import ScopeGrantEvaluator
from domain.rbac.filter import RATE_FIELDS, AccessControlFilter
from domain.rbac.models import (
    AccessReviewRecord,
    AccessReviewReport,
    AuthorizationDecision,
    DisclosureMetadata,
    FilteredAggregateResult,
    Permission,
    ResourceTarget,
    RoleDefinition,
    ScopeGrant,
)
from domain.rbac.service import RBACService, get_rbac_service

__all__ = [
    "CANONICAL_PERMISSIONS",
    "ROLE_SYNONYMS",
    "AccessControlFilter",
    "AccessReviewRecord",
    "AccessReviewReport",
    "AuthorizationDecision",
    "DisclosureMetadata",
    "FilteredAggregateResult",
    "Permission",
    "PermissionCatalogue",
    "RATE_FIELDS",
    "RBACService",
    "ResourceTarget",
    "RoleDefinition",
    "ScopeGrant",
    "ScopeGrantEvaluator",
    "get_permission_catalogue",
    "get_rbac_service",
]
