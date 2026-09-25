"""API Contract Tests verifying OpenAPI Schema Conformity & Headers."""

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_openapi_schema_contract(client: TestClient):
    """Verify OpenAPI 3.1 schema is valid and contains required route definitions."""
    res = client.get("/openapi.json")
    assert res.status_code == 200
    data = res.json()
    assert data["openapi"].startswith("3.")
    assert data["info"]["title"] == "CloudLens API"

    paths = data["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/health/liveness" in paths
    assert "/api/v1/health/readiness" in paths
    assert "/api/v1/config/inspector" in paths
    assert "/api/v1/features" in paths
    assert "/metrics" in paths


def test_correlation_id_header_contract(client: TestClient):
    """Verify all HTTP endpoints echo back X-Correlation-ID and X-Response-Time-MS."""
    client_corr_id = "test-contract-correlation-header-999"
    res = client.get("/api/v1/health", headers={"X-Correlation-ID": client_corr_id})
    assert res.status_code == 200
    assert res.headers["X-Correlation-ID"] == client_corr_id
    assert "X-Response-Time-MS" in res.headers
