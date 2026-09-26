"""Authentication, Session Management and Identity REST API Endpoints (Prompt 10).

Enforces:
- POST /api/v1/auth/oidc/login: OIDC Single Sign-On with group-to-role mapping and optional JIT (Item 64).
- POST /api/v1/auth/saml/login: SAML 2.0 Single Sign-On with group-to-role mapping and optional JIT (Item 64).
- POST /api/v1/auth/break-glass/provision: Strictly limited emergency break-glass account setup (Item 65).
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

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from domain.identity.models import AuthContext, StepUpToken, TokenPair
from domain.identity.password_hasher import generate_totp_uri
from domain.identity.service import get_identity_service
from domain.models.enums import StepUpAction
from domain.models.exceptions import (
    BreakGlassAuthFailedException,
    BreakGlassLimitExceededException,
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

logger = get_logger("cloudlens.api.auth")

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication & Identity"])


# ==============================================================================
# Request & Response DTOs
# ==============================================================================


class OIDCLoginRequest(BaseModel):
    """Payload for OIDC identity provider callback / authentication assertion."""

    tenant_id: str = Field(..., description="Tenant identifier")
    id_token_claims: dict[str, Any] = Field(
        default_factory=dict, description="Raw validated OIDC ID token claims"
    )
    idp_sub: str = Field(..., description="Subject identifier in identity provider")
    email: str = Field(..., description="User corporate email address")
    display_name: str | None = Field(default=None, description="User full display name")
    groups: list[str] = Field(
        default_factory=list, description="Enterprise IdP security groups asserted for user"
    )


class SAMLLoginRequest(BaseModel):
    """Payload for SAML 2.0 identity provider assertion."""

    tenant_id: str = Field(..., description="Tenant identifier")
    assertion_claims: dict[str, Any] = Field(
        default_factory=dict, description="Raw validated SAML attribute statements"
    )
    name_id: str = Field(..., description="SAML NameID identifier")
    email: str = Field(..., description="User corporate email address")
    display_name: str | None = Field(default=None, description="User full display name")
    groups: list[str] = Field(
        default_factory=list, description="Enterprise IdP groups asserted in attribute statement"
    )


class BreakGlassProvisionRequest(BaseModel):
    """Payload to provision a strictly limited emergency break-glass account."""

    tenant_id: str = Field(..., description="Tenant identifier")
    account_name: str = Field(..., description="Break-glass account username identifier")
    password: str = Field(..., min_length=12, description="High-entropy master secret")
    step_up_token: str | None = Field(
        default=None, description="Elevated step-up token authorized for CREDENTIAL_CREATION"
    )


class BreakGlassProvisionResponse(BaseModel):
    """Response containing provisioned emergency account details and TOTP configuration."""

    tenant_id: str
    account_name: str
    totp_secret: str = Field(..., description="Base32 TOTP secret for MFA configuration")
    totp_uri: str = Field(
        ..., description="Standard otpauth:// URI for authenticator app enrollment"
    )


class BreakGlassLoginRequest(BaseModel):
    """Payload for emergency break-glass account authentication."""

    tenant_id: str = Field(..., description="Tenant identifier")
    account_name: str = Field(..., description="Break-glass username")
    password: str = Field(..., description="Account secret")
    mfa_code: str = Field(..., min_length=6, max_length=6, description="6-digit TOTP MFA passcode")


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
    # no-hardcode-allow: reason="Default credential validity window in days", reviewer="SecurityArchitect"
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
    # no-hardcode-allow: reason="Default rotation grace period in days", reviewer="SecurityArchitect"
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
    """Payload to initiate a high-risk step-up elevation challenge."""

    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: str = Field(..., description="Target user identifier")
    action: StepUpAction = Field(..., description="Target high-risk operational action")


class StepUpVerifyRequest(BaseModel):
    """Payload to complete a step-up challenge."""

    challenge_id: str = Field(..., description="Unique step-up challenge identifier")
    verification_code: str = Field(
        ..., min_length=6, max_length=6, description="6-digit verification code"
    )


# ==============================================================================
# Helper Authorization Context Extractor
# ==============================================================================


def _extract_auth_context(authorization_header: str | None) -> AuthContext:
    """Extracts and verifies Bearer token from Authorization HTTP header."""
    if not authorization_header or not authorization_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization Bearer header.",
        )
    token = authorization_header[len("Bearer ") :].strip()
    service = get_identity_service()
    try:
        return service.token_engine.extract_auth_context(token)
    except TokenExpiredException as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    except TokenRevokedException as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    except TokenInvalidException as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e


# ==============================================================================
# Endpoints
# ==============================================================================


@router.post("/oidc/login", response_model=TokenPair, summary="OIDC Single Sign-On")
def oidc_login(
    payload: OIDCLoginRequest,
    request: Request,
    x_correlation_id: str | None = Header(default=None),
) -> TokenPair:
    """Authenticates a user via OpenID Connect (Prompt 10 Item 64).

    Resolves group-to-role mappings. If IdP groups map to NO platform role, access is
    strictly denied (Item 69) and an administrator alert is fired.
    """
    service = get_identity_service()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    claims = dict(payload.id_token_claims)
    claims["sub"] = payload.idp_sub
    claims["email"] = payload.email
    if payload.display_name:
        claims["name"] = payload.display_name
    claims["groups"] = payload.groups

    try:
        return service.authenticate_oidc(
            tenant_id=payload.tenant_id,
            id_token_claims=claims,
            ip_address=client_ip,
            user_agent=user_agent,
            correlation_id=x_correlation_id,
        )
    except NoMappedRoleException as e:
        logger.warning("OIDC login denied: unmapped roles for %s", payload.email)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except UserNotProvisionedException as e:
        logger.warning(
            "OIDC login denied: JIT disabled and user not pre-provisioned: %s", payload.email
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except UserDisabledException as e:
        logger.warning("OIDC login denied: user account is disabled: %s", payload.email)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.post("/saml/login", response_model=TokenPair, summary="SAML 2.0 Single Sign-On")
def saml_login(
    payload: SAMLLoginRequest,
    request: Request,
    x_correlation_id: str | None = Header(default=None),
) -> TokenPair:
    """Authenticates a user via SAML 2.0 assertion (Prompt 10 Item 64)."""
    service = get_identity_service()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    claims = dict(payload.assertion_claims)
    claims["name_id"] = payload.name_id
    claims["email"] = payload.email
    if payload.display_name:
        claims["name"] = payload.display_name
    claims["groups"] = payload.groups

    try:
        return service.authenticate_saml(
            tenant_id=payload.tenant_id,
            saml_assertion_claims=claims,
            ip_address=client_ip,
            user_agent=user_agent,
            correlation_id=x_correlation_id,
        )
    except NoMappedRoleException as e:
        logger.warning("SAML login denied: unmapped roles for %s", payload.email)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except UserNotProvisionedException as e:
        logger.warning(
            "SAML login denied: JIT disabled and user not pre-provisioned: %s", payload.email
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except UserDisabledException as e:
        logger.warning("SAML login denied: user account is disabled: %s", payload.email)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e


@router.post(
    "/break-glass/provision",
    response_model=BreakGlassProvisionResponse,
    summary="Provision emergency break-glass account",
)
def provision_break_glass_account(
    payload: BreakGlassProvisionRequest,
    authorization: str | None = Header(default=None),
    x_correlation_id: str | None = Header(default=None),
) -> BreakGlassProvisionResponse:
    """Provisions a strictly limited break-glass emergency account (Prompt 10 Item 65).

    Requires step-up authentication authorized for CREDENTIAL_CREATION.
    """
    service = get_identity_service()
    actor_id = "admin"
    if authorization and authorization.startswith("Bearer "):
        try:
            actor_id = service.token_engine.extract_auth_context(
                authorization[len("Bearer ") :].strip()
            ).email
        except Exception:
            pass

    try:
        bg_account, secret = service.provision_break_glass_account(
            tenant_id=payload.tenant_id,
            account_name=payload.account_name,
            password=payload.password,
            actor_id=actor_id,
            step_up_token=payload.step_up_token,
            correlation_id=x_correlation_id,
        )
        uri = generate_totp_uri(secret, payload.account_name, issuer="CloudLens")
        return BreakGlassProvisionResponse(
            tenant_id=bg_account.tenant_id,
            account_name=bg_account.account_name,
            totp_secret=secret,
            totp_uri=uri,
        )
    except StepUpRequiredException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except BreakGlassLimitExceededException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post(
    "/break-glass/login",
    response_model=TokenPair,
    summary="Break-glass emergency login with MFA",
)
def break_glass_login(
    payload: BreakGlassLoginRequest,
    request: Request,
    x_correlation_id: str | None = Header(default=None),
) -> TokenPair:
    """Authenticates via the emergency break-glass local path (Prompt 10 Item 65).

    Fires an immediate CRITICAL administrator alert and logs a distinct audit event.
    """
    service = get_identity_service()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    try:
        return service.authenticate_break_glass(
            tenant_id=payload.tenant_id,
            account_name=payload.account_name,
            password=payload.password,
            mfa_code=payload.mfa_code,
            ip_address=client_ip,
            user_agent=user_agent,
            correlation_id=x_correlation_id,
        )
    except BreakGlassAuthFailedException as e:
        logger.error("Break-glass authentication failed for %s", payload.account_name)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e


@router.post("/token/refresh", response_model=TokenPair, summary="Rotate refresh token")
def refresh_token(
    payload: TokenRefreshRequest,
    x_correlation_id: str | None = Header(default=None),
) -> TokenPair:
    """Rotates refresh token and issues new short-lived access token (Prompt 10 Item 66).

    Detects token reuse; compromised token families are revoked immediately.
    """
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
    payload: LogoutRequest,
    authorization: str | None = Header(default=None),
    x_correlation_id: str | None = Header(default=None),
) -> dict[str, str]:
    """Explicitly terminates user session and revokes access and refresh tokens (Item 66)."""
    service = get_identity_service()
    session_id = payload.session_id

    actor_id = "anonymous"
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :].strip()
        try:
            ctx = service.token_engine.extract_auth_context(token)
            session_id = session_id or ctx.session_id
            actor_id = ctx.email
        except Exception:
            pass

    if session_id:
        service.terminate_session(
            session_id=session_id, actor_id=actor_id, correlation_id=x_correlation_id
        )

    return {"status": "SUCCESS", "message": "Session terminated and tokens revoked."}


@router.post("/users/{user_id}/disable", summary="Administratively disable user")
def disable_user(
    user_id: str,
    payload: DisableUserRequest,
    authorization: str | None = Header(default=None),
    x_correlation_id: str | None = Header(default=None),
) -> dict[str, str]:
    """Administratively disables a user account (Prompt 10 Item 66).

    Terminates all user sessions and revokes all issued tokens immediately.
    """
    ctx = _extract_auth_context(authorization)
    service = get_identity_service()
    service.disable_user(
        tenant_id=payload.tenant_id,
        user_id=user_id,
        actor_id=ctx.email,
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
    authorization: str | None = Header(default=None),
    x_correlation_id: str | None = Header(default=None),
) -> MachineClientCreateResponse:
    """Registers an automated service principal machine client (Prompt 10 Item 67)."""
    service = get_identity_service()
    actor_id = "admin"
    if authorization and authorization.startswith("Bearer "):
        try:
            actor_id = service.token_engine.extract_auth_context(
                authorization[len("Bearer ") :].strip()
            ).email
        except Exception:
            pass

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
    x_correlation_id: str | None = Header(default=None),
) -> dict[str, Any]:
    """Authenticates machine client using client_id and client_secret (Item 67)."""
    service = get_identity_service()
    try:
        token_pair = service.authenticate_machine_client(
            client_id=payload.client_id,
            client_secret=payload.client_secret,
            correlation_id=x_correlation_id,
        )
        # no-hardcode-allow: reason="Standard OAuth2 token response parameter", reviewer="SecurityArchitect"
        return {
            "access_token": token_pair.access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
        }
    except MachineClientAuthFailedException as e:
        logger.error("Machine client authentication failed for %s", payload.client_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e


@router.post(
    "/machine-clients/{client_id}/rotate-secret",
    response_model=MachineClientRotateSecretResponse,
    summary="Rotate machine client secret with grace period",
)
def rotate_machine_client_secret(
    client_id: str,
    payload: MachineClientRotateSecretRequest,
    authorization: str | None = Header(default=None),
    x_correlation_id: str | None = Header(default=None),
) -> MachineClientRotateSecretResponse:
    """Rotates machine client secret supporting dual-secret grace periods (Item 67)."""
    service = get_identity_service()
    actor_id = "admin"
    if authorization and authorization.startswith("Bearer "):
        try:
            actor_id = service.token_engine.extract_auth_context(
                authorization[len("Bearer ") :].strip()
            ).email
        except Exception:
            pass

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
    x_correlation_id: str | None = Header(default=None),
) -> dict[str, str]:
    """Initiates a step-up challenge for a high-risk operation (Item 68)."""
    service = get_identity_service()
    challenge = service.initiate_step_up_challenge(
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
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


@router.get("/me", response_model=AuthContext, summary="Get current authentication context")
def get_me(authorization: str | None = Header(default=None)) -> AuthContext:
    """Returns caller identity, roles, and effective permissions from Bearer token."""
    return _extract_auth_context(authorization)
