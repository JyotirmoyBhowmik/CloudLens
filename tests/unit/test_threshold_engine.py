"""Comprehensive Unit and Acceptance Tests for Threshold Engine & Anti-Flapping (Prompt 27).

Verifies:
- Prompt 27: Six states (NORMAL, WARNING, HIGH, CRITICAL, INFORMATIONAL, UNKNOWN/NO DATA).
- Prompt 27: Ten threshold bases.
- Prompt 27: Contiguous and non-overlapping band definitions; rejected at save time if not.
- Prompt 27: Five-tier precedence resolution with explicit source disclosure (AC-064 / FR-262).
- Prompt 27: Anti-flapping discipline:
  * Dwell time: requires configured consecutive cycles before publishing state change.
  * Asymmetric hysteresis: entry vs exit boundaries suppress oscillation.
  * Cool-down period (AC-063): value oscillating around boundary produces at most 1 alert in cool-down.
  * Storm grouping: scope-level grouping when child transitions exceed storm threshold.
  * Data-quality gate: missing data produces data-quality signal, never a threshold breach.
- Prompt 27: Idempotency (AC-065): re-running evaluation on unchanged data produces identical state.
- Prompt 27: Overrides mechanism (temporary with reason >= 20 chars & expiry; administrative).
- Prompt 27: Phase 2 preview capability gated behind ENABLE_THRESHOLD_PREVIEW = False.
- API-035, API-036 contract endpoints and error mapping.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.models.exceptions import (
    BandDiscontinuityException,
    BandOverlapException,
    ThresholdOverrideReasonTooShortException,
    ThresholdPreviewDisabledException,
)
from domain.tenant.context import TenantContext
from domain.thresholds.defaults import (
    create_configurable_budget_bands,
    create_tenant_default_budget_rule,
)
from domain.thresholds.evaluator import ThresholdEvaluator
from domain.thresholds.models import (
    ThresholdBandDefinition,
    ThresholdBasis,
    ThresholdEvaluateRequest,
    ThresholdEvaluationResult,
    ThresholdOverride,
    ThresholdRule,
    ThresholdSourceType,
    ThresholdState,
    validate_contiguous_non_overlapping_bands,
)
from domain.thresholds.precedence import PrecedenceResolver, ResolvedThreshold
from domain.thresholds.preview import (
    HistoricalDataPoint,
    simulate_threshold_rule,
)
from domain.thresholds.repository import (
    reset_threshold_repository,
)
from domain.thresholds.service import (
    get_threshold_service,
    reset_threshold_service,
)


@pytest.fixture(autouse=True)
def reset_threshold_state() -> None:
    """Resets repository and service singletons before each test."""
    reset_threshold_repository()
    reset_threshold_service()


@pytest.fixture
def tenant_context() -> TenantContext:
    """Fixture providing a standard authenticated TenantContext."""
    return TenantContext(
        tenant_id="tenant-finops-01",
        user_id="user-lead-01",
        roles=["OPERATOR", "FINOPS_ANALYST"],
        correlation_id=f"corr-{uuid.uuid4().hex[:12]}",
    )


# ==============================================================================
# 1. Six States & Ten Bases Verification
# ==============================================================================


class TestThresholdStatesAndBases:
    """Validates the six states and ten bases defined in Prompt 27."""

    def test_six_states_colors_and_classifications(self) -> None:
        """Verifies Prompt 27: Normal (green), Warning (amber), High (orange), Critical (red), Informational (blue), Unknown (grey)."""
        assert ThresholdState.NORMAL.get_color_hex() == "#10b981"
        assert ThresholdState.WARNING.get_color_hex() == "#f59e0b"
        assert ThresholdState.HIGH.get_color_hex() == "#f97316"
        assert ThresholdState.CRITICAL.get_color_hex() == "#ef4444"
        assert ThresholdState.INFORMATIONAL.get_color_hex() == "#3b82f6"
        assert ThresholdState.UNKNOWN.get_color_hex() == "#94a3b8"

        # Breach classifications
        assert ThresholdState.NORMAL.is_breach() is False
        assert ThresholdState.INFORMATIONAL.is_breach() is False
        assert ThresholdState.UNKNOWN.is_breach() is False
        assert ThresholdState.WARNING.is_breach() is True
        assert ThresholdState.HIGH.is_breach() is True
        assert ThresholdState.CRITICAL.is_breach() is True

        # Compliance
        assert ThresholdState.NORMAL.is_compliant() is True
        assert ThresholdState.INFORMATIONAL.is_compliant() is True
        assert ThresholdState.UNKNOWN.is_compliant() is False
        assert ThresholdState.CRITICAL.is_compliant() is False

    def test_ten_threshold_bases_defined(self) -> None:
        """Verifies Prompt 27: all ten threshold bases are supported."""
        expected_bases = {
            "ABSOLUTE_VALUE",
            "PERCENTAGE",
            "BUDGET_UTILISATION",
            "FORECAST",
            "RUNTIME",
            "VOLUME",
            "GROWTH_PERCENTAGE",
            "VARIANCE_FROM_BASELINE",
            "HISTORICAL_AVERAGE",
            "SEASONAL_BASELINE",
            "QUOTA_HEADROOM",
        }
        actual_bases = {b.value for b in ThresholdBasis}
        assert expected_bases == actual_bases


# ==============================================================================
# 2. Band Validation & Configurability
# ==============================================================================


class TestBandValidation:
    """Verifies Prompt 27: bands are contiguous and non-overlapping, rejected at save time if not."""

    def test_valid_contiguous_non_overlapping_bands(self) -> None:
        """Validates that valid bands pass without error."""
        bands = create_configurable_budget_bands(
            normal_upper=Decimal("70.0"),
            warning_upper=Decimal("90.0"),
            high_upper=Decimal("100.0"),
        )
        validate_contiguous_non_overlapping_bands(bands)

    def test_reject_overlapping_bands(self) -> None:
        """Verifies BandOverlapException when upper bound exceeds subsequent lower bound."""
        bands = [
            ThresholdBandDefinition(
                state=ThresholdState.NORMAL,
                name="Normal",
                lower_bound=Decimal("0"),
                upper_bound=Decimal("75"),  # overlaps next band starting at 70
            ),
            ThresholdBandDefinition(
                state=ThresholdState.WARNING,
                name="Warning",
                lower_bound=Decimal("70"),
                upper_bound=Decimal("90"),
            ),
        ]
        with pytest.raises(BandOverlapException) as exc_info:
            validate_contiguous_non_overlapping_bands(bands)
        assert "overlap" in str(exc_info.value).lower()

    def test_reject_gap_discontinuous_bands(self) -> None:
        """Verifies BandDiscontinuityException when gap exists between bands."""
        bands = [
            ThresholdBandDefinition(
                state=ThresholdState.NORMAL,
                name="Normal",
                lower_bound=Decimal("0"),
                upper_bound=Decimal("70"),
            ),
            ThresholdBandDefinition(
                state=ThresholdState.WARNING,
                name="Warning",
                lower_bound=Decimal("75"),  # gap between 70 and 75
                upper_bound=Decimal("90"),
            ),
        ]
        with pytest.raises(BandDiscontinuityException) as exc_info:
            validate_contiguous_non_overlapping_bands(bands)
        assert (
            "discontinuity" in str(exc_info.value).lower() or "gap" in str(exc_info.value).lower()
        )

    def test_rule_save_rejects_invalid_bands(self, tenant_context: TenantContext) -> None:
        """Verifies ThresholdRule model validator rejects overlapping bands on instantiation."""
        with pytest.raises(BandOverlapException):
            ThresholdRule(
                tenant_id=tenant_context.tenant_id,
                name="Invalid Overlapping Rule",
                basis=ThresholdBasis.PERCENTAGE,
                bands=[
                    ThresholdBandDefinition(
                        state=ThresholdState.NORMAL,
                        name="Normal",
                        lower_bound=Decimal("0"),
                        upper_bound=Decimal("80"),
                    ),
                    ThresholdBandDefinition(
                        state=ThresholdState.CRITICAL,
                        name="Critical",
                        lower_bound=Decimal("70"),
                        upper_bound=None,
                    ),
                ],
            )


# ==============================================================================
# 3. Precedence Resolution & Source Disclosure (AC-064 / FR-262)
# ==============================================================================


class TestPrecedenceResolution:
    """Verifies Prompt 27 / AC-064: 5-tier resolution and explicit origin disclosure."""

    def test_precedence_hierarchy_and_source_disclosure(
        self, tenant_context: TenantContext
    ) -> None:
        """Verifies Temporary override > Admin override > Local > Nearest ancestor > Tenant default."""
        tenant_default = create_tenant_default_budget_rule(tenant_context.tenant_id)

        # 1. When only tenant default exists -> returns TENANT_DEFAULT
        resolved = PrecedenceResolver.resolve(
            entity_id="res-vm-01",
            basis=ThresholdBasis.BUDGET_UTILISATION,
            scope_id="scope-prod",
            rules=[],
            overrides=[],
            tenant_default_rule=tenant_default,
        )
        assert resolved.source_type == ThresholdSourceType.TENANT_DEFAULT
        assert "Tenant default" in resolved.source_display

        # 2. Add Ancestor Scope Rule -> beats tenant default
        scope_rule = ThresholdRule(
            id="rule-scope-prod",
            tenant_id=tenant_context.tenant_id,
            name="Prod Scope Budget Rule",
            basis=ThresholdBasis.BUDGET_UTILISATION,
            scope_id="scope-prod",
            bands=create_configurable_budget_bands(normal_upper=Decimal("60.0")),
        )
        resolved_scope = PrecedenceResolver.resolve(
            entity_id="res-vm-01",
            basis=ThresholdBasis.BUDGET_UTILISATION,
            scope_id="scope-prod",
            rules=[scope_rule],
            overrides=[],
            tenant_default_rule=tenant_default,
        )
        assert resolved_scope.source_type == ThresholdSourceType.INHERITED_ANCESTOR
        assert "scope-prod" in resolved_scope.source_display

        # 3. Add Local Resource Rule -> beats ancestor
        local_rule = ThresholdRule(
            id="rule-local-vm-01",
            tenant_id=tenant_context.tenant_id,
            name="VM 01 Local Rule",
            basis=ThresholdBasis.BUDGET_UTILISATION,
            resource_id="res-vm-01",
            bands=create_configurable_budget_bands(normal_upper=Decimal("50.0")),
        )
        resolved_local = PrecedenceResolver.resolve(
            entity_id="res-vm-01",
            basis=ThresholdBasis.BUDGET_UTILISATION,
            scope_id="scope-prod",
            rules=[scope_rule, local_rule],
            overrides=[],
            tenant_default_rule=tenant_default,
        )
        assert resolved_local.source_type == ThresholdSourceType.LOCAL
        assert "VM 01 Local Rule" in resolved_local.source_display

        # 4. Add Admin Override -> beats local rule
        admin_ovr = ThresholdOverride(
            id="ovr-admin-01",
            tenant_id=tenant_context.tenant_id,
            target_id="res-vm-01",
            source_type=ThresholdSourceType.ADMIN_OVERRIDE,
            reason="Approved permanent business exception for end-of-year batch jobs.",
            created_by="user-admin",
            approved_by="vp-engineering",
        )
        resolved_admin = PrecedenceResolver.resolve(
            entity_id="res-vm-01",
            basis=ThresholdBasis.BUDGET_UTILISATION,
            scope_id="scope-prod",
            rules=[scope_rule, local_rule],
            overrides=[admin_ovr],
            tenant_default_rule=tenant_default,
        )
        assert resolved_admin.source_type == ThresholdSourceType.ADMIN_OVERRIDE
        assert "ovr-admin-01" in resolved_admin.source_display

        # 5. Add Temporary Override -> beats admin override
        temp_ovr = ThresholdOverride(
            id="ovr-temp-01",
            tenant_id=tenant_context.tenant_id,
            target_id="res-vm-01",
            source_type=ThresholdSourceType.TEMPORARY_OVERRIDE,
            reason="Temporary operational exception during incident remediation window.",
            created_by="oncall-eng",
            expires_at=datetime.now(UTC) + timedelta(hours=4),
        )
        resolved_temp = PrecedenceResolver.resolve(
            entity_id="res-vm-01",
            basis=ThresholdBasis.BUDGET_UTILISATION,
            scope_id="scope-prod",
            rules=[scope_rule, local_rule],
            overrides=[admin_ovr, temp_ovr],
            tenant_default_rule=tenant_default,
        )
        assert resolved_temp.source_type == ThresholdSourceType.TEMPORARY_OVERRIDE
        assert "ovr-temp-01" in resolved_temp.source_display

    def test_expired_temporary_override_auto_reverts(self, tenant_context: TenantContext) -> None:
        """Verifies that expired temporary overrides are ignored and evaluation reverts to underlying rule."""
        tenant_default = create_tenant_default_budget_rule(tenant_context.tenant_id)
        past_time = datetime.now(UTC) - timedelta(hours=2)

        expired_ovr = ThresholdOverride(
            id="ovr-expired-01",
            tenant_id=tenant_context.tenant_id,
            target_id="res-vm-01",
            source_type=ThresholdSourceType.TEMPORARY_OVERRIDE,
            reason="Temporary operational exception that has already expired.",
            created_by="oncall-eng",
            expires_at=past_time,
        )
        assert expired_ovr.is_expired() is True

        resolved = PrecedenceResolver.resolve(
            entity_id="res-vm-01",
            basis=ThresholdBasis.BUDGET_UTILISATION,
            rules=[],
            overrides=[expired_ovr],
            tenant_default_rule=tenant_default,
        )
        # Should bypass expired override and resolve to tenant default
        assert resolved.source_type == ThresholdSourceType.TENANT_DEFAULT


# ==============================================================================
# 4. Overrides Mechanism
# ==============================================================================


class TestThresholdOverrides:
    """Verifies override creation rules, rationale length validation, and temporary expiry."""

    def test_temporary_override_requires_min_20_char_reason(
        self, tenant_context: TenantContext
    ) -> None:
        """Verifies rejection when override reason is too short (< 20 characters)."""
        with pytest.raises(ThresholdOverrideReasonTooShortException):
            ThresholdOverride(
                tenant_id=tenant_context.tenant_id,
                target_id="res-01",
                source_type=ThresholdSourceType.TEMPORARY_OVERRIDE,
                reason="Too short",  # < 20 chars
                created_by="tester",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )

    def test_temporary_override_requires_mandatory_expires_at(
        self, tenant_context: TenantContext
    ) -> None:
        """Verifies temporary overrides without expiry are rejected."""
        with pytest.raises(ValueError, match="mandatory 'expires_at'"):
            ThresholdOverride(
                tenant_id=tenant_context.tenant_id,
                target_id="res-01",
                source_type=ThresholdSourceType.TEMPORARY_OVERRIDE,
                reason="Valid lengthy justification meeting the twenty character threshold requirement.",
                created_by="tester",
                expires_at=None,
            )


# ==============================================================================
# 5. Anti-Flapping Discipline (AC-063 / FR-264)
# ==============================================================================


class TestAntiFlappingDiscipline:
    """Verifies all five anti-flapping controls per Prompt 27 and AC-063."""

    def test_data_quality_gate_missing_data_never_breaches(
        self, tenant_context: TenantContext
    ) -> None:
        """Prompt 27 Negative Constraint: 'Do not let missing data produce a threshold breach'."""
        evaluator = ThresholdEvaluator()
        rule = create_tenant_default_budget_rule(tenant_context.tenant_id)
        resolved = ResolvedThreshold(
            rule=rule,
            bands=rule.bands,
            source_type=ThresholdSourceType.TENANT_DEFAULT,
            source_id=rule.id,
            source_display="Tenant Default",
        )

        result = evaluator.evaluate(
            entity_id="res-dq-01",
            value=None,  # Missing / No Data
            resolved=resolved,
            tenant_context=tenant_context,
        )

        assert result.committed_state == ThresholdState.UNKNOWN
        assert result.evaluated_state == ThresholdState.UNKNOWN
        assert result.is_data_quality_issue is True
        assert result.is_alert_dispatched is False
        assert result.committed_state.is_breach() is False

    def test_dwell_time_requires_configured_consecutive_cycles(
        self, tenant_context: TenantContext
    ) -> None:
        """Prompt 27: 'Do not publish a state on a single evaluation where dwell time applies'."""
        evaluator = ThresholdEvaluator()
        # Rule with dwell = 3 cycles
        rule = create_tenant_default_budget_rule(
            tenant_context.tenant_id,
            dwell_evaluations=3,
        )
        resolved = ResolvedThreshold(
            rule=rule,
            bands=rule.bands,
            source_type=ThresholdSourceType.TENANT_DEFAULT,
            source_id=rule.id,
            source_display="Tenant Default",
        )

        # Baseline: Start in Normal state (50%)
        res0 = evaluator.evaluate(
            entity_id="res-dwell-01",
            value=Decimal("50.0"),
            resolved=resolved,
            tenant_context=tenant_context,
        )
        assert res0.committed_state == ThresholdState.NORMAL

        # Spike to Critical (110%) - Cycle 1: Dwell pending, should hold NORMAL
        res1 = evaluator.evaluate(
            entity_id="res-dwell-01",
            value=Decimal("110.0"),
            resolved=resolved,
            tenant_context=tenant_context,
        )
        assert res1.evaluated_state == ThresholdState.CRITICAL
        assert res1.committed_state == ThresholdState.NORMAL  # Held by dwell
        assert res1.is_flapping_suppressed is True
        assert "Dwell time pending: 1/3" in (res1.suppression_reason or "")

        # Cycle 2: Dwell pending (2/3), still NORMAL
        res2 = evaluator.evaluate(
            entity_id="res-dwell-01",
            value=Decimal("110.0"),
            resolved=resolved,
            tenant_context=tenant_context,
        )
        assert res2.committed_state == ThresholdState.NORMAL
        assert res2.is_flapping_suppressed is True
        assert "Dwell time pending: 2/3" in (res2.suppression_reason or "")

        # Cycle 3: Dwell satisfied (3/3), now committed to CRITICAL
        res3 = evaluator.evaluate(
            entity_id="res-dwell-01",
            value=Decimal("110.0"),
            resolved=resolved,
            tenant_context=tenant_context,
        )
        assert res3.committed_state == ThresholdState.CRITICAL
        assert res3.transition_occurred is True
        assert res3.is_flapping_suppressed is False

    def test_asymmetric_hysteresis_boundary_suppression(self) -> None:
        """Verifies asymmetric exit threshold prevents oscillation when value hovers at boundary."""
        bands = create_configurable_budget_bands(
            normal_upper=Decimal("70.0"),
            hysteresis_pct=Decimal("2.0"),  # exit threshold lower is 68.0
        )
        # 1. Rising to 70.0 enters WARNING
        state1 = ThresholdEvaluator.evaluate_raw_band(
            Decimal("70.5"), bands, current_committed_state=ThresholdState.NORMAL
        )
        assert state1 == ThresholdState.WARNING

        # 2. Value dips slightly below 70.0 (e.g. 69.5) but above 68.0 exit threshold
        state2 = ThresholdEvaluator.evaluate_raw_band(
            Decimal("69.5"), bands, current_committed_state=ThresholdState.WARNING
        )
        # Hysteresis holds WARNING state
        assert state2 == ThresholdState.WARNING

        # 3. Value drops clearly below exit threshold (67.5 < 68.0)
        state3 = ThresholdEvaluator.evaluate_raw_band(
            Decimal("67.5"), bands, current_committed_state=ThresholdState.WARNING
        )
        assert state3 == ThresholdState.NORMAL

    def test_cooldown_suppresses_repeat_alerts_ac063(self, tenant_context: TenantContext) -> None:
        """AC-063: Value oscillating around a boundary produces at most one alert in cool-down."""
        evaluator = ThresholdEvaluator()
        # Cooldown = 3600s
        rule = create_tenant_default_budget_rule(
            tenant_context.tenant_id,
            dwell_evaluations=1,
            cooldown_seconds=3600,
        )
        resolved = ResolvedThreshold(
            rule=rule,
            bands=rule.bands,
            source_type=ThresholdSourceType.TENANT_DEFAULT,
            source_id=rule.id,
            source_display="Tenant Default",
        )

        base_time = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)

        # 1. First breach at 12:00:00 -> Alert dispatched
        res1 = evaluator.evaluate(
            entity_id="res-osc-01",
            value=Decimal("105.0"),
            resolved=resolved,
            evaluated_at=base_time,
            tenant_context=tenant_context,
        )
        assert res1.committed_state == ThresholdState.CRITICAL
        assert res1.is_alert_dispatched is True

        # 2. Value dips to Normal at 12:05:00
        res2 = evaluator.evaluate(
            entity_id="res-osc-01",
            value=Decimal("50.0"),
            resolved=resolved,
            evaluated_at=base_time + timedelta(minutes=5),
            tenant_context=tenant_context,
        )
        assert res2.committed_state == ThresholdState.NORMAL

        # 3. Value breaches again at 12:10:00 (within 3600s cool-down)
        # State transitions to CRITICAL but alert is SUPPRESSED
        res3 = evaluator.evaluate(
            entity_id="res-osc-01",
            value=Decimal("105.0"),
            resolved=resolved,
            evaluated_at=base_time + timedelta(minutes=10),
            tenant_context=tenant_context,
        )
        assert res3.committed_state == ThresholdState.CRITICAL
        assert res3.is_alert_dispatched is False  # Suppressed by cool-down
        assert res3.is_flapping_suppressed is True
        assert "cool-down period" in (res3.suppression_reason or "")

    def test_storm_grouping_suppression(self, tenant_context: TenantContext) -> None:
        """Verifies storm grouping when more than configured child transitions occur in one cycle."""
        evaluator = ThresholdEvaluator()
        # Storm threshold = 5
        rule = create_tenant_default_budget_rule(tenant_context.tenant_id)
        resolved = ResolvedThreshold(
            rule=rule,
            bands=rule.bands,
            source_type=ThresholdSourceType.TENANT_DEFAULT,
            source_id=rule.id,
            source_display="Tenant Default",
        )

        cycle_now = datetime(2026, 10, 1, 14, 0, 0, tzinfo=UTC)
        scope_id = "scope-big-app"

        # Fire 6 simultaneous child entity transitions in same cycle
        results: list[ThresholdEvaluationResult] = []
        for i in range(6):
            child_id = f"child-res-{i:02d}"
            res = evaluator.evaluate(
                entity_id=child_id,
                value=Decimal("105.0"),
                resolved=resolved,
                scope_id=scope_id,
                evaluated_at=cycle_now,
                tenant_context=tenant_context,
            )
            results.append(res)

        # First 5 children get individual alerts dispatched
        for i in range(5):
            assert results[i].is_alert_dispatched is True

        # 6th child exceeds threshold of 5 -> storm suppressed
        assert results[5].is_alert_dispatched is False
        assert results[5].is_flapping_suppressed is True
        assert "storm suppressed" in (results[5].suppression_reason or "").lower()


# ==============================================================================
# 6. Idempotency (AC-065 / FR-266)
# ==============================================================================


class TestThresholdIdempotency:
    """Verifies AC-065: Re-running evaluation on unchanged data produces identical state."""

    def test_idempotent_evaluation_replay(self, tenant_context: TenantContext) -> None:
        """Evaluates same entity with identical value repeatedly; produces same state without alerts."""
        service = get_threshold_service()
        req = ThresholdEvaluateRequest(
            entity_id="res-idem-01",
            value=Decimal("75.0"),
            basis=ThresholdBasis.BUDGET_UTILISATION,
        )

        # Run 1
        res1 = service.evaluate_entity(req, tenant_context=tenant_context)
        assert res1.committed_state == ThresholdState.WARNING
        assert res1.is_alert_dispatched is True

        # Run 2 with exact same input
        res2 = service.evaluate_entity(req, tenant_context=tenant_context)
        assert res2.committed_state == res1.committed_state
        assert res2.evaluated_state == res1.evaluated_state
        assert res2.transition_occurred is False
        assert res2.is_alert_dispatched is False  # No duplicate alert


# ==============================================================================
# 7. Phase 2 Preview Capability
# ==============================================================================


class TestThresholdPreviewCapability:
    """Verifies preview simulation flag gating (Prompt 27 Negative Constraint)."""

    def test_preview_raises_disabled_exception_by_default(
        self, tenant_context: TenantContext
    ) -> None:
        """Prompt 27: Simulation against historical series flag-gated behind ENABLE_THRESHOLD_PREVIEW = False."""
        rule = create_tenant_default_budget_rule(tenant_context.tenant_id)
        pts = [
            HistoricalDataPoint(
                timestamp=datetime(2026, 10, 1, 10, 0, 0, tzinfo=UTC),
                value=Decimal("50.0"),
            )
        ]

        # By default, preview is disabled
        with pytest.raises(ThresholdPreviewDisabledException):
            simulate_threshold_rule(
                rule=rule,
                data_points=pts,
                tenant_context=tenant_context,
                override_enabled_flag=False,
            )

    def test_preview_simulation_runs_when_enabled(self, tenant_context: TenantContext) -> None:
        """Verifies simulation runs properly when explicitly enabled."""
        rule = create_tenant_default_budget_rule(tenant_context.tenant_id)
        pts = [
            HistoricalDataPoint(
                timestamp=datetime(2026, 10, 1, 10, 0, 0, tzinfo=UTC),
                value=Decimal("50.0"),
            ),
            HistoricalDataPoint(
                timestamp=datetime(2026, 10, 1, 11, 0, 0, tzinfo=UTC),
                value=Decimal("95.0"),
            ),
            HistoricalDataPoint(
                timestamp=datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC),
                value=Decimal("110.0"),
            ),
        ]

        result = simulate_threshold_rule(
            rule=rule,
            data_points=pts,
            tenant_context=tenant_context,
            override_enabled_flag=True,
        )

        assert result.total_data_points == 3
        assert result.total_transitions == 2
        assert len(result.steps) == 3


# ==============================================================================
# 8. API Contract Endpoints (API-035, API-036)
# ==============================================================================


class TestThresholdAPIContracts:
    """Verifies FastAPI endpoints for API-035, API-036, overrides, and evaluation."""

    @pytest.fixture
    def auth_headers(self) -> dict[str, str]:
        from domain.identity.service import get_identity_service
        token = get_identity_service().token_engine.issue_access_token(
            user_id="usr-api-01",
            tenant_id="tenant-api-01",
            email="api01@cloudlens.internal",
            session_id="sess-test-threshold",
            token_family_id="fam-test-threshold",
            roles=["ADMIN"],
            permissions=["*"],
            ttl_seconds=3600,
        )
        return {"Authorization": f"Bearer {token}", "X-Tenant-ID": "tenant-api-01"}

    def test_api_035_list_threshold_rules(self, auth_headers: dict[str, str]) -> None:
        """API-035: GET /api/v1/thresholds returns configured threshold rules."""
        client = TestClient(app)
        get_threshold_service().repository.ensure_tenant_default_rules(
            tenant_context=TenantContext(tenant_id="tenant-api-01")
        )
        response = client.get(
            "/api/v1/thresholds",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1  # Auto-seeded default rule exists

    def test_api_036_create_threshold_rule(self, auth_headers: dict[str, str]) -> None:
        """API-036: POST /api/v1/thresholds creates rule with validated bands."""
        client = TestClient(app)
        payload = {
            "name": "Production CPU Absolute Limit",
            "description": "Monitors absolute CPU core utilization",
            "basis": "ABSOLUTE_VALUE",
            "bands": [
                {
                    "state": "NORMAL",
                    "name": "Normal Core Range",
                    "lower_bound": "0.0",
                    "upper_bound": "16.0",
                },
                {
                    "state": "WARNING",
                    "name": "High Core Range",
                    "lower_bound": "16.0",
                    "upper_bound": "32.0",
                },
                {
                    "state": "CRITICAL",
                    "name": "Critical Core Saturation",
                    "lower_bound": "32.0",
                    "upper_bound": None,
                },
            ],
            "unit": "Cores",
        }
        response = client.post(
            "/api/v1/thresholds",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 201
        created = response.json()
        assert created["name"] == "Production CPU Absolute Limit"
        assert len(created["bands"]) == 3

    def test_api_036_rejects_overlapping_bands(self, auth_headers: dict[str, str]) -> None:
        """Verifies API-036 returns 422/400 error when bands overlap."""
        client = TestClient(app)
        payload = {
            "name": "Bad Overlapping Rule",
            "basis": "PERCENTAGE",
            "bands": [
                {
                    "state": "NORMAL",
                    "name": "Normal",
                    "lower_bound": "0.0",
                    "upper_bound": "80.0",
                },
                {
                    "state": "WARNING",
                    "name": "Warning",
                    "lower_bound": "70.0",  # Overlap 70 < 80
                    "upper_bound": "100.0",
                },
            ],
        }
        response = client.post(
            "/api/v1/thresholds",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code in (400, 422)
        err = response.json()
        assert "overlap" in str(err).lower()

    def test_api_evaluate_endpoint(self, auth_headers: dict[str, str]) -> None:
        """POST /api/v1/thresholds/evaluate returns evaluation result with provenance."""
        client = TestClient(app)
        payload = {
            "entity_id": "res-api-vm-01",
            "entity_type": "RESOURCE",
            "value": "85.5",
            "basis": "BUDGET_UTILISATION",
        }
        response = client.post(
            "/api/v1/thresholds/evaluate",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 200
        res = response.json()
        assert res["committed_state"] == "WARNING"
        assert res["color_hex"] == "#f59e0b"
        assert "resolved_source_display" in res
        assert res["source_provenance"]["origin_type"] == "DERIVED"

    def test_api_preview_disabled_in_mvp(self, auth_headers: dict[str, str]) -> None:
        """POST /api/v1/thresholds/preview returns 403 Forbidden in MVP."""
        client = TestClient(app)
        rule = create_tenant_default_budget_rule("tenant-api-01")
        payload = {
            "rule": rule.model_dump(mode="json"),
            "data_points": [
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "value": "50.0",
                }
            ],
        }
        response = client.post(
            "/api/v1/thresholds/preview",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 403
        data = response.json()
        assert data["error_code"] == "THRESHOLD_PREVIEW_DISABLED"
