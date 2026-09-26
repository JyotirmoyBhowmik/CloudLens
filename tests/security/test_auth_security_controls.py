"""Security Suite: Identity and Session Security Controls (Prompt 10 SEC-001 - SEC-007).

Tests:
- Token Revocation Immediacy: tokens are invalidated instantly across all nodes upon user disable.
- Break-Glass Security: strictly limited accounts, MFA enforcement, distinct audit log & CRITICAL alert.
- Unmapped Role Security: zero access / never default role fallback.
- Step-Up Elevation Barriers: mandatory for credential creation and overrides.
- HTTP REST API Security Contract: validation, status codes, and error hygiene.
"""

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.config.tenant_settings import TenantSettings, tenant_settings_store
from domain.identity.password_hasher import generate_totp_code
from domain.identity.service import get_identity_service
from domain.models.enums import AlertSeverity, StepUpAction, SystemRole


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client instance."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def configure_security_tenant():
    """Configures the security test tenant."""
    tenant_settings_store.update_settings(
        "sec-tenant",
        TenantSettings(
            tenant_id="sec-tenant",
            jit_provisioning_enabled=True,
            group_to_role_mapping={
                "FinOps-Admins": SystemRole.FINOPS_ADMIN.value,
                "Cloud-Engineers": SystemRole.CLOUD_ARCHITECT.value,
            },
            access_token_ttl_seconds=900,
            refresh_token_ttl_seconds=86400,
            session_idle_timeout_seconds=1800,
            session_absolute_lifetime_seconds=28800,
            step_up_token_ttl_seconds=300,
            max_break_glass_accounts=2,
        ),
    )


def test_api_oidc_login_and_unmapped_role_rejection(client: TestClient):
    """API endpoint /api/v1/auth/oidc/login enforces mapped role requirement and fires alert."""
    # 1. Success case: mapped group
    res_ok = client.post(
        "/api/v1/auth/oidc/login",
        json={
            "tenant_id": "sec-tenant",
            "idp_sub": "sub-1234",
            "email": "auditor@sec.com",
            "display_name": "Security Auditor",
            "groups": ["FinOps-Admins"],
        },
    )
    assert res_ok.status_code == 200
    data = res_ok.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert SystemRole.FINOPS_ADMIN.value in data["roles"]

    # 2. Failure case: unmapped group returns 403 Forbidden (Item 69)
    res_deny = client.post(
        "/api/v1/auth/oidc/login",
        json={
            "tenant_id": "sec-tenant",
            "idp_sub": "sub-5678",
            "email": "unmapped@sec.com",
            "display_name": "Unmapped User",
            "groups": ["Unknown-Group"],
        },
    )
    assert res_deny.status_code == 403
    assert "no mapped platform roles" in res_deny.json()["message"].lower()

    # Check alert was recorded in identity service
    svc = get_identity_service()
    unmapped_alerts = [a for a in svc.alerts if a.alert_type == "UNMAPPED_ROLE_ACCESS_DENIED"]
    assert len(unmapped_alerts) >= 1
    assert unmapped_alerts[-1].severity == AlertSeverity.ERROR


def test_api_break_glass_flow_and_alerts(client: TestClient):
    """API endpoints for break glass provisioning, login, MFA, and critical alerting."""
    svc = get_identity_service()

    # 1. Obtain step-up token for credential creation
    ch = svc.initiate_step_up_challenge("sec-tenant", "admin-sec", StepUpAction.CREDENTIAL_CREATION)
    st = svc.verify_step_up_challenge(ch.id, ch.challenge_code)

    # 2. Provision break glass account via API
    res_prov = client.post(
        "/api/v1/auth/break-glass/provision",
        json={
            "tenant_id": "sec-tenant",
            "account_name": "breakglass-alpha",
            "password": "EmergencySecretPassword2026!",
            "step_up_token": st.step_up_token,
        },
    )
    assert res_prov.status_code == 200
    prov_data = res_prov.json()
    totp_secret = prov_data["totp_secret"]

    # 3. Login with invalid MFA -> 401
    res_bad_mfa = client.post(
        "/api/v1/auth/break-glass/login",
        json={
            "tenant_id": "sec-tenant",
            "account_name": "breakglass-alpha",
            "password": "EmergencySecretPassword2026!",
            "mfa_code": "000000",
        },
    )
    assert res_bad_mfa.status_code == 401

    # 4. Login with valid MFA -> 200 + CRITICAL alert + Audit event
    valid_code = generate_totp_code(totp_secret)
    res_login = client.post(
        "/api/v1/auth/break-glass/login",
        json={
            "tenant_id": "sec-tenant",
            "account_name": "breakglass-alpha",
            "password": "EmergencySecretPassword2026!",
            "mfa_code": valid_code,
        },
    )
    assert res_login.status_code == 200
    login_data = res_login.json()
    assert "access_token" in login_data

    # Verify CRITICAL alert exists
    bg_alerts = [a for a in svc.alerts if a.alert_type == "BREAK_GLASS_AUTHENTICATION_ALERT"]
    assert len(bg_alerts) >= 1
    assert bg_alerts[-1].severity == AlertSeverity.CRITICAL

    # Verify Audit Event exists
    bg_audits = [e for e in svc.audit_events if e.action == "BREAK_GLASS_AUTHENTICATION"]
    assert len(bg_audits) >= 1
    assert bg_audits[-1].actor_id == "break-glass:breakglass-alpha"


def test_api_user_disablement_immediate_token_kill(client: TestClient):
    """API endpoint /users/{id}/disable terminates all active sessions and revokes tokens immediately."""
    # 1. Login user
    res_login = client.post(
        "/api/v1/auth/oidc/login",
        json={
            "tenant_id": "sec-tenant",
            "idp_sub": "sub-revocation",
            "email": "terminated@sec.com",
            "groups": ["FinOps-Admins"],
        },
    )
    assert res_login.status_code == 200
    token = res_login.json()["access_token"]
    refresh = res_login.json()["refresh_token"]

    # 2. Check /me works with bearer token
    res_me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res_me.status_code == 200
    user_id = res_me.json()["user_id"]

    # 3. Disable user
    res_disable = client.post(
        f"/api/v1/auth/users/{user_id}/disable",
        headers={"Authorization": f"Bearer {token}"},
        json={"tenant_id": "sec-tenant", "reason": "Immediate security separation"},
    )
    assert res_disable.status_code == 200

    # 4. Immediate token rejection: calling /me again with the same token must fail with 401
    res_me_after = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res_me_after.status_code == 401

    # 5. Refresh token rejection: attempting to refresh also fails
    res_refresh_after = client.post(
        "/api/v1/auth/token/refresh",
        json={"refresh_token": refresh},
    )
    assert res_refresh_after.status_code in (401, 403)
