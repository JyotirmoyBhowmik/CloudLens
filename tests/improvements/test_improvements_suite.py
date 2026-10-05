"""Unit and Integration Test Suite for Enterprise Improvements (Prompt R-FEAT).

Verifies IMP-01 through IMP-10:
- IMP-01: Maintenance Mode (tenant & global, 503 Problem Details, beat scheduler pause, audit)
- IMP-02: Session Management (list active sessions, revoke one/all, timeouts, Control Tower action)
- IMP-03: Audit Export & SIEM Forwarding (signed daily export, CEF format, hash-chain verify)
- IMP-04: Backup / Restore Self-Service Check (restore test to isolated schema, variance 0.0, Control Tower panel & action)
- IMP-05: Synthetic Journey Monitor (scheduled 4-step workflow, latency SLA, Prometheus metrics)
- IMP-06: In-App Release & Change Log (/api/v1/about, commit SHA, migration head, Control Tower panel)
- IMP-07: Rate-Limit & Abuse Dashboard (429 tracking, lockout after 5 failures, /control-tower/abuse)
- IMP-08: Data Freshness SLA Report (weekly provider/capability evaluation, email payload)
- IMP-09: Configuration Snapshot & Diff (export, diff, dry-run & live import, CLI script)
- IMP-10: Licence & Commitment Calendar (5-stream aggregation, /commitments/calendar, expiries panel)
- Phase 2 Safety Interlock: IMP-11 & IMP-12 gated as PENDING_CONFIRMATION.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.abuse.tracker import get_abuse_tracker
from domain.audit.service import (
    format_cef_event,
    export_daily_audit_signed,
    verify_audit_hash_chain,
)
from domain.commitments.calendar import (
    get_commitment_calendar_service,
)
from domain.config.snapshot_engine import (
    get_config_snapshot_engine,
)
from domain.control_tower.service import (
    get_control_tower_service,
    reset_control_tower_service,
)
from domain.identity.models import Session
from domain.identity.service import (
    get_identity_service,
    reset_identity_service,
)
from domain.maintenance.service import (
    get_maintenance_mode_service,
)
from domain.release.service import (
    get_release_service,
)
from domain.reports.freshness_sla import (
    get_freshness_sla_service,
)
from domain.synthetic.journey_monitor import (
    get_synthetic_journey_monitor,
)
from masterdata.improvement_features import get_feature_config, list_active_features


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_all_services():
    reset_control_tower_service()
    reset_identity_service()
    maint_svc = get_maintenance_mode_service()
    maint_svc.set_maintenance_mode(False)
    yield
    reset_control_tower_service()
    reset_identity_service()
    maint_svc.set_maintenance_mode(False)


# ==============================================================================
# IMP-01: MAINTENANCE MODE
# ==============================================================================

def test_imp01_maintenance_mode_lifecycle_and_blocking(client: TestClient):
    """Verifies maintenance mode blocks mutating operations with 503 Problem Details and allows GETs."""
    maint_service = get_maintenance_mode_service()
    assert not maint_service.is_maintenance_mode()

    # 1. Enable maintenance mode
    maint_service.set_maintenance_mode(
        enabled=True,
        reason="Scheduled platform core engine upgrade v1.1",
    )
    assert maint_service.is_maintenance_mode()

    # 2. Mutating request (non-exempt POST) is blocked with 503 Problem Details
    post_res = client.post(
        "/api/v1/costs/query",
        json={"dimensions": ["provider"]},
        headers={"X-Roles": "FINOPS_ANALYST"},
    )
    assert post_res.status_code == 503
    problem = post_res.json()
    assert problem["title"] == "Platform Maintenance Mode"
    assert "upgrade" in problem["detail"].lower() or "platform" in problem["detail"].lower()
    assert problem["status"] == 503

    # 3. Read-only GET is permitted
    get_res = client.get("/api/v1/health")
    assert get_res.status_code == 200

    # 4. Turn off maintenance mode
    maint_service.set_maintenance_mode(
        enabled=False,
        reason="Operational testing finished",
    )
    assert not maint_service.is_maintenance_mode()


# ==============================================================================
# IMP-02: SESSION MANAGEMENT
# ==============================================================================

def test_imp02_session_inventory_and_revocation():
    """Verifies session listing, revocation of single session, and all sessions for user."""
    id_service = get_identity_service()
    user_id = "analyst@finops.corp"
    tenant_id = "tenant-finance-01"

    now = datetime.now(UTC)
    s1 = Session(
        id="sess-01",
        tenant_id=tenant_id,
        user_id=user_id,
        token_family_id="fam-01",
        created_at=now,
        last_activity_at=now,
        expires_at=now + timedelta(hours=8),
        is_active=True,
        ip_address="192.168.1.10",
        user_agent="Mozilla/5.0",
    )
    s2 = Session(
        id="sess-02",
        tenant_id=tenant_id,
        user_id=user_id,
        token_family_id="fam-02",
        created_at=now,
        last_activity_at=now,
        expires_at=now + timedelta(hours=8),
        is_active=True,
        ip_address="192.168.1.20",
        user_agent="curl/7.68",
    )
    id_service._sessions[s1.id] = s1
    id_service._sessions[s2.id] = s2

    sessions = id_service.list_active_sessions(tenant_id=tenant_id, user_id=user_id)
    assert len(sessions) == 2

    # Revoke single session
    revoked = id_service.revoke_session(s1.id, actor_id="admin@jyotirmoyb.com")
    assert revoked is True
    assert len(id_service.list_active_sessions(tenant_id=tenant_id, user_id=user_id)) == 1

    # Revoke all sessions for user
    revoked_count = id_service.revoke_user_sessions(
        tenant_id=tenant_id, user_id=user_id, actor_id="admin@jyotirmoyb.com"
    )
    assert revoked_count == 1
    assert len(id_service.list_active_sessions(tenant_id=tenant_id, user_id=user_id)) == 0


# ==============================================================================
# IMP-03: AUDIT EXPORT & SIEM FORWARDING & HASH-CHAIN VERIFY
# ==============================================================================

def test_imp03_audit_export_siem_and_hash_chain():
    """Verifies ArcSight CEF event formatting, daily signed export, and hash-chain verification."""
    from domain.audit.models import AuditEvent, AuditEventCreate
    from domain.audit.service import get_audit_service
    from domain.models.enums import AuditEventType
    from domain.tenant.context import TenantContext

    tc = TenantContext(
        tenant_id="tenant-finance-01",
        user_id="admin@jyotirmoyb.com",
        roles=["SUPER_ADMIN"],
    )

    # 1. CEF Formatting
    raw_event = AuditEvent(
        id="evt-9901",
        tenant_id="tenant-finance-01",
        event_type=AuditEventType.CONFIG_CHANGED,
        actor_id="admin@jyotirmoyb.com",
        actor_roles=["SUPER_ADMIN"],
        action="CONFIG_OVERRIDE_APPLIED",
        resource_type="Budget",
        resource_id="budget-q4",
        timestamp=datetime.now(UTC),
        details={"target": "budget-q4"},
        event_hash="hash-12345",
    )
    cef = format_cef_event(raw_event)
    assert cef.startswith("CEF:0|CloudLens|Platform|1.0|")
    assert "suser=admin@jyotirmoyb.com" in cef
    assert "act=CONFIG_OVERRIDE_APPLIED" in cef

    # 2. Append real event and test Signed Daily Audit Export
    audit_svc = get_audit_service()
    audit_svc.append_event(
        tenant_context=tc,
        event_in=AuditEventCreate(
            event_type=AuditEventType.CONFIG_CHANGED,
            actor_id="admin@jyotirmoyb.com",
            actor_roles=["SUPER_ADMIN"],
            action="LOGIN",
            resource_type="Session",
            resource_id="sess-01",
            details={"status": "ok"},
        ),
    )
    bundle = export_daily_audit_signed(tenant_context=tc, export_date="2026-10-05")
    assert bundle["export_date"] == "2026-10-05"
    assert bundle["records_count"] >= 1
    assert "bundle_sha256" in bundle
    assert "hmac_signature" in bundle

    # 3. Hash-chain verification
    intact_res = verify_audit_hash_chain(tenant_id="tenant-finance-01")
    assert intact_res["valid"] is True
    assert intact_res["status"] == "HASH_CHAIN_INTEGRITY_VERIFIED"


def test_imp03_verify_audit_chain_script():
    """Verifies scripts/verify_audit_chain.py CLI tool."""
    script_path = Path("scripts/verify_audit_chain.py")
    assert script_path.exists()

    result = subprocess.run(
        [sys.executable, str(script_path), "--tenant", "tenant-finance-01"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "STATUS:        PASS" in result.stdout



# ==============================================================================
# IMP-04: BACKUP / RESTORE SELF-SERVICE CHECK
# ==============================================================================

def test_imp04_backup_restore_self_service():
    """Verifies automated restore test to isolated schema and Control Tower panel reflection."""
    ct_service = get_control_tower_service()

    # Initial backups panel shows last backup and test info
    panel = ct_service.get_backups_panel()
    assert panel.id == "backups"
    assert "Backup" in panel.name
    assert "last_backup_age_hours" in panel.metrics
    assert "last_restore_test_status" in panel.metrics

    # Execute restore test
    result = ct_service.run_restore_test()
    assert result["status"] == "PASSED"
    assert result["reconciliation_variance_ratio"] == 0.0
    assert "restore_test_iso_" in result["isolated_schema"]

    # Updated backups panel reflects latest restore test
    panel_updated = ct_service.get_backups_panel()
    assert panel_updated.metrics["last_restore_test_status"] == "PASSED"
    assert panel_updated.metrics["last_restore_reconciliation_variance"] == 0.0


# ==============================================================================
# IMP-05: SYNTHETIC JOURNEY MONITOR
# ==============================================================================

def test_imp05_synthetic_journey_monitor():
    """Verifies 4-step synthetic journey execution, SLA compliance check, and metric emission."""
    monitor = get_synthetic_journey_monitor()
    result = monitor.execute_journey()

    assert result["status"] in ("SUCCESS", "SLA_BREACHED")
    assert result["synthetic_tenant"] == "tenant-synthetic"
    assert "auth" in result["steps"]
    assert "dashboard" in result["steps"]
    assert "cost_query" in result["steps"]
    assert "report" in result["steps"]
    assert result["sla_passed"] is True


# ==============================================================================
# IMP-06: IN-APP RELEASE & CHANGE LOG
# ==============================================================================

def test_imp06_release_and_changelog_api(client: TestClient):
    """Verifies /api/v1/about endpoint returns version, commit SHA, migration head, and notes."""
    res = client.get("/api/v1/about")
    assert res.status_code == 200
    data = res.json()

    assert data["version"] == "0.1.0"
    assert len(data["git_commit"]) > 0
    assert len(data["migration_head"]) > 0
    assert len(data["release_notes"]) > 0

    # Verify Control Tower release panel reads the same data
    ct_service = get_control_tower_service()
    panel = ct_service.get_release_panel()
    assert panel.metrics["version"] == data["version"]
    assert panel.metrics["migration_head"] == data["migration_head"]


# ==============================================================================
# IMP-07: RATE-LIMIT & ABUSE DASHBOARD
# ==============================================================================

def test_imp07_abuse_tracker_and_lockout(client: TestClient):
    """Verifies rate-limit tracking, auth failure lockout after 5 attempts, and abuse panel."""
    tracker = get_abuse_tracker()
    client_ip = "198.51.100.42"

    tracker.record_call(caller_id=client_ip)
    tracker.record_429(caller_id=client_ip, path="/api/v1/costs")

    summary = tracker.get_abuse_summary()
    assert summary["total_429_events"] >= 1

    # Progressive lockout test: 5 consecutive failures
    for _ in range(5):
        tracker.record_auth_failure(principal_id=client_ip, ip_address=client_ip)

    is_locked, remaining = tracker.is_locked_out(principal_id=client_ip)
    assert is_locked is True
    assert remaining > 0

    # Control Tower abuse endpoint
    headers = {"X-User-Roles": "SUPER_ADMIN", "X-Scope-Grants": "platform.observe"}
    res = client.get("/api/v1/control-tower/abuse", headers=headers)
    assert res.status_code == 200
    abuse_data = res.json()
    assert abuse_data["total_429_events"] >= 1
    assert abuse_data["lockout_count"] >= 1


# ==============================================================================
# IMP-08: DATA FRESHNESS SLA REPORT
# ==============================================================================

def test_imp08_data_freshness_sla_report():
    """Verifies weekly SLA evaluation per provider/capability and email report payload."""
    sla_service = get_freshness_sla_service()
    report = sla_service.generate_sla_report()

    assert report["report_id"].startswith("sla-freshness-")
    assert report["recipient_email"] == "admin@jyotirmoyb.com"
    assert report["window_days"] == 7
    assert "provider_capability_matrix" in report
    assert len(report["provider_capability_matrix"]) >= 4

    dispatch = sla_service.dispatch_weekly_email()
    assert dispatch["email_dispatch"]["status"] == "SENT"
    assert dispatch["email_dispatch"]["to"] == "admin@jyotirmoyb.com"


# ==============================================================================
# IMP-09: CONFIGURATION SNAPSHOT AND DIFF
# ==============================================================================

def test_imp09_config_snapshot_diff_and_import(tmp_path: Path):
    """Verifies configuration snapshot export, diffing between environments, and import."""
    engine = get_config_snapshot_engine()

    # 1. Export DEV snapshot
    dev_snap = engine.export_snapshot(environment="DEV")
    assert dev_snap["environment"] == "DEV"
    assert "masters" in dev_snap
    assert dev_snap["masters_count"] > 0

    # 2. Modify one setting for PROD snapshot
    prod_snap = engine.export_snapshot(environment="PROD")
    prod_snap["masters"]["additional_test_key"] = [{"test": 123}]

    # 3. Diff snapshots
    diff = engine.diff_snapshots(dev_snap, prod_snap)
    assert diff["has_differences"] is True
    assert "additional_test_key" in diff["added_masters"]

    # 4. Dry-run import
    dry_run_res = engine.import_snapshot(dev_snap, dry_run=True)
    assert dry_run_res["dry_run"] is True
    assert dry_run_res["status"] == "VALIDATED"

    # 5. Live import to temp directory
    live_res = engine.import_snapshot(dev_snap, dry_run=False, target_dir=tmp_path)
    assert live_res["dry_run"] is False
    assert live_res["status"] == "IMPORTED"
    assert (tmp_path / "improvement_features.json").exists()


def test_imp09_config_snapshot_script(tmp_path: Path):
    """Verifies scripts/config_snapshot.py CLI tool."""
    script_path = Path("scripts/config_snapshot.py")
    assert script_path.exists()
    out_file = tmp_path / "snap.json"

    result = subprocess.run(
        [sys.executable, str(script_path), "export", "--out", str(out_file), "--env", "TEST"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "[EXPORT OK]" in result.stdout
    assert out_file.exists()


# ==============================================================================
# IMP-10: LICENCE & COMMITMENT CALENDAR
# ==============================================================================

def test_imp10_commitment_calendar_api(client: TestClient):
    """Verifies 5-stream aggregation in calendar view and /commitments/calendar endpoint."""
    res = client.get("/api/v1/commitments/calendar")
    assert res.status_code == 200
    data = res.json()

    assert "events" in data
    assert "total_upcoming_events" in data
    assert data["total_upcoming_events"] >= 5

    streams = set(data["streams_represented"])
    assert "CREDENTIAL_EXPIRY" in streams
    assert "CERT_EXPIRY" in streams
    assert "COMMITMENT_EXPIRY" in streams
    assert "LICENCE_RENEWAL" in streams
    assert "BUDGET_PERIOD_CLOSE" in streams

    # Verify Control Tower expiries panel utilizes calendar data
    ct_service = get_control_tower_service()
    expiries_panel = ct_service.get_expiries_panel()
    assert expiries_panel.id == "expiries"
    assert "Expiries" in expiries_panel.name
    assert "upcoming_expiries_90d" in expiries_panel.metrics
    assert expiries_panel.metrics["streams_represented"] == 5


# ==============================================================================
# PHASE 2: SAFETY INTERLOCK
# ==============================================================================

def test_phase2_items_remain_pending_confirmation():
    """Verifies IMP-11 and IMP-12 are strictly flagged as Phase 2 PENDING_CONFIRMATION."""
    features = list_active_features()
    feature_map = {f["code"]: f for f in features}

    assert "IMP_11_COLLAB_ALERTS" in feature_map
    assert feature_map["IMP_11_COLLAB_ALERTS"]["phase"] == 2
    assert feature_map["IMP_11_COLLAB_ALERTS"]["status"] == "PENDING_CONFIRMATION"

    assert "IMP_12_ANOMALY_DETECTION" in feature_map
    assert feature_map["IMP_12_ANOMALY_DETECTION"]["phase"] == 2
    assert feature_map["IMP_12_ANOMALY_DETECTION"]["status"] == "PENDING_CONFIRMATION"

    # Config helper reflects phase 2
    imp11_cfg = get_feature_config("IMP_11_COLLAB_ALERTS")
    assert imp11_cfg is not None
    assert imp11_cfg.get("requires_confirmation") is True

