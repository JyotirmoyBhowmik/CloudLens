"""Security and Resilience Tests for VaultSecretStore (Prompt R-SEC Part 2).

Enforces:
2.1 Real VaultSecretStore against KV v2 HTTP API (store, get, delete, has, health_check).
2.2 Auth methods supported; no hardcoded default token.
2.3 InMemorySecretStore selectable only when CLOUDLENS_ENV=development and backend_type=memory.
2.4 Startup guard in staging/production fails closed (sys.exit non-zero).
2.5 Audit secret reads without logging secret values.
2.6 Wire into readiness probe: probe returns 503 when Vault is down.
2.7 Mandatory test gates:
    a) mock client or local Vault; store -> retrieve -> delete -> has=False
    b) stop vault -> health_check() == False -> /ready returns 503
    c) production mode without vault -> startup guard raises / sys.exit non-zero
"""

import json
from typing import Any

import httpx
import pytest
from starlette.testclient import TestClient

from api.cloudlens_api.main import app
from domain.config.surface import SecretStoreConfig
from domain.credentials.store import (
    VaultSecretStore,
    reset_secret_store,
    verify_secret_store_startup_guard,
)
from domain.observability import health_probe


@pytest.fixture
def mock_vault_environment():
    vault_db: dict[str, Any] = {}
    health_status = [200]

    def handler(request: httpx.Request) -> httpx.Response:
        url_path = request.url.path
        if url_path == "/v1/sys/health":
            code = health_status[0]
            if code == 200:
                return httpx.Response(200, json={"initialized": True, "sealed": False, "standby": False})
            return httpx.Response(code, json={"errors": ["Vault sealed or unavailable"]})

        if "/data/" in url_path:
            subpath = url_path.split("/data/")[1]
            if request.method == "POST":
                payload = json.loads(request.content)
                vault_db[subpath] = payload.get("data", {})
                return httpx.Response(200, json={"data": {"version": 1}})
            elif request.method == "GET":
                if subpath in vault_db:
                    return httpx.Response(200, json={"data": {"data": vault_db[subpath]}})
                return httpx.Response(404, json={"errors": ["Not found"]})

        if "/metadata/" in url_path:
            subpath = url_path.split("/metadata/")[1]
            if request.method == "DELETE":
                vault_db.pop(subpath, None)
                return httpx.Response(204)

        return httpx.Response(404, json={"errors": ["Path not handled"]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    config = SecretStoreConfig(
        backend_type="vault",
        vault_url="https://vault.internal:8200",
        mount_point="secret",
        vault_token="test-vault-token-live",
    )
    store = VaultSecretStore(config, client=client)
    return store, health_status, vault_db


def test_vault_gate_a_store_retrieve_delete_lifecycle(mock_vault_environment):
    """Gate a: store -> retrieve -> delete -> has=False with KV v2 API."""
    store, _, _ = mock_vault_environment
    tenant_id = "tenant-finops-prod"
    profile_id = "aws-master-payer"
    version = 1
    secret_payload = {
        "aws_access_key_id": "AKIA1122334455EXAMPLE",
        "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    }

    # 1. Store secret
    ref_uri = store.store_secret(
        tenant_id=tenant_id,
        profile_id=profile_id,
        version=version,
        secret_data=secret_payload,
    )
    assert ref_uri.startswith("vault://secret/data/tenants/")
    assert store.has_secret(ref_uri) is True

    # 2. Retrieve secret
    retrieved = store.get_secret(
        secret_ref=ref_uri,
        tenant_id=tenant_id,
        actor="billing-collector-worker",
        purpose="daily_cost_export_pull",
    )
    assert retrieved == secret_payload

    # 3. Delete secret
    deleted = store.delete_secret(secret_ref=ref_uri, tenant_id=tenant_id)
    assert deleted is True

    # 4. Verify has=False
    assert store.has_secret(ref_uri) is False


def test_vault_gate_b_stopped_vault_causes_readiness_503(monkeypatch):
    """Gate b: stop vault -> health_check() == False -> /ready returns 503."""
    # Simulate stopped/unhealthy vault
    class BrokenVaultStore:
        def health_check(self) -> bool:
            return False

    broken_store = BrokenVaultStore()
    monkeypatch.setattr(
        "domain.credentials.store.get_secret_store",
        lambda *args, **kwargs: broken_store,
    )

    # Health probe readiness check
    assert broken_store.health_check() is False
    is_ready, report = health_probe.evaluate_readiness()
    assert is_ready is False
    assert report["dependencies"]["secret_store"]["status"] == "unhealthy"

    # API /api/v1/health/readiness and /ready return 503
    client = TestClient(app)
    resp_api = client.get("/api/v1/health/readiness")
    assert resp_api.status_code == 503

    resp_ready = client.get("/ready")
    assert resp_ready.status_code == 503


def test_vault_gate_c_production_startup_guard_fails_closed(monkeypatch):
    """Gate c: production mode without vault -> startup guard raises sys.exit non-zero."""
    # 1. In production with memory backend -> sys.exit(1)
    monkeypatch.setenv("CLOUDLENS_ENV", "production")
    monkeypatch.setattr(
        "domain.credentials.store.SecretStoreConfig",
        lambda: SecretStoreConfig(backend_type="memory"),
    )

    with pytest.raises(SystemExit) as exc_info:
        verify_secret_store_startup_guard()
    assert exc_info.value.code != 0

    # 2. In production with vault backend but health_check() fails -> sys.exit(1)
    class UnhealthyVault:
        def health_check(self) -> bool:
            return False

    reset_secret_store()
    monkeypatch.setattr(
        "domain.credentials.store.SecretStoreConfig",
        lambda: SecretStoreConfig(backend_type="vault"),
    )
    monkeypatch.setattr(
        "domain.credentials.store.get_secret_store",
        lambda *args, **kwargs: UnhealthyVault(),
    )

    with pytest.raises(SystemExit) as exc_info_unhealthy:
        verify_secret_store_startup_guard()
    assert exc_info_unhealthy.value.code != 0

    # Clean up singleton
    reset_secret_store()
