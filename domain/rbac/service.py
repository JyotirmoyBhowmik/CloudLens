"""RBAC Service (Prompt 11 Item 70-75).

Orchestrates:
- Permission catalogue and built-in role definitions (Item 70).
- Custom role composition and validation (Item 70).
- Declarative multidimensional scope grants (Item 71).
- Deny-over-allow evaluation (Item 72).
- Financial data sensitivity and rate masking (Item 73).
- Aggregate filtering with disclosure metadata (Item 74).
- Access review audit report export in JSON and CSV formats (Item 75).
"""

import csv
import io
import uuid
from datetime import UTC, datetime
from typing import Any

from domain.identity.service import get_identity_service
from domain.models.enums import GranteeType
from domain.models.exceptions import (
    FinancialDetailAccessDeniedException,
    PermissionDeniedException,
    ScopeAccessDeniedException,
)
from domain.observability import get_logger
from domain.rbac.catalogue import PermissionCatalogue, get_permission_catalogue
from domain.rbac.evaluator import ScopeGrantEvaluator
from domain.rbac.filter import AccessControlFilter
from domain.rbac.models import (
    AccessReviewRecord,
    AccessReviewReport,
    AuthorizationDecision,
    FilteredAggregateResult,
    Permission,
    ResourceTarget,
    RoleDefinition,
    ScopeGrant,
)

logger = get_logger("cloudlens.domain.rbac.service")


class RBACService:
    """Enterprise RBAC and Scope Grant Orchestration Service."""

    def __init__(
        self,
        catalogue: PermissionCatalogue | None = None,
        evaluator: ScopeGrantEvaluator | None = None,
        access_filter: AccessControlFilter | None = None,
    ) -> None:
        self._catalogue = catalogue or get_permission_catalogue()
        self._evaluator = evaluator or ScopeGrantEvaluator(self._catalogue)
        self._filter = access_filter or AccessControlFilter(self._evaluator)
        self._grants: dict[str, ScopeGrant] = {}

    @property
    def catalogue(self) -> PermissionCatalogue:
        return self._catalogue

    @property
    def evaluator(self) -> ScopeGrantEvaluator:
        return self._evaluator

    @property
    def filter(self) -> AccessControlFilter:
        return self._filter

    # ----------------------------------------------------------------------
    # Item 70: Permission Catalogue & Roles Management
    # ----------------------------------------------------------------------

    def list_permissions(self) -> list[Permission]:
        """Returns all platform permissions defined in the catalogue."""
        return self._catalogue.list_permissions()

    def get_permission(self, code: str) -> Permission | None:
        """Retrieves a single permission by its stable machine code."""
        return self._catalogue.get_permission(code)

    def list_roles(self, tenant_id: str | None = None) -> list[RoleDefinition]:
        """Returns all built-in roles plus tenant custom roles."""
        if tenant_id:
            return self._catalogue.list_roles_for_tenant(tenant_id)
        return self._catalogue.list_built_in_roles()

    def get_role(
        self, role_code_or_name: str, tenant_id: str | None = None
    ) -> RoleDefinition | None:
        """Retrieves a built-in or custom role by canonical code or display title."""
        return self._catalogue.get_role(role_code_or_name, tenant_id=tenant_id)

    def create_custom_role(
        self,
        tenant_id: str,
        code: str,
        display_name: str,
        description: str,
        allowed_permissions: list[str],
    ) -> RoleDefinition:
        """Creates a new tenant-specific custom role composed from the permission catalogue."""
        role = self._catalogue.register_custom_role(
            tenant_id=tenant_id,
            code=code,
            display_name=display_name,
            description=description,
            allowed_permissions=allowed_permissions,
        )
        logger.info(
            "Created custom role for tenant",
            extra={
                "tenant_id": tenant_id,
                "role_code": role.code,
                "permissions_count": len(role.allowed_permissions),
            },
        )
        return role

    # ----------------------------------------------------------------------
    # Item 71 & 72: Scope Grant Lifecycle Management
    # ----------------------------------------------------------------------

    def create_scope_grant(self, grant: ScopeGrant) -> ScopeGrant:
        """Registers a declarative scope grant."""
        if not grant.id:
            grant.id = f"grant-{uuid.uuid4().hex[:12]}"
        self._grants[grant.id] = grant
        logger.info(
            "Registered scope grant",
            extra={
                "grant_id": grant.id,
                "tenant_id": grant.tenant_id,
                "grantee_type": grant.grantee_type.value,
                "grantee_id": grant.grantee_id,
                "effect": grant.effect.value,
            },
        )
        return grant

    def get_scope_grant(self, grant_id: str) -> ScopeGrant | None:
        """Retrieves a scope grant by ID."""
        return self._grants.get(grant_id)

    def list_scope_grants(
        self, tenant_id: str | None = None, grantee_id: str | None = None
    ) -> list[ScopeGrant]:
        """Lists active scope grants filtered by tenant and optional grantee."""
        grants = list(self._grants.values())
        if tenant_id:
            grants = [g for g in grants if g.tenant_id in (tenant_id, "*")]
        if grantee_id:
            grants = [g for g in grants if g.grantee_id == grantee_id]
        return grants

    def list_grants_for_user(
        self, user_id: str, role_codes: list[str], tenant_id: str
    ) -> list[ScopeGrant]:
        """Returns all grants directly targeting the user or any of their assigned roles."""
        return [
            g
            for g in self._grants.values()
            if g.is_active
            and g.tenant_id in (tenant_id, "*")
            and (
                (g.grantee_type == GranteeType.USER and g.grantee_id == user_id)
                or (g.grantee_type == GranteeType.ROLE and g.grantee_id in role_codes)
            )
        ]

    def delete_scope_grant(self, grant_id: str) -> bool:
        """Revokes / removes a scope grant."""
        if grant_id in self._grants:
            del self._grants[grant_id]
            logger.info("Deleted scope grant", extra={"grant_id": grant_id})
            return True
        return False

    def clear_scope_grants(self) -> None:
        """Resets all scope grants (useful for testing)."""
        self._grants.clear()

    # ----------------------------------------------------------------------
    # Item 71-73: Authorization & Enforcement Engine
    # ----------------------------------------------------------------------

    def authorize(
        self,
        user_id: str,
        tenant_id: str,
        role_codes: list[str],
        permission_code: str,
        target: ResourceTarget | None = None,
    ) -> AuthorizationDecision:
        """Evaluates permission and scope grant policies for an operation."""
        applicable_grants = self.list_grants_for_user(user_id, role_codes, tenant_id)
        return self._evaluator.evaluate(
            user_id=user_id,
            tenant_id=tenant_id,
            role_codes=role_codes,
            permission_code=permission_code,
            target=target,
            grants=applicable_grants,
        )

    def assert_authorized(
        self,
        user_id: str,
        tenant_id: str,
        role_codes: list[str],
        permission_code: str,
        target: ResourceTarget | None = None,
    ) -> AuthorizationDecision:
        """Evaluates authorization and raises explicit domain exceptions on denial."""
        decision = self.authorize(
            user_id=user_id,
            tenant_id=tenant_id,
            role_codes=role_codes,
            permission_code=permission_code,
            target=target,
        )
        if not decision.allowed:
            if "Permission denied" in decision.reason:
                raise PermissionDeniedException(permission=permission_code, message=decision.reason)
            if "requires 'financial:detail:read'" in decision.reason:
                raise FinancialDetailAccessDeniedException(message=decision.reason)
            raise ScopeAccessDeniedException(
                resource_id=target.resource_id if target else None,
                dimension=None,
                message=decision.reason,
            )
        return decision

    # ----------------------------------------------------------------------
    # Item 74: Aggregate & Dataset Filtering with Mandatory Disclosure
    # ----------------------------------------------------------------------

    def filter_dataset(
        self,
        user_id: str,
        tenant_id: str,
        role_codes: list[str],
        permission_code: str,
        items: list[Any],
        target_extractor: Any = None,
    ) -> FilteredAggregateResult:
        """Filters a collection of records and attaches disclosure metadata."""
        applicable_grants = self.list_grants_for_user(user_id, role_codes, tenant_id)
        return self._filter.filter_dataset(
            user_id=user_id,
            tenant_id=tenant_id,
            role_codes=role_codes,
            permission_code=permission_code,
            items=items,
            grants=applicable_grants,
            target_extractor=target_extractor,
        )

    # ----------------------------------------------------------------------
    # Item 75: Access Review Audit Export (JSON & CSV)
    # ----------------------------------------------------------------------

    def generate_access_review(self, tenant_id: str) -> AccessReviewReport:
        """Builds a comprehensive access review report across all users in a tenant."""
        identity_service = get_identity_service()
        # Retrieve all tenant users
        users = [
            u
            for u in identity_service._users.values()
            if u.tenant_id == tenant_id or tenant_id == "*"
        ]

        records: list[AccessReviewRecord] = []
        for u in users:
            role_values = [r.value for r in u.roles]
            user_perms: set[str] = set()
            for r_val in role_values:
                role_def = self._catalogue.get_role(r_val, tenant_id=u.tenant_id)
                if role_def:
                    user_perms.update(role_def.allowed_permissions)

            user_grants = [
                g.model_dump(mode="json")
                for g in self.list_grants_for_user(u.id, role_values, u.tenant_id)
            ]

            records.append(
                AccessReviewRecord(
                    user_id=u.id,
                    email=u.email,
                    display_name=u.display_name,
                    status=u.status.value,
                    assigned_roles=role_values,
                    effective_permissions=sorted(user_perms),
                    scope_grants=user_grants,
                    last_sign_in_at=u.last_login_at,
                    created_at=u.created_at,
                    is_break_glass=u.is_break_glass,
                )
            )

        return AccessReviewReport(
            tenant_id=tenant_id,
            generated_at=datetime.now(UTC),
            total_users=len(records),
            records=records,
        )

    def export_access_review_json(self, tenant_id: str) -> str:
        """Exports the tenant access review report as a formatted JSON document."""
        report = self.generate_access_review(tenant_id)
        return report.model_dump_json(indent=2)

    def export_access_review_csv(self, tenant_id: str) -> str:
        """Exports the tenant access review report as RFC 4180-compliant CSV text."""
        report = self.generate_access_review(tenant_id)
        output = io.StringIO()
        fieldnames = [
            "user_id",
            "email",
            "display_name",
            "status",
            "assigned_roles",
            "permissions_count",
            "effective_permissions",
            "scope_grants_count",
            "last_sign_in_at",
            "created_at",
            "is_break_glass",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()

        for rec in report.records:
            writer.writerow(
                {
                    "user_id": rec.user_id,
                    "email": rec.email,
                    "display_name": rec.display_name or "",
                    "status": rec.status,
                    "assigned_roles": ";".join(rec.assigned_roles),
                    "permissions_count": len(rec.effective_permissions),
                    "effective_permissions": ";".join(rec.effective_permissions),
                    "scope_grants_count": len(rec.scope_grants),
                    "last_sign_in_at": (
                        rec.last_sign_in_at.isoformat() if rec.last_sign_in_at else ""
                    ),
                    "created_at": rec.created_at.isoformat(),
                    "is_break_glass": "true" if rec.is_break_glass else "false",
                }
            )

        return output.getvalue()


# Global Singleton Service
_rbac_service: RBACService | None = None


def get_rbac_service() -> RBACService:
    """Returns the shared RBACService singleton."""
    global _rbac_service
    if _rbac_service is None:
        _rbac_service = RBACService()
    return _rbac_service
