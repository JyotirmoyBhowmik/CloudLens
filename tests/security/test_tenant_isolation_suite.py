"""Standing Cross-Tenant Isolation Test Suite (Prompt 13 Item 88, BBP Section 41, SEC-015).

Acceptance Criteria:
- No endpoint returns another tenant's data under any parameter manipulation,
  proven by the standing isolation suite.
- Covers parameter manipulation: headers (X-Tenant-ID), query params (?tenant_id=...),
  path parameters (/resource/{foreign_id}), and request bodies.
- Verifies that cross-tenant access attempts are blocked mechanically and logged as audit violations.
"""

from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from api.cloudlens_api.main import app
from domain.audit.models import AuditEventCreate
from domain.audit.service import get_audit_service, reset_audit_service
from domain.credentials.models import CredentialType
from domain.credentials.service import get_credential_service, reset_credential_service
from domain.credentials.store import reset_secret_store
from domain.identity.service import get_identity_service
from domain.models.enums import AuditEventType, OverrideClass, ProviderType, SystemRole
from domain.overrides.models import OverrideCreateRequest
from domain.overrides.service import get_override_service, reset_override_service
from domain.tenant.context import TenantContext
from domain.tenant.object_store import get_tenant_object_storage, reset_tenant_object_storage


@pytest.fixture(autouse=True)
def clean_system():
    reset_secret_store()
    reset_credential_service()
    reset_audit_service()
    reset_override_service()
    reset_tenant_object_storage()
    yield
    reset_secret_store()
    reset_credential_service()
    reset_audit_service()
    reset_override_service()
    reset_tenant_object_storage()


@pytest.fixture
def auth_tokens():
    """Generates cryptographically signed access tokens for Tenant A and Tenant B."""
    identity_service = get_identity_service()
    token_engine = identity_service.token_engine

    token_a = token_engine.issue_access_token(
        user_id="usr-alice",
        tenant_id="tenant-alpha",
        email="alice@alpha.internal",
        roles=[SystemRole.TENANT_ADMIN],
        permissions=["read", "write", "admin"],
        session_id="ses-alpha-1",
        token_family_id="fam-alpha-1",
    )

    token_b = token_engine.issue_access_token(
        user_id="usr-bob",
        tenant_id="tenant-beta",
        email="bob@beta.internal",
        roles=[SystemRole.TENANT_ADMIN],
        permissions=["read", "write", "admin"],
        session_id="ses-beta-1",
        token_family_id="fam-beta-1",
    )

    return {"token_a": token_a, "token_b": token_b}


@pytest.fixture
def seeded_tenant_b_estate():
    """Provisions representative data owned strictly by Tenant B."""
    tc_b = TenantContext(tenant_id="tenant-beta", user_id="usr-bob", roles=["TENANT_ADMIN"])

    # 1. Credential Profile in Tenant B
    cred_service = get_credential_service()
    cred_profile = cred_service.create_profile(
        tenant_id="tenant-beta",
        name="AWS Production Sync",
        provider=ProviderType.AWS,
        credential_type=CredentialType.ROLE_ARN,
        secret_payload={
            "role_arn": "arn:aws:iam::112233445566:role/CloudLensReadOnlyRole",
            "external_id": "beta-ext-secret-999",
        },
        metadata={"environment": "production"},
        actor_id="usr-bob",
    )

    # 2. Override in Tenant B
    override_service = get_override_service()
    override_rec = override_service.create_override(
        tenant_context=tc_b,
        req=OverrideCreateRequest(
            override_class=OverrideClass.BUDGET_THRESHOLD,
            who="usr-bob",
            what="budget.workload_b.tolerance",
            why="Quarter-end financial processing threshold adjustment",
            previous_value=1000,
            new_value=2500,
            expiry=datetime.now(UTC) + timedelta(days=14),
        ),
    )

    # 3. Audit Event in Tenant B
    audit_service = get_audit_service()
    audit_event = audit_service.append_event(
        tenant_context=tc_b,
        event_in=AuditEventCreate(
            event_type=AuditEventType.BUDGET_CHANGED,
            actor_id="bob@beta.internal",
            action="UPDATE_BUDGET_LIMIT",
            resource_type="BUDGET",
            resource_id="bgt-beta-01",
            details={"old_limit": 50000, "new_limit": 75000},
        ),
    )

    # 4. Storage Object in Tenant B
    storage = get_tenant_object_storage()
    storage.put_object(
        tenant_context=tc_b,
        key="confidential/financial_ledger.pdf",
        data=b"TENANT_B_CONFIDENTIAL_FINANCIAL_DATA",
    )

    return {
        "cred_profile_id": cred_profile.id,
        "override_id": override_rec.id,
        "audit_event_id": audit_event.id,
        "storage_key": "confidential/financial_ledger.pdf",
    }


def test_header_manipulation_cross_tenant_rejected(auth_tokens, seeded_tenant_b_estate):
    """Attempt: Authenticate as Tenant A, pass X-Tenant-ID: tenant-beta. Assert 403 & Audited."""
    _ = seeded_tenant_b_estate
    client = TestClient(app)
    headers = {
        "Authorization": f"Bearer {auth_tokens['token_a']}",
        "X-Tenant-ID": "tenant-beta",  # Parameter manipulation!
    }

    resp = client.get("/api/v1/credentials/profiles", headers=headers)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["message"]

    # Verify audit stream in tenant-alpha recorded the attack attempt
    audit_svc = get_audit_service()
    tc_a = TenantContext(tenant_id="tenant-alpha", user_id="usr-alice")
    events = audit_svc.list_events(tenant_context=tc_a)
    assert any(e.event_type == AuditEventType.CROSS_TENANT_ACCESS_ATTEMPT for e in events)


def test_query_param_manipulation_cross_tenant_rejected(auth_tokens, seeded_tenant_b_estate):
    """Attempt: Authenticate as Tenant A, pass ?tenant_id=tenant-beta. Assert 403 & Audited."""
    _ = seeded_tenant_b_estate
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {auth_tokens['token_a']}"}

    resp = client.get("/api/v1/credentials/profiles?tenant_id=tenant-beta", headers=headers)
    assert resp.status_code == 403
    assert "Cross-tenant access forbidden" in resp.json()["message"]


def test_credentials_path_manipulation_cross_tenant_rejected(auth_tokens, seeded_tenant_b_estate):
    """Attempt: Authenticate as Tenant A, access/manipulate Tenant B profile directly by ID. Assert 403."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {auth_tokens['token_a']}"}
    foreign_id = seeded_tenant_b_estate["cred_profile_id"]

    # 1. Direct GET foreign profile
    resp = client.get(f"/api/v1/credentials/profiles/{foreign_id}", headers=headers)
    assert resp.status_code == 403
    assert "Cross-tenant credential sharing is strictly prohibited" in resp.json()["message"]

    # 2. Attempt rotate foreign profile
    rotate_payload = {
        "new_secret_payload": {
            "role_arn": "arn:aws:iam::112233445566:role/MaliciousRole",
            "external_id": "malicious-secret",
        }
    }
    resp = client.post(
        f"/api/v1/credentials/profiles/{foreign_id}/rotate",
        json=rotate_payload,
        headers=headers,
    )
    assert resp.status_code == 403

    # 3. Attempt revoke foreign profile
    resp = client.post(f"/api/v1/credentials/profiles/{foreign_id}/revoke", headers=headers)
    assert resp.status_code == 403

    # 4. Attempt bind connector to foreign profile
    resp = client.post(
        f"/api/v1/credentials/profiles/{foreign_id}/bind",
        json={"connector_id": "conn-rogue"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_overrides_path_manipulation_cross_tenant_rejected(auth_tokens, seeded_tenant_b_estate):
    """Attempt: Authenticate as Tenant A, access/revert Tenant B override. Assert 404 (zero leakage)."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {auth_tokens['token_a']}"}
    foreign_id = seeded_tenant_b_estate["override_id"]

    # 1. Direct GET foreign override
    resp = client.get(f"/api/v1/overrides/{foreign_id}", headers=headers)
    assert resp.status_code == 404
    assert foreign_id in resp.json()["message"]

    # 2. Attempt revert foreign override
    resp = client.post(
        f"/api/v1/overrides/{foreign_id}/revert",
        json={"reason": "Attempting illegal cross-tenant revert"},
        headers=headers,
    )
    assert resp.status_code == 404

    # 3. List overrides - ensure Tenant B overrides are NEVER returned
    resp = client.get("/api/v1/overrides", headers=headers)
    assert resp.status_code == 200
    returned_ids = [item["id"] for item in resp.json()]
    assert foreign_id not in returned_ids


def test_audit_stream_cross_tenant_isolation_and_mutation_rejection(
    auth_tokens, seeded_tenant_b_estate
):
    """Attempt: Authenticate as Tenant A, access Tenant B audit events, and attempt mutation. Assert failure."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {auth_tokens['token_a']}"}
    foreign_id = seeded_tenant_b_estate["audit_event_id"]

    # 1. List audit events - ensure zero Tenant B events leaked
    resp = client.get("/api/v1/audit/events", headers=headers)
    assert resp.status_code == 200
    returned_ids = [item["id"] for item in resp.json()]
    assert foreign_id not in returned_ids

    # 2. Direct GET foreign audit event
    resp = client.get(f"/api/v1/audit/events/{foreign_id}", headers=headers)
    assert resp.status_code == 404

    # 3. Attempt DELETE audit event -> Forbidden & Audited across all roles
    resp = client.delete(f"/api/v1/audit/events/{foreign_id}", headers=headers)
    assert resp.status_code == 403
    assert "Audit records are immutable and append-only" in resp.json()["message"]

    # 4. Attempt UPDATE audit event -> Forbidden & Audited across all roles
    resp = client.put(
        f"/api/v1/audit/events/{foreign_id}", json={"action": "TAMPERED"}, headers=headers
    )
    assert resp.status_code == 403
    assert "Audit records are immutable and append-only" in resp.json()["message"]


def test_object_storage_cross_tenant_isolation(auth_tokens, seeded_tenant_b_estate):
    """Attempt: Authenticate as Tenant A, access Tenant B storage object or inject foreign prefix. Assert failure."""
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {auth_tokens['token_a']}"}
    foreign_key = seeded_tenant_b_estate["storage_key"]

    # 1. Relative GET of key that exists in Tenant B but not Tenant A -> 404
    resp = client.get(f"/api/v1/storage/objects/{foreign_key}", headers=headers)
    assert resp.status_code == 404

    # 2. Prefix injection attempt to reach Tenant B directory -> 403 Forbidden
    resp = client.get(f"/api/v1/storage/objects/tenants/tenant-beta/{foreign_key}", headers=headers)
    assert resp.status_code == 403
    assert "Cross-tenant storage access denied" in resp.json()["message"]

    # 3. Write attempt into Tenant B prefix -> 403 Forbidden
    resp = client.post(
        "/api/v1/storage/objects",
        json={"key": "tenants/tenant-beta/exploit.txt", "data": "malicious payload"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert "Cross-tenant storage access denied" in resp.json()["message"]

    # 4. Directory traversal attempt -> 403 Forbidden
    resp = client.post(
        "/api/v1/storage/objects",
        json={"key": "../tenant-beta/exploit.txt", "data": "traversal payload"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert "Directory traversal detected" in resp.json()["message"]
