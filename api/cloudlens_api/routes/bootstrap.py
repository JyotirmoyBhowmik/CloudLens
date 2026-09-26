"""CloudLens System Bootstrap REST API Endpoints (Prompt 49A & 49B).

Enforces:
- Prompt 49A:
  - POST /api/v1/system/bootstrap/pre-identity: Executes pre-identity bootstrap.
  - GET  /api/v1/system/bootstrap/pre-identity/status: Retrieves pre-identity verification report.
- Prompt 49B:
  - POST /api/v1/system/bootstrap/superuser/provision: Provisions single superuser from master data.
  - POST /api/v1/system/bootstrap/superuser/activate: Redeems one-time activation token and sets credentials.
  - POST /api/v1/system/bootstrap/superuser/login: Superuser sign-in with mandatory MFA, alerting & elevated audit.
  - GET  /api/v1/system/bootstrap/identity/report: Returns authoritative Identity Verification Report (Item 20).
  - POST /api/v1/system/bootstrap/superuser/delegate: Superuser first task: creates working tenant & Platform Admin.
  - POST /api/v1/system/bootstrap/superuser/routine-check: Tracks routine operations and alerts when threshold exceeded.
"""

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from domain.bootstrap import (
    IdentityVerificationReport,
    PreIdentityVerificationReport,
    SuperuserActivationToken,
    get_pre_identity_bootstrap_service,
    get_superuser_service,
)
from domain.identity.models import TokenPair
from domain.models.exceptions import (
    SuperuserActivationException,
)
from domain.observability import get_logger

logger = get_logger("cloudlens.api.bootstrap")

router = APIRouter(prefix="/api/v1/system/bootstrap", tags=["System Bootstrap & Superuser"])


# ==============================================================================
# Request & Response DTOs
# ==============================================================================


class SuperuserProvisionResponse(BaseModel):
    """Response payload for superuser provisioning."""

    user_id: str
    superuser_email: str
    role: str
    scope: str
    activation_token: SuperuserActivationToken
    break_glass_consolidated: bool = True
    message: str


class SuperuserActivateRequest(BaseModel):
    """Payload to establish superuser credentials via one-time activation token."""

    activation_token: str = Field(..., description="One-time secret activation token")
    password: str = Field(..., min_length=12, description="New strong password")
    totp_code: str | None = Field(
        default=None, description="Initial TOTP verification code if pairing MFA"
    )


class SuperuserLoginRequest(BaseModel):
    """Payload for superuser sign-in with mandatory multi-factor authentication."""

    email: str = Field(..., description="Superuser email identifier")
    password: str = Field(..., description="Established password")
    mfa_code: str = Field(
        ..., min_length=6, max_length=6, description="Mandatory 6-digit TOTP code"
    )


class DelegationHandoverRequest(BaseModel):
    """Payload for superuser first operational task: creating working tenant and Platform Admin."""

    working_tenant_id: str = Field(..., description="Working tenant identifier")
    working_tenant_name: str = Field(..., description="Human-readable tenant display name")
    admin_email: str = Field(..., description="Platform Administrator email address")
    admin_name: str = Field(..., description="Platform Administrator display name")


class RoutineOperationCheckRequest(BaseModel):
    """Payload to track routine superuser operation and verify delegation limits."""

    action: str = Field(..., description="Operational action attempted")
    activity_date: str | None = Field(
        default=None, description="Optional ISO date string for test simulations"
    )


# ==============================================================================
# Prompt 49A: Pre-Identity Bootstrap Endpoints
# ==============================================================================


@router.post("/pre-identity", response_model=PreIdentityVerificationReport)
def run_pre_identity_bootstrap(
    dry_run: bool = Query(default=False, description="Dry-run simulation mode"),
    x_correlation_id: str | None = Header(default=None),
) -> PreIdentityVerificationReport:
    """Executes the pre-identity system bootstrap sequence (Prompt 49A)."""
    service = get_pre_identity_bootstrap_service()
    return service.bootstrap(dry_run=dry_run, correlation_id=x_correlation_id)


@router.get("/pre-identity/status", response_model=PreIdentityVerificationReport | dict)
def get_pre_identity_bootstrap_status() -> PreIdentityVerificationReport | dict:
    """Retrieves current pre-identity bootstrap verification report (Prompt 49A)."""
    service = get_pre_identity_bootstrap_service()
    report = service.get_verification_report()
    if report is None:
        if service.is_initialised():
            report = service.bootstrap(dry_run=True)
        else:
            return {
                "status": "NOT_INITIALISED",
                "is_already_initialized": False,
                "is_interactively_usable": False,
                "message": "Pre-identity bootstrap has not yet been executed.",
            }
    return report


# ==============================================================================
# Prompt 49B: Superuser Provisioning & Break-Glass Consolidation Endpoints
# ==============================================================================


@router.post(
    "/superuser/provision",
    response_model=SuperuserProvisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Provision Single Superuser (Prompt 49B Item 15, 16)",
)
def provision_superuser(
    x_correlation_id: str | None = Header(default=None),
) -> SuperuserProvisionResponse:
    """Provisions exactly one superuser from master data with unrestricted scope (Item 15, 16)."""
    service = get_superuser_service()
    user, token = service.provision_superuser(correlation_id=x_correlation_id)
    return SuperuserProvisionResponse(
        user_id=user.id,
        superuser_email=user.email,
        role="GLOBAL_ADMIN",
        scope="PLATFORM_UNRESTRICTED",
        activation_token=token,
        break_glass_consolidated=True,
        message="Superuser provisioned from master data. Activate account using one-time token.",
    )


@router.post(
    "/superuser/activate",
    summary="Activate Superuser Credential (Prompt 49B Item 17)",
)
def activate_superuser(
    payload: SuperuserActivateRequest,
    x_correlation_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Establishes superuser credentials at first use with mandatory MFA setup (Item 17)."""
    service = get_superuser_service()
    try:
        return service.activate_superuser(
            activation_token=payload.activation_token,
            password=payload.password,
            totp_code=payload.totp_code,
            correlation_id=x_correlation_id,
        )
    except SuperuserActivationException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/superuser/login",
    response_model=TokenPair,
    summary="Superuser Sign-In with Mandatory MFA (Prompt 49B Item 17)",
)
def superuser_login(
    payload: SuperuserLoginRequest,
    x_correlation_id: str | None = Header(default=None),
) -> TokenPair:
    """Authenticates platform superuser with mandatory MFA, alerting and elevated audit (Item 17)."""
    service = get_superuser_service()
    try:
        return service.authenticate_superuser(
            email=payload.email,
            password=payload.password,
            mfa_code=payload.mfa_code,
            correlation_id=x_correlation_id,
        )
    except SuperuserActivationException as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e


@router.get(
    "/identity/report",
    response_model=IdentityVerificationReport,
    summary="Identity Verification Report (Prompt 49B Item 20)",
)
def get_identity_verification_report(
    x_correlation_id: str | None = Header(default=None),
) -> IdentityVerificationReport:
    """Returns the authoritative Identity Verification Report confirming superuser and controls (Item 20)."""
    service = get_superuser_service()
    return service.generate_verification_report(correlation_id=x_correlation_id)


@router.post(
    "/superuser/delegate",
    summary="Superuser First Task: Delegate to Platform Admin (Prompt 49B Item 19)",
)
def delegate_to_platform_admin(
    payload: DelegationHandoverRequest,
    x_correlation_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Superuser first operational task: creates working tenant, creates Platform Admin, and hands over."""
    service = get_superuser_service()
    admin_user = service.delegate_to_platform_admin(
        working_tenant_id=payload.working_tenant_id,
        working_tenant_name=payload.working_tenant_name,
        admin_email=payload.admin_email,
        admin_name=payload.admin_name,
        correlation_id=x_correlation_id,
    )
    return {
        "status": "HANDOVER_COMPLETED",
        "working_tenant_id": payload.working_tenant_id,
        "platform_admin_id": admin_user.id,
        "platform_admin_email": admin_user.email,
        "message": "Working tenant created and Platform Administrator provisioned. Superuser delegated operational authority.",
    }


@router.post(
    "/superuser/routine-check",
    summary="Track Routine Use and Alert on Threshold (Prompt 49B Item 19)",
)
def check_routine_use(
    payload: RoutineOperationCheckRequest,
    x_correlation_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Tracks consecutive days of routine superuser use and alerts when limit exceeded (Item 19)."""
    service = get_superuser_service()
    alert = service.record_routine_operation(
        action=payload.action,
        activity_date=payload.activity_date,
        correlation_id=x_correlation_id,
    )
    return {
        "consecutive_routine_days": service._routine_days_count,
        "alert_triggered": alert is not None,
        "alert_message": alert.message if alert else None,
    }
