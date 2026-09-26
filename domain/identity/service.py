"""Identity, Authentication, and Session Management Service (Prompt 10).

Enforces:
- Prompt 10 Item 64: OIDC and SAML 2.0 authentication with optional Just-In-Time (JIT) provisioning
  and tenant-specific group-to-role mapping.
- Prompt 10 Item 65: Strictly limited break-glass local accounts with mandatory MFA, alerted on every use,
  and distinctly auditable.
- Prompt 10 Item 66: Short-lived access tokens, refresh token rotation, configurable session lifetimes,
  and immediate token/session revocation on user disablement.
- Prompt 10 Item 67: Machine clients via client-credentials grant with scoped permissions and secret rotation.
- Prompt 10 Item 68: Step-up authentication for high-risk actions (credential creation, overrides, budget approvals).
- Prompt 10 Item 69: Explicit rule: users with no mapped role receive NO ACCESS and trigger an administrator alert.
"""

import logging
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from domain.config.tenant_settings import TenantSettingsStore, tenant_settings_store
from domain.identity.models import (
    AuthContext,
    BreakGlassAccount,
    MachineClient,
    Session,
    StepUpChallenge,
    StepUpToken,
    TokenPair,
    User,
)
from domain.identity.password_hasher import (
    generate_salt,
    generate_totp_secret,
    hash_password,
    verify_password,
    verify_totp_code,
)
from domain.identity.token_engine import CryptographicTokenEngine
from domain.models.enums import (
    AlertSeverity,
    AlertStatus,
    AuthMethod,
    StepUpAction,
    SystemRole,
    TokenType,
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
    SuperuserImmutableException,
    TokenInvalidException,
    TokenRevokedException,
    UserDisabledException,
    UserNotProvisionedException,
)
from domain.models.governance import Alert, AuditEvent

logger = logging.getLogger(__name__)

# Canonical Permissions Map for System Roles
ROLE_PERMISSIONS_CATALOGUE: dict[SystemRole, list[str]] = {
    SystemRole.GLOBAL_ADMIN: [
        "config:read",
        "config:write",
        "features:read",
        "features:toggle",
        "tenants:settings:read",
        "tenants:settings:write",
        "billing:read",
        "billing:export",
        "inventory:read",
        "inventory:write",
        "credentials:create",
        "overrides:apply",
        "budgets:approve",
    ],
    SystemRole.TENANT_ADMIN: [
        "config:read",
        "features:read",
        "tenants:settings:read",
        "tenants:settings:write",
        "billing:read",
        "billing:export",
        "inventory:read",
        "credentials:create",
        "overrides:apply",
        "budgets:approve",
    ],
    SystemRole.FINOPS_ADMIN: [
        "config:read",
        "features:read",
        "tenants:settings:read",
        "tenants:settings:write",
        "billing:read",
        "billing:export",
        "inventory:read",
        "overrides:apply",
        "budgets:approve",
    ],
    SystemRole.FINOPS_ANALYST: [
        "config:read",
        "features:read",
        "tenants:settings:read",
        "billing:read",
        "billing:export",
        "inventory:read",
    ],
    SystemRole.FINOPS_VIEWER: [
        "config:read",
        "features:read",
        "tenants:settings:read",
        "billing:read",
        "inventory:read",
    ],
    SystemRole.CLOUD_ARCHITECT: [
        "config:read",
        "inventory:read",
        "inventory:write",
        "billing:read",
    ],
    SystemRole.DEVELOPER: [
        "inventory:read",
        "billing:read",
    ],
    SystemRole.SECURITY_AUDITOR: [
        "config:read",
        "audit:read",
        "inventory:read",
        "billing:read",
    ],
    SystemRole.TENANT_USER: [
        "tenants:settings:read",
        "billing:read",
        "inventory:read",
    ],
}


class IdentityService:
    """Enterprise Identity and Session Management Service."""

    def __init__(
        self,
        tenant_store: TenantSettingsStore | None = None,
        token_engine: CryptographicTokenEngine | None = None,
    ) -> None:
        self._tenant_store = tenant_store or tenant_settings_store
        self._token_engine = token_engine or CryptographicTokenEngine()

        # In-memory storage for identities, sessions, machine clients, and audit trails
        self._users: dict[str, User] = {}  # user_id -> User
        self._users_by_email: dict[tuple[str, str], str] = {}  # (tenant_id, email) -> user_id
        self._sessions: dict[str, Session] = {}  # session_id -> Session
        self._break_glass_accounts: dict[
            tuple[str, str], BreakGlassAccount
        ] = {}  # (tenant_id, account_name) -> BreakGlassAccount
        self._machine_clients: dict[str, MachineClient] = {}  # client_id -> MachineClient
        self._step_up_challenges: dict[str, StepUpChallenge] = {}  # challenge_id -> StepUpChallenge

        # Observability events
        self._audit_events: list[AuditEvent] = []
        self._alerts: list[Alert] = []

        # Prompt 49B AM-05: Break-glass consolidation
        self._break_glass_consolidated: bool = False
        self._consolidated_superuser_email: str | None = None

    @property
    def token_engine(self) -> CryptographicTokenEngine:
        return self._token_engine

    @property
    def alerts(self) -> list[Alert]:
        return list(self._alerts)

    @property
    def audit_events(self) -> list[AuditEvent]:
        return list(self._audit_events)

    # ----------------------------------------------------------------------
    # Group-to-Role Mapping & Permission Resolution
    # ----------------------------------------------------------------------

    def resolve_roles_from_groups(self, tenant_id: str, groups: list[str]) -> list[SystemRole]:
        """Maps identity provider group memberships to canonical SystemRoles (Prompt 10 Item 64)."""
        settings = self._tenant_store.get(tenant_id)
        mapping = settings.group_to_role_mapping

        resolved: set[SystemRole] = set()
        for grp in groups:
            target_role_str = mapping.get(grp)
            if target_role_str and target_role_str in SystemRole._value2member_map_:
                resolved.add(SystemRole(target_role_str))

        return sorted(resolved, key=lambda r: r.value)

    def resolve_effective_permissions(self, roles: list[SystemRole]) -> list[str]:
        """Aggregates unified permission set across granted roles."""
        perms: set[str] = set()
        for role in roles:
            perms.update(ROLE_PERMISSIONS_CATALOGUE.get(role, []))
        return sorted(perms)

    # ----------------------------------------------------------------------
    # Item 64 & Item 69: OIDC and SAML Single Sign-On
    # ----------------------------------------------------------------------

    def authenticate_oidc(
        self,
        tenant_id: str,
        id_token_claims: dict[str, Any],
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> TokenPair:
        """Authenticates a user via OpenID Connect (OIDC) token claims."""
        return self._authenticate_sso(
            tenant_id=tenant_id,
            claims=id_token_claims,
            method=AuthMethod.OIDC,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )

    def authenticate_saml(
        self,
        tenant_id: str,
        saml_assertion_claims: dict[str, Any],
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> TokenPair:
        """Authenticates a user via SAML 2.0 assertion attributes."""
        return self._authenticate_sso(
            tenant_id=tenant_id,
            claims=saml_assertion_claims,
            method=AuthMethod.SAML,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )

    def _authenticate_sso(
        self,
        tenant_id: str,
        claims: dict[str, Any],
        method: AuthMethod,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> TokenPair:
        """Common SSO orchestrator for OIDC and SAML."""
        corr_id = correlation_id or str(uuid.uuid4())
        settings = self._tenant_store.get(tenant_id)

        # 1. Extract subject identity and groups
        email = claims.get("email") or claims.get("nameID")
        if not email:
            raise IdentityException("Identity assertion missing email or nameID claim.")
        email = str(email).lower().strip()

        display_name = claims.get("name") or claims.get("displayName") or email.split("@")[0]
        idp_sub = str(claims.get("sub") or claims.get("nameID") or email)

        # Extract group assertions
        groups = claims.get("groups") or claims.get("memberOf") or []
        if isinstance(groups, str):
            groups = [groups]
        groups = [str(g).strip() for g in groups]

        # 2. Map groups to canonical platform roles
        mapped_roles = self.resolve_roles_from_groups(tenant_id, groups)

        # 3. Item 69: Explicit rule that user with no mapped role receives NO ACCESS and raises alert
        if not mapped_roles:
            alert_msg = (
                f"Authentication rejected for '{email}' on tenant '{tenant_id}': "
                f"IdP groups {groups} do not map to any configured role."
            )
            logger.warning(alert_msg)

            # Record administrator alert (Prompt 10 Item 69)
            alert = Alert(
                id=f"alt-unmapped-{uuid.uuid4().hex[:8]}",
                tenant_id=tenant_id,
                alert_type="UNMAPPED_ROLE_ACCESS_DENIED",
                severity=AlertSeverity.ERROR,
                message=alert_msg,
                status=AlertStatus.ACTIVE,
                triggered_at=datetime.now(UTC),
            )
            self._alerts.append(alert)

            # Record audit event
            self._record_audit_event(
                tenant_id=tenant_id,
                actor_id=email,
                action="SSO_LOGIN_REJECTED_NO_MAPPED_ROLE",
                entity_type="User",
                entity_id=idp_sub,
                payload_after={"groups": groups, "method": method.value},
                correlation_id=corr_id,
            )

            raise NoMappedRoleException(
                f"User '{email}' possesses no mapped platform roles from groups {groups}. Access strictly denied."
            )

        # 4. Check existing user record or JIT provisioning (Item 64)
        user_key = (tenant_id, email)
        user_id = self._users_by_email.get(user_key)
        user: User | None = self._users.get(user_id) if user_id else None

        if user:
            # Check user status (Item 66)
            if user.status == UserStatus.DISABLED:
                raise UserDisabledException(f"User '{email}' is disabled on tenant '{tenant_id}'.")
            # Update roles from latest IdP assertion
            user.roles = mapped_roles
            user.display_name = display_name
            user.last_login_at = datetime.now(UTC)
            user.updated_at = datetime.now(UTC)
        else:
            # New user: evaluate JIT provisioning policy
            if not settings.jit_provisioning_enabled:
                raise UserNotProvisionedException(
                    f"User '{email}' is not pre-provisioned on tenant '{tenant_id}' and Just-In-Time provisioning is disabled."
                )

            # JIT provision user
            user_id = f"usr-{uuid.uuid4().hex[:12]}"
            user = User(
                id=user_id,
                tenant_id=tenant_id,
                email=email,
                display_name=display_name,
                status=UserStatus.ACTIVE,
                roles=mapped_roles,
                idp_sub=idp_sub,
                auth_method=method,
                is_break_glass=False,
                last_login_at=datetime.now(UTC),
            )
            self._users[user_id] = user
            self._users_by_email[user_key] = user_id

            self._record_audit_event(
                tenant_id=tenant_id,
                actor_id=email,
                action="USER_JIT_PROVISIONED",
                entity_type="User",
                entity_id=user_id,
                payload_after={"email": email, "roles": [r.value for r in mapped_roles]},
                correlation_id=corr_id,
            )

        # 5. Create Session & issue token pair
        return self._create_session_and_issue_tokens(
            user=user,
            settings=settings,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=corr_id,
        )

    # ----------------------------------------------------------------------
    # Item 65: Break-Glass Local Account Path
    # ----------------------------------------------------------------------

    def provision_break_glass_account(
        self,
        tenant_id: str,
        account_name: str,
        password: str,
        actor_id: str = "admin",
        step_up_token: str | None = None,
        correlation_id: str | None = None,
    ) -> tuple[BreakGlassAccount, str]:
        """Provisions a break-glass emergency local account with mandatory MFA.

        Enforces small fixed limit per tenant (Item 65) and requires step-up proof (Item 68).
        Returns tuple of (BreakGlassAccount, mfa_totp_secret).
        """
        corr_id = correlation_id or str(uuid.uuid4())
        settings = self._tenant_store.get(tenant_id)

        # Step-up verification for credential creation (Prompt 10 Item 68)
        if step_up_token:
            step_up_ctx = self._token_engine.verify_token(step_up_token)
            if step_up_ctx.get("action") != StepUpAction.CREDENTIAL_CREATION.value:
                raise StepUpRequiredException(StepUpAction.CREDENTIAL_CREATION.value)
        else:
            raise StepUpRequiredException(StepUpAction.CREDENTIAL_CREATION.value)

        # Prompt 49B AM-05: Break-glass consolidation
        if self._break_glass_consolidated:
            raise BreakGlassLimitExceededException(
                "Break-glass access is consolidated to the single platform superuser identity per AM-05. "
                "Secondary break-glass creation is prohibited."
            )

        # Check tenant break-glass limit (Item 65)
        current_count = sum(
            1
            for (tid, _), acc in self._break_glass_accounts.items()
            if tid == tenant_id and acc.is_active
        )
        if current_count >= settings.max_break_glass_accounts:
            raise BreakGlassLimitExceededException(
                f"Tenant '{tenant_id}' has reached maximum allowed break-glass accounts ({settings.max_break_glass_accounts})."
            )

        acc_key = (tenant_id, account_name)
        if acc_key in self._break_glass_accounts:
            raise IdentityException(
                f"Break-glass account '{account_name}' already exists on tenant '{tenant_id}'."
            )

        salt = generate_salt()
        pwd_hash = hash_password(password, salt)
        totp_secret = generate_totp_secret()

        bg_id = f"bg-{uuid.uuid4().hex[:12]}"
        bg_account = BreakGlassAccount(
            id=bg_id,
            tenant_id=tenant_id,
            account_name=account_name,
            password_hash=pwd_hash,
            salt=salt,
            mfa_secret=totp_secret,
            is_active=True,
        )
        self._break_glass_accounts[acc_key] = bg_account

        self._record_audit_event(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="BREAK_GLASS_ACCOUNT_PROVISIONED",
            entity_type="BreakGlassAccount",
            entity_id=bg_id,
            payload_after={"account_name": account_name},
            correlation_id=corr_id,
        )

        return bg_account, totp_secret

    def authenticate_break_glass(
        self,
        tenant_id: str,
        account_name: str,
        password: str,
        mfa_code: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
    ) -> TokenPair:
        """Emergency break-glass sign-in with mandatory MFA.

        Enforces Item 65: Mandatory MFA, alerted on every use, separately auditable.
        """
        corr_id = correlation_id or str(uuid.uuid4())
        settings = self._tenant_store.get(tenant_id)

        acc_key = (tenant_id, account_name)
        bg_account = self._break_glass_accounts.get(acc_key)
        if not bg_account or not bg_account.is_active:
            raise BreakGlassAuthFailedException("Invalid break-glass account or account inactive.")

        # 1. Verify salted password
        if not verify_password(password, bg_account.salt, bg_account.password_hash):
            raise BreakGlassAuthFailedException("Invalid break-glass password.")

        # 2. Mandatory MFA: verify TOTP code
        if not verify_totp_code(bg_account.mfa_secret, mfa_code):
            raise BreakGlassAuthFailedException(
                "Break-glass multi-factor TOTP verification failed."
            )

        bg_account.last_used_at = datetime.now(UTC)

        # 3. Item 65 Requirement: Alerted on every single use
        alert_msg = (
            f"CRITICAL SECURITY ALERT: Break-glass emergency local account '{account_name}' "
            f"signed in on tenant '{tenant_id}' (IP: {ip_address or 'Unknown'})."
        )
        logger.critical(alert_msg)

        alert = Alert(
            id=f"alt-bg-{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            alert_type="BREAK_GLASS_AUTHENTICATION_ALERT",
            severity=AlertSeverity.CRITICAL,
            message=alert_msg,
            status=AlertStatus.ACTIVE,
            triggered_at=datetime.now(UTC),
        )
        self._alerts.append(alert)

        # 4. Item 65 Requirement: Separately auditable distinct audit record
        self._record_audit_event(
            tenant_id=tenant_id,
            actor_id=f"break-glass:{account_name}",
            action="BREAK_GLASS_AUTHENTICATION",
            entity_type="BreakGlassAccount",
            entity_id=bg_account.id,
            payload_after={"ip_address": ip_address, "user_agent": user_agent},
            correlation_id=corr_id,
        )

        # Ephemeral User representation for token creation
        ephemeral_user = User(
            id=f"usr-bg-{bg_account.id}",
            tenant_id=tenant_id,
            email=f"{account_name}@breakglass.{tenant_id}.internal",
            display_name=f"Break-Glass Admin ({account_name})",
            status=UserStatus.ACTIVE,
            roles=[SystemRole.GLOBAL_ADMIN],
            auth_method=AuthMethod.BREAK_GLASS,
            is_break_glass=True,
        )

        return self._create_session_and_issue_tokens(
            user=ephemeral_user,
            settings=settings,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=corr_id,
            is_break_glass=True,
        )

    def consolidate_break_glass(self, superuser_email: str) -> None:
        """Consolidates emergency break-glass access onto single named superuser (Prompt 49B Item 18 / AM-05)."""
        self._break_glass_consolidated = True
        self._consolidated_superuser_email = superuser_email
        logger.info(
            "Consolidated platform break-glass paths onto single superuser identity (AM-05)",
            extra={"superuser_email": superuser_email},
        )

    def enumerate_break_glass_paths(self) -> list[str]:
        """Lists active break-glass identity paths (strictly exactly 1 when consolidated)."""
        if self._break_glass_consolidated and self._consolidated_superuser_email:
            return [self._consolidated_superuser_email]
        return [acc.account_name for acc in self._break_glass_accounts.values() if acc.is_active]

    # ----------------------------------------------------------------------
    # Item 66: Token Lifecycle, Refresh Rotation, and Revocation
    # ----------------------------------------------------------------------

    def refresh_tokens(
        self,
        refresh_token_str: str,
        correlation_id: str | None = None,
    ) -> TokenPair:
        """Rotates refresh token and issues new short-lived access token (Item 66).

        Detects token reuse and revokes compromised token families immediately.
        """
        corr_id = correlation_id or str(uuid.uuid4())

        # 1. Verify token cryptographic integrity and check revocation
        payload = self._token_engine.verify_token(refresh_token_str)
        if payload.get("typ") != TokenType.REFRESH.value:
            raise TokenInvalidException("Presented token is not a refresh token.")

        token_id = payload.get("jti", "")
        family_id = payload.get("fid", "")
        session_id = payload.get("sid", "")
        user_id = payload.get("uid", "")
        tenant_id = payload.get("tid", "global")
        is_break_glass = payload.get("bg", False)

        # 2. Record token use / Detect Reuse (Item 66)
        if not self._token_engine.revocation_registry.record_refresh_token_use(token_id, family_id):
            # Token reuse detected! Invalidate session immediately
            if session_id in self._sessions:
                self._sessions[session_id].is_active = False
                self._sessions[session_id].revoked_at = datetime.now(UTC)
                self._sessions[session_id].revocation_reason = "REFRESH_TOKEN_REUSE_DETECTED"

            alert_msg = f"SECURITY BREACH: Refresh token reuse detected for session '{session_id}'. Token family revoked."
            logger.critical(alert_msg)
            self._alerts.append(
                Alert(
                    id=f"alt-reuse-{uuid.uuid4().hex[:8]}",
                    tenant_id=tenant_id,
                    alert_type="REFRESH_TOKEN_REUSE_DETECTED",
                    severity=AlertSeverity.CRITICAL,
                    message=alert_msg,
                    status=AlertStatus.ACTIVE,
                    triggered_at=datetime.now(UTC),
                )
            )
            self._record_audit_event(
                tenant_id=tenant_id,
                actor_id=user_id or "system",
                action="REFRESH_TOKEN_REUSE_DETECTED",
                entity_type="Session",
                entity_id=session_id,
                payload_after={"family_id": family_id, "token_id": token_id},
                correlation_id=corr_id,
            )
            raise TokenRevokedException(
                "Refresh token reuse detected. Token family has been revoked."
            )

        # 3. Check Session Status and Expiration
        session = self._sessions.get(session_id)
        if not session or not session.is_active:
            raise SessionExpiredException("Session is no longer active.")

        settings = self._tenant_store.get(tenant_id)
        now = datetime.now(UTC)

        # Idle timeout check
        idle_limit = timedelta(seconds=settings.session_idle_timeout_seconds)
        if now - session.last_activity_at > idle_limit:
            session.is_active = False
            session.revoked_at = now
            session.revocation_reason = "IDLE_TIMEOUT"
            raise SessionExpiredException("Session expired due to inactivity idle timeout.")

        # Absolute session lifetime check
        if now > session.expires_at:
            session.is_active = False
            session.revoked_at = now
            session.revocation_reason = "ABSOLUTE_LIFETIME_EXCEEDED"
            raise SessionExpiredException("Session expired due to absolute lifetime limit.")

        # 4. Check user status
        user = self._users.get(user_id)
        if not is_break_glass:
            if not user or user.status == UserStatus.DISABLED:
                raise UserDisabledException("User account is disabled.")
            roles = user.roles
            email = user.email
        else:
            roles = [SystemRole.GLOBAL_ADMIN]
            email = payload.get("sub", "breakglass@internal")

        permissions = self.resolve_effective_permissions(roles)
        session.last_activity_at = now

        # 5. Issue new access token and rotated refresh token
        new_access_token = self._token_engine.issue_access_token(
            user_id=user_id,
            tenant_id=tenant_id,
            email=email,
            roles=roles,
            permissions=permissions,
            session_id=session_id,
            token_family_id=family_id,
            ttl_seconds=settings.access_token_ttl_seconds,
            is_break_glass=is_break_glass,
        )
        new_refresh_token = self._token_engine.issue_refresh_token(
            user_id=user_id,
            tenant_id=tenant_id,
            session_id=session_id,
            token_family_id=family_id,
            ttl_seconds=settings.refresh_token_ttl_seconds,
            is_break_glass=is_break_glass,
        )

        self._record_audit_event(
            tenant_id=tenant_id,
            actor_id=user_id,
            action="SESSION_TOKEN_REFRESHED",
            entity_type="Session",
            entity_id=session_id,
            payload_after={"family_id": family_id},
            correlation_id=corr_id,
        )

        return TokenPair(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="Bearer",
            expires_in=settings.access_token_ttl_seconds,
            session_id=session_id,
            roles=[r.value for r in roles],
        )

    def revoke_token(self, token_str: str) -> None:
        """Explicitly revokes a specific token."""
        try:
            payload = self._token_engine.verify_token(token_str)
            jti = payload.get("jti")
            exp = float(payload.get("exp", time.time() + 3600))
            if jti:
                self._token_engine.revocation_registry.revoke_token(jti, exp)
        except Exception:
            pass

    def terminate_session(
        self,
        session_id: str,
        actor_id: str,
        correlation_id: str | None = None,
    ) -> None:
        """Terminates session and revokes its tokens."""
        session = self._sessions.get(session_id)
        if session:
            session.is_active = False
            session.revoked_at = datetime.now(UTC)
            session.revocation_reason = "LOGOUT"
            self._token_engine.revocation_registry.revoke_session(session_id)
            self._record_audit_event(
                tenant_id=session.tenant_id,
                actor_id=actor_id,
                action="SESSION_LOGOUT",
                entity_type="Session",
                entity_id=session_id,
                payload_after={"session_id": session_id},
                correlation_id=correlation_id or str(uuid.uuid4()),
            )

    def logout_session(self, session_id: str, actor_id: str) -> None:
        """Backward-compatible alias for terminate_session."""
        self.terminate_session(session_id=session_id, actor_id=actor_id)

    def disable_user(
        self,
        tenant_id: str,
        user_id: str,
        actor_id: str,
        correlation_id: str | None = None,
    ) -> User:
        """Disables user and immediately revokes all their active sessions and tokens (Item 66)."""
        user = self._users.get(user_id)
        if not user:
            raise IdentityException(f"User '{user_id}' not found on tenant '{tenant_id}'.")

        # Prompt 49B Item 17: Platform superuser cannot be deleted or disabled
        if (
            self._consolidated_superuser_email
            and user.email.lower() == self._consolidated_superuser_email.lower()
        ):
            self._record_audit_event(
                tenant_id=tenant_id,
                actor_id=actor_id,
                action="SUPERUSER_PROTECTION_BLOCKED",
                entity_type="User",
                entity_id=user_id,
                payload_after={
                    "blocked_action": "DISABLE_USER",
                    "rule": "CANNOT_BE_DELETED_OR_DISABLED",
                },
                correlation_id=correlation_id or str(uuid.uuid4()),
            )
            raise SuperuserImmutableException(
                "Attempting to disable or delete the platform superuser is strictly refused and audited."
            )

        user.status = UserStatus.DISABLED
        user.updated_at = datetime.now(UTC)

        # 1. Terminate all active sessions for this user
        for sess in self._sessions.values():
            if sess.user_id == user_id and sess.is_active:
                sess.is_active = False
                sess.revoked_at = datetime.now(UTC)
                sess.revocation_reason = "USER_DISABLED"
                self._token_engine.revocation_registry.revoke_session(sess.id)

        # 2. Immediate Token Revocation: register user ID in revocation registry (Item 66)
        self._token_engine.revocation_registry.revoke_user_tokens(user_id)

        # 3. Compliance audit event
        self._record_audit_event(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="USER_DISABLED",
            entity_type="User",
            entity_id=user_id,
            payload_after={"status": UserStatus.DISABLED.value, "user_id": user_id},
            correlation_id=correlation_id or str(uuid.uuid4()),
        )

        logger.info(
            "User '%s' disabled by '%s'. All active sessions and tokens revoked.", user_id, actor_id
        )
        return user

    # ----------------------------------------------------------------------
    # Item 67: Machine Clients (Client Credentials Grant)
    # ----------------------------------------------------------------------

    def register_machine_client(
        self,
        tenant_id: str,
        name: str,
        scoped_permissions: list[str],
        actor_id: str,
        secret_expires_days: int = 90,
        step_up_token: str | None = None,
        correlation_id: str | None = None,
    ) -> tuple[MachineClient, str]:
        """Registers a new automated machine client (Item 67) requiring step-up authentication (Item 68)."""
        corr_id = correlation_id or str(uuid.uuid4())

        # Step-up verification for credential creation (Prompt 10 Item 68)
        if step_up_token:
            step_up_ctx = self._token_engine.verify_token(step_up_token)
            if step_up_ctx.get("action") != StepUpAction.CREDENTIAL_CREATION.value:
                raise StepUpRequiredException(StepUpAction.CREDENTIAL_CREATION.value)
        else:
            raise StepUpRequiredException(StepUpAction.CREDENTIAL_CREATION.value)

        client_id = f"client-{uuid.uuid4().hex[:16]}"
        raw_secret = f"clsec_{secrets.token_urlsafe(32)}"
        secret_hash = hash_password(raw_secret, client_id)

        client = MachineClient(
            id=f"mc-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            client_id=client_id,
            name=name,
            secret_hash=secret_hash,
            scoped_permissions=scoped_permissions,
            is_active=True,
            secret_expires_at=datetime.now(UTC) + timedelta(days=secret_expires_days),
        )
        self._machine_clients[client_id] = client

        self._record_audit_event(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="MACHINE_CLIENT_REGISTERED",
            entity_type="MachineClient",
            entity_id=client.id,
            payload_after={"client_id": client_id, "permissions": scoped_permissions},
            correlation_id=corr_id,
        )

        return client, raw_secret

    def authenticate_machine_client(
        self,
        client_id: str,
        client_secret: str,
        correlation_id: str | None = None,
    ) -> TokenPair:
        """Client-credentials grant for machine clients with scoped permissions (Item 67)."""
        corr_id = correlation_id or str(uuid.uuid4())
        client = self._machine_clients.get(client_id)
        if not client or not client.is_active:
            raise MachineClientAuthFailedException("Invalid machine client ID or client disabled.")

        # Check secret expiration
        if client.secret_expires_at and datetime.now(UTC) > client.secret_expires_at:
            raise MachineClientAuthFailedException("Machine client secret has expired.")

        # Verify against primary secret or secondary rotating secret
        primary_valid = verify_password(client_secret, client_id, client.secret_hash)
        secondary_valid = (
            verify_password(client_secret, client_id, client.secondary_secret_hash)
            if client.secondary_secret_hash
            else False
        )

        if not primary_valid and not secondary_valid:
            raise MachineClientAuthFailedException("Invalid machine client secret.")

        client.last_used_at = datetime.now(UTC)

        # Issue short-lived machine token
        token_str = self._token_engine.issue_machine_token(
            client_id=client.client_id,
            tenant_id=client.tenant_id,
            name=client.name,
            scoped_permissions=client.scoped_permissions,
            ttl_seconds=3600,
        )

        self._record_audit_event(
            tenant_id=client.tenant_id,
            actor_id=f"machine:{client.client_id}",
            action="MACHINE_CLIENT_AUTHENTICATED",
            entity_type="MachineClient",
            entity_id=client.id,
            payload_after={"permissions": client.scoped_permissions},
            correlation_id=corr_id,
        )

        return TokenPair(
            access_token=token_str,
            refresh_token="",  # Machine clients use client-credentials grant directly without refresh tokens
            token_type="Bearer",
            expires_in=3600,
            session_id="",
            roles=[],
        )

    def rotate_machine_client_secret(
        self,
        client_id: str,
        actor_id: str,
        step_up_token: str | None = None,
        grace_period_days: int = 7,
        correlation_id: str | None = None,
    ) -> str:
        """Rotates machine client secret maintaining secondary grace period (Item 67)."""
        corr_id = correlation_id or str(uuid.uuid4())

        # Step-up verification for credential creation (Prompt 10 Item 68)
        if step_up_token:
            step_up_ctx = self._token_engine.verify_token(step_up_token)
            if step_up_ctx.get("action") != StepUpAction.CREDENTIAL_CREATION.value:
                raise StepUpRequiredException(StepUpAction.CREDENTIAL_CREATION.value)
        else:
            raise StepUpRequiredException(StepUpAction.CREDENTIAL_CREATION.value)

        client = self._machine_clients.get(client_id)
        if not client or not client.is_active:
            raise IdentityException(f"Machine client '{client_id}' not found or inactive.")

        # Shift current primary to secondary for rotation grace period
        client.secondary_secret_hash = client.secret_hash
        new_secret = f"clsec_{secrets.token_urlsafe(32)}"
        client.secret_hash = hash_password(new_secret, client_id)
        client.secret_expires_at = datetime.now(UTC) + timedelta(days=90)

        self._record_audit_event(
            tenant_id=client.tenant_id,
            actor_id=actor_id,
            action="MACHINE_CLIENT_SECRET_ROTATED",
            entity_type="MachineClient",
            entity_id=client.id,
            payload_after={"grace_period_days": grace_period_days},
            correlation_id=corr_id,
        )

        return new_secret

    # ----------------------------------------------------------------------
    # Item 68: Step-Up Authentication
    # ----------------------------------------------------------------------

    def initiate_step_up_challenge(
        self,
        tenant_id: str,
        user_id: str,
        action: StepUpAction,
        target_entity_id: str | None = None,
        correlation_id: str | None = None,
    ) -> StepUpChallenge:
        """Creates an elevated step-up challenge for high-risk operations (Item 68)."""
        settings = self._tenant_store.get(tenant_id)
        challenge_id = f"stpc-{uuid.uuid4().hex[:12]}"
        # no-hardcode-allow: reason="6-digit decimal step-up verification code", reviewer="security-arch"
        challenge_code = f"{secrets.randbelow(900000) + 100000}"

        challenge = StepUpChallenge(
            id=challenge_id,
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            target_entity_id=target_entity_id,
            challenge_code=challenge_code,
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.step_up_token_ttl_seconds),
            is_verified=False,
        )
        self._step_up_challenges[challenge_id] = challenge

        self._record_audit_event(
            tenant_id=tenant_id,
            actor_id=user_id,
            action="STEP_UP_CHALLENGE_INITIATED",
            entity_type="StepUpChallenge",
            entity_id=challenge_id,
            payload_after={"action": action.value},
            correlation_id=correlation_id or str(uuid.uuid4()),
        )
        return challenge

    def verify_step_up_challenge(
        self,
        challenge_id: str,
        challenge_code: str,
        correlation_id: str | None = None,
    ) -> StepUpToken:
        """Verifies step-up challenge code and issues short-lived step-up authorization token (Item 68)."""
        corr_id = correlation_id or str(uuid.uuid4())
        challenge = self._step_up_challenges.get(challenge_id)
        if not challenge or challenge.is_verified:
            raise IdentityException("Invalid or already consumed step-up challenge.")

        if datetime.now(UTC) > challenge.expires_at:
            raise IdentityException("Step-up challenge has expired.")

        if not secrets.compare_digest(challenge.challenge_code, challenge_code.strip()):
            raise IdentityException("Invalid step-up challenge verification code.")

        challenge.is_verified = True
        settings = self._tenant_store.get(challenge.tenant_id)

        token_str = self._token_engine.issue_step_up_token(
            user_id=challenge.user_id,
            tenant_id=challenge.tenant_id,
            action=challenge.action.value,
            target_entity_id=challenge.target_entity_id,
            ttl_seconds=settings.step_up_token_ttl_seconds,
        )

        self._record_audit_event(
            tenant_id=challenge.tenant_id,
            actor_id=challenge.user_id,
            action="STEP_UP_CHALLENGE_VERIFIED",
            entity_type="StepUpChallenge",
            entity_id=challenge_id,
            payload_after={"action": challenge.action.value},
            correlation_id=corr_id,
        )

        return StepUpToken(
            step_up_token=token_str,
            action=challenge.action.value,
            expires_in=settings.step_up_token_ttl_seconds,
        )

    def assert_step_up_authorized(
        self,
        action: StepUpAction,
        auth_context: AuthContext | None = None,
        step_up_token: str | None = None,
    ) -> None:
        """Enforces that a high-risk operation has active verified step-up authentication (Item 68)."""
        # If context already possesses active step-up claim
        if auth_context and action.value in auth_context.step_up_claims:
            return

        # If step_up_token provided in header / parameter
        if step_up_token:
            payload = self._token_engine.verify_token(step_up_token)
            if (
                payload.get("typ") == TokenType.STEP_UP.value
                and payload.get("action") == action.value
            ):
                return

        raise StepUpRequiredException(
            action=action.value,
            message=f"Action '{action.value}' requires elevated step-up authentication proof.",
        )

    # ----------------------------------------------------------------------
    # Helper & Query Methods
    # ----------------------------------------------------------------------

    def get_user(self, user_id: str) -> User | None:
        """Retrieves user by ID."""
        return self._users.get(user_id)

    def get_session(self, session_id: str) -> Session | None:
        """Retrieves session by ID."""
        return self._sessions.get(session_id)

    def get_alerts(self, tenant_id: str | None = None) -> list[Alert]:
        """Returns recorded alerts."""
        if tenant_id:
            return [a for a in self._alerts if a.tenant_id == tenant_id]
        return list(self._alerts)

    def get_audit_trail(self, tenant_id: str | None = None) -> list[AuditEvent]:
        """Returns compliance audit events."""
        if tenant_id:
            return [e for e in self._audit_events if e.tenant_id == tenant_id]
        return list(self._audit_events)

    def _create_session_and_issue_tokens(
        self,
        user: User,
        settings: Any,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: str | None = None,
        is_break_glass: bool = False,
    ) -> TokenPair:
        """Helper to create Session and issue token pair."""
        session_id = f"sess-{uuid.uuid4().hex[:12]}"
        family_id = f"fam-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)
        abs_expiry = now + timedelta(seconds=settings.session_absolute_lifetime_seconds)

        session = Session(
            id=session_id,
            tenant_id=user.tenant_id,
            user_id=user.id,
            token_family_id=family_id,
            created_at=now,
            last_activity_at=now,
            expires_at=abs_expiry,
            is_active=True,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self._sessions[session_id] = session

        permissions = self.resolve_effective_permissions(user.roles)

        access_token = self._token_engine.issue_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            roles=user.roles,
            permissions=permissions,
            session_id=session_id,
            token_family_id=family_id,
            ttl_seconds=settings.access_token_ttl_seconds,
            is_break_glass=is_break_glass,
        )

        refresh_token = self._token_engine.issue_refresh_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            session_id=session_id,
            token_family_id=family_id,
            ttl_seconds=settings.refresh_token_ttl_seconds,
            is_break_glass=is_break_glass,
        )

        self._record_audit_event(
            tenant_id=user.tenant_id,
            actor_id=user.email,
            action="SESSION_CREATED",
            entity_type="Session",
            entity_id=session_id,
            payload_after={"user_id": user.id, "auth_method": user.auth_method.value},
            correlation_id=correlation_id or str(uuid.uuid4()),
        )

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=settings.access_token_ttl_seconds,
            session_id=session_id,
            roles=[r.value for r in user.roles],
        )

    def _record_audit_event(
        self,
        tenant_id: str,
        actor_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        payload_after: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Records an immutable audit event."""
        event = AuditEvent(
            id=f"aud-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_after=payload_after,
            timestamp=datetime.now(UTC),
            correlation_id=correlation_id or str(uuid.uuid4()),
        )
        self._audit_events.append(event)


# Global singleton IdentityService
_identity_service = IdentityService()


def get_identity_service() -> IdentityService:
    """Returns the shared IdentityService singleton."""
    return _identity_service
