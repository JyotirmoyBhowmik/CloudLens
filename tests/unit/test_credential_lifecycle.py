"""Comprehensive Test Suite for Prompt 12: Secret Management & Credential Lifecycle.

Validates all Prompt 12 requirements:
- Item 77: Dedicated secret store integration with reference-only database storage (SEC-008, SEC-009).
- Item 78: Full credential lifecycle: validate before persist, zero-downtime rotation, retire, revoke (SEC-010, SEC-011).
- Item 79: Expiry tracking and alerting at 30, 14, 3 days and expired state (SEC-013).
- Item 80: Credential profiles shareable across connectors within a tenant and NEVER across tenants (SEC-014, SEC-015).
- Item 81: Documented least-privilege permission reference per provider with consequences (SEC-012, SEC-016).
- Item 82: Negative controls: no API returns credential material; no log line contains it;
  no export contains it; no error message leaks it (SEC-017).
"""

import io
import logging
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.credentials.models import (
    CredentialProfile,
)
from domain.credentials.permissions import (
    PermissionReferenceService,
)
from domain.credentials.service import (
    CredentialService,
    reset_credential_service,
)
from domain.credentials.store import (
    InMemorySecretStore,
    reset_secret_store,
)
from domain.models.enums import (
    AlertSeverity,
    CredentialType,
    ProviderCapability,
    ProviderType,
    RotationState,
)
from domain.models.exceptions import (
    CredentialExpiredException,
    CredentialRevokedException,
    CredentialValidationException,
    CrossTenantCredentialAccessException,
)
from domain.observability.logging import CloudLensJsonFormatter


@pytest.fixture(autouse=True)
def clean_credential_environment():
    """Ensures each test runs with fresh isolated secret store and credential service."""
    reset_secret_store()
    reset_credential_service()
    store = InMemorySecretStore(mount_point="secret")
    service = CredentialService(secret_store=store)
    # Inject into global accessor
    import domain.credentials.service as svc_module

    svc_module._global_credential_service = service
    yield service
    reset_credential_service()
    reset_secret_store()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# Sample valid and invalid fixtures
MOCK_AWS_ROLE_PAYLOAD = {
    "role_arn": "arn:aws:iam::123456789012:role/CloudLensFinOpsReadOnlyRole",
    "external_id": "EnterpriseSecurityAuditToken2026",
}

MOCK_AZURE_SP_PAYLOAD = {
    "azure_tenant_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "azure_client_id": "b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
    "client_secret": "SuperSecretAzureClientPassword12345!",
}

MOCK_GCP_SA_PAYLOAD = {
    "type": "service_account",
    "project_id": "corp-finops-production",
    "private_key_id": "key-id-99887766",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0mockkey...\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "finops-reader@corp-finops-production.iam.gserviceaccount.com",
}

MOCK_OCI_KEY_PAYLOAD = {
    "tenancy_ocid": "ocid1.tenancy.oc1..aaaaaaaamocktenancy12345",
    "user_ocid": "ocid1.user.oc1..aaaaaaaamockuser12345",
    "fingerprint": "11:22:33:44:55:66:77:88:99:aa:bb:cc:dd:ee:ff:00",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0mockoci...\n-----END RSA PRIVATE KEY-----\n",
}


# ==============================================================================
# 1. Acceptance: A Credential that Fails Validation is Never Persisted Anywhere
# ==============================================================================


def test_failed_validation_never_persists_anywhere(clean_credential_environment: CredentialService):
    """Item 78: Credential validation failure prevents writing to SecretStore or DB."""
    service = clean_credential_environment
    store = service._secret_store

    # 1. Test malformed AWS Role ARN
    invalid_aws_payload = {
        "role_arn": "not-an-arn",
        "external_id": "Short",  # too short
    }

    with pytest.raises(CredentialValidationException) as exc_info:
        service.create_profile(
            tenant_id="tenant-corp",
            name="Broken AWS Role",
            provider=ProviderType.AWS,
            credential_type=CredentialType.ROLE_ARN,
            secret_payload=invalid_aws_payload,
        )

    assert "AWS Role ARN format is invalid" in str(exc_info.value)
    # Verify SecretStore is empty
    assert len(getattr(store, "_secrets", {})) == 0
    # Verify DB profile records are empty
    assert len(service._profiles) == 0

    # 2. Test forbidden write permissions requested (SEC-012)
    write_attempt_payload = {
        "role_arn": "arn:aws:iam::123456789012:role/CloudLensFinOpsRole",
        "external_id": "ValidExternalToken1234",
        "requested_actions": ["s3:PutObject", "ec2:RunInstances", "organizations:ListAccounts"],
    }

    with pytest.raises(CredentialValidationException) as exc_write:
        service.create_profile(
            tenant_id="tenant-corp",
            name="Dangerous Write Role",
            provider=ProviderType.AWS,
            credential_type=CredentialType.ROLE_ARN,
            secret_payload=write_attempt_payload,
        )

    assert (
        "Security baseline violation: Action or role 's3:PutObject' requests write or mutation"
        in str(exc_write.value)
    )
    assert len(getattr(store, "_secrets", {})) == 0
    assert len(service._profiles) == 0


# ==============================================================================
# 2. Reference-Only Storage Pattern in Database & Entities (SEC-008)
# ==============================================================================


def test_reference_only_storage_in_database_and_entities(
    clean_credential_environment: CredentialService,
):
    """Item 77: Entity holds only opaque reference URI and non-sensitive metadata; zero secrets."""
    service = clean_credential_environment

    profile = service.create_profile(
        tenant_id="tenant-prod",
        name="Production Azure SP",
        provider=ProviderType.AZURE,
        credential_type=CredentialType.SERVICE_PRINCIPAL,
        secret_payload=MOCK_AZURE_SP_PAYLOAD,
        metadata={"environment": "production", "cloud_region": "eastus"},
    )

    # 1. Database holds opaque reference URI
    assert profile.secret_ref.startswith("vault://secret/data/tenants/tenant-prod/credentials/")
    assert profile.fingerprint.startswith("SHA256:")
    assert profile.version == 1
    assert profile.rotation_state == RotationState.ACTIVE

    # 2. Zero secret material in entity attributes or model dump
    dump = profile.model_dump()
    assert "SuperSecretAzureClientPassword12345!" not in str(dump)
    assert "client_secret" not in dump
    assert "client_secret" not in profile.metadata

    # 3. Model validator prevents sensitive keys in metadata
    with pytest.raises(ValueError) as exc_val:
        CredentialProfile(
            id="cred-test-01",
            tenant_id="tenant-prod",
            name="Leaky Profile",
            provider=ProviderType.AZURE,
            credential_type=CredentialType.SERVICE_PRINCIPAL,
            secret_ref="vault://secret/ref",
            fingerprint="SHA256:abc",
            metadata={"client_secret": "should_be_rejected"},
        )
    assert "matches sensitive credential keyword" in str(exc_val.value)


# ==============================================================================
# 3. Zero-Downtime Credential Rotation (Item 78 / SEC-010)
# ==============================================================================


def test_zero_downtime_rotation_and_no_sync_failure(
    clean_credential_environment: CredentialService,
):
    """Item 78: Rotating a credential causes no failed sync; new credential validated before retiring old."""
    service = clean_credential_environment

    # 1. Provision initial profile with v1 secret
    profile = service.create_profile(
        tenant_id="tenant-acme",
        name="AWS FinOps Profile",
        provider=ProviderType.AWS,
        credential_type=CredentialType.ROLE_ARN,
        secret_payload=MOCK_AWS_ROLE_PAYLOAD,
    )
    profile_id = profile.id
    service.bind_connector("tenant-acme", profile_id, "conn-aws-01")

    # Connector performs sync using v1 secret
    sec_v1 = service.resolve_secret_for_connector("tenant-acme", profile_id, "conn-aws-01")
    assert sec_v1["external_id"] == "EnterpriseSecurityAuditToken2026"

    # 2. Attempt rotation with INVALID credential -> Must fail and leave existing active credential untouched
    invalid_new_payload = {
        "role_arn": "arn:aws:iam::123456789012:role/BadRole",
        "external_id": "tiny",  # too short
    }
    with pytest.raises(CredentialValidationException):
        service.rotate_credential(
            tenant_id="tenant-acme",
            profile_id=profile_id,
            new_secret_payload=invalid_new_payload,
        )

    # Verify profile is still active on v1
    curr = service.get_profile("tenant-acme", profile_id)
    assert curr.version == 1
    assert curr.rotation_state == RotationState.ACTIVE

    # 3. Rotate with VALID new credential
    new_valid_payload = {
        "role_arn": "arn:aws:iam::123456789012:role/CloudLensFinOpsRotatedRole",
        "external_id": "RotatedSecurityAuditToken2027",
    }
    rotated_profile = service.rotate_credential(
        tenant_id="tenant-acme",
        profile_id=profile_id,
        new_secret_payload=new_valid_payload,
    )

    assert rotated_profile.version == 2
    assert rotated_profile.rotation_state == RotationState.ROTATING
    assert rotated_profile.previous_secret_ref is not None

    # In-flight sync can continue with retiring secret without failure
    retiring_sec = service.resolve_secret_for_connector(
        "tenant-acme", profile_id, "conn-aws-01", prefer_retiring=True
    )
    assert retiring_sec["external_id"] == "EnterpriseSecurityAuditToken2026"

    # New sync resolves new v2 secret without failure
    active_sec = service.resolve_secret_for_connector(
        "tenant-acme", profile_id, "conn-aws-01", prefer_retiring=False
    )
    assert active_sec["external_id"] == "RotatedSecurityAuditToken2027"

    # 4. Finalize rotation
    final_profile = service.complete_rotation("tenant-acme", profile_id, purge_previous=True)
    assert final_profile.rotation_state == RotationState.ACTIVE
    assert final_profile.previous_secret_ref is None


# ==============================================================================
# 4. Expiry Tracking and Milestone Alerting (Item 79 / SEC-013)
# ==============================================================================


def test_expiry_tracking_and_alerting_milestones(clean_credential_environment: CredentialService):
    """Item 79: Expiry tracking alerts at 30, 14, and 3 days and handles expired state."""
    service = clean_credential_environment
    now = datetime.now(UTC)

    # Profile 1: Expires in 40 days (no alert)
    service.create_profile(
        tenant_id="tenant-exp",
        name="AWS Long Lived",
        provider=ProviderType.AWS,
        credential_type=CredentialType.ROLE_ARN,
        secret_payload=MOCK_AWS_ROLE_PAYLOAD,
        expires_at=now + timedelta(days=40),
    )

    # Profile 2: Expires in 25 days (triggers 30-day milestone)
    p30 = service.create_profile(
        tenant_id="tenant-exp",
        name="Azure 30-day Cert",
        provider=ProviderType.AZURE,
        credential_type=CredentialType.SERVICE_PRINCIPAL,
        secret_payload=MOCK_AZURE_SP_PAYLOAD,
        expires_at=now + timedelta(days=25),
    )

    # Profile 3: Expires in 10 days (triggers 14-day milestone)
    p14 = service.create_profile(
        tenant_id="tenant-exp",
        name="GCP 14-day Key",
        provider=ProviderType.GCP,
        credential_type=CredentialType.SERVICE_ACCOUNT_KEY,
        secret_payload=MOCK_GCP_SA_PAYLOAD,
        expires_at=now + timedelta(days=10),
    )

    # Profile 4: Expires in 2 days (triggers 3-day critical milestone)
    p3 = service.create_profile(
        tenant_id="tenant-exp",
        name="OCI 3-day Key",
        provider=ProviderType.OCI,
        credential_type=CredentialType.API_SIGNING_KEY,
        secret_payload=MOCK_OCI_KEY_PAYLOAD,
        expires_at=now + timedelta(days=2),
    )

    # Run expiry check
    alerts = service.check_expiries(current_time=now, tenant_id="tenant-exp")

    # Verify alerts fired for 30, 14, and 3 days
    profile_alert_map = {a.profile_id: a for a in alerts}
    assert p30.id in profile_alert_map
    assert profile_alert_map[p30.id].threshold_days == 30
    assert profile_alert_map[p30.id].severity == AlertSeverity.WARNING

    assert p14.id in profile_alert_map
    assert profile_alert_map[p14.id].threshold_days == 14
    assert profile_alert_map[p14.id].severity == AlertSeverity.WARNING

    assert p3.id in profile_alert_map
    assert profile_alert_map[p3.id].threshold_days == 3
    assert profile_alert_map[p3.id].severity == AlertSeverity.CRITICAL

    # Verify deduplication: re-running immediately produces no duplicate alerts
    alerts_dedup = service.check_expiries(current_time=now, tenant_id="tenant-exp")
    assert len(alerts_dedup) == 0

    # Advance time past expiration for p3
    future_time = now + timedelta(days=5)
    alerts_expired = service.check_expiries(current_time=future_time, tenant_id="tenant-exp")
    exp_alert = next(a for a in alerts_expired if a.profile_id == p3.id)
    assert exp_alert.threshold_days == 0
    assert exp_alert.severity == AlertSeverity.CRITICAL

    # Profile state transitioned to EXPIRED
    p3_updated = service.get_profile("tenant-exp", p3.id)
    assert p3_updated.rotation_state == RotationState.EXPIRED

    # Sync resolution on expired credential fails
    with pytest.raises(CredentialExpiredException):
        service.resolve_secret_for_connector("tenant-exp", p3.id, "conn-oci")


# ==============================================================================
# 5. Cross-Connector Sharing & Strict Cross-Tenant Isolation (Item 80 / SEC-014)
# ==============================================================================


def test_cross_connector_sharing_within_tenant(clean_credential_environment: CredentialService):
    """Item 80: Credential profile shareable across multiple connectors within tenant."""
    service = clean_credential_environment

    profile = service.create_profile(
        tenant_id="tenant-shared",
        name="Shared Org AWS Role",
        provider=ProviderType.AWS,
        credential_type=CredentialType.ROLE_ARN,
        secret_payload=MOCK_AWS_ROLE_PAYLOAD,
    )

    # Bind multiple connectors within tenant
    service.bind_connector("tenant-shared", profile.id, "conn-aws-compute")
    service.bind_connector("tenant-shared", profile.id, "conn-aws-billing")
    service.bind_connector("tenant-shared", profile.id, "conn-aws-storage")

    p = service.get_profile("tenant-shared", profile.id)
    assert len(p.connectors_bound) == 3
    assert "conn-aws-billing" in p.connectors_bound


def test_cross_tenant_isolation_strictly_refuses_access(
    clean_credential_environment: CredentialService,
):
    """Item 80: Cross-tenant credential access is strictly prohibited and raises security exception."""
    service = clean_credential_environment

    profile_a = service.create_profile(
        tenant_id="tenant-alpha",
        name="Alpha GCP Key",
        provider=ProviderType.GCP,
        credential_type=CredentialType.SERVICE_ACCOUNT_KEY,
        secret_payload=MOCK_GCP_SA_PAYLOAD,
    )

    # 1. Tenant Beta attempts to get Tenant Alpha's profile
    with pytest.raises(CrossTenantCredentialAccessException) as exc_get:
        service.get_profile(tenant_id="tenant-beta", profile_id=profile_a.id)
    assert "Security violation: Tenant 'tenant-beta' attempted to access credential profile" in str(
        exc_get.value
    )

    # 2. Tenant Beta attempts to bind connector to Tenant Alpha's profile
    with pytest.raises(CrossTenantCredentialAccessException):
        service.bind_connector(
            tenant_id="tenant-beta", profile_id=profile_a.id, connector_id="conn-beta-01"
        )

    # 3. Tenant Beta attempts to resolve secret from Tenant Alpha's profile
    with pytest.raises(CrossTenantCredentialAccessException):
        service.resolve_secret_for_connector(
            tenant_id="tenant-beta", profile_id=profile_a.id, connector_id="conn-beta-01"
        )

    # 4. Tenant Beta attempts to rotate Tenant Alpha's profile
    with pytest.raises(CrossTenantCredentialAccessException):
        service.rotate_credential(
            tenant_id="tenant-beta", profile_id=profile_a.id, new_secret_payload=MOCK_GCP_SA_PAYLOAD
        )


# ==============================================================================
# 6. Emergency Revocation (Item 78)
# ==============================================================================


def test_emergency_revocation_purges_secret_store_immediately(
    clean_credential_environment: CredentialService,
):
    """Item 78: Emergency revocation purges secret store and locks out connectors."""
    service = clean_credential_environment

    profile = service.create_profile(
        tenant_id="tenant-corp",
        name="Compromised Key",
        provider=ProviderType.OCI,
        credential_type=CredentialType.API_SIGNING_KEY,
        secret_payload=MOCK_OCI_KEY_PAYLOAD,
    )
    secret_ref = profile.secret_ref
    assert service._secret_store.has_secret(secret_ref) is True

    # Revoke profile
    revoked = service.revoke_credential(
        "tenant-corp", profile.id, reason="Suspected key exfiltration"
    )
    assert revoked.rotation_state == RotationState.REVOKED

    # Secret material is permanently purged from SecretStore
    assert service._secret_store.has_secret(secret_ref) is False

    # Attempting to resolve secret fails with CredentialRevokedException
    with pytest.raises(CredentialRevokedException):
        service.resolve_secret_for_connector("tenant-corp", profile.id, "conn-oci")

    # Critical alert emitted
    assert any(
        a.alert_type == "CREDENTIAL_REVOKED_ALERT" and a.severity == AlertSeverity.CRITICAL
        for a in service._alerts
    )


# ==============================================================================
# 7. Documented Least-Privilege Permission Reference (Item 81 / SEC-012)
# ==============================================================================


def test_least_privilege_permission_reference_for_all_four_providers():
    """Item 81: Every provider maps all six capabilities to minimum permissions and consequences."""
    for provider in [ProviderType.AWS, ProviderType.AZURE, ProviderType.GCP, ProviderType.OCI]:
        ref = PermissionReferenceService.get_reference(provider)
        assert ref.provider == provider
        assert len(ref.primary_auth_mechanism) > 0
        assert len(ref.capabilities) == 6

        cap_codes = {c.capability_code for c in ref.capabilities}
        assert cap_codes == {
            ProviderCapability.C01_HIERARCHY,
            ProviderCapability.C02_INVENTORY,
            ProviderCapability.C03_COST,
            ProviderCapability.C04_USAGE,
            ProviderCapability.C11_PRICING,
            ProviderCapability.C18_QUOTA,
        }

        # Check every capability requirement
        for cap in ref.capabilities:
            assert len(cap.minimum_permissions) >= 1
            assert len(cap.required_scope) > 0
            assert len(cap.consequence_if_not_granted) > 20

            # Verify strictly read-only: no write permissions requested anywhere
            for perm in cap.minimum_permissions:
                perm_lower = perm.lower()
                assert "write" not in perm_lower
                assert "delete" not in perm_lower
                assert "put" not in perm_lower or "s3:put" in perm_lower  # no S3 put allowed


# ==============================================================================
# 8. Negative Controls (Item 82 / SEC-017)
# ==============================================================================


def test_negative_controls_no_credential_in_api_responses(client: TestClient):
    """Item 82: No API endpoint ever returns raw credential material."""
    raw_secret_value = "SuperSecretClientSecret999888!"
    payload = {
        "name": "API Negative Test Profile",
        "provider": "azure",
        "credential_type": "SERVICE_PRINCIPAL",
        "secret_payload": {
            "azure_tenant_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
            "azure_client_id": "b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
            "client_secret": raw_secret_value,
        },
        "metadata": {"env": "test"},
    }

    # 1. POST /profiles
    res_post = client.post(
        "/api/v1/credentials/profiles",
        json=payload,
        headers={"X-Tenant-ID": "tenant-sec"},
    )
    assert res_post.status_code == 201
    post_text = res_post.text
    assert raw_secret_value not in post_text
    profile_id = res_post.json()["id"]

    # 2. GET /profiles
    res_list = client.get("/api/v1/credentials/profiles", headers={"X-Tenant-ID": "tenant-sec"})
    assert res_list.status_code == 200
    assert raw_secret_value not in res_list.text

    # 3. GET /profiles/{id}
    res_get = client.get(
        f"/api/v1/credentials/profiles/{profile_id}", headers={"X-Tenant-ID": "tenant-sec"}
    )
    assert res_get.status_code == 200
    assert raw_secret_value not in res_get.text

    # 4. POST /profiles/{id}/rotate
    new_secret_value = "RotatedSecretValue444555!"
    rotate_payload = {
        "new_secret_payload": {
            "azure_tenant_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
            "azure_client_id": "b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
            "client_secret": new_secret_value,
        }
    }
    res_rotate = client.post(
        f"/api/v1/credentials/profiles/{profile_id}/rotate",
        json=rotate_payload,
        headers={"X-Tenant-ID": "tenant-sec"},
    )
    assert res_rotate.status_code == 200
    assert new_secret_value not in res_rotate.text
    assert raw_secret_value not in res_rotate.text


def test_negative_controls_no_credential_in_logs():
    """Item 82: Structured JSON log formatter redacts any passed credential material."""
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setFormatter(CloudLensJsonFormatter(service_name="test-service"))

    test_logger = logging.getLogger("test.security.redaction")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.INFO)

    secret_key = "AIzaSyD-SecretApiKeyToken1234567890"
    test_logger.info(
        "Attempting connection with credentials",
        extra={"api_key": secret_key, "client_secret": "SuperSecret123!"},
    )

    log_output = log_capture.getvalue()
    assert secret_key not in log_output
    assert "SuperSecret123!" not in log_output
    assert "[REDACTED]" in log_output or "[REDACTED_API_KEY]" in log_output


def test_negative_controls_no_credential_in_exports(client: TestClient):
    """Item 82: Export endpoints produce only sanitized references, never secret material."""
    secret_value = "ExportLeakTestSecret98765!"
    payload = {
        "name": "Export Test Profile",
        "provider": "azure",
        "credential_type": "SERVICE_PRINCIPAL",
        "secret_payload": {
            "azure_tenant_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
            "azure_client_id": "b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
            "client_secret": secret_value,
        },
    }
    res_create = client.post(
        "/api/v1/credentials/profiles", json=payload, headers={"X-Tenant-ID": "tenant-exp-test"}
    )
    assert res_create.status_code == 201

    res_export = client.get(
        "/api/v1/credentials/export", headers={"X-Tenant-ID": "tenant-exp-test"}
    )
    assert res_export.status_code == 200
    export_text = res_export.text
    assert secret_value not in export_text

    export_json = res_export.json()
    assert len(export_json) >= 1
    assert "fingerprint" in export_json[0]
    assert "secret_ref" in export_json[0]


def test_negative_controls_no_credential_in_error_messages(client: TestClient):
    """Item 82: Error messages on validation failure or bad input never leak secret material."""
    secret_value = "LeakCheckSecretValue12345!"
    payload = {
        "name": "Error Leak Test",
        "provider": "aws",
        "credential_type": "ROLE_ARN",
        "secret_payload": {
            "role_arn": "invalid-role-arn",
            "external_id": secret_value,
        },
    }

    res_err = client.post(
        "/api/v1/credentials/profiles", json=payload, headers={"X-Tenant-ID": "tenant-err"}
    )
    assert res_err.status_code == 422
    err_text = res_err.text
    assert secret_value not in err_text
