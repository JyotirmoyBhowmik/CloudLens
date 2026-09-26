"""Identity and Authentication Domain Models (Prompt 10).

Defines core platform entities for:
- Platform Users (OIDC, SAML, Break-Glass)
- User Sessions with Token Families
- Break-Glass Emergency Local Accounts with mandatory MFA
- Machine Clients (Service Principals) with Scoped Permissions
- Step-Up Challenges and Elevated Tokens
- Token Pairs and Authentication Contexts
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from domain.models.base import CanonicalEntity
from domain.models.enums import AuthMethod, StepUpAction, SystemRole, TokenType, UserStatus


class User(CanonicalEntity):
    """Platform identity principal (human user or break-glass account)."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    email: str = Field(..., description="Unique email address identifier")
    display_name: str = Field(..., description="Human-readable full name")
    status: UserStatus = Field(default=UserStatus.ACTIVE, description="Account lifecycle status")
    roles: list[SystemRole] = Field(default_factory=list, description="Assigned canonical roles")
    idp_sub: str | None = Field(
        default=None, description="IdP subject identifier (OIDC sub or SAML NameID)"
    )
    auth_method: AuthMethod = Field(default=AuthMethod.OIDC, description="Authentication mechanism")
    is_break_glass: bool = Field(
        default=False, description="True for emergency break-glass accounts"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp in UTC"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Last update timestamp in UTC"
    )
    last_login_at: datetime | None = Field(
        default=None, description="Last successful sign-in timestamp in UTC"
    )


class Session(CanonicalEntity):
    """Active authenticated user session with sliding idle and absolute lifetimes."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    user_id: str = Field(..., description="Foreign key to User entity")
    token_family_id: str = Field(
        ..., description="Cryptographic family ID for refresh token reuse detection"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Session creation timestamp in UTC"
    )
    last_activity_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Last request activity timestamp in UTC",
    )
    expires_at: datetime = Field(
        ..., description="Absolute session lifetime expiration timestamp in UTC"
    )
    is_active: bool = Field(
        default=True, description="True if session is active; False if revoked or expired"
    )
    revoked_at: datetime | None = Field(default=None, description="Revocation timestamp in UTC")
    revocation_reason: str | None = Field(default=None, description="Reason for session revocation")
    ip_address: str | None = Field(default=None, description="Originating client IP address")
    user_agent: str | None = Field(default=None, description="Originating client User-Agent")


class BreakGlassAccount(CanonicalEntity):
    """Emergency local break-glass account with mandatory MFA (Prompt 10 Item 65)."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    account_name: str = Field(..., description="Unique emergency account username")
    password_hash: str = Field(
        ..., description="Salted cryptographic PBKDF2-HMAC-SHA256 password hash"
    )
    salt: str = Field(..., description="Cryptographic salt hex string")
    mfa_secret: str = Field(
        ..., description="Base32 TOTP secret seed for mandatory multi-factor authentication"
    )
    is_active: bool = Field(default=True, description="Active status")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp in UTC"
    )
    last_used_at: datetime | None = Field(
        default=None, description="Last emergency activation timestamp in UTC"
    )


class MachineClient(CanonicalEntity):
    """Automated service principal for machine-to-machine integrations (Prompt 10 Item 67)."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    client_id: str = Field(..., description="Unique public client identifier")
    name: str = Field(..., description="Machine client descriptive label")
    secret_hash: str = Field(..., description="Salted hash of client secret")
    secondary_secret_hash: str | None = Field(
        default=None, description="Secondary secret hash for rotation grace period"
    )
    scoped_permissions: list[str] = Field(
        default_factory=list, description="Strictly enforced allowed permission strings"
    )
    is_active: bool = Field(default=True, description="Active status")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Creation timestamp in UTC"
    )
    secret_expires_at: datetime | None = Field(
        default=None, description="Secret expiration timestamp in UTC"
    )
    last_used_at: datetime | None = Field(
        default=None, description="Last machine authentication timestamp in UTC"
    )


class StepUpChallenge(CanonicalEntity):
    """Pending step-up challenge requiring elevated MFA proof for high-risk actions (Prompt 10 Item 68)."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    user_id: str = Field(..., description="Accountable user ID")
    action: StepUpAction = Field(..., description="Protected action requiring step-up")
    target_entity_id: str | None = Field(default=None, description="Optional target entity ID")
    challenge_code: str = Field(..., description="Verification challenge code or nonce")
    expires_at: datetime = Field(..., description="Challenge expiration timestamp in UTC")
    is_verified: bool = Field(default=False, description="True once MFA proof is verified")


class TokenPair(BaseModel):
    """Standard OAuth2 / OIDC token pair response."""

    access_token: str = Field(..., description="Short-lived signed access token")
    refresh_token: str = Field(..., description="Rotated single-use refresh token")
    token_type: str = Field(default="Bearer", description="Token type descriptor")
    expires_in: int = Field(..., description="Access token lifespan in seconds")
    session_id: str = Field(..., description="Session identifier")
    roles: list[str] = Field(default_factory=list, description="Granted canonical role names")


class StepUpToken(BaseModel):
    """Elevated authorization token for high-risk operations."""

    step_up_token: str = Field(..., description="Short-lived signed step-up claim token")
    action: str = Field(..., description="Authorized protected action")
    expires_in: int = Field(..., description="Token lifespan in seconds")


class AuthContext(BaseModel):
    """Security context parsed from verified Bearer token."""

    user_id: str = Field(..., description="Authenticated user ID or machine client ID")
    tenant_id: str = Field(..., description="Tenant ID")
    email: str = Field(..., description="User email or machine client identifier")
    roles: list[SystemRole] = Field(default_factory=list, description="Canonical roles")
    permissions: list[str] = Field(default_factory=list, description="Effective permission set")
    session_id: str | None = Field(default=None, description="Associated session ID")
    token_type: TokenType = Field(default=TokenType.ACCESS, description="Token type")
    is_break_glass: bool = Field(
        default=False, description="True if authenticated via break-glass path"
    )
    step_up_claims: list[str] = Field(
        default_factory=list, description="Active elevated step-up action claims"
    )
    is_machine: bool = Field(default=False, description="True for machine clients")
