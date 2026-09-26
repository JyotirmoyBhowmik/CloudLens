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
    correlation_id: str | None = Field(default=None, description="Request trace correlation ID")
    is_superuser: bool = Field(
        default=False, description="True for unrestricted platform superuser"
    )
    is_system: bool = Field(default=False, description="True for internal background jobs")

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
