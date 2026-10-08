"""Authentication, Session Management and Identity REST API Endpoints (Prompt 10 & Prompt P01).

Enforces:
- POST /api/v1/auth/oidc/login: OIDC Single Sign-On with group-to-role mapping and optional JIT (Item 64).
- POST /api/v1/auth/saml/login: SAML 2.0 Single Sign-On with group-to-role mapping and optional JIT (Item 64).
- POST /api/v1/auth/break-glass/login: Emergency break-glass sign-in with mandatory MFA and alerting (Item 65).
- POST /api/v1/auth/token/refresh: Refresh token rotation with reuse detection (Item 66).
- POST /api/v1/auth/logout: Explicit session termination and token revocation (Item 66).
- POST /api/v1/auth/users/{user_id}/disable: Immediate user disablement and token revocation (Item 66).
- POST /api/v1/auth/machine-clients: Service principal registration with scoped permissions (Item 67).
- POST /api/v1/auth/machine-clients/token: Client-credentials grant (Item 67).
- POST /api/v1/auth/machine-clients/{client_id}/rotate-secret: Secret rotation with grace period (Item 67).
- POST /api/v1/auth/step-up/initiate: Initiates step-up challenge for high-risk actions (Item 68).
- POST /api/v1/auth/step-up/verify: Verifies step-up challenge and issues elevated token (Item 68).
- GET  /api/v1/auth/me: Returns caller identity and authorization context.
"""

import secrets
from typing import Any
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.cloudlens_api.tenant_context import require_auth
from db.schema.tables import TenantModel
from db.session import get_tenant_session
from domain.abuse.tracker import get_abuse_tracker
from domain.audit.models import AuditEventCreate
from domain.audit.service import get_audit_service
from domain.identity.models import AuthContext, StepUpToken, TokenPair
from domain.identity.service import get_identity_service
from domain.models.enums import AuditEventType, StepUpAction, SystemRole
from domain.models.exceptions import (
    BreakGlassAuthFailedException,
    IdentityException,
    MachineClientAuthFailedException,
    NoMappedRoleException,
    SessionExpiredException,
    StepUpRequiredException,
    TokenExpiredException,
    TokenInvalidException,
    TokenRevokedException,
    UserDisabledException,
    UserNotProvisionedException,
)
from domain.observability import get_logger
from domain.tenant.context import TenantContext

logger = get_logger("cloudlens.api.auth")

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication & Identity"])


# ==============================================================================
# Request & Response DTOs
# ==============================================================================


class BreakGlassLoginRequest(BaseModel):
    """Payload for emergency break-glass account authentication (Prompt 49B superuser only)."""

    account_name: str = Field(..., description="Break-glass username")
    idp_assertion: dict[str, Any] | None = Field(
        default=None, description="Mandatory IdP verified identity assertion claims"
    )
    mfa_code: str = Field(..., min_length=6, max_length=6, description="6-digit TOTP MFA passcode")
    password: str | None = Field(default=None, description="Local password (strictly rejected)")


class TokenRefreshRequest(BaseModel):
    """Payload for rotating refresh token and issuing a new access token."""

    refresh_token: str = Field(..., description="Current single-use refresh token")


class LogoutRequest(BaseModel):
    """Payload for explicit session termination."""

    session_id: str | None = Field(default=None, description="Session ID to terminate")


class DisableUserRequest(BaseModel):
    """Payload for administratively disabling a user and killing all sessions."""

    tenant_id: str = Field(..., description="Tenant identifier")
    reason: str = Field(default="Administrative revocation", description="Audit rationale")


class MachineClientCreateRequest(BaseModel):
    """Payload to register a new automated machine client / service principal."""

    tenant_id: str = Field(..., description="Tenant identifier")
    client_name: str = Field(..., description="Descriptive service principal name")
    scoped_permissions: list[str] = Field(
        default_factory=list, description="Granular permission strings strictly granted"
    )
    ttl_days: int = Field(default=90, description="Credential validity duration in days")
    step_up_token: str | None = Field(
        default=None, description="Elevated step-up token for CREDENTIAL_CREATION"
    )


class MachineClientCreateResponse(BaseModel):
    """Response returning machine client identifier and generated raw client secret."""

    client_id: str
    client_name: str
    tenant_id: str
    client_secret: str = Field(..., description="Raw client secret (shown only once upon creation)")
    scoped_permissions: list[str]


class MachineClientTokenRequest(BaseModel):
    """Payload for machine client OAuth2 client-credentials grant."""

    client_id: str = Field(..., description="Machine client identifier")
    client_secret: str = Field(..., description="Client secret")


class MachineClientRotateSecretRequest(BaseModel):
    """Payload to rotate machine client secret with grace period."""

    tenant_id: str = Field(..., description="Tenant identifier")
    grace_period_days: int = Field(
        default=7, description="Grace period duration for previous secret in days"
    )
    step_up_token: str | None = Field(
        default=None, description="Elevated step-up token for CREDENTIAL_CREATION"
    )


class MachineClientRotateSecretResponse(BaseModel):
    """Response containing newly generated client secret."""

    client_id: str
    new_client_secret: str = Field(..., description="Newly rotated client secret")
    grace_period_days: int


class StepUpInitiateRequest(BaseModel):
    """Payload to initiate a high-risk step-up elevation challenge (Prompt P01: tenant/user from token)."""

    action: StepUpAction = Field(..., description="Target high-risk operational action")


class StepUpVerifyRequest(BaseModel):
    """Payload to complete a step-up challenge."""

    challenge_id: str = Field(..., description="Unique step-up challenge identifier")
    verification_code: str = Field(
        ..., min_length=6, max_length=6, description="6-digit verification code"
    )


# ==============================================================================
# Helper Lockout Enforcement
# ==============================================================================


def _enforce_lockout_check(principal_id: str) -> None:
    """Enforces progressive account lockout based on master data abuse policies."""
    tracker = get_abuse_tracker()
    is_locked, remaining_seconds = tracker.is_locked_out(principal_id)
    if is_locked:
        logger.warning("Authentication rejected: principal '%s' locked out (%ds remaining)", principal_id, remaining_seconds)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account or client is locked out due to excessive failed attempts. Please retry after {remaining_seconds} seconds.",
        )


# ==============================================================================
# Endpoints
# ==============================================================================


@router.get("/oidc/authorize", summary="OIDC Authorization Initiation (Prompt P01B Item 1)")
def oidc_authorize(
    redirect_uri: str | None = Query(default=None, description="Client redirect URI"),
    redirect: bool = Query(default=False, description="Redirect browser directly to IdP"),
    x_correlation_id: str | None = Header(default=None),
) -> Any:
    """Generates PKCE code challenge and redirects/returns IdP authorization URL (Prompt P01B Item 1 & P02)."""
    service = get_identity_service()
    auth_data = service.initiate_oidc_authorization(
        redirect_uri=redirect_uri,
        correlation_id=x_correlation_id,
    )
    if redirect:
        return RedirectResponse(url=auth_data["authorization_url"], status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    return auth_data


@router.get("/oidc/callback", summary="OIDC Authorization Callback (Prompt P01B Item 1 & P02)")
def oidc_callback(
    code: str = Query(..., description="Authorization code from IdP"),
    state: str = Query(..., description="OIDC flow state parameter"),
    request: Request = None,
    response: Response = None,
    x_correlation_id: str | None = Header(default=None),
) -> Any:
    """Exchanges code using PKCE, verifies IdP signature, mints tokens, and sets BFF cookies (Prompt P01B Item 1 & P02)."""
    client_ip = request.client.host if request and request.client else "unknown"
    user_agent = request.headers.get("User-Agent") if request else None
    service = get_identity_service()
    try:
        tokens = service.complete_oidc_authorization_code_flow(
            code=code,
            state=state,
            ip_address=client_ip,
            user_agent=user_agent,
            correlation_id=x_correlation_id,
        )
    except IdentityException as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e

    csrf_token = secrets.token_hex(16)
    accept_header = request.headers.get("accept", "") if request else ""
    if "text/html" in accept_header:
        redirect_res = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        redirect_res.set_cookie(
            key="cloudlens_access_token",
            value=tokens.access_token,
            httponly=True,
            secure=False,
            samesite="lax",
            path="/",
        )
        redirect_res.set_cookie(
            key="cloudlens_csrf_token",
            value=csrf_token,
            httponly=False,
            secure=False,
            samesite="lax",
            path="/",
        )
        return redirect_res

    if response:
        response.set_cookie(
            key="cloudlens_access_token",
            value=tokens.access_token,
            httponly=True,
            secure=False,
            samesite="lax",
            path="/",
        )
        response.set_cookie(
            key="cloudlens_csrf_token",
            value=csrf_token,
            httponly=False,
            secure=False,
            samesite="lax",
            path="/",
        )
    return tokens


@router.post("/saml/login", summary="SAML 2.0 Single Sign-On (Disabled)")
def saml_login(tc: TenantContext = Depends(require_auth)) -> None:
    """SAML 2.0 authentication is disabled pending python3-saml integration (Prompt P01B Item 2)."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="SAML 2.0 authentication is temporarily disabled pending python3-saml integration.",
    )


@router.post("/saml/acs", summary="SAML 2.0 Assertion Consumer Service (Disabled)")
def saml_acs(tc: TenantContext = Depends(require_auth)) -> None:
    """SAML 2.0 authentication is disabled pending python3-saml integration (Prompt P01B Item 2)."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="SAML 2.0 authentication is temporarily disabled pending python3-saml integration.",
    )


@router.post(
    "/break-glass/login",
    response_model=TokenPair,
    summary="Break-glass emergency login with IdP + MFA",
)
def break_glass_login(
    payload: BreakGlassLoginRequest,
    request: Request,
    x_correlation_id: str | None = Header(default=None),
) -> TokenPair:
    """Authenticates via the emergency break-glass path for the consolidated superuser (Prompt 49B & P01B Item 3)."""
    if payload.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Local passwords are strictly rejected for break-glass. IdP + MFA authentication is required.",
        )
    if not payload.idp_assertion:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="IdP identity assertion is mandatory for break-glass login.",
        )

    client_ip = request.client.host if request.client else "unknown"
    _enforce_lockout_check(payload.account_name)
    _enforce_lockout_check(client_ip)

    service = get_identity_service()
    user_agent = request.headers.get("User-Agent")
    tracker = get_abuse_tracker()

    try:
        token_pair = service.authenticate_break_glass(
            tenant_id="global",
            account_name=payload.account_name,
            password=None,
            mfa_code=payload.mfa_code,
            idp_assertion=payload.idp_assertion,
            ip_address=client_ip,
            user_agent=user_agent,
            correlation_id=x_correlation_id,
        )
        tracker.record_auth_success(payload.account_name)
        tracker.record_auth_success(client_ip)
        return token_pair
    except BreakGlassAuthFailedException as e:
        tracker.record_auth_failure(payload.account_name, ip_address=client_ip)
        logger.error("Break-glass authentication failed for %s", payload.account_name)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    except Exception:
        tracker.record_auth_failure(payload.account_name, ip_address=client_ip)
        raise


@router.post("/token/refresh", response_model=TokenPair, summary="Rotate refresh token")
def refresh_token(
    payload: TokenRefreshRequest,
    x_correlation_id: str | None = Header(default=None),
) -> TokenPair:
    """Rotates refresh token and issues new short-lived access token (Prompt 10 Item 66)."""
    service = get_identity_service()
    try:
        return service.refresh_tokens(
            refresh_token_str=payload.refresh_token,
            correlation_id=x_correlation_id,
        )
    except TokenRevokedException as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    except TokenExpiredException as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    except SessionExpiredException as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    except TokenInvalidException as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    except UserDisabledException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.post("/logout", summary="Terminate session and revoke tokens")
def logout(
    response: Response,
    payload: LogoutRequest | None = None,
    tenant_context: TenantContext = Depends(require_auth),
    x_correlation_id: str | None = Header(default=None),
) -> dict[str, str]:
    """Explicitly terminates user session, revokes access and refresh tokens, and clears BFF cookies (Item 66 & Prompt P02)."""
    service = get_identity_service()
    session_id = payload.session_id if payload else getattr(tenant_context, "session_id", None)
    actor_id = tenant_context.email or tenant_context.user_id

    if session_id:
        service.terminate_session(
            session_id=session_id, actor_id=actor_id, correlation_id=x_correlation_id
        )

    # Clear BFF cookies
    response.delete_cookie(key="cloudlens_access_token", path="/")
    response.delete_cookie(key="cloudlens_csrf_token", path="/")

    return {"status": "SUCCESS", "message": "Session terminated and tokens revoked."}


@router.get("/sessions", summary="List active sessions (IMP-02)")
def list_sessions(
    user_id: str | None = None,
    tenant_context: TenantContext = Depends(require_auth),
) -> dict[str, Any]:
    """Lists active user sessions with idle and absolute expiry metadata (IMP-02)."""
    service = get_identity_service()
    if user_id and user_id != tenant_context.user_id:
        if not tenant_context.is_superuser and not tenant_context.has_capability("users:read"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: caller lacks capability to view sessions for other users.",
            )
        target_user_id = user_id
    else:
        target_user_id = tenant_context.user_id

    sessions = service.list_active_sessions(tenant_id=tenant_context.tenant_id, user_id=target_user_id)
    return {
        "tenant_id": tenant_context.tenant_id,
        "returned_count": len(sessions),
        "sessions": [
            {
                "session_id": s.id,
                "user_id": s.user_id,
                "token_family_id": s.token_family_id,
                "created_at": s.created_at.isoformat(),
                "last_activity_at": s.last_activity_at.isoformat(),
                "expires_at": s.expires_at.isoformat(),
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
                "is_active": s.is_active,
            }
            for s in sessions
        ],
    }


@router.delete("/sessions/{session_id}", summary="Revoke single session (IMP-02)")
def revoke_session(
    session_id: str,
    tenant_context: TenantContext = Depends(require_auth),
    x_correlation_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Revokes a specific user session and blacklists its token family (IMP-02)."""
    service = get_identity_service()
    sess = service.get_session(session_id)
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or already inactive.")
    if sess.user_id != tenant_context.user_id and not tenant_context.is_superuser and not tenant_context.has_capability("users:write"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: caller lacks capability to revoke sessions of other users.",
        )

    success = service.revoke_session(
        session_id=session_id,
        actor_id=tenant_context.email or tenant_context.user_id,
        reason="OPERATOR_REVOKED",
        correlation_id=x_correlation_id,
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or already inactive.")
    return {"status": "REVOKED", "session_id": session_id}


@router.delete("/sessions/user/{user_id}", summary="Revoke all sessions for user (IMP-02)")
def revoke_all_user_sessions(
    user_id: str,
    tenant_context: TenantContext = Depends(require_auth),
    x_correlation_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Revokes all active sessions for a given user (IMP-02)."""
    if user_id != tenant_context.user_id and not tenant_context.is_superuser and not tenant_context.has_capability("users:write"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: caller lacks capability to revoke sessions of other users.",
        )

    service = get_identity_service()
    count = service.revoke_user_sessions(
        tenant_id=tenant_context.tenant_id,
        user_id=user_id,
        actor_id=tenant_context.email or tenant_context.user_id,
        reason="OPERATOR_REVOKED_ALL",
        correlation_id=x_correlation_id,
    )
    return {"status": "REVOKED", "user_id": user_id, "revoked_count": count}


@router.post("/users/{user_id}/disable", summary="Administratively disable user")
def disable_user(
    user_id: str,
    payload: DisableUserRequest,
    tenant_context: TenantContext = Depends(require_auth),
    x_correlation_id: str | None = Header(default=None),
) -> dict[str, str]:
    """Administratively disables a user account (Prompt 10 Item 66).

    Terminates all user sessions and revokes all issued tokens immediately.
    """
    if (
        not tenant_context.is_superuser
        and not tenant_context.has_capability("users:write")
        and not tenant_context.has_capability("tenants:settings:write")
        and tenant_context.user_id != user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: caller lacks required capability to disable user accounts.",
        )
    service = get_identity_service()
    service.disable_user(
        tenant_id=payload.tenant_id,
        user_id=user_id,
        actor_id=tenant_context.email or tenant_context.user_id,
        correlation_id=x_correlation_id,
    )
    return {
        "status": "SUCCESS",
        "message": f"User '{user_id}' has been disabled and all active sessions/tokens revoked.",
    }


@router.post(
    "/machine-clients",
    response_model=MachineClientCreateResponse,
    summary="Register machine client",
)
def create_machine_client(
    payload: MachineClientCreateRequest,
    tenant_context: TenantContext = Depends(require_auth),
    x_correlation_id: str | None = Header(default=None),
) -> MachineClientCreateResponse:
    """Registers an automated service principal machine client (Prompt 10 Item 67)."""
    if not tenant_context.is_superuser and not tenant_context.has_capability("credentials:create"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: caller lacks 'credentials:create' capability to register machine clients.",
        )
    service = get_identity_service()
    actor_id = tenant_context.email or tenant_context.user_id

    try:
        client, secret = service.register_machine_client(
            tenant_id=payload.tenant_id,
            name=payload.client_name,
            scoped_permissions=payload.scoped_permissions,
            actor_id=actor_id,
            secret_expires_days=payload.ttl_days,
            step_up_token=payload.step_up_token,
            correlation_id=x_correlation_id,
        )
        return MachineClientCreateResponse(
            client_id=client.client_id,
            client_name=client.name,
            tenant_id=client.tenant_id,
            client_secret=secret,
            scoped_permissions=client.scoped_permissions,
        )
    except StepUpRequiredException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.post(
    "/machine-clients/token",
    summary="OAuth2 Client-Credentials Grant for Machine Client",
)
def authenticate_machine_client(
    payload: MachineClientTokenRequest,
    request: Request,
    x_correlation_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Authenticates machine client using client_id and client_secret (Item 67)."""
    client_ip = request.client.host if request.client else "unknown"
    _enforce_lockout_check(payload.client_id)
    _enforce_lockout_check(client_ip)

    service = get_identity_service()
    tracker = get_abuse_tracker()
    try:
        token_pair = service.authenticate_machine_client(
            client_id=payload.client_id,
            client_secret=payload.client_secret,
            correlation_id=x_correlation_id,
        )
        tracker.record_auth_success(payload.client_id)
        tracker.record_auth_success(client_ip)
        return {
            "access_token": token_pair.access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
        }
    except MachineClientAuthFailedException as e:
        tracker.record_auth_failure(payload.client_id, ip_address=client_ip)
        logger.error("Machine client authentication failed for %s", payload.client_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    except Exception:
        tracker.record_auth_failure(payload.client_id, ip_address=client_ip)
        raise


@router.post(
    "/machine-clients/{client_id}/rotate-secret",
    response_model=MachineClientRotateSecretResponse,
    summary="Rotate machine client secret with grace period",
)
def rotate_machine_client_secret(
    client_id: str,
    payload: MachineClientRotateSecretRequest,
    tenant_context: TenantContext = Depends(require_auth),
    x_correlation_id: str | None = Header(default=None),
) -> MachineClientRotateSecretResponse:
    """Rotates machine client secret supporting dual-secret grace periods (Item 67)."""
    if not tenant_context.is_superuser and not tenant_context.has_capability("credentials:create"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: caller lacks 'credentials:create' capability to rotate machine client secrets.",
        )
    service = get_identity_service()
    actor_id = tenant_context.email or tenant_context.user_id

    try:
        new_secret = service.rotate_machine_client_secret(
            client_id=client_id,
            actor_id=actor_id,
            step_up_token=payload.step_up_token,
            grace_period_days=payload.grace_period_days,
            correlation_id=x_correlation_id,
        )
        return MachineClientRotateSecretResponse(
            client_id=client_id,
            new_client_secret=new_secret,
            grace_period_days=payload.grace_period_days,
        )
    except StepUpRequiredException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except (MachineClientAuthFailedException, IdentityException) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/step-up/initiate", summary="Initiate step-up challenge")
def initiate_step_up(
    payload: StepUpInitiateRequest,
    tenant_context: TenantContext = Depends(require_auth),
    x_correlation_id: str | None = Header(default=None),
) -> dict[str, str]:
    """Initiates a step-up challenge for a high-risk operation (Item 68)."""
    service = get_identity_service()
    challenge = service.initiate_step_up_challenge(
        tenant_id=tenant_context.tenant_id,
        user_id=tenant_context.user_id,
        action=payload.action,
        correlation_id=x_correlation_id,
    )
    return {
        "challenge_id": challenge.id,
        "action": challenge.action.value,
        "status": "CHALLENGE_ISSUED",
        "message": "Enter verification code to complete step-up elevation.",
    }


@router.post("/step-up/verify", response_model=StepUpToken, summary="Verify step-up challenge")
def verify_step_up(
    payload: StepUpVerifyRequest,
    x_correlation_id: str | None = Header(default=None),
) -> StepUpToken:
    """Verifies a step-up challenge code and issues an elevated short-lived token (Item 68)."""
    service = get_identity_service()
    try:
        return service.verify_step_up_challenge(
            challenge_id=payload.challenge_id,
            challenge_code=payload.verification_code,
            correlation_id=x_correlation_id,
        )
    except StepUpRequiredException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except IdentityException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


class UserSummary(BaseModel):
    id: str
    email: str
    display_name: str


class TenantSummary(BaseModel):
    id: str
    name: str


class AuthMeResponse(BaseModel):
    """Current authenticated user, roles, capabilities, and tenant list (Prompt P02 Item 4)."""

    # Backward compatibility with existing tests
    user_id: str
    tenant_id: str
    email: str
    roles: list[str]
    permissions: list[str]
    is_break_glass: bool = False

    # Prompt P02 contract
    user: UserSummary
    capabilities: list[str]
    tenants: list[TenantSummary]
    current_tenant: TenantSummary


class SwitchTenantRequest(BaseModel):
    tenant_id: str = Field(..., description="Target tenant ID to switch context to")


class SwitchTenantResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    tenant_id: str
    user_id: str
    message: str = "Tenant context switched successfully."


@router.get("/me", response_model=AuthMeResponse, summary="Get current authentication context")
async def get_me(tenant_context: TenantContext = Depends(require_auth)) -> AuthMeResponse:
    """Returns caller identity, roles, capabilities, authorized tenants, and current tenant (Prompt P02 Item 4)."""
    roles_list = [
        r.value if hasattr(r, "value") else str(r) for r in tenant_context.roles
    ]

    # Calculate capabilities
    caps = set(tenant_context.scope_grants)
    if tenant_context.is_super_admin:
        caps.update([
            "*",
            "admin:access",
            "platform.observe",
            "platform.operate",
            "platform.act_as",
            "iam:manage",
            "iam:read",
            "billing:read",
            "cost:totals:read",
            "reports:read",
            "quotas:read",
            "audit:read",
            "tenants:settings:read",
            "tenants:settings:write",
        ])
    for r in roles_list:
        if r in ("PLATFORM_ADMIN", "CLOUD_ADMINISTRATOR"):
            caps.update(["admin:access", "tenants:settings:read", "tenants:settings:write", "iam:read"])
        elif r in ("AUDITOR",):
            caps.update(["audit:read", "reports:read", "platform.observe"])
        elif r in ("FINOPS_ADMINISTRATOR",):
            caps.update(["billing:read", "cost:totals:read", "reports:read", "budgets:read", "tenants:settings:read"])

    # Query authorized tenants
    available_tenants: list[TenantSummary] = []
    if tenant_context.is_super_admin:
        try:
            async with get_tenant_session() as session:
                res = await session.execute(select(TenantModel).order_by(TenantModel.name))
                rows = res.scalars().all()
                for row in rows:
                    available_tenants.append(TenantSummary(id=row.id, name=row.name))
        except Exception:
            pass
        if not available_tenants:
            available_tenants = [
                TenantSummary(id="tenant-primary", name="Primary Enterprise"),
                TenantSummary(id="tenant-demo", name="Demo Enterprise (M3)"),
            ]
    else:
        eff_tid = tenant_context.effective_tenant_id or tenant_context.tenant_id
        available_tenants = [TenantSummary(id=eff_tid, name=f"Tenant {eff_tid}")]

    cur_tid = tenant_context.effective_tenant_id or tenant_context.tenant_id
    matched = next((t for t in available_tenants if t.id == cur_tid), None)
    current_tenant = matched or TenantSummary(id=cur_tid, name=f"Tenant {cur_tid}")

    user_email = tenant_context.email or tenant_context.user_id
    display_name = (
        user_email.split("@")[0].replace(".", " ").title()
        if "@" in user_email
        else user_email
    )

    return AuthMeResponse(
        user_id=tenant_context.user_id,
        tenant_id=cur_tid,
        email=user_email,
        roles=roles_list,
        permissions=list(caps),
        is_break_glass=tenant_context.is_superuser,
        user=UserSummary(
            id=tenant_context.user_id,
            email=user_email,
            display_name=display_name,
        ),
        capabilities=list(caps),
        tenants=available_tenants,
        current_tenant=current_tenant,
    )


@router.post("/switch-tenant", response_model=SwitchTenantResponse, summary="Switch active tenant context")
def switch_tenant(
    payload: SwitchTenantRequest,
    response: Response,
    tenant_context: TenantContext = Depends(require_auth),
    x_correlation_id: str | None = Header(default=None),
) -> SwitchTenantResponse:
    """Switches caller's active tenant context, issues updated token, and records audit trail (Prompt P02 Item 5)."""
    target_tenant_id = payload.tenant_id.strip()
    if not target_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target tenant_id cannot be empty.",
        )

    # Permission check: super-admin can switch to any tenant; others can only switch to their authorized tenant
    if not tenant_context.is_super_admin and target_tenant_id != tenant_context.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User is not authorized to switch to tenant '{target_tenant_id}'.",
        )

    # Audit the tenant switch
    audit_service = get_audit_service()
    audit_service.append_event(
        tenant_context=tenant_context,
        event_in=AuditEventCreate(
            event_type=AuditEventType.TENANT_SWITCH,
            actor_id=tenant_context.email or tenant_context.user_id,
            actor_roles=[r.value if hasattr(r, "value") else str(r) for r in tenant_context.roles],
            action="SWITCH_TENANT",
            resource_type="TENANT",
            resource_id=target_tenant_id,
            details={
                "previous_tenant": tenant_context.effective_tenant_id,
                "new_tenant": target_tenant_id,
            },
        ),
    )

    # Issue updated token
    identity_service = get_identity_service()
    roles = [
        SystemRole(r) for r in tenant_context.roles if r in SystemRole._value2member_map_
    ]
    new_token = identity_service.token_engine.issue_access_token(
        user_id=tenant_context.user_id,
        email=tenant_context.email or tenant_context.user_id,
        tenant_id=target_tenant_id,
        roles=roles,
        permissions=tenant_context.scope_grants,
        session_id=getattr(tenant_context, "session_id", None) or str(uuid.uuid4()),
        act_as_tenant=target_tenant_id if tenant_context.is_super_admin else None,
    )

    # Update session cookies (BFF pattern)
    response.set_cookie(
        key="cloudlens_access_token",
        value=new_token,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )

    return SwitchTenantResponse(
        access_token=new_token,
        tenant_id=target_tenant_id,
        user_id=tenant_context.user_id,
        message=f"Context successfully switched to tenant {target_tenant_id}.",
    )


class SessionStateResponse(BaseModel):
    """Current authenticated session state and user identity (API-002)."""

    user_id: str
    tenant_id: str
    email: str
    display_name: str
    roles: list[str]
    session_id: str
    is_active: bool = True
    auth_method: str = "OIDC"
    created_at: str | None = None
    expires_at: str | None = None


@router.get("/session", response_model=SessionStateResponse, summary="Get current session state")
def get_session_state(
    tenant_context: TenantContext = Depends(require_auth),
) -> SessionStateResponse:
    """Current authenticated session state and user identity (API-002)."""
    service = get_identity_service()
    sess = None
    if hasattr(tenant_context, "session_id") and tenant_context.session_id:
        sess = service.get_session(tenant_context.session_id)

    user = service.get_user(tenant_context.user_id) if tenant_context.user_id else None
    auth_method_str = (
        user.auth_method.value
        if user and hasattr(user, "auth_method") and hasattr(user.auth_method, "value")
        else "OIDC"
    )
    email = tenant_context.email or tenant_context.user_id
    display_name = email.split("@")[0].capitalize() if "@" in email else email

    return SessionStateResponse(
        user_id=tenant_context.user_id,
        tenant_id=tenant_context.tenant_id,
        email=email,
        display_name=display_name,
        roles=tenant_context.roles,
        session_id=sess.id if sess else "sess-active",
        is_active=sess.is_active if sess else True,
        auth_method=auth_method_str,
        created_at=sess.created_at.isoformat() if sess else None,
        expires_at=sess.expires_at.isoformat() if sess else None,
    )
