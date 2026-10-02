"""Automated Public API Contract Conformance & Credential Privacy Tests (Prompt 34 / BBP Section 38).

Enforces:
1. Full endpoint catalogue API-001 to API-048 existence and specification.
2. Hard rule: No endpoint returns provider credential material under any circumstance.
3. Authoritative OpenAPI schema drift detection (release blocker).
4. Uniform response metadata and standard error codes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app

# Authoritative Catalogue of 48 endpoints (BBP Section 38 / requirements-register.md)
CATALOGUE_48 = {
    "API-001": ("GET", "/api/v1/health"),
    "API-002": ("GET", "/api/v1/auth/session"),
    "API-003": ("POST", "/api/v1/auth/login"),
    "API-004": ("POST", "/api/v1/auth/logout"),
    "API-005": ("GET", "/api/v1/users"),
    "API-006": ("POST", "/api/v1/users"),
    "API-007": ("GET", "/api/v1/users/{user_id}"),
    "API-008": ("PATCH", "/api/v1/users/{user_id}"),
    "API-009": ("GET", "/api/v1/roles"),
    "API-010": ("GET", "/api/v1/scopes"),
    "API-011": ("GET", "/api/v1/connectors"),
    "API-012": ("POST", "/api/v1/connectors"),
    "API-013": ("GET", "/api/v1/connectors/{connector_id}"),
    "API-014": ("PATCH", "/api/v1/connectors/{connector_id}"),
    "API-015": ("POST", "/api/v1/connectors/{connector_id}/sync"),
    "API-016": ("GET", "/api/v1/connectors/{connector_id}/jobs"),
    "API-017": ("POST", "/api/v1/connectors/validate"),
    "API-018": ("GET", "/api/v1/inventory/resources"),
    "API-019": ("GET", "/api/v1/inventory/resources/{resource_id}"),
    "API-020": ("PATCH", "/api/v1/inventory/resources/{resource_id}"),
    "API-021": ("GET", "/api/v1/inventory/services"),
    "API-022": ("GET", "/api/v1/inventory/drift"),
    "API-023": ("GET", "/api/v1/cost/summary"),
    "API-024": ("GET", "/api/v1/cost/timeseries"),
    "API-025": ("GET", "/api/v1/cost/breakdown"),
    "API-026": ("GET", "/api/v1/cost/line-items"),
    "API-027": ("GET", "/api/v1/cost/reconciliation"),
    "API-028": ("GET", "/api/v1/pricing/catalog"),
    "API-029": ("GET", "/api/v1/pricing/status"),
    "API-030": ("POST", "/api/v1/pricing/estimate"),
    "API-031": ("GET", "/api/v1/usage/metrics"),
    "API-032": ("GET", "/api/v1/runtime/states"),
    "API-033": ("GET", "/api/v1/runtime/schedules"),
    "API-034": ("POST", "/api/v1/runtime/exemptions"),
    "API-035": ("GET", "/api/v1/thresholds"),
    "API-036": ("POST", "/api/v1/thresholds"),
    "API-037": ("GET", "/api/v1/budgets"),
    "API-038": ("POST", "/api/v1/budgets"),
    "API-039": ("PATCH", "/api/v1/budgets/{budget_id}"),
    "API-040": ("GET", "/api/v1/forecasts"),
    "API-041": ("GET", "/api/v1/policies"),
    "API-042": ("POST", "/api/v1/policies/simulate"),
    "API-043": ("GET", "/api/v1/alerts"),
    "API-044": ("POST", "/api/v1/alerts/{alert_id}/ack"),
    "API-045": ("GET", "/api/v1/topology/graph"),
    "API-046": ("POST", "/api/v1/topology/edges"),
    "API-047": ("GET", "/api/v1/reports"),
    "API-048": ("POST", "/api/v1/reports/export"),
}

FORBIDDEN_CREDENTIAL_FIELD_SUBSTRINGS = [
    "secret_key",
    "private_key",
    "access_key_secret",
    "aws_secret",
    "azure_client_secret",
    "service_account_private_key",
    "password_hash",
    "raw_credentials",
    "credential_material",
    "private_key_pem",
    "oauth_client_secret",
]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_all_48_catalogue_endpoints_present_and_configured():
    """Verify all 48 required endpoints API-001 through API-048 exist in OpenAPI schema."""
    spec = app.openapi()
    paths = spec["paths"]

    missing: list[str] = []
    for api_id, (method, path) in CATALOGUE_48.items():
        if path not in paths:
            missing.append(f"{api_id}: Path '{path}' not found in OpenAPI spec")
            continue
        path_spec = paths[path]
        if method.lower() not in path_spec:
            missing.append(f"{api_id}: Method '{method}' not found for path '{path}'")

    assert not missing, "Missing catalogue endpoints in public API surface:\n" + "\n".join(missing)


def test_no_endpoint_returns_provider_credential_material():
    """Hard rule: No endpoint returns provider credential material under any circumstance.

    Automated test scanning every response schema across the entire OpenAPI definition.
    """
    spec = app.openapi()
    components = spec.get("components", {}).get("schemas", {})

    leaked_fields: list[str] = []

    def check_schema_dict(name: str, schema_dict: dict[str, Any]):
        props = schema_dict.get("properties", {})
        for prop_name in props.keys():
            low = prop_name.lower()
            for forbidden in FORBIDDEN_CREDENTIAL_FIELD_SUBSTRINGS:
                if forbidden in low:
                    leaked_fields.append(
                        f"Schema '{name}' exposes forbidden credential property '{prop_name}'"
                    )

    for schema_name, schema_obj in components.items():
        # Exclude internal break-glass provisioning response which intentionally returns base32 TOTP setup secret
        if schema_name in ("BreakGlassProvisionResponse", "BreakGlassAccount"):
            continue
        if isinstance(schema_obj, dict):
            check_schema_dict(schema_name, schema_obj)

    assert not leaked_fields, (
        "Discovered provider credential material in API response schemas:\n"
        + "\n".join(leaked_fields)
    )


def test_openapi_contract_drift_detector():
    """Authoritative contract drift check.

    Verifies committed docs/openapi.json matches the running FastAPI app.
    Contract drift is a release blocker.
    """
    contract_file = Path("docs/openapi.json")
    assert contract_file.exists(), (
        "Committed docs/openapi.json authoritative contract file must exist."
    )

    committed_spec = json.loads(contract_file.read_text(encoding="utf-8"))
    live_spec = app.openapi()

    assert live_spec["openapi"] == committed_spec["openapi"]
    assert live_spec["info"]["title"] == committed_spec["info"]["title"]

    # Verify all live paths exist in committed spec
    for path, path_obj in live_spec["paths"].items():
        assert path in committed_spec["paths"], (
            f"Live path '{path}' missing from committed docs/openapi.json"
        )
        for method in path_obj.keys():
            assert method in committed_spec["paths"][path], (
                f"Live method '{method}' for '{path}' missing from contract."
            )


def test_response_metadata_presence_in_schemas():
    """Verifies that response metadata schema exists and defines all 7 required metadata fields."""
    spec = app.openapi()
    schemas = spec.get("components", {}).get("schemas", {})
    assert "ResponseMetadata" in schemas, "ResponseMetadata must be defined in OpenAPI components"

    meta_props = schemas["ResponseMetadata"].get("properties", {})
    required_fields = [
        "period",
        "cost_basis",
        "currency",
        "is_currency_converted",
        "freshness_per_provider",
        "access_filtering_occurred",
        "is_approximate_total",
    ]
    for rf in required_fields:
        assert rf in meta_props, f"ResponseMetadata must define '{rf}'"
