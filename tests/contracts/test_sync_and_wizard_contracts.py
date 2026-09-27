"""Contract Tests for Synchronization, Wizard, and Diagnostics API Endpoints (Prompt 15).

Validates:
- /api/v1/sync:
  - POST /api/v1/sync/jobs (trigger sync supporting all 7 sync types, returns 202)
  - GET /api/v1/sync/jobs/{job_id} & GET /api/v1/sync/jobs
  - GET /api/v1/sync/lag (sync lag & freshness query)
  - GET & PUT /api/v1/sync/schedules (schedules & cadence warnings)
  - GET /api/v1/sync/quarantine (dead-letter queue)
- /api/v1/wizard:
  - POST /api/v1/wizard/sessions (start session, returns 201)
  - GET /api/v1/wizard/permissions-reference/{provider} (Step 2 permission reference before credentials)
  - POST /api/v1/wizard/sessions/{session_id}/validate-credentials (Step 4 validation)
  - POST /api/v1/wizard/sessions/{session_id}/validate-permissions (Step 5 "Not Supported" degradation)
  - GET /api/v1/wizard/sessions/{session_id}/discover-scopes (Step 6 hierarchy discovery)
  - GET /api/v1/wizard/sessions/{session_id}/estimates (Step 12 pre-completion sizing & cost)
  - POST /api/v1/wizard/sessions/{session_id}/complete (Step 13 completion & schedule bootstrap)
- /api/v1/connectors:
  - GET /api/v1/connectors/{connector_id}/diagnostics (per-capability diagnostics)
  - GET /api/v1/connectors/{connector_id}/outage-gap-report (outage gap analysis)
  - POST /api/v1/connectors/{connector_id}/resume (pagination checkpoint resumption)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from connectors.contract.checkpoint_store import checkpoint_store
from domain.models.enums import ConnectorCapability
from domain.tenant.context import TenantContext


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def tenant_headers() -> dict[str, str]:
    return {
        "X-Tenant-ID": "tenant-api-contract-01",
        "X-Correlation-ID": "corr-api-contract-001",
    }


# ==============================================================================
# 1. Sync Orchestration Endpoints
# ==============================================================================


def test_contract_trigger_sync_job(client: TestClient, tenant_headers: dict[str, str]):
    """Item 97: Trigger sync job endpoint executes and returns SyncJob response with 202 status."""
    payload = {
        "connector_id": "conn-sim-aws-01",
        "sync_type": "initial_discovery",
        "target_scopes": ["111122223333"],
    }
    res = client.post("/api/v1/sync/jobs", json=payload, headers=tenant_headers)
    assert res.status_code == 202
    data = res.json()
    assert "id" in data
    assert data["connector_id"] == "conn-sim-aws-01"
    assert data["sync_type"] == "initial_discovery"
    assert data["status"] in ("COMPLETED", "PARTIAL_SUCCESS")
    assert "rows_ingested" in data
    assert data["rows_ingested"] >= 0

    job_id = data["id"]

    # Verify GET /jobs/{job_id}
    res_get = client.get(f"/api/v1/sync/jobs/{job_id}", headers=tenant_headers)
    assert res_get.status_code == 200
    assert res_get.json()["id"] == job_id

    # Verify GET /jobs listing
    res_list = client.get("/api/v1/sync/jobs?limit=10", headers=tenant_headers)
    assert res_list.status_code == 200
    items = res_list.json()
    assert any(j["id"] == job_id for j in items)


def test_contract_sync_lag(client: TestClient, tenant_headers: dict[str, str]):
    """Item 99: Sync lag endpoint returns freshness metrics and staleness status."""
    res = client.get(
        "/api/v1/sync/lag?connector_id=conn-sim-aws-01&capability=discover_resources",
        headers=tenant_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["connector_id"] == "conn-sim-aws-01"
    assert data["capability"] == "discover_resources"
    assert "is_stale" in data
    assert "lag_seconds" in data


def test_contract_sync_schedules_and_cadence_warning(
    client: TestClient, tenant_headers: dict[str, str]
):
    """Item 98: Schedules endpoint lists defaults and warns on non-productive cadence."""
    connector_id = "conn-sched-test"
    from connectors.sync.scheduler import get_sync_scheduler

    tc = TenantContext(
        tenant_id=tenant_headers["X-Tenant-ID"],
        user_id="usr-test",
        roles=["TENANT_ADMIN"],
        correlation_id=tenant_headers["X-Correlation-ID"],
    )
    get_sync_scheduler().initialize_connector_schedules(connector_id, tenant_context=tc)

    # GET schedules
    res = client.get(f"/api/v1/sync/schedules?connector_id={connector_id}", headers=tenant_headers)
    assert res.status_code == 200
    schedules = res.json()
    assert len(schedules) >= 5

    # Update schedule to an overly frequent interval (e.g., pricing every 30 mins)
    update_payload = {
        "connector_id": connector_id,
        "capability": "collect_pricing_public",
        "interval_minutes": 30,
        "is_enabled": True,
    }
    res_put = client.put(
        "/api/v1/sync/schedules",
        json=update_payload,
        headers=tenant_headers,
    )
    assert res_put.status_code == 200
    resp_data = res_put.json()
    assert "schedule" in resp_data
    assert "warning" in resp_data
    # Should contain cadence warning
    assert resp_data["warning"] is not None
    assert "catalogs" in resp_data["warning"]["warning_message"].lower()


def test_contract_quarantine_listing(client: TestClient, tenant_headers: dict[str, str]):
    """Item 99: Dead-letter quarantine endpoint lists quarantined records."""
    res = client.get("/api/v1/sync/quarantine?limit=20", headers=tenant_headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)


# ==============================================================================
# 2. Onboarding Wizard Endpoints
# ==============================================================================


def test_contract_wizard_full_progression(client: TestClient, tenant_headers: dict[str, str]):
    """Items 100-103: End-to-end 13-step wizard progression through API."""
    # Step 1: Start wizard
    res_start = client.post("/api/v1/wizard/sessions", headers=tenant_headers)
    assert res_start.status_code == 201
    start_data = res_start.json()
    session_data = start_data["session"]
    session_id = session_data["id"]
    assert session_data["current_step"] == "select_provider"

    # Step 2: Permission reference rendered before credentials (Item 101)
    res_ref = client.get("/api/v1/wizard/permissions-reference/aws", headers=tenant_headers)
    assert res_ref.status_code == 200
    ref_data = res_ref.json()
    assert ref_data["provider"] == "aws"
    assert len(ref_data["capabilities"]) > 0

    # Advance Step 1 (SELECT_PROVIDER)
    res_s1 = client.post(
        f"/api/v1/wizard/sessions/{session_id}/step/select_provider",
        json={"step_data": {"provider": "aws"}},
        headers=tenant_headers,
    )
    assert res_s1.status_code == 200

    # Advance Step 2 (SELECT_CONNECTION_METHOD)
    res_s2 = client.post(
        f"/api/v1/wizard/sessions/{session_id}/step/select_connection_method",
        json={"step_data": {"connection_method": "role_delegation"}},
        headers=tenant_headers,
    )
    assert res_s2.status_code == 200

    # Step 4: Validate Credentials (VALIDATE_CREDENTIALS)
    res_val_cred = client.post(
        f"/api/v1/wizard/sessions/{session_id}/validate-credentials",
        json={
            "credentials": {
                "role_arn": "arn:aws:iam::123456789012:role/ProdFinOps",
                "external_id": "ext-prod-001",
            }
        },
        headers=tenant_headers,
    )
    assert res_val_cred.status_code == 200
    assert res_val_cred.json()["valid"] is True

    # Step 5: Validate Permissions & Degradation (Item 102)
    res_val_perm = client.post(
        f"/api/v1/wizard/sessions/{session_id}/validate-permissions",
        json={"simulate_missing_permissions": ["ce:GetCostAndUsage"]},
        headers=tenant_headers,
    )
    assert res_val_perm.status_code == 200
    reports = res_val_perm.json()
    # Check that missing capability renders as "Not Supported", NOT zero
    cost_report = next(r for r in reports if r["permission"] == "ce:GetCostAndUsage")
    assert cost_report["present"] is False
    assert cost_report["status_display"] == "Not Supported"

    # Step 6: Discover Scopes
    res_disc = client.get(
        f"/api/v1/wizard/sessions/{session_id}/discover-scopes",
        headers=tenant_headers,
    )
    assert res_disc.status_code == 200
    discovered_scopes = res_disc.json()
    assert len(discovered_scopes) > 0

    # Step 7: Select Scopes
    selected_scope_ids = [s["scope_id"] for s in discovered_scopes[:2]]
    res_s7 = client.post(
        f"/api/v1/wizard/sessions/{session_id}/step/select_scopes",
        json={"step_data": {"selected_scopes": selected_scope_ids, "include_future_scopes": True}},
        headers=tenant_headers,
    )
    assert res_s7.status_code == 200

    # Step 8: Configure Synchronisation
    client.post(
        f"/api/v1/wizard/sessions/{session_id}/step/configure_synchronisation",
        json={"step_data": {"cadence": "standard"}},
        headers=tenant_headers,
    )
    # Step 9: Configure Cost Ingestion
    client.post(
        f"/api/v1/wizard/sessions/{session_id}/step/configure_cost_ingestion",
        json={"step_data": {"cost_granularity": "hourly"}},
        headers=tenant_headers,
    )
    # Step 10: Configure Resource Discovery
    client.post(
        f"/api/v1/wizard/sessions/{session_id}/step/configure_resource_discovery",
        json={"step_data": {"scan_interval_hours": 6}},
        headers=tenant_headers,
    )
    # Step 11: Configure Usage Monitoring
    client.post(
        f"/api/v1/wizard/sessions/{session_id}/step/configure_usage_monitoring",
        json={"step_data": {"metrics_enabled": True}},
        headers=tenant_headers,
    )
    # Step 12: Configure Budgets & Thresholds
    client.post(
        f"/api/v1/wizard/sessions/{session_id}/step/configure_budgets_thresholds",
        json={"step_data": {"alerts": True}},
        headers=tenant_headers,
    )

    # Step 12: Pre-Completion Estimates (Item 103)
    res_est = client.get(f"/api/v1/wizard/sessions/{session_id}/estimates", headers=tenant_headers)
    assert res_est.status_code == 200
    est = res_est.json()
    assert est["resource_count_estimate"] > 0
    assert est["expected_duration_seconds"] > 0
    assert est["metric_call_volume_estimate"] > 0
    assert est["provider_cost_implication_estimate_usd"] >= 0

    # Step 13: Complete Wizard
    res_comp = client.post(f"/api/v1/wizard/sessions/{session_id}/complete", headers=tenant_headers)
    assert res_comp.status_code == 200
    comp_data = res_comp.json()
    assert comp_data["status"] == "COMPLETED"
    assert "connector_id" in comp_data
    assert "initial_sync_job_id" in comp_data


# ==============================================================================
# 3. Connector Diagnostics Endpoints
# ==============================================================================


def test_contract_diagnostics_report(client: TestClient, tenant_headers: dict[str, str]):
    """Item 104: Diagnostics endpoint returns per-capability diagnostics and headroom."""
    connector_id = "conn-diag-api-01"
    res = client.get(f"/api/v1/connectors/{connector_id}/diagnostics", headers=tenant_headers)
    assert res.status_code == 200
    diag = res.json()
    assert diag["connector_id"] == connector_id
    assert "overall_state" in diag
    assert "capabilities" in diag
    assert len(diag["capabilities"]) == 17


def test_contract_outage_gap_report(client: TestClient, tenant_headers: dict[str, str]):
    """Item 105: Outage gap report returns missed windows and scopes."""
    connector_id = "conn-diag-api-01"
    start_time = (datetime.now(UTC) - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
    res = client.get(
        f"/api/v1/connectors/{connector_id}/outage-gap-report?outage_start={start_time}",
        headers=tenant_headers,
    )
    assert res.status_code == 200
    gap = res.json()
    assert gap["connector_id"] == connector_id
    assert gap["duration_hours"] >= 11.5
    assert len(gap["missed_periods"]) >= 2
    assert "recommended_backfill_types" in gap


def test_contract_checkpoint_resumption(client: TestClient, tenant_headers: dict[str, str]):
    """Item 105: Resumes connector sync from pagination checkpoint."""
    connector_id = "conn-diag-api-01"
    capability = ConnectorCapability.DISCOVER_RESOURCES

    # Save checkpoint
    checkpoint_store.save_checkpoint(
        tenant_context=TenantContext(
            tenant_id="tenant-api-contract-01",
            user_id="usr-test",
            roles=["TENANT_ADMIN"],
            correlation_id="corr-test",
        ),
        job_id="latest",
        connector_id=connector_id,
        capability=capability,
        continuation_token="tok-continuation-contract",
        page_number=2,
        records_ingested=100,
    )

    res = client.post(
        f"/api/v1/connectors/{connector_id}/resume",
        json={"capability": "discover_resources"},
        headers=tenant_headers,
    )
    assert res.status_code == 200
    resumed = res.json()
    assert resumed["status"] == "RESUMED"
    assert resumed["connector_id"] == connector_id
    assert resumed["page_number"] == 2
    assert resumed["continuation_token_present"] is True


def test_contract_onboarding_step_restoration_and_alert_delivery(
    client: TestClient, tenant_headers: dict[str, str]
):
    """Prompt 15B Items 21-27: Test alert delivery, first-sync progress, completion summary, and notification log API contracts."""
    # 1. Start a new session
    res_start = client.post("/api/v1/wizard/sessions", headers=tenant_headers)
    assert res_start.status_code == 201
    session_id = res_start.json()["session"]["id"]

    # 2. Test Alert Delivery endpoint (Item 24)
    probe_payload = {
        "channels": [
            {"channel": "EMAIL", "recipient": "ops-contract@test.cloudlens.io"},
            {"channel": "SLACK", "recipient": "https://hooks.slack.com/contract-test"},
        ]
    }
    res_test = client.post(
        f"/api/v1/wizard/sessions/{session_id}/test-alert-delivery",
        json=probe_payload,
        headers=tenant_headers,
    )
    assert res_test.status_code == 200
    report = res_test.json()
    assert report["is_test"] is True
    assert report["total_channels"] == 2
    assert report["successful_channels"] == 2
    assert report["can_proceed"] is True

    # 3. Complete Wizard (Items 21, 22, 27)
    res_comp = client.post(f"/api/v1/wizard/sessions/{session_id}/complete", headers=tenant_headers)
    assert res_comp.status_code == 200
    comp_data = res_comp.json()
    assert comp_data["status"] == "COMPLETED"
    assert "landing_destination" in comp_data
    assert "/onboarding/first-sync-progress" in comp_data["landing_destination"]
    assert "first_sync_progress" in comp_data
    assert "completion_summary" in comp_data

    # 4. GET /first-sync-progress (Item 21)
    res_fsp = client.get(
        f"/api/v1/wizard/sessions/{session_id}/first-sync-progress",
        headers=tenant_headers,
    )
    assert res_fsp.status_code == 200
    fsp_data = res_fsp.json()
    assert fsp_data["total_stages"] == 5
    assert len(fsp_data["stages"]) == 5
    cost_stage = next(s for s in fsp_data["stages"] if s["stage_id"] == "retrieve_cost_data")
    assert "Provider billing latency" in cost_stage["latency_explanation"]

    # 5. GET /completion-summary (Item 27)
    res_sum = client.get(
        f"/api/v1/wizard/sessions/{session_id}/completion-summary",
        headers=tenant_headers,
    )
    assert res_sum.status_code == 200
    sum_data = res_sum.json()
    assert sum_data["session_id"] == session_id
    assert len(sum_data["capabilities_available"]) > 0
    assert "4 to 8 hours" in sum_data["estimated_time_to_first_cost_data"]

    # 6. GET /notifications/log (Item 25)
    res_logs = client.get("/api/v1/wizard/notifications/log", headers=tenant_headers)
    assert res_logs.status_code == 200
    logs = res_logs.json()
    assert isinstance(logs, list)
    matching = [rec for rec in logs if rec.get("metadata", {}).get("session_id") == session_id]
    assert len(matching) >= 2
    for rec in matching:
        assert rec["is_test"] is True
        assert rec["alert_id"] is None
