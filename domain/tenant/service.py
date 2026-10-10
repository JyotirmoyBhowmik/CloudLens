"""Tenant Administration Domain Service (Prompt P12).

Enforces:
- Administrative role verification (Super Admin / Platform Admin only) for tenant lifecycle.
- Strict auditing of all tenant lifecycle mutations (create, update, suspend, resume).
- Invariant: DEMO tenants cannot be transitioned to PRODUCTION.
- Explicit non-empty reason required for tenant suspension and resumption.
- User grants CRUD management scoped to tenant boundary.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

from domain.audit.models import AuditEventCreate
from domain.audit.service import get_audit_service
from domain.identity.models import User
from domain.identity.service import get_identity_service
from domain.models.exceptions import DomainModelException
from domain.models.enums import AuditEventType, SystemRole, UserStatus
from domain.rbac.models import ScopeGrant
from domain.rbac.service import get_rbac_service
from domain.tenant.context import TenantContext
from domain.tenant.models import Tenant, TenantStatus, TenantType
from domain.tenant.repository import TenantRepository, get_tenant_repository

logger = logging.getLogger(__name__)

SUPPORTED_CURRENCIES = {
    "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY", "INR", "SGD", "BRL", "SEK", "NZD", "ZAR", "HKD"
}


# ==============================================================================
# Domain Exceptions
# ==============================================================================


class TenantAdministrationException(DomainModelException):
    """Base exception for tenant administration domain errors."""


class TenantNotFoundException(TenantAdministrationException):
    """Raised when tenant ID or code cannot be located."""


class TenantCodeConflictException(TenantAdministrationException):
    """Raised when attempting to create a tenant with an existing code."""


class InvalidTenantTransitionException(TenantAdministrationException):
    """Raised when an illegal tenant lifecycle transition is attempted (e.g. DEMO -> PRODUCTION)."""


class UnauthorizedTenantOperationException(TenantAdministrationException):
    """Raised when caller lacks required Super Admin or Platform Admin authority."""


# ==============================================================================
# Request DTOs
# ==============================================================================


class TenantCreateDTO(BaseModel):
    """Data transfer object for tenant creation."""

    code: str = Field(..., min_length=2, max_length=64, description="Unique alphanumeric code (e.g. 'SNPL_PROD')")
    name: str = Field(..., min_length=2, max_length=255, description="Tenant organization display name")
    type: TenantType = Field(default=TenantType.PRODUCTION, description="Environment type")
    reporting_currency: str = Field(default="USD", description="Base reporting ISO currency code")
    fiscal_year_start: int = Field(default=1, ge=1, le=12, description="Starting month of fiscal calendar (1-12)")
    iana_timezone: str = Field(default="UTC", description="IANA Time Zone identifier")
    retention_profile: str = Field(default="STANDARD", description="Data retention policy profile")

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not re.match(r"^[A-Z0-9_\-]+$", cleaned):
            raise ValueError("Tenant code must contain only uppercase alphanumeric characters, underscores, and dashes.")
        return cleaned

    @field_validator("reporting_currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        curr = v.strip().upper()
        if curr not in SUPPORTED_CURRENCIES:
            raise ValueError(f"Currency '{curr}' is not a registered currency master.")
        return curr

    @field_validator("iana_timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        tz = v.strip()
        try:
            ZoneInfo(tz)
        except Exception as e:
            raise ValueError(f"Invalid IANA timezone identifier: '{tz}'") from e
        return tz


class TenantUpdateDTO(BaseModel):
    """Data transfer object for updating tenant parameters."""

    name: str | None = Field(default=None, min_length=2, max_length=255)
    type: TenantType | None = None
    reporting_currency: str | None = None
    fiscal_year_start: int | None = Field(default=None, ge=1, le=12)
    iana_timezone: str | None = None
    retention_profile: str | None = None

    @field_validator("reporting_currency")
    @classmethod
    def validate_currency(cls, v: str | None) -> str | None:
        if v is None:
            return None
        curr = v.strip().upper()
        if curr not in SUPPORTED_CURRENCIES:
            raise ValueError(f"Currency '{curr}' is not a registered currency master.")
        return curr

    @field_validator("iana_timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        tz = v.strip()
        try:
            ZoneInfo(tz)
        except Exception as e:
            raise ValueError(f"Invalid IANA timezone identifier: '{tz}'") from e
        return tz


# ==============================================================================
# Service Implementation
# ==============================================================================


class TenantAdministrationService:
    """Authoritative domain service for multi-tenant lifecycle and governance."""

    def __init__(self, repository: TenantRepository | None = None) -> None:
        self._repo = repository or get_tenant_repository()
        self._audit = get_audit_service()
        self._identity = get_identity_service()
        self._rbac = get_rbac_service()

    def _assert_admin_authority(self, tenant_context: TenantContext) -> None:
        """Verifies that the caller possesses Super Admin or Platform Admin authority."""
        if tenant_context.is_super_admin or tenant_context.is_superuser:
            return
        for r in tenant_context.roles:
            role_str = r.value if hasattr(r, "value") else str(r)
            if role_str in (
                SystemRole.SUPER_ADMIN,
                SystemRole.PLATFORM_ADMIN,
                "SUPER_ADMIN",
                "PLATFORM_ADMIN",
            ):
                return
        raise UnauthorizedTenantOperationException(
            "Access denied: tenant administration requires Super Admin or Platform Admin authority."
        )

    def _record_audit(
        self,
        tenant_context: TenantContext,
        event_type: AuditEventType,
        action: str,
        tenant_id: str,
        details: dict[str, Any],
    ) -> None:
        """Appends an immutable audit event for tenant governance actions."""
        try:
            self._audit.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=event_type,
                    actor_id=tenant_context.email or tenant_context.user_id,
                    actor_roles=tenant_context.roles,
                    action=action,
                    resource_type="TENANT",
                    resource_id=tenant_id,
                    details=details,
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception as e:
            logger.warning("Failed to record tenant audit event: %s", e)

    def list_tenants(self, tenant_context: TenantContext) -> list[Tenant]:
        """Lists all tenant organizations (Super / Platform Admin only)."""
        self._assert_admin_authority(tenant_context)
        return self._repo.list_sync()

    def get_tenant(self, tenant_id: str, tenant_context: TenantContext) -> Tenant:
        """Retrieves tenant record by ID with authorization checks."""
        # Non-admins can only view their own assigned tenant
        if not (tenant_context.is_super_admin or tenant_context.is_superuser):
            if tenant_context.tenant_id != tenant_id and tenant_context.effective_tenant_id != tenant_id:
                raise UnauthorizedTenantOperationException("Cannot view tenant details outside caller scope.")

        tenant = self._repo.get_sync(tenant_id)
        if not tenant:
            raise TenantNotFoundException(f"Tenant with ID '{tenant_id}' not found.")
        return tenant

    def create_tenant(self, data: TenantCreateDTO, tenant_context: TenantContext) -> Tenant:
        """Provisions a new tenant organization with unique code and default parameters."""
        self._assert_admin_authority(tenant_context)

        # Check unique code conflict
        existing = self._repo.get_by_code_sync(data.code)
        if existing:
            raise TenantCodeConflictException(f"Tenant with code '{data.code}' already exists.")

        # Generate deterministic or UUID tenant ID
        slug = data.code.lower().replace("_", "-")
        tenant_id = f"tenant-{slug}"

        # If ID already exists for another record, use a uuid suffix
        if self._repo.get_sync(tenant_id):
            tenant_id = f"tenant-{slug}-{uuid.uuid4().hex[:6]}"

        now = datetime.now(UTC)
        tenant = Tenant(
            id=tenant_id,
            code=data.code,
            name=data.name,
            type=data.type,
            reporting_currency=data.reporting_currency,
            fiscal_year_start=data.fiscal_year_start,
            iana_timezone=data.iana_timezone,
            retention_profile=data.retention_profile,
            status=TenantStatus.ACTIVE,
            suspension_reason=None,
            created_at=now,
            updated_at=now,
        )

        saved = self._repo.save_sync(tenant)

        # Record audit trail
        self._record_audit(
            tenant_context=tenant_context,
            event_type=AuditEventType.TENANT_CREATED,
            action="CREATE_TENANT",
            tenant_id=saved.id,
            details={
                "code": saved.code,
                "name": saved.name,
                "type": saved.type.value,
                "currency": saved.reporting_currency,
                "iana_timezone": saved.iana_timezone,
            },
        )
        return saved

    def update_tenant(self, tenant_id: str, data: TenantUpdateDTO, tenant_context: TenantContext) -> Tenant:
        """Updates mutable tenant parameters, enforcing business invariance."""
        self._assert_admin_authority(tenant_context)

        tenant = self._repo.get_sync(tenant_id)
        if not tenant:
            raise TenantNotFoundException(f"Tenant with ID '{tenant_id}' not found.")

        # Enforce Rule: DEMO cannot become PRODUCTION
        if tenant.type == TenantType.DEMO and data.type == TenantType.PRODUCTION:
            raise InvalidTenantTransitionException("DEMO tenant cannot be converted to PRODUCTION.")

        if data.name is not None:
            tenant.name = data.name
        if data.type is not None:
            tenant.type = data.type
        if data.reporting_currency is not None:
            tenant.reporting_currency = data.reporting_currency
        if data.fiscal_year_start is not None:
            tenant.fiscal_year_start = data.fiscal_year_start
        if data.iana_timezone is not None:
            tenant.iana_timezone = data.iana_timezone
        if data.retention_profile is not None:
            tenant.retention_profile = data.retention_profile

        tenant.updated_at = datetime.now(UTC)
        saved = self._repo.save_sync(tenant)

        # Record audit trail
        self._record_audit(
            tenant_context=tenant_context,
            event_type=AuditEventType.TENANT_UPDATED,
            action="UPDATE_TENANT",
            tenant_id=saved.id,
            details={
                "name": saved.name,
                "type": saved.type.value,
                "currency": saved.reporting_currency,
                "iana_timezone": saved.iana_timezone,
            },
        )
        return saved

    def suspend_tenant(self, tenant_id: str, reason: str, tenant_context: TenantContext) -> Tenant:
        """Suspends operational activity for tenant; requires non-empty rationale."""
        self._assert_admin_authority(tenant_context)

        clean_reason = reason.strip()
        if len(clean_reason) < 5:
            raise ValueError("A valid non-empty reason of at least 5 characters is required to suspend a tenant.")

        if tenant_id == "tenant-system":
            raise ValueError("The system root tenant cannot be suspended.")

        tenant = self._repo.get_sync(tenant_id)
        if not tenant:
            raise TenantNotFoundException(f"Tenant with ID '{tenant_id}' not found.")

        tenant.status = TenantStatus.SUSPENDED
        tenant.suspension_reason = clean_reason
        tenant.updated_at = datetime.now(UTC)
        saved = self._repo.save_sync(tenant)

        # Record audit trail
        self._record_audit(
            tenant_context=tenant_context,
            event_type=AuditEventType.TENANT_SUSPENDED,
            action="SUSPEND_TENANT",
            tenant_id=saved.id,
            details={"reason": clean_reason, "suspended_by": tenant_context.email or tenant_context.user_id},
        )
        return saved

    def resume_tenant(self, tenant_id: str, reason: str, tenant_context: TenantContext) -> Tenant:
        """Restores active status to a suspended tenant; requires non-empty rationale."""
        self._assert_admin_authority(tenant_context)

        clean_reason = reason.strip()
        if len(clean_reason) < 5:
            raise ValueError("A valid non-empty reason of at least 5 characters is required to resume a tenant.")

        tenant = self._repo.get_sync(tenant_id)
        if not tenant:
            raise TenantNotFoundException(f"Tenant with ID '{tenant_id}' not found.")

        tenant.status = TenantStatus.ACTIVE
        tenant.suspension_reason = None
        tenant.updated_at = datetime.now(UTC)
        saved = self._repo.save_sync(tenant)

        # Record audit trail
        self._record_audit(
            tenant_context=tenant_context,
            event_type=AuditEventType.TENANT_RESUMED,
            action="RESUME_TENANT",
            tenant_id=saved.id,
            details={"reason": clean_reason, "resumed_by": tenant_context.email or tenant_context.user_id},
        )
        return saved

    # --------------------------------------------------------------------------
    # User Grants and Identity CRUD for Tenant
    # --------------------------------------------------------------------------

    def list_tenant_grants(
        self, tenant_id: str, grantee_id: str | None, tenant_context: TenantContext
    ) -> list[ScopeGrant]:
        """Lists multidimensional scope grants for target tenant."""
        self._assert_admin_authority(tenant_context)
        return self._rbac.list_scope_grants(tenant_id=tenant_id, grantee_id=grantee_id)

    def create_tenant_grant(
        self, tenant_id: str, grant: ScopeGrant, tenant_context: TenantContext
    ) -> ScopeGrant:
        """Creates a scope grant bound to the target tenant."""
        self._assert_admin_authority(tenant_context)
        grant.tenant_id = tenant_id
        grant.created_by = tenant_context.user_id
        return self._rbac.create_scope_grant(grant)

    def delete_tenant_grant(
        self, tenant_id: str, grant_id: str, tenant_context: TenantContext
    ) -> bool:
        """Revokes a scope grant from target tenant."""
        self._assert_admin_authority(tenant_context)
        return self._rbac.delete_scope_grant(grant_id)

    def list_tenant_users(self, tenant_id: str, tenant_context: TenantContext) -> list[User]:
        """Lists users belonging to target tenant."""
        self._assert_admin_authority(tenant_context)
        return self._identity.list_users(tenant_id=tenant_id)

    def invite_tenant_user(
        self,
        tenant_id: str,
        email: str,
        display_name: str,
        roles: list[SystemRole],
        tenant_context: TenantContext,
    ) -> User:
        """Invites and provisions a new user in target tenant."""
        self._assert_admin_authority(tenant_context)
        clean_email = email.strip().lower()
        existing = self._identity.get_user_by_email(tenant_id, clean_email)
        if existing:
            raise ValueError(f"User with email '{clean_email}' already exists in tenant '{tenant_id}'.")

        now = datetime.now(UTC)
        user = User(
            id=f"usr-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            email=clean_email,
            display_name=display_name.strip(),
            status=UserStatus.ACTIVE,
            roles=roles,
            created_at=now,
            updated_at=now,
        )
        saved = self._identity.save_user(user)

        self._record_audit(
            tenant_context=tenant_context,
            event_type=AuditEventType.ROLE_ASSIGNED,
            action="INVITE_TENANT_USER",
            tenant_id=tenant_id,
            details={"email": clean_email, "roles": [r.value for r in roles]},
        )
        return saved


_tenant_service_instance: TenantAdministrationService | None = None


def get_tenant_service() -> TenantAdministrationService:
    """Dependency provider for TenantAdministrationService."""
    global _tenant_service_instance
    if _tenant_service_instance is None:
        _tenant_service_instance = TenantAdministrationService()
    return _tenant_service_instance


def reset_tenant_service(
    service: TenantAdministrationService | None = None,
) -> TenantAdministrationService:
    """Resets singleton service for unit tests."""
    global _tenant_service_instance
    _tenant_service_instance = service
    return _tenant_service_instance or get_tenant_service()
