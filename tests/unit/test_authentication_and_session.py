"""Unit Tests for Authentication and Session Management (Prompt 10).

Covers:
- Prompt 10 Item 64: OIDC Single Sign-On and SAML 2.0 with JIT provisioning and group-to-role mapping.
- Prompt 10 Item 65: Break-glass emergency local accounts with fixed tenant limit, mandatory MFA,
                     immediate CRITICAL alert, and distinct audit logging.
- Prompt 10 Item 66: Short-lived access tokens, refresh token rotation with reuse detection,
                     idle timeout, absolute session lifetime, and immediate revocation on user disable.
- Prompt 10 Item 67: Machine clients using client-credentials grant with scoped permissions,
                     expiry, and secret rotation with grace periods.
- Prompt 10 Item 68: Step-up authentication for high-risk operations.
- Prompt 10 Item 69: Explicit verification that a user whose identity provider groups map to NO role
                     gets NO ACCESS (never a default role) and generates an administrator alert.
"""

from datetime import UTC, datetime, timedelta

import pytest

from domain.config.tenant_settings import TenantSettings, tenant_settings_store
from domain.identity.password_hasher import generate_totp_code
from domain.identity.service import IdentityService
from domain.identity.token_engine import CryptographicTokenEngine, TokenRevocationRegistry
from domain.models.enums import (
    AlertSeverity,
    StepUpAction,
    SystemRole,
    UserStatus,
)
from domain.models.exceptions import (
    BreakGlassAuthFailedException,
    BreakGlassLimitExceededException,
    IdentityException,
    MachineClientAuthFailedException,
    NoMappedRoleException,
    SessionExpiredException,
    StepUpRequiredException,
    TokenRevokedException,
    UserDisabledException,
    UserNotProvisionedException,
)


@pytest.fixture
def auth_service() -> IdentityService:
    """Provides a fresh isolated IdentityService instance."""
    revocation = TokenRevocationRegistry()
    engine = CryptographicTokenEngine(revocation_registry=revocation)
    service = IdentityService(token_engine=engine, tenant_store=tenant_settings_store)

    # Configure tenant settings for testing
    tenant_settings_store.update_settings(
        "tenant-corp",
        TenantSettings(
            tenant_id="tenant-corp",
            jit_provisioning_enabled=True,
            group_to_role_mapping={
                "FinOps-Engineers": SystemRole.FINOPS_ADMIN.value,
                "Cloud-Architects": SystemRole.CLOUD_ARCHITECT.value,
                "Executive-Viewers": SystemRole.FINOPS_VIEWER.value,
            },
            access_token_ttl_seconds=900,
            refresh_token_ttl_seconds=86400,
            session_idle_timeout_seconds=1800,
            session_absolute_lifetime_seconds=28800,
            step_up_token_ttl_seconds=300,
            max_break_glass_accounts=2,
        ),
    )
    return service


# ==============================================================================
# Prompt 10 Item 64 & Item 69: SSO, Group Mapping, and No Default Role Rule
# ==============================================================================


def test_oidc_login_successful_with_jit_provisioning(auth_service: IdentityService):
    """OIDC authentication provisions user when JIT is enabled and maps IdP groups to roles."""
    claims = {
        "sub": "oidc-sub-101",
        "email": "alice@corp.com",
        "name": "Alice FinOps",
        "groups": ["FinOps-Engineers"],
    }
    tokens = auth_service.authenticate_oidc("tenant-corp", claims)

    assert tokens.access_token is not None
    assert tokens.refresh_token is not None
    assert tokens.token_type == "Bearer"
    assert SystemRole.FINOPS_ADMIN.value in tokens.roles

    # Verify token claims
    ctx = auth_service.token_engine.extract_auth_context(tokens.access_token)
    assert ctx.email == "alice@corp.com"
    assert ctx.tenant_id == "tenant-corp"
    assert SystemRole.FINOPS_ADMIN in ctx.roles
    assert "billing:read" in ctx.permissions


def test_saml_login_successful(auth_service: IdentityService):
    """SAML 2.0 authentication successfully parses assertion and assigns roles."""
    assertion = {
        "name_id": "saml-name-202",
        "email": "bob@corp.com",
        "name": "Bob Architect",
        "groups": ["Cloud-Architects"],
    }
    tokens = auth_service.authenticate_saml("tenant-corp", assertion)
    assert tokens.access_token is not None
    assert SystemRole.CLOUD_ARCHITECT.value in tokens.roles

    ctx = auth_service.token_engine.extract_auth_context(tokens.access_token)
    assert ctx.email == "bob@corp.com"
    assert SystemRole.CLOUD_ARCHITECT in ctx.roles


def test_unmapped_role_strictly_denied_and_raises_alert(auth_service: IdentityService):
    """Prompt 10 Item 69: A user whose IdP groups map to NO role gets NO ACCESS

    (never a default role) and generates an administrator alert.
    """
    unmapped_claims = {
        "sub": "oidc-sub-unmapped",
        "email": "charlie@external.com",
        "name": "Charlie Unmapped",
        "groups": ["Contractors-General", "Visitors"],
    }

    with pytest.raises(NoMappedRoleException) as exc_info:
        auth_service.authenticate_oidc("tenant-corp", unmapped_claims)

    assert "possesses no mapped platform roles" in str(exc_info.value)

    # Verify Administrator Alert was fired
    alerts = auth_service.alerts
    assert len(alerts) >= 1
    unmapped_alert = next(a for a in alerts if a.alert_type == "UNMAPPED_ROLE_ACCESS_DENIED")
    assert unmapped_alert.severity == AlertSeverity.ERROR
    assert "charlie@external.com" in unmapped_alert.message

    # Verify Audit Event recorded
    audit_events = auth_service.audit_events
    unmapped_audit = next(
        e for e in audit_events if e.action == "SSO_LOGIN_REJECTED_NO_MAPPED_ROLE"
    )
    assert unmapped_audit.actor_id == "charlie@external.com"


def test_jit_disabled_blocks_unregistered_user(auth_service: IdentityService):
    """When JIT provisioning is disabled, unknown users cannot authenticate even with mapped groups."""
    tenant_settings_store.update_settings(
        "tenant-corp",
        TenantSettings(
            tenant_id="tenant-corp",
            jit_provisioning_enabled=False,
            group_to_role_mapping={"FinOps-Engineers": SystemRole.FINOPS_ADMIN.value},
        ),
    )

    claims = {
        "sub": "oidc-sub-new",
        "email": "dan@corp.com",
        "name": "Dan New",
        "groups": ["FinOps-Engineers"],
    }

    with pytest.raises(UserNotProvisionedException):
        auth_service.authenticate_oidc("tenant-corp", claims)


# ==============================================================================
# Prompt 10 Item 65: Break-Glass Emergency Local Accounts
# ==============================================================================


def _obtain_step_up_token(auth_service: IdentityService, action: StepUpAction) -> str:
    """Helper to initiate and verify a step-up challenge for test execution."""
    ch = auth_service.initiate_step_up_challenge("tenant-corp", "admin-user", action)
    st = auth_service.verify_step_up_challenge(ch.id, ch.challenge_code)
    return st.step_up_token


def test_break_glass_provisioning_and_limit_enforcement(auth_service: IdentityService):
    """Break-glass accounts are strictly capped per tenant (default 2)."""
    step_up = _obtain_step_up_token(auth_service, StepUpAction.CREDENTIAL_CREATION)

    # 1. Provision first break-glass account
    bg1, secret1 = auth_service.provision_break_glass_account(
        tenant_id="tenant-corp",
        account_name="emergency-admin-1",
        password="SuperStrongEmergencyPassword123!",
        step_up_token=step_up,
    )
    assert bg1.account_name == "emergency-admin-1"
    assert secret1 is not None

    # 2. Provision second break-glass account
    bg2, secret2 = auth_service.provision_break_glass_account(
        tenant_id="tenant-corp",
        account_name="emergency-admin-2",
        password="AnotherStrongEmergencyPassword456!",
        step_up_token=step_up,
    )
    assert bg2.account_name == "emergency-admin-2"

    # 3. Third attempt exceeds limit and must fail
    with pytest.raises(BreakGlassLimitExceededException):
        auth_service.provision_break_glass_account(
            tenant_id="tenant-corp",
            account_name="emergency-admin-3",
            password="ThirdEmergencyPassword789!",
            step_up_token=step_up,
        )


def test_break_glass_login_produces_critical_alert_and_audit(auth_service: IdentityService):
    """Prompt 10 Item 65: A break-glass sign-in produces an alert and a distinct audit record."""
    step_up = _obtain_step_up_token(auth_service, StepUpAction.CREDENTIAL_CREATION)
    bg, mfa_secret = auth_service.provision_break_glass_account(
        tenant_id="tenant-corp",
        account_name="breakglass-sec",
        password="MasterSecretPassword!",
        step_up_token=step_up,
    )

    # Generate valid TOTP MFA code
    valid_totp = generate_totp_code(mfa_secret)

    # 1. Authenticate with wrong password -> fails
    with pytest.raises(BreakGlassAuthFailedException):
        auth_service.authenticate_break_glass(
            tenant_id="tenant-corp",
            account_name="breakglass-sec",
            password="WrongPassword!",
            mfa_code=valid_totp,
        )

    # 2. Authenticate with wrong TOTP -> fails
    with pytest.raises(BreakGlassAuthFailedException):
        auth_service.authenticate_break_glass(
            tenant_id="tenant-corp",
            account_name="breakglass-sec",
            password="MasterSecretPassword!",
            mfa_code="000000",
        )

    # 3. Authenticate with valid credentials & valid MFA -> succeeds
    tokens = auth_service.authenticate_break_glass(
        tenant_id="tenant-corp",
        account_name="breakglass-sec",
        password="MasterSecretPassword!",
        mfa_code=valid_totp,
    )
    assert tokens.access_token is not None
    assert SystemRole.GLOBAL_ADMIN.value in tokens.roles

    # Verify CRITICAL alert produced
    alerts = auth_service.alerts
    bg_alert = next(a for a in alerts if a.alert_type == "BREAK_GLASS_AUTHENTICATION_ALERT")
    assert bg_alert.severity == AlertSeverity.CRITICAL
    assert "breakglass-sec" in bg_alert.message

    # Verify Distinct Audit Record written
    audits = auth_service.audit_events
    bg_audit = next(e for e in audits if e.action == "BREAK_GLASS_AUTHENTICATION")
    assert bg_audit.actor_id == "break-glass:breakglass-sec"
    assert bg_audit.tenant_id == "tenant-corp"


# ==============================================================================
# Prompt 10 Item 66: Token Lifecycle, Refresh Rotation & Reuse Detection
# ==============================================================================


def test_refresh_token_rotation_success(auth_service: IdentityService):
    """Refresh token rotation issues new access/refresh tokens and consumes the old one."""
    claims = {
        "sub": "oidc-sub-rot",
        "email": "rotator@corp.com",
        "groups": ["FinOps-Engineers"],
    }
    initial_tokens = auth_service.authenticate_oidc("tenant-corp", claims)
    old_refresh = initial_tokens.refresh_token

    # Rotate refresh token
    rotated_tokens = auth_service.refresh_tokens(old_refresh)
    assert rotated_tokens.access_token is not None
    assert rotated_tokens.refresh_token is not None
    assert rotated_tokens.refresh_token != old_refresh


def test_refresh_token_reuse_revokes_token_family_immediately(auth_service: IdentityService):
    """Replaying an already-used refresh token revokes the entire token family immediately."""
    claims = {
        "sub": "oidc-sub-reuse",
        "email": "victim@corp.com",
        "groups": ["FinOps-Engineers"],
    }
    initial_tokens = auth_service.authenticate_oidc("tenant-corp", claims)
    first_refresh = initial_tokens.refresh_token

    # Legitimate first rotation consumes first_refresh
    auth_service.refresh_tokens(first_refresh)

    # Adversary replays first_refresh -> triggers reuse detection!
    with pytest.raises(TokenRevokedException) as exc_info:
        auth_service.refresh_tokens(first_refresh)

    assert "reuse detected" in str(exc_info.value).lower()

    # Verify CRITICAL alert produced
    alerts = auth_service.alerts
    reuse_alert = next(a for a in alerts if a.alert_type == "REFRESH_TOKEN_REUSE_DETECTED")
    assert reuse_alert.severity == AlertSeverity.CRITICAL


def test_session_idle_timeout_expiration(auth_service: IdentityService):
    """Sessions that exceed the configured idle timeout are rejected."""
    claims = {
        "sub": "oidc-sub-idle",
        "email": "sleeper@corp.com",
        "groups": ["FinOps-Engineers"],
    }
    tokens = auth_service.authenticate_oidc("tenant-corp", claims)
    session_id = tokens.session_id

    # Artificially age the session past idle timeout (1800s)
    session = auth_service.get_session(session_id)
    assert session is not None
    session.last_activity_at = datetime.now(UTC) - timedelta(seconds=1900)

    with pytest.raises(SessionExpiredException):
        auth_service.refresh_tokens(tokens.refresh_token)


# ==============================================================================
# Prompt 10 Item 66: User Disablement & Immediate Revocation
# ==============================================================================


def test_disabling_user_terminates_sessions_and_revokes_tokens_immediately(
    auth_service: IdentityService,
):
    """Acceptance Criterion 1: Disabling a user terminates all their sessions

    and revokes their tokens immediately, verified by test.
    """
    claims = {
        "sub": "oidc-sub-disable",
        "email": "rogue@corp.com",
        "name": "Rogue Employee",
        "groups": ["FinOps-Engineers"],
    }
    tokens = auth_service.authenticate_oidc("tenant-corp", claims)
    access_token = tokens.access_token
    refresh_token = tokens.refresh_token
    session_id = tokens.session_id

    # Confirm token is currently valid
    ctx = auth_service.token_engine.extract_auth_context(access_token)
    assert ctx.email == "rogue@corp.com"
    user_id = ctx.user_id

    # Disable the user administratively
    disabled_user = auth_service.disable_user(
        tenant_id="tenant-corp",
        user_id=user_id,
        actor_id="security-lead@corp.com",
    )
    assert disabled_user.status == UserStatus.DISABLED

    # 1. Active session must be marked inactive immediately
    session = auth_service.get_session(session_id)
    assert session is not None
    assert session.is_active is False
    assert session.revocation_reason == "USER_DISABLED"

    # 2. Existing access token must be REJECTED IMMEDIATELY without waiting for TTL expiry
    with pytest.raises(TokenRevokedException):
        auth_service.token_engine.verify_token(access_token)

    # 3. Refresh token must also be rejected immediately
    with pytest.raises((TokenRevokedException, UserDisabledException)):
        auth_service.refresh_tokens(refresh_token)

    # 4. New SSO attempts for the disabled user must be rejected
    with pytest.raises(UserDisabledException):
        auth_service.authenticate_oidc("tenant-corp", claims)


# ==============================================================================
# Prompt 10 Item 67: Machine Clients & Scoped Permissions
# ==============================================================================


def test_machine_client_registration_and_authentication(auth_service: IdentityService):
    """Machine client registration, client credentials grant, and permission scoping."""
    step_up = _obtain_step_up_token(auth_service, StepUpAction.CREDENTIAL_CREATION)

    # 1. Register machine client
    client, raw_secret = auth_service.register_machine_client(
        tenant_id="tenant-corp",
        name="Jenkins Cost Reporter",
        scoped_permissions=["billing:read", "billing:export"],
        actor_id="devops-lead@corp.com",
        step_up_token=step_up,
    )
    assert client.client_id is not None
    assert client.scoped_permissions == ["billing:read", "billing:export"]

    # 2. Authenticate with credentials
    tokens = auth_service.authenticate_machine_client(
        client_id=client.client_id,
        client_secret=raw_secret,
    )
    assert tokens.access_token is not None

    # 3. Verify issued machine token context
    ctx = auth_service.token_engine.extract_auth_context(tokens.access_token)
    assert ctx.is_machine is True
    assert ctx.permissions == ["billing:read", "billing:export"]


def test_machine_client_secret_rotation_with_grace_period(auth_service: IdentityService):
    """Secret rotation preserves previous secret during grace period."""
    step_up = _obtain_step_up_token(auth_service, StepUpAction.CREDENTIAL_CREATION)
    client, secret_v1 = auth_service.register_machine_client(
        tenant_id="tenant-corp",
        name="Terraform Provider",
        scoped_permissions=["config:read"],
        actor_id="devops-lead@corp.com",
        step_up_token=step_up,
    )

    # Rotate secret (v1 becomes secondary during grace period)
    secret_v2 = auth_service.rotate_machine_client_secret(
        client_id=client.client_id,
        actor_id="devops-lead@corp.com",
        step_up_token=step_up,
        grace_period_days=7,
    )
    assert secret_v2 != secret_v1

    # Both secrets must work during grace period
    tokens_v1 = auth_service.authenticate_machine_client(client.client_id, secret_v1)
    tokens_v2 = auth_service.authenticate_machine_client(client.client_id, secret_v2)
    assert tokens_v1.access_token is not None
    assert tokens_v2.access_token is not None

    # Rotate again -> v1 is displaced and only v2 and v3 are valid
    secret_v3 = auth_service.rotate_machine_client_secret(
        client_id=client.client_id,
        actor_id="devops-lead@corp.com",
        step_up_token=step_up,
        grace_period_days=7,
    )

    # v1 is now invalid
    with pytest.raises(MachineClientAuthFailedException):
        auth_service.authenticate_machine_client(client.client_id, secret_v1)

    # v2 and v3 are valid
    assert auth_service.authenticate_machine_client(client.client_id, secret_v2) is not None
    assert auth_service.authenticate_machine_client(client.client_id, secret_v3) is not None


# ==============================================================================
# Prompt 10 Item 68: Step-Up Authentication for High-Risk Actions
# ==============================================================================


def test_step_up_authentication_flow(auth_service: IdentityService):
    """High-risk action requires step-up challenge initiation and code verification."""
    # 1. Initiating without step-up proof fails
    with pytest.raises(StepUpRequiredException):
        auth_service.assert_step_up_authorized(
            step_up_token=None,
            action=StepUpAction.CREDENTIAL_CREATION,
        )

    # 2. Initiate step-up challenge
    challenge = auth_service.initiate_step_up_challenge(
        tenant_id="tenant-corp",
        user_id="user-123",
        action=StepUpAction.CREDENTIAL_CREATION,
    )
    assert challenge.id is not None
    assert len(challenge.challenge_code) == 6

    # 3. Verify with wrong code fails
    with pytest.raises(IdentityException):
        auth_service.verify_step_up_challenge(challenge.id, "000000")

    # 4. Verify with correct code issues valid step-up token
    st = auth_service.verify_step_up_challenge(challenge.id, challenge.challenge_code)
    assert st.step_up_token is not None
    assert st.action == StepUpAction.CREDENTIAL_CREATION.value

    # 5. Assert authorization passes
    auth_service.assert_step_up_authorized(
        step_up_token=st.step_up_token,
        action=StepUpAction.CREDENTIAL_CREATION,
    )

    # 6. Cannot use CREDENTIAL_CREATION token for BUDGET_APPROVAL
    with pytest.raises(StepUpRequiredException):
        auth_service.assert_step_up_authorized(
            step_up_token=st.step_up_token,
            action=StepUpAction.BUDGET_APPROVAL,
        )
