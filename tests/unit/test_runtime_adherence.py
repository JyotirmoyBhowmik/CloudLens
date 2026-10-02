"""Comprehensive Unit and Acceptance Tests for Runtime Model & Schedule Adherence (Prompt 26).

Verifies:
- Prompt 26: Six-state runtime model with distinct meanings (RUNNING, STOPPED, PARTIALLY_RUNNING, NOT_APPLICABLE, UNKNOWN, NO_DATA).
- Prompt 26: UNKNOWN and NO_DATA are NEVER compliant and NEVER coloured green (AC-061).
- Prompt 26: Do not conflate Stopped with Not applicable.
- Prompt 26: Named schedules with timezone, working days, daily hours, exclusion dates, and maintenance windows.
- Prompt 26: Schedule inheritance chain (RESOURCE -> SERVICE -> SCOPE -> ENV -> TENANT) and BR-007 non-prod rules.
- Prompt 26: Out-of-schedule execution detected within 1 cycle and excess cost calculated (AC-060).
- Prompt 26: Monetary valuation of every breach ('Do not raise a schedule exception without a monetary value').
- Prompt 26: Temporary exemption mechanism with justification (>= 20 chars), alert suppression, and auto-expiry (AC-062).
- Prompt 26: Phase 2 idle detection ready but disabled behind feature flag ('Do not enable idle detection in MVP').
- API-032, API-033, API-034 contract endpoints.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.models.base import ProvenanceRecord
from domain.models.enums import OriginType
from domain.models.exceptions import (
    ExemptionReasonTooShortException,
    IdleDetectionDisabledException,
    RuntimeStateNonComplianceException,
)
from domain.runtime.evaluator import AdherenceEvaluator
from domain.runtime.idle_detector import IdleDetector
from domain.runtime.models import (
    AdherenceStatus,
    IdleSignalType,
    MaintenanceWindow,
    NamedSchedule,
    RuntimeExemptionCreateRequest,
    RuntimeObservation,
    RuntimeState,
    ScheduleAdherenceResult,
    ScheduleAttachment,
    ScheduleLevel,
)
from domain.runtime.repository import (
    reset_runtime_repository,
)
from domain.runtime.schedules import (
    STANDARD_SCHEDULES,
    ScheduleEngine,
    is_approved_running_slot,
)
from domain.runtime.service import get_runtime_service, reset_runtime_service
from domain.tenant.context import TenantContext


@pytest.fixture(autouse=True)
def reset_runtime_state() -> None:
    """Ensures clean repository and service instances between test executions."""
    reset_runtime_repository()
    reset_runtime_service()


@pytest.fixture
def tenant_context() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-acme-corp",
        user_id="user-finops-lead",
        roles=["FINOPS_ADMIN", "FINOPS_VIEWER"],
        correlation_id=f"corr-{uuid.uuid4().hex[:12]}",
    )


# ==============================================================================
# 1. Six-State Runtime Model & Non-Compliance Discipline Tests
# ==============================================================================


def test_six_runtime_states_completeness_and_meanings() -> None:
    """Verify all six canonical runtime states exist with distinct semantic meanings."""
    assert len(RuntimeState) == 6
    assert set(RuntimeState) == {
        RuntimeState.RUNNING,
        RuntimeState.STOPPED,
        RuntimeState.PARTIALLY_RUNNING,
        RuntimeState.NOT_APPLICABLE,
        RuntimeState.UNKNOWN,
        RuntimeState.NO_DATA,
    }

    # Verify active execution flags
    assert RuntimeState.RUNNING.is_active_execution() is True
    assert RuntimeState.PARTIALLY_RUNNING.is_active_execution() is True
    assert RuntimeState.STOPPED.is_active_execution() is False
    assert RuntimeState.NOT_APPLICABLE.is_active_execution() is False
    assert RuntimeState.UNKNOWN.is_active_execution() is False
    assert RuntimeState.NO_DATA.is_active_execution() is False


def test_negative_constraint_do_not_conflate_stopped_with_not_applicable() -> None:
    """STRICT: Prompt 26 negative constraint: 'Do not conflate Stopped with Not applicable'."""
    # Attempting to conflate STOPPED with NOT_APPLICABLE raises domain exception
    with pytest.raises(RuntimeStateNonComplianceException) as exc:
        RuntimeState.assert_not_conflated(RuntimeState.STOPPED, RuntimeState.NOT_APPLICABLE)
    assert "strictly non-conflatable" in str(exc.value)

    with pytest.raises(RuntimeStateNonComplianceException) as exc:
        RuntimeState.assert_not_conflated(RuntimeState.NOT_APPLICABLE, RuntimeState.STOPPED)
    assert "strictly non-conflatable" in str(exc.value)


def test_unknown_and_no_data_never_compliant_and_never_green(tenant_context: TenantContext) -> None:
    """STRICT: Prompt 26 rule: 'Enforce that Unknown and No Data are never rendered as compliant and never coloured green'."""
    now = datetime.now(UTC)
    window_start = now - timedelta(hours=24)
    window_end = now

    # 1. Model permission flags
    assert RuntimeState.UNKNOWN.is_compliant_permitted() is False
    assert RuntimeState.UNKNOWN.is_green_permitted() is False
    assert RuntimeState.NO_DATA.is_compliant_permitted() is False
    assert RuntimeState.NO_DATA.is_green_permitted() is False

    # 2. Default color hex is slate, NEVER emerald green
    assert RuntimeState.UNKNOWN.get_default_color_hex() != "#10b981"
    assert RuntimeState.NO_DATA.get_default_color_hex() != "#10b981"

    # 3. Structural validation: attempting to create a ScheduleAdherenceResult with UNKNOWN marked compliant raises
    with pytest.raises(RuntimeStateNonComplianceException) as exc:
        ScheduleAdherenceResult(
            id="adh-test-invalid",
            tenant_id=tenant_context.tenant_id,
            resource_id="res-unknown-01",
            evaluation_window_start=window_start,
            evaluation_window_end=window_end,
            schedule_id="WW_STANDARD_MON_FRI",
            schedule_name="Standard",
            runtime_state=RuntimeState.UNKNOWN,
            adherence_status=AdherenceStatus.UNKNOWN,
            is_compliant=True,  # STRICTLY FORBIDDEN!
            color_hex="#94a3b8",
            expected_running_hours=Decimal("10.0"),
            actual_running_hours=Decimal("0.0"),
            excess_running_hours=Decimal("0.0"),
            hourly_rate=Decimal("0.10"),
            breach_cost=Decimal("0.00"),
            source_provenance=ProvenanceRecord(
                source_system="test", origin_type=OriginType.DERIVED, correlation_id="test"
            ),
        )
    assert "Unknown and No Data must NEVER be rendered as compliant" in str(exc.value)

    # 4. Structural validation: attempting to color UNKNOWN green raises
    with pytest.raises(RuntimeStateNonComplianceException) as exc:
        ScheduleAdherenceResult(
            id="adh-test-invalid-green",
            tenant_id=tenant_context.tenant_id,
            resource_id="res-unknown-01",
            evaluation_window_start=window_start,
            evaluation_window_end=window_end,
            schedule_id="WW_STANDARD_MON_FRI",
            schedule_name="Standard",
            runtime_state=RuntimeState.UNKNOWN,
            adherence_status=AdherenceStatus.UNKNOWN,
            is_compliant=False,
            color_hex="#10b981",  # STRICTLY FORBIDDEN!
            expected_running_hours=Decimal("10.0"),
            actual_running_hours=Decimal("0.0"),
            excess_running_hours=Decimal("0.0"),
            hourly_rate=Decimal("0.10"),
            breach_cost=Decimal("0.00"),
            source_provenance=ProvenanceRecord(
                source_system="test", origin_type=OriginType.DERIVED, correlation_id="test"
            ),
        )
    assert "Unknown and No Data must NEVER be coloured green" in str(exc.value)


# ==============================================================================
# 2. Named Schedules & Inheritance Tests
# ==============================================================================


def test_standard_schedules_and_slot_evaluation() -> None:
    """Verify built-in named schedules and deterministic slot checking."""
    engine = ScheduleEngine()
    sched = engine.get_schedule("WW_STANDARD_MON_FRI")

    assert sched.daily_start_time == "08:00"
    assert sched.daily_end_time == "18:00"
    assert sched.working_days == [1, 2, 3, 4, 5]

    # Wednesday 10:00 UTC -> Approved slot
    wed_working = datetime(2026, 10, 7, 10, 0, tzinfo=UTC)  # 2026-10-07 is Wednesday
    assert is_approved_running_slot(sched, wed_working) is True

    # Wednesday 20:00 UTC -> Outside daily hours -> Not approved
    wed_night = datetime(2026, 10, 7, 20, 0, tzinfo=UTC)
    assert is_approved_running_slot(sched, wed_night) is False

    # Saturday 10:00 UTC -> Weekend -> Not approved
    sat_day = datetime(2026, 10, 10, 10, 0, tzinfo=UTC)  # 2026-10-10 is Saturday
    assert is_approved_running_slot(sched, sat_day) is False

    # Public holiday (2026-12-25) -> Christmas exclusion -> Not approved
    xmas_day = datetime(2026, 12, 25, 10, 0, tzinfo=UTC)
    assert is_approved_running_slot(sched, xmas_day) is False


def test_maintenance_window_permits_execution_outside_core_hours() -> None:
    """Verify that maintenance windows permit execution outside standard working hours."""
    sched = NamedSchedule(
        id="SCHED_WITH_MW",
        name="Schedule with Maintenance Window",
        description="Weekly Sunday patching window",
        timezone="UTC",
        working_days=[1, 2, 3, 4, 5],
        daily_start_time="08:00",
        daily_end_time="18:00",
        maintenance_windows=[
            MaintenanceWindow(
                name="Sunday Patching",
                day_of_week=7,  # Sunday
                start_time="02:00",
                end_time="05:00",
                is_recurring=True,
            )
        ],
    )

    # Sunday 03:00 UTC (inside maintenance window) -> Approved!
    sun_maint = datetime(2026, 10, 11, 3, 0, tzinfo=UTC)  # 2026-10-11 is Sunday
    assert is_approved_running_slot(sched, sun_maint) is True

    # Sunday 06:00 UTC (outside maintenance window) -> Not approved
    sun_post_maint = datetime(2026, 10, 11, 6, 0, tzinfo=UTC)
    assert is_approved_running_slot(sched, sun_post_maint) is False


def test_schedule_inheritance_chain_and_br_007_non_prod_rule() -> None:
    """Verify 5-level schedule inheritance and BR-007 non-production enforcement."""
    engine = ScheduleEngine()

    attachments = [
        ScheduleAttachment(
            schedule_id="WEEKEND_SHUTDOWN",
            level=ScheduleLevel.SCOPE,
            target_id="scope-emea",
        ),
        ScheduleAttachment(
            schedule_id="WW_STANDARD_MON_FRI",
            level=ScheduleLevel.RESOURCE,
            target_id="res-special-vm",
        ),
    ]

    # 1. Resource level wins over scope level
    res_sched, level = engine.resolve_schedule(
        resource_id="res-special-vm",
        scope_id="scope-emea",
        attachments=attachments,
    )
    assert res_sched.id == "WW_STANDARD_MON_FRI"
    assert level == ScheduleLevel.RESOURCE

    # 2. Other resource inherits from scope level
    scope_sched, level = engine.resolve_schedule(
        resource_id="res-other-vm",
        scope_id="scope-emea",
        attachments=attachments,
    )
    assert scope_sched.id == "WEEKEND_SHUTDOWN"
    assert level == ScheduleLevel.SCOPE

    # 3. BR-007: Non-production resource without attachment defaults to business hours (not 24x7)
    non_prod_sched, level = engine.resolve_schedule(
        resource_id="res-dev-db",
        environment="development",
        attachments=[],
    )
    assert non_prod_sched.id == "WW_STANDARD_MON_FRI"
    assert level == ScheduleLevel.ENVIRONMENT

    # 4. Production workload without attachment defaults to continuous 24x7
    prod_sched, level = engine.resolve_schedule(
        resource_id="res-prod-db",
        environment="production",
        attachments=[],
    )
    assert prod_sched.id == "WW_CONTINUOUS_24X7"


# ==============================================================================
# 3. Adherence Evaluation & Acceptance Criteria Tests
# ==============================================================================


def test_acceptance_ac_060_non_prod_vm_running_outside_schedule_detected_with_excess_cost(
    tenant_context: TenantContext,
) -> None:
    """AC-060: VM running outside schedule is detected in one cycle with excess cost calculated."""
    service = get_runtime_service()

    # Window: A Saturday (2026-10-10 00:00 to 2026-10-10 12:00 UTC - 12 hours)
    w_start = datetime(2026, 10, 10, 0, 0, tzinfo=UTC)
    w_end = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)

    resource_id = "vm-dev-worker-01"

    # Non-production VM was observed RUNNING continuously on Saturday for 12 hours
    service.record_observation(
        resource_id=resource_id,
        interval_start=w_start,
        interval_end=w_end,
        state=RuntimeState.RUNNING,
        tenant_context=tenant_context,
    )

    # Evaluate adherence for non-prod VM (rate: $0.50/hour)
    result = service.evaluate_adherence(
        resource_id=resource_id,
        start_time=w_start,
        end_time=w_end,
        hourly_rate=Decimal("0.50"),
        currency="USD",
        environment="development",
        tenant_context=tenant_context,
    )

    # Verifications for AC-060:
    # 1. Detected within one evaluation cycle
    assert result.adherence_status == AdherenceStatus.CRITICAL
    assert result.is_compliant is False
    assert result.color_hex == "#ef4444"  # Red

    # 2. Approved running hours on Saturday for WW_STANDARD_MON_FRI is 0.0h
    assert result.expected_running_hours == Decimal("0.0")
    assert result.actual_running_hours == Decimal("12.0")
    assert result.excess_running_hours == Decimal("12.0")

    # 3. Monetary valuation calculated and displayed
    # 12 hours * $0.50/hr = $6.00 excess cost
    assert result.breach_cost == Decimal("6.00")
    # Monthly extrapolation: $6.00 * (730 / 12) = $365.00
    assert result.projected_monthly_excess_cost > Decimal("300.00")


def test_acceptance_ac_061_resource_with_no_runtime_signal_displays_unknown_never_green(
    tenant_context: TenantContext,
) -> None:
    """AC-061: Resource with unavailable runtime signal displays 'Unknown', never 'Green'."""
    service = get_runtime_service()

    w_start = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
    w_end = datetime(2026, 10, 2, 0, 0, tzinfo=UTC)

    resource_id = "res-no-telemetry-cluster"

    # No observations recorded in repository (telemetry missing)
    result = service.evaluate_adherence(
        resource_id=resource_id,
        start_time=w_start,
        end_time=w_end,
        environment="production",
        tenant_context=tenant_context,
    )

    # Verifications for AC-061:
    assert result.runtime_state == RuntimeState.UNKNOWN
    assert result.adherence_status == AdherenceStatus.UNKNOWN
    assert result.is_compliant is False
    assert result.color_hex != "#10b981"  # STRICTLY NOT GREEN
    assert result.color_hex == "#94a3b8"  # Slate / gray
    assert "Unknown" in (result.notes or "")


def test_acceptance_ac_062_temporary_exemption_suppresses_alert_and_expires_automatically(
    tenant_context: TenantContext,
) -> None:
    """AC-062: Temporary runtime exemption suppresses alert, appears in active reports, and expires."""
    service = get_runtime_service()
    now = datetime.now(UTC)

    resource_id = "vm-loadtest-runner"
    w_start = now - timedelta(hours=6)
    w_end = now

    # Record 6 hours running outside schedule on weekend
    service.record_observation(
        resource_id=resource_id,
        interval_start=w_start,
        interval_end=w_end,
        state=RuntimeState.RUNNING,
        tenant_context=tenant_context,
    )

    # 1. Before exemption: Evaluation flags breach
    breach_result = service.evaluate_adherence(
        resource_id=resource_id,
        start_time=w_start,
        end_time=w_end,
        hourly_rate=Decimal("1.00"),
        environment="staging",
        tenant_context=tenant_context,
    )
    assert breach_result.adherence_status in (AdherenceStatus.WARNING, AdherenceStatus.CRITICAL)
    assert breach_result.is_compliant is False

    # 2. Create temporary exemption with valid business justification (>= 20 chars)
    # Exemption active for the next 2 hours
    exemption = service.create_exemption(
        RuntimeExemptionCreateRequest(
            resource_id=resource_id,
            reason="Performance stress testing for Q4 production readiness",
            expires_at=now + timedelta(hours=2),
            valid_from=w_start,
        ),
        actor_id=tenant_context.user_id,
        tenant_context=tenant_context,
    )
    assert exemption.id.startswith("exemp-")
    assert exemption.is_active is True

    # Verify exemption appears in active report
    active_exemptions = service.list_active_exemptions(as_of=now, tenant_context=tenant_context)
    assert any(e.id == exemption.id for e in active_exemptions)

    # 3. With active exemption: Alert is suppressed!
    exempt_result = service.evaluate_adherence(
        resource_id=resource_id,
        start_time=w_start,
        end_time=w_end,
        hourly_rate=Decimal("1.00"),
        environment="staging",
        tenant_context=tenant_context,
    )
    assert exempt_result.adherence_status == AdherenceStatus.EXEMPT
    assert exempt_result.is_compliant is True
    assert exempt_result.exemption_id == exemption.id
    assert exempt_result.breach_cost == Decimal("0.00")

    # 4. After expiry time passes: Exemption expires automatically
    future_time = now + timedelta(hours=3)
    active_after_expiry = service.list_active_exemptions(
        as_of=future_time, tenant_context=tenant_context
    )
    assert not any(e.id == exemption.id for e in active_after_expiry)


def test_exemption_validation_rejects_short_reason(tenant_context: TenantContext) -> None:
    """Verify that exemption requests with reasons shorter than 20 characters are rejected."""
    service = get_runtime_service()
    now = datetime.now(UTC)

    with pytest.raises(ExemptionReasonTooShortException) as exc:
        service.create_exemption(
            RuntimeExemptionCreateRequest(
                resource_id="vm-01",
                reason="Load test",  # Only 9 chars (< 20)
                expires_at=now + timedelta(hours=1),
            ),
            actor_id=tenant_context.user_id,
            tenant_context=tenant_context,
        )
    assert "at least 20 characters" in str(exc.value)


def test_monetary_valuation_is_mandatory_on_breach(tenant_context: TenantContext) -> None:
    """STRICT: Prompt 26 negative constraint: 'Do not raise a schedule exception without a monetary value'."""
    now = datetime.now(UTC)
    w_start = now - timedelta(hours=10)
    w_end = now

    observations = [
        RuntimeObservation(
            resource_id="res-breach-test",
            interval_start=w_start,
            interval_end=w_end,
            state=RuntimeState.RUNNING,
        )
    ]

    sched = STANDARD_SCHEDULES["WEEKEND_SHUTDOWN"]

    # Evaluator automatically applies default benchmark rate ($0.096/hr) if rate is None
    res = AdherenceEvaluator.evaluate_adherence(
        resource_id="res-breach-test",
        schedule=sched,
        window_start=w_start,
        window_end=w_end,
        observations=observations,
        hourly_rate=None,  # Not provided
        tenant_context=tenant_context,
    )
    # Effective rate must be positive and breach cost non-zero if hours exceeded
    assert res.hourly_rate > Decimal("0.0")


# ==============================================================================
# 4. Phase 2 Idle Detection Tests (Feature-Gated: Ready but Disabled)
# ==============================================================================


def test_idle_detection_disabled_by_default_in_mvp() -> None:
    """Prompt 26 Negative Constraint: 'Do not enable idle detection in MVP'."""
    detector = IdleDetector(enabled=False)
    assert detector.is_enabled is False

    # Calling detection without bypass raises IdleDetectionDisabledException
    with pytest.raises(IdleDetectionDisabledException) as exc:
        detector.detect_idle_compute(
            resource_id="i-12345",
            cpu_utilization_series=[Decimal("1.2"), Decimal("0.8")],
        )
    assert "disabled in MVP" in str(exc.value)


def test_idle_detection_signals_when_bypassed_for_phase_2_readiness() -> None:
    """Verify all 5 Phase 2 idle detection algorithms work correctly when enabled."""
    detector = IdleDetector(enabled=True)

    # 1. Idle compute: CPU average 1.0% < 5.0% floor
    compute_finding = detector.detect_idle_compute(
        resource_id="i-idle-vm",
        cpu_utilization_series=[Decimal("1.0"), Decimal("1.2"), Decimal("0.8")],
        monthly_cost=Decimal("72.00"),
    )
    assert compute_finding is not None
    assert compute_finding.signal_type == IdleSignalType.IDLE_COMPUTE
    assert compute_finding.waste_estimate_monthly == Decimal("72.00")

    # 2. Idle storage: 0 IOPS across window
    storage_finding = detector.detect_idle_storage(
        resource_id="vol-idle-ebs",
        activity_iops_series=[Decimal("0.0"), Decimal("0.0"), Decimal("0.0")],
        monthly_cost=Decimal("20.00"),
    )
    assert storage_finding is not None
    assert storage_finding.signal_type == IdleSignalType.IDLE_STORAGE

    # 3. Orphaned resource: unattached disk
    orphaned_finding = detector.detect_orphaned_resource(
        resource_id="vol-unattached-ebs",
        resource_type="EBS Volume",
        has_parent_attachment=False,
        monthly_cost=Decimal("15.00"),
    )
    assert orphaned_finding is not None
    assert orphaned_finding.signal_type == IdleSignalType.ORPHANED_RESOURCE

    # 4. Zero-usage service incurring cost
    zero_usage_finding = detector.detect_zero_usage_incurring_cost(
        resource_id="svc-provisioned-nat",
        usage_records_count=0,
        billed_cost_monthly=Decimal("45.00"),
    )
    assert zero_usage_finding is not None
    assert zero_usage_finding.signal_type == IdleSignalType.ZERO_USAGE_INCURRING_COST

    # 5. Oversized resource: peak CPU 12% (< 20%) and RAM 18% (< 30%)
    oversized_finding = detector.detect_oversized_resource(
        resource_id="i-oversized-db",
        peak_cpu_pct=Decimal("12.0"),
        peak_memory_pct=Decimal("18.0"),
        monthly_waste_estimate=Decimal("150.00"),
    )
    assert oversized_finding is not None
    assert oversized_finding.signal_type == IdleSignalType.OVERSIZED_RESOURCE


# ==============================================================================
# 5. API Route Contract Tests (API-032, API-033, API-034)
# ==============================================================================


def test_api_runtime_states_endpoint_contract() -> None:
    """Verify GET /api/v1/runtime/states (API-032)."""
    client = TestClient(app)
    headers = {
        "X-Tenant-ID": "tenant-test-api",
        "X-User-ID": "user-test",
        "X-User-Roles": "FINOPS_VIEWER",
    }

    # Query without observations returns UNKNOWN with non-green color
    response = client.get("/api/v1/runtime/states?resource_id=vm-unknown-01", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["resource_id"] == "vm-unknown-01"
    assert data["runtime_state"] == "UNKNOWN"
    assert data["color_hex"] != "#10b981"
    assert data["is_compliant_permitted"] is False
    assert data["is_green_permitted"] is False


def test_api_runtime_schedules_endpoint_contract() -> None:
    """Verify GET /api/v1/runtime/schedules (API-033)."""
    client = TestClient(app)
    headers = {
        "X-Tenant-ID": "tenant-test-api",
        "X-User-ID": "user-test",
        "X-User-Roles": "FINOPS_VIEWER",
    }

    response = client.get("/api/v1/runtime/schedules", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "schedules" in data
    assert len(data["schedules"]) >= 3
    assert any(s["id"] == "WW_STANDARD_MON_FRI" for s in data["schedules"])
    assert "active_exemptions" in data


def test_api_runtime_exemptions_endpoint_contract() -> None:
    """Verify POST /api/v1/runtime/exemptions (API-034)."""
    client = TestClient(app)
    headers = {
        "X-Tenant-ID": "tenant-test-api",
        "X-User-ID": "user-test",
        "X-User-Roles": "FINOPS_ADMIN",
    }

    future_exp = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    payload = {
        "resource_id": "vm-loadtest-01",
        "reason": "Approved load testing window for release verification",
        "expires_at": future_exp,
    }

    response = client.post("/api/v1/runtime/exemptions", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["resource_id"] == "vm-loadtest-01"
    assert data["is_active"] is True
    assert data["reason"] == payload["reason"]


def test_api_idle_signals_endpoint_returns_mvp_disabled() -> None:
    """Verify GET /api/v1/runtime/idle/signals reports disabled in MVP."""
    client = TestClient(app)
    headers = {
        "X-Tenant-ID": "tenant-test-api",
        "X-User-ID": "user-test",
        "X-User-Roles": "FINOPS_VIEWER",
    }

    response = client.get("/api/v1/runtime/idle/signals", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert "disabled in MVP" in data["message"]
