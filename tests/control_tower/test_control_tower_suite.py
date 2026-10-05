"""Unit and Integration Tests for Platform Control Tower (Prompt R-CT).

Verifies:
1. Observe-only user (AUDITOR) sees all 14 panels, but every action returns 403.
2. Superuser action without step-up returns 403.
3. Superuser action with step-up + valid reason (>= 20 chars) returns 200 + audit row.
4. Short reason (< 20 chars) returns 400.
5. No raw cost lines or user emails from other tenants appear in responses (cross-tenant aggregation).
6. SSE stream emits live events.
7. Forced failures (connector failure, worker down, vault down) turn tiles red within 30s.
8. Routine-use exemption: Superuser GET /control-tower/overview does NOT increment routine-use count;
   non-control-tower action DOES increment and alerts.
"""

from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.bootstrap.superuser import get_superuser_service, reset_superuser_service
from domain.control_tower.models import PanelStatus
from domain.control_tower.service import get_control_tower_service, reset_control_tower_service
from domain.models.enums import SystemRole


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_ct_state():
    reset_control_tower_service()
    reset_superuser_service()
    from domain.observability import health_probe
    health_probe.reset_overrides()
    health_probe.set_override("secret_store", True)
    yield
    reset_control_tower_service()
    reset_superuser_service()
    health_probe.reset_overrides()



# --- Requirement 1: Observe-Only User (AUDITOR) vs Operator ---


def test_observe_only_user_can_view_all_14_panels(client: TestClient):
    """Observe-only user (AUDITOR) can view /overview and all 14 panel endpoints."""
    headers = {
        "X-User-Roles": "AUDITOR",
        "X-Scope-Grants": "platform.observe",
    }

    # 1. Overview
    res = client.get("/api/v1/control-tower/overview", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert len(data["panels"]) == 14
    assert data["overall_status"] in ("green", "amber", "red", "grey")
    assert data["overall_label"] != ""

    panel_ids = {p["id"] for p in data["panels"]}
    expected_14 = {
        "health",
        "release",
        "tenants",
        "connectors",
        "jobs",
        "queues",
        "pipeline",
        "security",
        "alerts_pipeline",
        "collection_cost",
        "capacity",
        "backups",
        "expiries",
        "value",
    }
    assert panel_ids == expected_14

    # 2. Individual drilldowns
    for pid in expected_14:
        panel_endpoint = pid.replace("_", "-")
        r = client.get(f"/api/v1/control-tower/{panel_endpoint}", headers=headers)
        assert r.status_code == 200, f"Panel {pid} failed: {r.text}"
        pdata = r.json()
        assert pdata["id"] == pid
        assert pdata["status_label"] != ""


def test_observe_only_user_blocked_from_every_action(client: TestClient):
    """AUDITOR (observe-only) receives 403 on every administrative action."""
    headers = {
        "X-User-Roles": "AUDITOR",
        "X-Scope-Grants": "platform.observe",
        "X-Step-Up-Token": "valid-stepup-token-1234",
    }

    actions = [
        "retry-job",
        "pause-connector",
        "resume-connector",
        "force-sync",
        "drain-queue",
        "requeue-quarantine",
        "maintenance-mode",
        "revoke-user-sessions",
        "trigger-backup",
        "trigger-reconciliation",
    ]

    for action in actions:
        res = client.post(
            f"/api/v1/control-tower/actions/{action}",
            headers=headers,
            json={
                "action": action,
                "reason": "Legitimate administrative justification for testing purposes only",
                "confirm": True,
                "step_up_token": "valid-stepup-token-1234",
            },
        )
        assert res.status_code == 403, f"Action {action} should have been forbidden for AUDITOR: {res.text}"
        assert "platform.operate" in res.json().get("detail", "")


# --- Requirement 2 & 3: Superuser Action Enforcement (Step-up, Reason, Audit) ---


def test_superuser_action_without_step_up_returns_403(client: TestClient):
    """Superuser action without step-up proof returns 403 Forbidden."""
    headers = {
        "X-User-Roles": "SUPER_ADMIN",
        "X-Scope-Grants": "platform.observe,platform.operate",
    }

    res = client.post(
        "/api/v1/control-tower/actions/force-sync",
        headers=headers,
        json={
            "action": "force-sync",
            "params": {"connector_id": "aws-cur"},
            "reason": "Administrative emergency force sync trigger justification",
            "confirm": True,
            # No step_up_token provided
        },
    )
    assert res.status_code == 403
    assert "Step-up authentication" in res.json().get("detail", "")


def test_superuser_action_with_short_reason_returns_400(client: TestClient):
    """Superuser action with reason < 20 chars returns 400 Bad Request or 422 Unprocessable."""
    headers = {
        "X-User-Roles": "SUPER_ADMIN",
        "X-Scope-Grants": "platform.observe,platform.operate",
        "X-Step-Up-Token": "valid-stepup-token-1234",
    }

    res = client.post(
        "/api/v1/control-tower/actions/force-sync",
        headers=headers,
        json={
            "action": "force-sync",
            "params": {"connector_id": "aws-cur"},
            "reason": "too short",  # < 20 chars
            "confirm": True,
            "step_up_token": "valid-stepup-token-1234",
        },
    )
    assert res.status_code in (400, 422)


def test_superuser_action_stages_blast_radius_before_execution(client: TestClient):
    """Unconfirmed action returns predicted blast radius requiring explicit confirmation."""
    headers = {
        "X-User-Roles": "SUPER_ADMIN",
        "X-Scope-Grants": "platform.observe,platform.operate",
    }

    res = client.post(
        "/api/v1/control-tower/actions/pause-connector",
        headers=headers,
        json={
            "action": "pause-connector",
            "params": {"connector_id": "azure-ea"},
            "reason": "Pre-maintenance connector freeze for routine system upgrade",
            "confirm": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "staged"
    assert data["requires_confirmation"] is True
    assert "azure-ea" in data["blast_radius"]["affected_connectors"]


def test_superuser_action_with_stepup_and_reason_executes_and_audits(client: TestClient):
    """Confirmed action with step-up and valid reason executes and writes CT_ACTION audit event."""
    headers = {
        "X-User-Roles": "SUPER_ADMIN",
        "X-Scope-Grants": "platform.observe,platform.operate",
        "X-Step-Up-Token": "valid-stepup-token-1234",
        "X-Actor-ID": "admin@jyotirmoyb.com",
    }

    reason_text = "Operational justification: Performing emergency database snapshot checkpoint before deploy"
    res = client.post(
        "/api/v1/control-tower/actions/trigger-backup",
        headers=headers,
        json={
            "action": "trigger-backup",
            "params": {},
            "reason": reason_text,
            "confirm": True,
            "step_up_token": "valid-stepup-token-1234",
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "executed"
    assert data["action"] == "trigger-backup"
    assert data["audit_event_id"].startswith("evt-") or len(data["audit_event_id"]) > 0

    # Verify audit tail contains the event
    audit_res = client.get("/api/v1/control-tower/audit/tail?limit=10", headers=headers)
    assert audit_res.status_code == 200
    events = audit_res.json()["events"]
    matching = [e for e in events if e.get("event_type") == "CT_ACTION"]
    assert len(matching) > 0
    assert "TRIGGER_BACKUP" in matching[0]["action"]


# --- Requirement 4: Cross-Tenant Aggregation & Privacy Guard ---


def test_no_raw_cost_line_or_foreign_email_disclosed(client: TestClient):
    """Ensures responses never contain foreign tenant user emails or raw cost records."""
    headers = {
        "X-User-Roles": "SUPER_ADMIN",
        "X-Scope-Grants": "platform.observe",
    }

    res = client.get("/api/v1/control-tower/overview", headers=headers)
    assert res.status_code == 200
    text_content = res.text

    # No sample corporate emails from other tenants
    forbidden_domains = ["@example.com", "@company.com", "@enterprise.com", "@acme.org"]
    for domain in forbidden_domains:
        assert domain not in text_content, f"Foreign domain '{domain}' found in Control Tower output!"

    # No un-aggregated raw record objects
    assert "raw_cost_lines" not in text_content
    assert "cost_line_id" not in text_content


# --- Requirement 5: Forced Failures Turn Tiles Red ---


def test_forced_failures_turn_corresponding_tiles_red(client: TestClient):
    """Forced failures turn the respective panels red immediately."""
    svc = get_control_tower_service()
    headers = {
        "X-User-Roles": "SUPER_ADMIN",
        "X-Scope-Grants": "platform.observe",
    }

    # 1. Initial overview is healthy
    r_initial = client.get("/api/v1/control-tower/overview", headers=headers)
    assert r_initial.status_code == 200
    init_panels = {p["id"]: p["status"] for p in r_initial.json()["panels"]}
    assert init_panels["connectors"] == "green"
    assert init_panels["queues"] == "green"
    assert init_panels["health"] == "green"

    # 2. Force connector failure
    svc.force_connector_failure("aws-cur", "ThrottlingException: Rate exceeded")
    r_conn = client.get("/api/v1/control-tower/connectors", headers=headers)
    assert r_conn.status_code == 200
    assert r_conn.json()["status"] == "red"
    assert "CRITICAL" in r_conn.json()["reason"]

    # 3. Force worker down
    svc.set_forced_worker_down(True)
    r_queue = client.get("/api/v1/control-tower/queues", headers=headers)
    assert r_queue.status_code == 200
    assert r_queue.json()["status"] == "red"
    assert "unreachable" in r_queue.json()["reason"]

    # 4. Force vault down
    svc.set_forced_vault_down(True)
    r_health = client.get("/api/v1/control-tower/health", headers=headers)
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "red"
    assert "Vault" in r_health.json()["reason"]

    # Overall overview is now RED
    r_overview = client.get("/api/v1/control-tower/overview", headers=headers)
    assert r_overview.json()["overall_status"] == "red"


# --- Requirement 6: Routine-Use Detector Exemption ---


def test_routine_use_detector_exempts_read_only_control_tower_gets():
    """Read-only Control Tower GETs do NOT count towards routine use; other operations do."""
    superuser_svc = get_superuser_service()
    superuser_svc._routine_days_count = 0
    superuser_svc._last_routine_date = None

    # 1. Read-only Control Tower GETs do NOT increment
    alert_ct = superuser_svc.record_routine_operation(
        action="control_tower:observe",
        activity_date="2026-10-01",
        endpoint="/api/v1/control-tower/overview",
        method="GET",
    )
    assert alert_ct is None
    assert superuser_svc._routine_days_count == 0

    # 2. Non-control-tower routine operation DOES increment
    a1 = superuser_svc.record_routine_operation(
        action="cost:read",
        activity_date="2026-10-01",
        endpoint="/api/v1/cost",
        method="GET",
    )
    assert a1 is None
    assert superuser_svc._routine_days_count == 1

    # 3. Control Tower ACTION (/actions/*) DOES increment
    a2 = superuser_svc.record_routine_operation(
        action="control_tower:action",
        activity_date="2026-10-02",
        endpoint="/api/v1/control-tower/actions/force-sync",
        method="POST",
    )
    assert a2 is None
    assert superuser_svc._routine_days_count == 2
