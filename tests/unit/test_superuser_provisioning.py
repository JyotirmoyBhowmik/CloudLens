"""Unit & Integration Tests for Superuser Provisioning & Break-Glass Consolidation (Prompt 49B).

Tests:
1. Item 15 & 16: Superuser identity held as master data with shipped default, provisioned with Super Admin and unrestricted scope.
2. Item 17: Mandatory non-disableable MFA, no password until one-time activation, sign-in alerting & elevated audit, immutable account protections.
3. Item 18: Break-glass consolidation: single break-glass path per AM-05; secondary break-glass creation blocked.
4. Item 19: Delegation rule: handover to Platform Admin, routine-use detection and alerting after consecutive days.
5. Item 20: Identity verification report generation and publication to disk.
6. REST API endpoints for provisioning, activation, sign-in, delegation, and reporting.
"""

import json

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.bootstrap import (
    get_superuser_service,
    load_superuser_master_data,
)
from domain.identity.password_hasher import generate_totp_code
from domain.identity.service import get_identity_service
from domain.models.enums import AlertSeverity, SystemRole
from domain.models.exceptions import (
    BreakGlassLimitExceededException,
    SuperuserActivationException,
    SuperuserImmutableException,
)
from domain.rbac.models import ResourceTarget
from domain.rbac.service import get_rbac_service
from masterdata.registry import is_master_registered

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_service():
    """Resets identity and superuser state between test runs."""
    identity_svc = get_identity_service()
    identity_svc._users.clear()
    identity_svc._alerts.clear()
    identity_svc._audit_events.clear()
    identity_svc._break_glass_accounts.clear()
    identity_svc._break_glass_consolidated = False
    identity_svc._consolidated_superuser_email = None

    rbac_svc = get_rbac_service()
    rbac_svc.clear_scope_grants()

    service = get_superuser_service()
    service._activation_tokens.clear()
    service._credentials.clear()
    service._delegation_completed = False
    service._routine_days_count = 0
    service._last_routine_date = None
    service._audit_records.clear()
    service._alerts.clear()
    yield


# ==============================================================================
# Item 15 & 16: Master Data Resolution & Superuser Provisioning
# ==============================================================================


def test_superuser_identity_held_as_master_data():
    """Item 16: Superuser identity is held as master data with shipped default (no hardcoded address)."""
    assert is_master_registered("SUPERUSER_IDENTITY") is True

    master_attrs = load_superuser_master_data()
    assert "email" in master_attrs
    assert "@" in master_attrs["email"]
    assert master_attrs["unrestricted_scope"] is True
    assert master_attrs["max_routine_days"] == 3


def test_superuser_provisioning_with_super_admin_and_unrestricted_scope():
    """Item 15: Exactly one superuser with Super Admin role and unrestricted scope."""
    service = get_superuser_service()
    user, token = service.provision_superuser()

    master_attrs = load_superuser_master_data()
    expected_email = master_attrs["email"]

    assert user.email == expected_email
    assert user.roles == [SystemRole.GLOBAL_ADMIN]
    assert user.is_break_glass is True

    # Scope evaluation across all arbitrary clouds and tenants
    rbac_svc = get_rbac_service()
    decision_aws = rbac_svc.authorize(
        user_id=user.id,
        tenant_id="tenant-any",
        role_codes=[SystemRole.GLOBAL_ADMIN.value],
        permission_code="billing:read",
        target=ResourceTarget(provider="aws", resource_id="res-1"),
    )
    assert decision_aws.allowed is True

    decision_azure = rbac_svc.authorize(
        user_id=user.id,
        tenant_id="tenant-other",
        role_codes=[SystemRole.GLOBAL_ADMIN.value],
        permission_code="config:write",
        target=ResourceTarget(provider="azure", is_administrative=True),
    )
    assert decision_azure.allowed is True


# ==============================================================================
# Item 17: Security Controls, Activation Flow & Invariant Controls
# ==============================================================================


def test_no_password_until_first_use_activation():
    """Item 17: No password shipped, embedded, or defaulted; established at first use."""
    service = get_superuser_service()
    user, token = service.provision_superuser()

    master_attrs = load_superuser_master_data()
    expected_email = master_attrs["email"]

    # Verify credentials dictionary has no pre-set password
    assert expected_email not in service._credentials

    # Attempting to sign in prior to activation must fail
    with pytest.raises(SuperuserActivationException) as exc_info:
        service.authenticate_superuser(
            email=expected_email,
            password="SomePassword123!",
            mfa_code="123456",
        )
    assert "Superuser is not yet activated" in str(exc_info.value)


def test_superuser_activation_flow():
    """Item 17: Activation via one-time, time-limited token with mandatory MFA setup."""
    service = get_superuser_service()
    user, token = service.provision_superuser()

    master_attrs = load_superuser_master_data()
    expected_email = master_attrs["email"]

    # 1. Invalid activation token rejected
    with pytest.raises(SuperuserActivationException):
        service.activate_superuser(
            activation_token="bogus-token",
            password="StrongPassword123!",
        )

    # 2. Weak password rejected
    with pytest.raises(SuperuserActivationException):
        service.activate_superuser(
            activation_token=token.token,
            password="weak",
        )

    # 3. Successful first-use activation
    res = service.activate_superuser(
        activation_token=token.token,
        password="SuperSecurePassword123!",
    )
    assert res["status"] == "ACTIVATED"
    assert res["superuser_email"] == expected_email
    assert "totp_secret" in res

    # 4. Attempting to re-use token fails (single-use constraint)
    with pytest.raises(SuperuserActivationException) as exc_reused:
        service.activate_superuser(
            activation_token=token.token,
            password="AnotherPassword123!",
        )
    assert "already been redeemed" in str(exc_reused.value)


def test_superuser_sign_in_alerting_and_elevated_audit():
    """Item 17: Every sign-in raises an alert to security address and writes distinct elevated audit."""
    service = get_superuser_service()
    user, token = service.provision_superuser()

    master_attrs = load_superuser_master_data()
    expected_email = master_attrs["email"]

    act_res = service.activate_superuser(
        activation_token=token.token,
        password="SuperSecurePassword123!",
    )
    totp_secret = act_res["totp_secret"]
    valid_totp = generate_totp_code(totp_secret)

    # 1. Invalid TOTP code fails
    with pytest.raises(SuperuserActivationException):
        service.authenticate_superuser(
            email=expected_email,
            password="SuperSecurePassword123!",
            mfa_code="000000",
        )

    # 2. Valid authentication succeeds
    tokens = service.authenticate_superuser(
        email=expected_email,
        password="SuperSecurePassword123!",
        mfa_code=valid_totp,
        ip_address="198.51.100.25",
    )
    assert tokens.access_token is not None
    assert tokens.refresh_token is not None

    # 3. Security alert raised to configured security address
    assert len(service._alerts) >= 1
    alert = service._alerts[-1]
    assert alert.severity == AlertSeverity.CRITICAL
    assert alert.alert_type == "SUPERUSER_SIGN_IN_ALERT"
    assert "198.51.100.25" in alert.message

    # 4. Distinct audit record with elevated retention (2555 days / 7 years)
    assert len(service._audit_records) >= 1
    audit_event = next(e for e in service._audit_records if e.action == "SUPERUSER_SIGN_IN")
    assert audit_event.actor_id == expected_email
    assert audit_event.payload_after.get("retention_days") == 2555


def test_immutable_account_protections():
    """Item 17: Superuser cannot be deleted, downgraded below Super Admin, or un-audited."""
    service = get_superuser_service()
    user, _ = service.provision_superuser()

    master_attrs = load_superuser_master_data()
    expected_email = master_attrs["email"]

    # 1. Deletion / disablement blocked
    with pytest.raises(SuperuserImmutableException) as exc_del:
        service.assert_superuser_invariants(target_email=expected_email, action="DELETE")
    assert "cannot be deleted" in str(exc_del.value)

    # Also test via IdentityService.disable_user
    identity_svc = get_identity_service()
    with pytest.raises(SuperuserImmutableException):
        identity_svc.disable_user(
            tenant_id=user.tenant_id,
            user_id=user.id,
            actor_id="admin",
        )

    # 2. Downgrade below Super Admin blocked
    with pytest.raises(SuperuserImmutableException) as exc_down:
        service.assert_superuser_invariants(
            target_email=expected_email,
            action="UPDATE_ROLES",
            new_roles=[SystemRole.TENANT_USER],
        )
    assert "cannot be downgraded" in str(exc_down.value)

    # 3. MFA disablement blocked
    with pytest.raises(SuperuserImmutableException) as exc_mfa:
        service.assert_superuser_invariants(target_email=expected_email, action="DISABLE_MFA")
    assert "mandatory and non-disableable" in str(exc_mfa.value)

    # 4. Audit exclusion blocked
    with pytest.raises(SuperuserImmutableException) as exc_audit:
        service.assert_superuser_invariants(target_email=expected_email, action="EXCLUDE_AUDIT")
    assert "cannot be excluded from security audit" in str(exc_audit.value)


# ==============================================================================
# Item 18: Break-Glass Consolidation (AM-05)
# ==============================================================================


def test_break_glass_consolidation_onto_single_superuser():
    """Item 18: Exactly one break-glass identity exists; secondary break-glass path prohibited."""
    service = get_superuser_service()
    user, _ = service.provision_superuser()

    master_attrs = load_superuser_master_data()
    expected_email = master_attrs["email"]

    identity_svc = get_identity_service()
    break_glass_paths = identity_svc.enumerate_break_glass_paths()
    assert len(break_glass_paths) == 1
    assert break_glass_paths[0] == expected_email

    # Attempting to provision a secondary break-glass account is blocked per AM-05
    from domain.models.enums import StepUpAction

    step_up = identity_svc.initiate_step_up_challenge(
        tenant_id="tenant-corp",
        user_id="user-corp",
        action=StepUpAction.CREDENTIAL_CREATION,
    )
    token = identity_svc.verify_step_up_challenge(
        challenge_id=step_up.id,
        challenge_code=step_up.challenge_code,
    )

    with pytest.raises(BreakGlassLimitExceededException) as exc_info:
        identity_svc.provision_break_glass_account(
            tenant_id="tenant-corp",
            account_name="emergency-secondary",
            password="EmergencyPassword123!",
            step_up_token=token.step_up_token,
        )
    assert "consolidated to the single platform superuser identity per AM-05" in str(exc_info.value)


# ==============================================================================
# Item 19: The Delegation Rule & Routine-Use Alerting
# ==============================================================================


def test_delegation_rule_first_operational_task():
    """Item 19: Superuser first operational task: create working tenant & Platform Admin."""
    service = get_superuser_service()
    service.provision_superuser()

    admin_user = service.delegate_to_platform_admin(
        working_tenant_id="tenant-acme-prod",
        working_tenant_name="Acme Production Tenant",
        admin_email="platform.admin@acme.com",
        admin_name="Acme Platform Admin",
    )
    assert admin_user.tenant_id == "tenant-acme-prod"
    assert admin_user.roles == [SystemRole.TENANT_ADMIN]
    assert service._delegation_completed is True

    # Audit event logged
    audit = next(e for e in service._audit_records if e.action == "SUPERUSER_DELEGATION_HANDOVER")
    assert audit.payload_after["working_tenant_id"] == "tenant-acme-prod"


def test_routine_use_detection_and_alerting():
    """Item 19: Alert when superuser is used for routine operations exceeding consecutive days."""
    service = get_superuser_service()
    service.provision_superuser()

    # Day 1
    a1 = service.record_routine_operation("cost:read", activity_date="2026-10-01")
    assert a1 is None

    # Day 2
    a2 = service.record_routine_operation("inventory:read", activity_date="2026-10-02")
    assert a2 is None

    # Day 3 (threshold is 3)
    a3 = service.record_routine_operation("reports:read", activity_date="2026-10-03")
    assert a3 is None

    # Day 4 (exceeds threshold) -> Triggers WARNING severity alert
    a4 = service.record_routine_operation("billing:read", activity_date="2026-10-04")
    assert a4 is not None
    assert a4.severity == AlertSeverity.WARNING
    assert a4.alert_type == "SUPERUSER_ROUTINE_USE_ALERT"
    assert "exceeds threshold of 3 days" in a4.message


# ==============================================================================
# Item 20: Identity Verification Report
# ==============================================================================


def test_identity_verification_report_generation_and_publishing():
    """Item 20: Authoritative verification report confirms all superuser attributes and single break-glass."""
    service = get_superuser_service()
    service.provision_superuser()

    report = service.generate_verification_report()
    assert report.superuser_exists is True
    assert report.role == "GLOBAL_ADMIN"
    assert report.unrestricted_scope is True
    assert report.mfa_enforced is True
    assert report.mfa_disableable is False
    assert report.break_glass_count == 1
    assert len(report.break_glass_paths) == 1
    assert report.is_interactively_usable is True

    # Verify report files on disk
    json_path = service._report_output_dir / "identity_verification_report.json"
    md_path = service._report_output_dir / "identity_verification_report.md"
    assert json_path.exists()
    assert md_path.exists()

    with open(json_path, encoding="utf-8") as f:
        disk_report = json.load(f)
        assert disk_report["break_glass_count"] == 1
        assert disk_report["role"] == "GLOBAL_ADMIN"


# ==============================================================================
# REST API Endpoints Verification
# ==============================================================================


def test_api_superuser_lifecycle_endpoints():
    """Verify REST API endpoints for superuser provisioning, activation, login, and reporting."""
    # 1. Provision superuser
    res_prov = client.post("/api/v1/system/bootstrap/superuser/provision")
    assert res_prov.status_code == 201
    prov_data = res_prov.json()
    assert prov_data["role"] == "GLOBAL_ADMIN"
    token = prov_data["activation_token"]["token"]
    email = prov_data["superuser_email"]

    # 2. Activate superuser
    act_payload = {
        "activation_token": token,
        "password": "ProductionSuperuser123!",
    }
    res_act = client.post("/api/v1/system/bootstrap/superuser/activate", json=act_payload)
    assert res_act.status_code == 200
    act_data = res_act.json()
    totp_secret = act_data["totp_secret"]

    # 3. Login with mandatory MFA
    totp_code = generate_totp_code(totp_secret)
    login_payload = {
        "email": email,
        "password": "ProductionSuperuser123!",
        "mfa_code": totp_code,
    }
    res_login = client.post("/api/v1/system/bootstrap/superuser/login", json=login_payload)
    assert res_login.status_code == 200
    tokens = res_login.json()
    assert "access_token" in tokens

    # 4. Identity Report Endpoint
    res_rep = client.get("/api/v1/system/bootstrap/identity/report")
    assert res_rep.status_code == 200
    rep_data = res_rep.json()
    assert rep_data["break_glass_count"] == 1
    assert rep_data["mfa_enforced"] is True
    assert rep_data["has_password"] is True

    # 5. Delegation Endpoint
    del_payload = {
        "working_tenant_id": "tenant-api-working",
        "working_tenant_name": "API Working Tenant",
        "admin_email": "admin@apiworking.internal",
        "admin_name": "Working Admin",
    }
    res_del = client.post("/api/v1/system/bootstrap/superuser/delegate", json=del_payload)
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "HANDOVER_COMPLETED"
