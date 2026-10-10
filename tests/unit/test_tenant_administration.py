"""Unit Tests for Tenant Administration & Governance (Prompt P12).

Tests:
1. Super/Platform Admin can list, create, get, update tenants.
2. DEMO cannot become PRODUCTION (invariant).
3. Suspend & resume require non-empty reason and update status.
4. User grants CRUD for tenant.
5. Non-admin caller receives 403 Forbidden.
"""

from __future__ import annotations

import pytest
from datetime import UTC, datetime

from domain.models.enums import FinancialSensitivity, GrantEffect, GranteeType, SystemRole
from domain.rbac.models import ScopeGrant
from domain.tenant.context import TenantContext
from domain.tenant.models import Tenant, TenantStatus, TenantType
from domain.tenant.service import (
    InvalidTenantTransitionException,
    TenantAdministrationService,
    TenantCodeConflictException,
    TenantCreateDTO,
    TenantNotFoundException,
    TenantUpdateDTO,
    UnauthorizedTenantOperationException,
)
from tests.fakes.tenant import InMemoryTenantRepository


@pytest.fixture
def tenant_admin_setup():
    repo = InMemoryTenantRepository()
    service = TenantAdministrationService(repository=repo)

    super_admin_ctx = TenantContext(
        tenant_id="tenant-system",
        user_id="usr-super-admin",
        email="superadmin@cloudlens.io",
        roles=[SystemRole.SUPER_ADMIN],
        is_superuser=True,
    )

    platform_admin_ctx = TenantContext(
        tenant_id="tenant-system",
        user_id="usr-platform-admin",
        email="platadmin@cloudlens.io",
        roles=[SystemRole.PLATFORM_ADMIN],
        is_superuser=False,
    )

    non_admin_ctx = TenantContext(
        tenant_id="tenant-system",
        user_id="usr-finance",
        email="finance@cloudlens.io",
        roles=[SystemRole.FINANCE_USER],
        is_superuser=False,
    )

    return {
        "repo": repo,
        "service": service,
        "super_admin": super_admin_ctx,
        "platform_admin": platform_admin_ctx,
        "non_admin": non_admin_ctx,
    }


def test_create_tenant_success(tenant_admin_setup):
    service: TenantAdministrationService = tenant_admin_setup["service"]
    ctx: TenantContext = tenant_admin_setup["super_admin"]

    dto = TenantCreateDTO(
        code="SNPL_PROD",
        name="SNPL Production",
        type=TenantType.PRODUCTION,
        reporting_currency="USD",
        fiscal_year_start=1,
        iana_timezone="UTC",
        retention_profile="STANDARD",
    )

    created = service.create_tenant(dto, ctx)
    assert created.code == "SNPL_PROD"
    assert created.name == "SNPL Production"
    assert created.type == TenantType.PRODUCTION
    assert created.reporting_currency == "USD"
    assert created.status == TenantStatus.ACTIVE
    assert created.suspension_reason is None

    # Fetch it back
    fetched = service.get_tenant(created.id, ctx)
    assert fetched.id == created.id
    assert fetched.name == "SNPL Production"


def test_create_tenant_duplicate_code_conflict(tenant_admin_setup):
    service: TenantAdministrationService = tenant_admin_setup["service"]
    ctx: TenantContext = tenant_admin_setup["super_admin"]

    dto = TenantCreateDTO(
        code="DUPLICATE_CODE",
        name="First Tenant",
        type=TenantType.PRODUCTION,
        reporting_currency="USD",
    )
    service.create_tenant(dto, ctx)

    # Attempt second tenant with same code
    dto_dup = TenantCreateDTO(
        code="DUPLICATE_CODE",
        name="Second Tenant",
        type=TenantType.NON_PRODUCTION,
        reporting_currency="EUR",
    )
    with pytest.raises(TenantCodeConflictException):
        service.create_tenant(dto_dup, ctx)


def test_update_tenant_demo_cannot_become_production(tenant_admin_setup):
    service: TenantAdministrationService = tenant_admin_setup["service"]
    ctx: TenantContext = tenant_admin_setup["super_admin"]

    dto = TenantCreateDTO(
        code="DEMO_CORP",
        name="Demo Corporation",
        type=TenantType.DEMO,
        reporting_currency="USD",
    )
    demo_tenant = service.create_tenant(dto, ctx)
    assert demo_tenant.type == TenantType.DEMO

    # Attempt to change type from DEMO to PRODUCTION
    update_dto = TenantUpdateDTO(type=TenantType.PRODUCTION)
    with pytest.raises(InvalidTenantTransitionException, match="DEMO tenant cannot be converted to PRODUCTION"):
        service.update_tenant(demo_tenant.id, update_dto, ctx)

    # Changing to NON_PRODUCTION or changing name is allowed
    update_ok = TenantUpdateDTO(name="Updated Demo Corporation", type=TenantType.NON_PRODUCTION)
    updated = service.update_tenant(demo_tenant.id, update_ok, ctx)
    assert updated.name == "Updated Demo Corporation"
    assert updated.type == TenantType.NON_PRODUCTION


def test_suspend_and_resume_tenant_with_reason(tenant_admin_setup):
    service: TenantAdministrationService = tenant_admin_setup["service"]
    ctx: TenantContext = tenant_admin_setup["platform_admin"]

    dto = TenantCreateDTO(
        code="SUSPEND_TEST",
        name="Suspend Test Tenant",
        type=TenantType.NON_PRODUCTION,
        reporting_currency="USD",
    )
    tenant = service.create_tenant(dto, ctx)
    assert tenant.status == TenantStatus.ACTIVE

    # Suspend with valid reason
    reason = "Commercial invoice payment overdue 60 days."
    suspended = service.suspend_tenant(tenant.id, reason, ctx)
    assert suspended.status == TenantStatus.SUSPENDED
    assert suspended.suspension_reason == reason

    # Resume with valid reason
    resume_reason = "Commercial balance paid in full."
    resumed = service.resume_tenant(tenant.id, resume_reason, ctx)
    assert resumed.status == TenantStatus.ACTIVE
    assert resumed.suspension_reason is None


def test_suspend_tenant_empty_reason_rejected(tenant_admin_setup):
    service: TenantAdministrationService = tenant_admin_setup["service"]
    ctx: TenantContext = tenant_admin_setup["super_admin"]

    dto = TenantCreateDTO(
        code="REASON_CHECK",
        name="Reason Check Tenant",
    )
    tenant = service.create_tenant(dto, ctx)

    with pytest.raises(ValueError, match="at least 5 characters"):
        service.suspend_tenant(tenant.id, "   ", ctx)


def test_suspend_system_tenant_forbidden(tenant_admin_setup):
    service: TenantAdministrationService = tenant_admin_setup["service"]
    ctx: TenantContext = tenant_admin_setup["super_admin"]

    with pytest.raises(ValueError, match="system root tenant cannot be suspended"):
        service.suspend_tenant("tenant-system", "Testing system suspension", ctx)


def test_non_admin_forbidden_403(tenant_admin_setup):
    service: TenantAdministrationService = tenant_admin_setup["service"]
    non_admin: TenantContext = tenant_admin_setup["non_admin"]

    # Listing tenants rejected
    with pytest.raises(UnauthorizedTenantOperationException):
        service.list_tenants(non_admin)

    # Creating tenant rejected
    dto = TenantCreateDTO(code="ROGUE_TENANT", name="Rogue Tenant")
    with pytest.raises(UnauthorizedTenantOperationException):
        service.create_tenant(dto, non_admin)


def test_user_grants_crud_on_tenant(tenant_admin_setup):
    service: TenantAdministrationService = tenant_admin_setup["service"]
    ctx: TenantContext = tenant_admin_setup["super_admin"]

    dto = TenantCreateDTO(code="GRANT_TENANT", name="Grant Tenant")
    tenant = service.create_tenant(dto, ctx)

    # Create grant
    grant = ScopeGrant(
        tenant_id=tenant.id,
        grantee_type=GranteeType.USER,
        grantee_id="usr-analyst-01",
        effect=GrantEffect.ALLOW,
        providers=["aws"],
        created_by=ctx.user_id,
        description="AWS analyst scope",
    )
    saved_grant = service.create_tenant_grant(tenant.id, grant, ctx)
    assert saved_grant.grantee_id == "usr-analyst-01"

    # List grants
    grants = service.list_tenant_grants(tenant.id, None, ctx)
    assert len(grants) == 1
    assert grants[0].id == saved_grant.id

    # Delete grant
    deleted = service.delete_tenant_grant(tenant.id, saved_grant.id, ctx)
    assert deleted is True

    # Confirm list is empty
    grants_after = service.list_tenant_grants(tenant.id, None, ctx)
    assert len(grants_after) == 0
