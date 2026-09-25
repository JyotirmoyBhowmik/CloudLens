"""Unit / API tests for Configuration Inspector, Tenant Settings and Feature Flag Endpoints."""

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.config import feature_flag_service, tenant_settings_store


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_stores():
    tenant_settings_store.reset()
    feature_flag_service.reset()
    yield
    tenant_settings_store.reset()
    feature_flag_service.reset()


def test_api_config_inspector_all(client: TestClient):
    """GET /api/v1/config/inspector returns all settings with masked secrets."""
    response = client.get("/api/v1/config/inspector")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 20

    # Ensure passwords and secrets are masked
    passwords = [item for item in data if item["key"] == "database.password"]
    assert len(passwords) == 1
    assert passwords[0]["effective_value"] == "******"
    assert passwords[0]["is_secret"] is True


def test_api_config_inspector_single_key(client: TestClient):
    """GET /api/v1/config/inspector/{setting_key} returns specific setting provenance."""
    response = client.get("/api/v1/config/inspector/database.port")
    assert response.status_code == 200
    data = response.json()
    assert data["key"] == "database.port"
    assert data["effective_value"] == 5432
    assert data["layer"] == "builtin_default"


def test_api_tenant_settings_get_and_update(client: TestClient):
    """GET and PUT /api/v1/tenants/{tenant_id}/settings."""
    tenant_id = "tenant-finops-101"

    # Default settings
    get_res = client.get(f"/api/v1/tenants/{tenant_id}/settings")
    assert get_res.status_code == 200
    assert get_res.json()["reporting_currency"] == "USD"
    assert get_res.json()["threshold_defaults"]["budget_alert_threshold_percentage"] == 80.0

    # Dynamic update of threshold defaults
    put_res = client.put(
        f"/api/v1/tenants/{tenant_id}/settings",
        json={"threshold_defaults": {"budget_alert_threshold_percentage": 68.0}},
    )
    assert put_res.status_code == 200
    assert put_res.json()["threshold_defaults"]["budget_alert_threshold_percentage"] == 68.0

    # Inspector shows updated value with 'tenant' provenance
    inspect_res = client.get(
        f"/api/v1/config/inspector/threshold_defaults.budget_alert_threshold_percentage?tenant_id={tenant_id}"
    )
    assert inspect_res.status_code == 200
    assert inspect_res.json()["effective_value"] == 68.0
    assert inspect_res.json()["layer"] == "tenant"


def test_api_features_lifecycle(client: TestClient):
    """Test feature flag listing, evaluation, toggle and audit log endpoints."""
    flag_key = "enable_oci_connector"

    # 1. List flags
    list_res = client.get("/api/v1/features")
    assert list_res.status_code == 200
    flags = {f["key"]: f for f in list_res.json()}
    assert flag_key in flags
    assert flags[flag_key]["effective_enabled"] is False

    # 2. Evaluate
    eval_res = client.get(f"/api/v1/features/{flag_key}/evaluate")
    assert eval_res.status_code == 200
    assert eval_res.json()["enabled"] is False

    # 3. Toggle
    toggle_res = client.post(
        f"/api/v1/features/{flag_key}/toggle",
        json={
            "enabled": True,
            "changed_by": "qa-lead",
            "reason": "Test toggle via API",
        },
    )
    assert toggle_res.status_code == 200
    assert toggle_res.json()["audit_event"]["new_value"] is True

    # 4. Check audit log
    audit_res = client.get(f"/api/v1/features/audit-log?flag_key={flag_key}")
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    assert len(audit_data) == 1
    assert audit_data[0]["changed_by"] == "qa-lead"
    assert audit_data[0]["reason"] == "Test toggle via API"


def test_api_unregistered_feature_returns_400(client: TestClient):
    """Evaluating or toggling unregistered flag returns 400 Bad Request."""
    eval_res = client.get("/api/v1/features/unregistered_mystery_flag/evaluate")
    assert eval_res.status_code == 400
    assert "not registered in the canonical registry" in eval_res.json()["message"]
