"""Tenant Context & Mechanical Scoping Model (Prompt 13 Items 83, 84).

Enforces:
- Deriving tenant from authenticated identity only, never client-supplied parameter (Item 83).
- Strict non-empty organization tenant identification required across all repository methods (Item 84).
- Deterministic context propagation to prevent cross-tenant leakage.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator

from domain.models.exceptions import MissingTenantContextException


class TenantContext(BaseModel):
    """Immutable, validated tenant execution context for data access and auditing."""

    tenant_id: str = Field(..., description="Organization tenant identifier")
    user_id: str = Field(default="system", description="Authenticated actor identity")
    email: str | None = Field(default=None, description="Actor email address")
    roles: list[str] = Field(default_factory=list, description="Actor assigned canonical roles")
    scope_grants: list[str] = Field(
        default_factory=lambda: ["*"], description="Authorized resource or organizational scope IDs"
    )
    correlation_id: str | None = Field(default=None, description="Request trace correlation ID")
    is_superuser: bool = Field(
        default=False, description="True for unrestricted platform superuser"
    )
    is_system: bool = Field(default=False, description="True for internal background jobs")
    act_as_tenant_id: str | None = Field(
        default=None, description="Audited act-as assumed tenant ID"
    )

    @property
    def effective_tenant_id(self) -> str:
        """Returns the audited act-as tenant ID if assumed, otherwise the base tenant ID."""
        return self.act_as_tenant_id or self.tenant_id

    @property
    def is_super_admin(self) -> bool:
        """Convenience property indicating unrestricted administrative access."""
        return self.is_superuser or any(
            r in ("SUPER_ADMIN", "SystemRole.SUPER_ADMIN") for r in self.roles
        )

    @property
    def actor_id(self) -> str:
        """Alias for user_id to support actor_id access across domain layers."""
        return self.user_id

    def has_capability(self, capability: str) -> bool:
        """Evaluates whether this tenant context holds the specified capability."""
        if self.is_superuser:
            return True
        if "*" in self.scope_grants or capability in self.scope_grants:
            return True
        from domain.rbac.catalogue import get_permission_catalogue
        catalogue = get_permission_catalogue()
        for role_name in self.roles:
            role_def = catalogue.get_role(role_name, tenant_id=self.tenant_id)
            if role_def and (capability in role_def.allowed_permissions or "*" in role_def.allowed_permissions):
                return True
        return False

    def require_capability(self, capability: str) -> None:
        """Enforces that this tenant context holds the specified capability; raises 403 otherwise."""
        if not self.has_capability(capability):
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: caller lacks required capability '{capability}'.",
            )

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise MissingTenantContextException("Tenant ID cannot be null, empty, or whitespace.")
        return v.strip()


def require_tenant_context(context: Any) -> TenantContext:
    """Validates and guarantees that an object is a non-null, valid TenantContext."""
    if context is None:
        raise MissingTenantContextException("Tenant context is required but was None.")
    if not isinstance(context, TenantContext):
        raise MissingTenantContextException(
            f"Expected TenantContext instance, got '{type(context).__name__}'."
        )
    if not context.tenant_id or not context.tenant_id.strip():
        raise MissingTenantContextException(
            "TenantContext contains an empty or whitespace tenant_id."
        )
    return context


def has_capability(context: Any, capability: str) -> bool:
    """Convenience helper to evaluate capability on TenantContext, AuthContext, or role collection."""
    if hasattr(context, "has_capability"):
        return context.has_capability(capability)
    return False

