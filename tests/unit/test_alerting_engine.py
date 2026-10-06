"""Comprehensive Unit and Integration Tests for Alerting Engine and Notifications (Prompt 31).

Enforces:
- Prompt 31 / BBP Section 35: The sixteen canonical alert types.
- BBP Section 35.2: Mandatory empirical evidence attached to every alert.
- Full alert lifecycle: creation, deduplication, acknowledgement, resolution, auto-resolution with dwell time.
- Scope storm grouping: >10 child alerts in a scope aggregated into single grouped alert.
- Recipient routing hierarchy with fallback admin & governance exception.
- Quiet hours, escalation SLAs (high severity never disappears silently), and delivery logging.
- Six inline contextual alert types with UI surfaces and dismissal.
- STRICT NEGATIVE CONSTRAINT: SMS and Voice are forbidden (ChannelNotSupportedException).
- Prompt 13 Item 84: 100% TenantContext validation and tenant isolation.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from starlette.testclient import TestClient

from api.cloudlens_api.main import app
from domain.alerting.catalogue import (
    get_alert_catalogue_map,
    get_alert_definition_by_id,
    get_alert_definition_by_type,
    get_default_alert_catalogue,
)
from domain.alerting.channels.email import EmailChannelAdapter
from domain.alerting.channels.in_app import InAppChannelAdapter
from domain.alerting.channels.registry import ChannelAdapterRegistry
from domain.alerting.channels.webhook import WebhookChannelAdapter
from domain.alerting.models import (
    AlertEntity,
    AlertEvidence,
    QuietHoursConfig,
    RecipientSubscription,
)
from domain.alerting.repository import AlertRepository
from domain.alerting.router import RecipientRouter
from domain.alerting.service import AlertService, reset_alert_service
from domain.audit.service import get_audit_service, reset_audit_service
from domain.models.enums import (
    AlertLifecycleStatus,
    AlertSeverity,
    AlertType,
    ContextualAlertType,
    ContextualAlertVisibility,
    DeliveryOutcome,
    EscalationState,
    NotificationChannel,
)
from domain.models.exceptions import (
    ChannelNotSupportedException,
    MissingAlertEvidenceException,
    MissingTenantContextException,
)
from domain.tenant.context import TenantContext

# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture(autouse=True)
def cleanup_alerting_state():
    """Resets singleton service state between test runs."""
    reset_alert_service()
    reset_audit_service()
    yield
    reset_alert_service()
    reset_audit_service()


@pytest.fixture
def tenant_ctx() -> TenantContext:
    """Standard authenticated tenant context."""
    return TenantContext(
        tenant_id="tenant-corp-alpha",
        user_id="user-finops-lead",
        correlation_id=str(uuid.uuid4()),
    )


@pytest.fixture
def other_tenant_ctx() -> TenantContext:
    """Secondary tenant context for isolation testing."""
    return TenantContext(
        tenant_id="tenant-corp-beta",
        user_id="user-beta-admin",
        correlation_id=str(uuid.uuid4()),
    )


@pytest.fixture
def alert_service() -> AlertService:
    """Fresh AlertService instance with clean in-memory state."""
    repo = AlertRepository()
    router = RecipientRouter()
    registry = ChannelAdapterRegistry()
    audit = get_audit_service()
    return AlertService(repository=repo, router=router, registry=registry, audit_service=audit)


def create_sample_evidence(summary: str = "Metric breached threshold") -> AlertEvidence:
    """Helper to build valid empirical evidence."""
    return AlertEvidence(
        summary=summary,
        datapoints=[{"timestamp": "2026-10-02T10:00:00Z", "value": 1250.0, "threshold": 1000.0}],
        records=[{"id": "rec-1", "cost": 1250.0}],
        context={"scope_id": "sub-123", "currency": "USD"},
    )


# ==============================================================================
# 1. Sixteen Canonical Alert Types Tests
# ==============================================================================


class TestTwentyCanonicalAlertTypes:
    """Validates that all twenty canonical alert types (AL-01 to AL-20) are fully supported (Prompt 31B, FR-560)."""

    @pytest.mark.parametrize(
        "alert_type",
        [
            AlertType.BUDGET_THRESHOLD,
            AlertType.FORECAST_BUDGET_BREACH,
            AlertType.RUNTIME_BREACH,
            AlertType.USAGE_THRESHOLD,
            AlertType.UNEXPECTED_COST_INCREASE,
            AlertType.MISSING_DATA,
            AlertType.STALE_CONNECTOR,
            AlertType.CONNECTOR_FAILURE,
            AlertType.RESOURCE_WITHOUT_OWNER,
            AlertType.RESOURCE_WITHOUT_MANDATORY_TAGS,
            AlertType.DEPENDENCY_CHANGE,
            AlertType.NEW_SERVICE_DETECTED,
            AlertType.DELETED_SERVICE,
            AlertType.UNEXPECTED_RESOURCE_CREATION,
            AlertType.CREDENTIAL_EXPIRING,
            AlertType.RECONCILIATION_FAILED,
            # Extended Addendum B alert types (Prompt 31B)
            AlertType.QUOTA_HEADROOM_LOW,
            AlertType.COMMITMENT_EXPIRING,
            AlertType.PROVISIONING_REQUEST_DECIDED,
            AlertType.ANALYTICAL_EXTRACT_LATE_OR_EMPTY,
        ],
    )
    def test_all_twenty_alert_types_can_be_raised_with_evidence(
        self,
        alert_service: AlertService,
        tenant_ctx: TenantContext,
        alert_type: AlertType,
    ):
        """Every one of the 20 alert types can be raised with attached empirical evidence."""
        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=alert_type,
            severity=AlertSeverity.WARNING,
            title=f"Test alert for {alert_type.value}",
            description=f"Automated verification of {alert_type.value}",
            source="test_suite",
            scope_id="scope-primary",
            evidence=create_sample_evidence(f"Empirical data for {alert_type.value}"),
        )
        raised = alert_service.raise_alert(alert, tenant_context=tenant_ctx)
        assert raised.id is not None
        assert raised.alert_type == alert_type
        assert raised.status == AlertLifecycleStatus.ACTIVE
        assert raised.evidence.summary == f"Empirical data for {alert_type.value}"


# ==============================================================================
# 2. Mandatory Evidence Enforcement Tests
# ==============================================================================


class TestMandatoryEvidenceEnforcement:
    """Verifies that alerts without empirical evidence are strictly rejected."""

    def test_missing_evidence_raises_exception_at_model_creation(self, tenant_ctx: TenantContext):
        """Constructing an alert with None evidence raises MissingAlertEvidenceException."""
        with pytest.raises(MissingAlertEvidenceException):
            AlertEntity(
                tenant_id=tenant_ctx.tenant_id,
                alert_type=AlertType.BUDGET_THRESHOLD,
                severity=AlertSeverity.CRITICAL,
                title="Invalid Alert",
                description="Has no evidence",
                source="test",
                evidence=None,  # type: ignore
            )

    def test_empty_evidence_records_and_datapoints_raises_exception(self):
        """Evidence without datapoints, records, or context is rejected."""
        with pytest.raises(MissingAlertEvidenceException):
            AlertEvidence(
                summary="Empty evidence",
                datapoints=[],
                records=[],
                context={},
            )

    def test_empty_evidence_summary_raises_exception(self):
        """Evidence with empty or whitespace summary is rejected."""
        with pytest.raises(MissingAlertEvidenceException):
            AlertEvidence(
                summary="   ",
                datapoints=[{"value": 100}],
            )


# ==============================================================================
# 3. Full Alert Lifecycle & Deduplication Tests
# ==============================================================================


class TestAlertLifecycle:
    """Verifies deduplication, acknowledgement, commenting, and auto-resolution."""

    def test_deduplication_updates_existing_active_alert(
        self,
        alert_service: AlertService,
        tenant_ctx: TenantContext,
    ):
        """Re-raising an active alert with the same fingerprint updates repeat_count and current_value."""
        evidence1 = create_sample_evidence("First breach $1100")
        alert1 = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.BUDGET_THRESHOLD,
            severity=AlertSeverity.WARNING,
            title="Budget Warning",
            description="Exceeded threshold",
            source="budget_engine",
            scope_id="sub-dedup",
            rule_id="rule-b-01",
            current_value=1100.0,
            threshold_value=1000.0,
            evidence=evidence1,
        )
        saved1 = alert_service.raise_alert(alert1, tenant_context=tenant_ctx)
        assert saved1.repeat_count == 1
        assert saved1.current_value == 1100.0

        # Second breach with higher value
        evidence2 = create_sample_evidence("Second breach $1250")
        alert2 = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.BUDGET_THRESHOLD,
            severity=AlertSeverity.WARNING,
            title="Budget Warning",
            description="Exceeded threshold again",
            source="budget_engine",
            scope_id="sub-dedup",
            rule_id="rule-b-01",
            current_value=1250.0,
            threshold_value=1000.0,
            evidence=evidence2,
        )
        saved2 = alert_service.raise_alert(alert2, tenant_context=tenant_ctx)

        # Same entity ID, updated repeat count and value
        assert saved2.id == saved1.id
        assert saved2.repeat_count == 2
        assert saved2.current_value == 1250.0
        assert saved2.evidence.summary == "Second breach $1250"

    def test_acknowledgement_and_resolution_flow(
        self,
        alert_service: AlertService,
        tenant_ctx: TenantContext,
    ):
        """Alert can be acknowledged and manually resolved with actor attribution."""
        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.USAGE_THRESHOLD,
            severity=AlertSeverity.WARNING,
            title="Usage Spike",
            description="CPU > 90%",
            source="usage_engine",
            evidence=create_sample_evidence("CPU at 94%"),
        )
        saved = alert_service.raise_alert(alert, tenant_context=tenant_ctx)

        # 1. Acknowledge
        ack = alert_service.acknowledge_alert(
            saved.id,
            actor="ops-lead@company.com",
            tenant_context=tenant_ctx,
            reason="Investigating worker nodes",
        )
        assert ack.status == AlertLifecycleStatus.ACKNOWLEDGED
        assert ack.acknowledged_by == "ops-lead@company.com"
        assert ack.acknowledgement_reason == "Investigating worker nodes"
        assert ack.acknowledged_at is not None

        # 2. Add comment
        commented = alert_service.add_comment(
            saved.id,
            author="ops-lead@company.com",
            text="Scaled up autoscaler pool",
            tenant_context=tenant_ctx,
        )
        assert len(commented.comments) == 1
        assert commented.comments[0].comment_text == "Scaled up autoscaler pool"

        # 3. Resolve
        res = alert_service.resolve_alert(
            saved.id,
            actor="ops-lead@company.com",
            tenant_context=tenant_ctx,
            reason="Autoscaler rebalanced",
        )
        assert res.status == AlertLifecycleStatus.RESOLVED
        assert res.resolved_by == "ops-lead@company.com"
        assert res.resolution_reason == "Autoscaler rebalanced"
        assert res.resolved_at is not None

    def test_auto_resolution_with_dwell_time(
        self,
        alert_service: AlertService,
        tenant_ctx: TenantContext,
    ):
        """Alert auto-resolves only after condition cleared and dwell time elapsed."""
        now = dt.datetime(2026, 10, 2, 12, 0, 0, tzinfo=dt.UTC)
        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.RUNTIME_BREACH,
            severity=AlertSeverity.WARNING,
            title="Off-hours VM running",
            description="VM running outside schedule",
            source="runtime_engine",
            dwell_time_seconds=300,  # 5 minutes
            evidence=create_sample_evidence("Running at 02:00 AM"),
        )
        saved = alert_service.raise_alert(alert, tenant_context=tenant_ctx)

        # 1. Mark condition cleared at T
        alert_service.mark_condition_cleared(saved.id, tenant_context=tenant_ctx, now=now)

        # 2. Evaluate at T + 2 minutes (dwell time NOT yet met)
        eval_t2 = now + dt.timedelta(minutes=2)
        auto1 = alert_service.evaluate_auto_resolutions(tenant_context=tenant_ctx, now=eval_t2)
        assert len(auto1) == 0

        # Check alert is still ACTIVE
        current = alert_service.get_alert(saved.id, tenant_context=tenant_ctx)
        assert current is not None
        assert current.status == AlertLifecycleStatus.ACTIVE

        # 3. Evaluate at T + 6 minutes (dwell time MET)
        eval_t6 = now + dt.timedelta(minutes=6)
        auto2 = alert_service.evaluate_auto_resolutions(tenant_context=tenant_ctx, now=eval_t6)
        assert len(auto2) == 1
        assert auto2[0].id == saved.id
        assert auto2[0].status == AlertLifecycleStatus.AUTO_RESOLVED
        assert auto2[0].is_auto_resolved is True


# ==============================================================================
# 4. Scope Storm Grouping Tests
# ==============================================================================


class TestScopeStormGrouping:
    """Verifies that >10 alerts in the same scope are grouped into a single alert."""

    def test_more_than_ten_alerts_in_scope_triggers_storm_grouping(
        self,
        alert_service: AlertService,
        tenant_ctx: TenantContext,
    ):
        """Raising 11 alerts for the same scope groups them into a parent grouped alert."""
        scope_id = "scope-storm-test"

        # Raise 10 alerts (within limit)
        for i in range(10):
            alert = AlertEntity(
                tenant_id=tenant_ctx.tenant_id,
                alert_type=AlertType.USAGE_THRESHOLD,
                severity=AlertSeverity.WARNING,
                title=f"Disk {i} high usage",
                description="High IOPS",
                source="usage_engine",
                scope_id=scope_id,
                affected_resource_id=f"disk-{i}",
                evidence=create_sample_evidence(f"Disk {i} usage at 95%"),
            )
            alert_service.raise_alert(alert, tenant_context=tenant_ctx, auto_dispatch=False)

        # Verify 10 active alerts exist
        active = alert_service.repository.list_active_by_scope(scope_id, tenant_context=tenant_ctx)
        assert len(active) == 10

        # Raise 11th alert -> triggers scope storm grouping!
        storm_alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.USAGE_THRESHOLD,
            severity=AlertSeverity.WARNING,
            title="Disk 10 high usage",
            description="High IOPS",
            source="usage_engine",
            scope_id=scope_id,
            affected_resource_id="disk-10",
            evidence=create_sample_evidence("Disk 10 usage at 95%"),
        )
        grouped_result = alert_service.raise_alert(
            storm_alert, tenant_context=tenant_ctx, auto_dispatch=False
        )

        # Parent grouped alert created
        assert grouped_result.alert_type == AlertType.SCOPE_STORM_GROUPED
        assert grouped_result.severity == AlertSeverity.HIGH
        assert len(grouped_result.child_alert_ids) == 11
        assert "Scope Alert Storm" in grouped_result.title

        # All 11 children are marked as GROUPED
        for child_id in grouped_result.child_alert_ids:
            child = alert_service.get_alert(child_id, tenant_context=tenant_ctx)
            assert child is not None
            assert child.status == AlertLifecycleStatus.GROUPED
            assert child.grouped_parent_id == grouped_result.id


# ==============================================================================
# 5. Recipient Routing & Governance Exception Tests
# ==============================================================================


class TestRecipientRoutingAndGovernanceException:
    """Verifies 4-stage recipient resolution hierarchy and governance exception fallback."""

    def test_stage_1_resolves_resource_owner_tag(
        self,
        alert_service: AlertService,
        tenant_ctx: TenantContext,
    ):
        """Resource with owner tag routes directly to resource owner."""
        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.RESOURCE_WITHOUT_MANDATORY_TAGS,
            severity=AlertSeverity.WARNING,
            title="Missing Tags",
            description="Resource missing env tag",
            source="policy_engine",
            affected_resource_id="vm-app-01",
            evidence=create_sample_evidence("Missing Env tag"),
        )
        resource_meta = {"tags": {"owner": "app-team@company.internal"}}
        raised = alert_service.raise_alert(
            alert, tenant_context=tenant_ctx, resource_metadata=resource_meta, auto_dispatch=False
        )
        assert raised.recipients == ["app-team@company.internal"]
        assert raised.governance_exception_raised is False

    def test_stage_2_resolves_scope_owner_when_resource_owner_absent(
        self,
        alert_service: AlertService,
        tenant_ctx: TenantContext,
    ):
        """When resource owner tag is absent, routes to scope owner."""
        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.BUDGET_THRESHOLD,
            severity=AlertSeverity.WARNING,
            title="Scope Budget Warning",
            description="Scope budget 85%",
            source="budget_engine",
            scope_id="sub-platform",
            evidence=create_sample_evidence("Budget 85%"),
        )
        scope_meta = {"owner": "platform-lead@company.internal"}
        raised = alert_service.raise_alert(
            alert, tenant_context=tenant_ctx, scope_metadata=scope_meta, auto_dispatch=False
        )
        assert raised.recipients == ["platform-lead@company.internal"]
        assert raised.governance_exception_raised is False

    def test_stage_3_resolves_explicit_tenant_subscription(
        self,
        alert_service: AlertService,
        tenant_ctx: TenantContext,
    ):
        """Explicit subscription routes alert matching type and scope."""
        sub = RecipientSubscription(
            tenant_id=tenant_ctx.tenant_id,
            recipient="finops-channel@company.internal",
            channel=NotificationChannel.EMAIL,
            alert_types=[AlertType.UNEXPECTED_COST_INCREASE],
        )
        alert_service.create_subscription(sub, tenant_context=tenant_ctx)

        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.UNEXPECTED_COST_INCREASE,
            severity=AlertSeverity.HIGH,
            title="Spike in NAT Gateway",
            description="300% cost increase",
            source="cost_engine",
            evidence=create_sample_evidence("NAT Gateway jumped $400"),
        )
        raised = alert_service.raise_alert(alert, tenant_context=tenant_ctx, auto_dispatch=False)
        assert "finops-channel@company.internal" in raised.recipients
        assert raised.governance_exception_raised is False

    def test_stage_4_fallback_to_scope_admin_raises_governance_exception(
        self,
        alert_service: AlertService,
        tenant_ctx: TenantContext,
    ):
        """When no owner or subscription is found, falls back to default admin and raises governance exception."""
        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.RESOURCE_WITHOUT_OWNER,
            severity=AlertSeverity.WARNING,
            title="Orphaned Storage Account",
            description="Storage account has no tags and unmapped scope",
            source="inventory_scanner",
            affected_resource_id="st-orphan-99",
            scope_id="sub-unknown",
            evidence=create_sample_evidence("Orphaned account st-orphan-99"),
        )
        # Empty metadata -> triggers Stage 4 fallback
        raised = alert_service.raise_alert(
            alert,
            tenant_context=tenant_ctx,
            resource_metadata={},
            scope_metadata={},
            auto_dispatch=False,
        )
        assert raised.recipients in (["governance-admin@cloudlens.internal"], ["governance-admin@cloudlens.local"])
        assert raised.governance_exception_raised is True


# ==============================================================================
# 6. Quiet Hours, Escalation, and Delivery Logging Tests
# ==============================================================================


class TestQuietHoursEscalationAndDigesting:
    """Verifies quiet hours suppression, escalation SLAs, and delivery logging."""

    def test_quiet_hours_suppresses_low_severity_alerts(
        self,
        alert_service: AlertService,
        tenant_ctx: TenantContext,
    ):
        """INFO alerts during quiet hours are marked suppressed/buffered."""
        now = dt.datetime(
            2026, 10, 2, 23, 30, 0, tzinfo=dt.UTC
        )  # 23:30 (Quiet hours: 22:00 to 08:00)
        sub = RecipientSubscription(
            tenant_id=tenant_ctx.tenant_id,
            recipient="user@company.internal",
            channel=NotificationChannel.EMAIL,
            quiet_hours=QuietHoursConfig(start_time="22:00", end_time="08:00", enabled=True),
        )
        alert_service.create_subscription(sub, tenant_context=tenant_ctx)

        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.NEW_SERVICE_DETECTED,
            severity=AlertSeverity.INFO,
            title="New Service",
            description="Service discovered",
            source="sync_job",
            evidence=create_sample_evidence("New S3 bucket"),
        )
        routing = alert_service.router.resolve_recipients(
            alert, tenant_context=tenant_ctx, subscriptions=[sub], now=now
        )
        # All recipients suppressed
        assert len(routing.recipients) == 0
        assert alert.quiet_hours_suppressed is True

    def test_high_and_critical_severity_bypass_quiet_hours(
        self,
        alert_service: AlertService,
        tenant_ctx: TenantContext,
    ):
        """CRITICAL alerts unconditionally bypass quiet hours."""
        now = dt.datetime(2026, 10, 2, 23, 30, 0, tzinfo=dt.UTC)
        sub = RecipientSubscription(
            tenant_id=tenant_ctx.tenant_id,
            recipient="oncall@company.internal",
            channel=NotificationChannel.EMAIL,
            quiet_hours=QuietHoursConfig(start_time="22:00", end_time="08:00", enabled=True),
        )
        alert_service.create_subscription(sub, tenant_context=tenant_ctx)

        crit_alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.CONNECTOR_FAILURE,
            severity=AlertSeverity.CRITICAL,
            title="Connector Dead",
            description="Auth tokens revoked",
            source="connector_monitor",
            evidence=create_sample_evidence("HTTP 401 Unauthorized"),
        )
        routing = alert_service.router.resolve_recipients(
            crit_alert, tenant_context=tenant_ctx, subscriptions=[sub], now=now
        )
        # NOT suppressed because it is CRITICAL!
        assert len(routing.recipients) == 1
        assert routing.recipients[0] == "oncall@company.internal"
        assert crit_alert.quiet_hours_suppressed is False

    def test_unacknowledged_high_severity_alert_escalates(
        self,
        alert_service: AlertService,
        tenant_ctx: TenantContext,
    ):
        """High-severity alerts unacknowledged after timeout increment escalation level."""
        t_create = dt.datetime(2026, 10, 2, 10, 0, 0, tzinfo=dt.UTC)
        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.FORECAST_BUDGET_BREACH,
            severity=AlertSeverity.HIGH,
            title="Forecast 140% of Budget",
            description="Projected breach in 4 days",
            source="forecasting_engine",
            created_at=t_create,
            evidence=create_sample_evidence("Run-rate exceeds cap"),
        )
        saved = alert_service.raise_alert(alert, tenant_context=tenant_ctx, auto_dispatch=False)
        assert saved.escalation_level == 0
        assert saved.escalation_state == EscalationState.PENDING

        # Evaluate at T + 2 hours (exceeds default 1-hour SLA)
        eval_time = t_create + dt.timedelta(hours=2)
        escalated = alert_service.evaluate_escalations(
            tenant_context=tenant_ctx, escalation_timeout_seconds=3600, now=eval_time
        )
        assert len(escalated) == 1
        assert escalated[0].id == saved.id
        assert escalated[0].escalation_level == 1
        assert escalated[0].escalation_state == EscalationState.ESCALATED
        assert escalated[0].escalated_at == eval_time


# ==============================================================================
# 7. Delivery Adapters & Negative Constraints Tests
# ==============================================================================


class TestDeliveryAdaptersAndNegativeConstraints:
    """Tests delivery adapters and verifies negative constraints (No SMS/Voice)."""

    def test_email_adapter_success_and_invalid_email_handling(
        self,
        tenant_ctx: TenantContext,
    ):
        """Email adapter delivers valid email and rejects invalid format."""
        adapter = EmailChannelAdapter()
        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.CREDENTIAL_EXPIRING,
            severity=AlertSeverity.WARNING,
            title="Cert Expiring",
            description="Cert expires in 7 days",
            source="cred_service",
            evidence=create_sample_evidence("Expires 2026-10-09"),
        )

        # Valid email
        log_ok = adapter.send(alert, "admin@domain.com", tenant_context=tenant_ctx)
        assert log_ok.outcome == DeliveryOutcome.DELIVERED
        assert log_ok.payload["to"] == "admin@domain.com"

        # Invalid email
        log_bad = adapter.send(alert, "invalid-not-an-email", tenant_context=tenant_ctx)
        assert log_bad.outcome == DeliveryOutcome.FAILED
        assert "Invalid email format" in str(log_bad.error_message)

    def test_webhook_adapter_hmac_signing_and_retries(
        self,
        tenant_ctx: TenantContext,
    ):
        """Webhook adapter signs payload with HMAC SHA-256 and handles retries."""
        adapter = WebhookChannelAdapter(default_signing_secret="super-secret")
        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.STALE_CONNECTOR,
            severity=AlertSeverity.HIGH,
            title="Connector Stale",
            description="Last sync 26 hours ago",
            source="sync_monitor",
            evidence=create_sample_evidence("Last sync T-26h"),
        )
        log = adapter.send(
            alert,
            "https://api.internal/webhook",
            tenant_context=tenant_ctx,
            options={"simulate_retries": 2},
        )
        assert log.outcome == DeliveryOutcome.DELIVERED
        assert log.attempt_count == 3
        headers = log.payload["headers"]
        assert "sha256=" in headers["X-CloudLens-Signature"]
        assert headers["X-CloudLens-Event"] == "alert.stale_connector"

    def test_in_app_adapter_inbox_and_mark_read(
        self,
        tenant_ctx: TenantContext,
    ):
        """In-app adapter manages user inbox and read states."""
        adapter = InAppChannelAdapter()
        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.DELETED_SERVICE,
            severity=AlertSeverity.INFO,
            title="RDS Cluster Terminated",
            description="RDS cluster deleted",
            source="inventory_scanner",
            evidence=create_sample_evidence("RDS cluster deleted"),
        )
        log = adapter.send(alert, "user-alice", tenant_context=tenant_ctx)
        assert log.outcome == DeliveryOutcome.DELIVERED

        inbox = adapter.get_inbox("user-alice", tenant_context=tenant_ctx)
        assert len(inbox) == 1
        assert inbox[0].is_read is False

        # Mark read
        adapter.mark_read(inbox[0].item_id, "user-alice", tenant_context=tenant_ctx)
        assert inbox[0].is_read is True

    @pytest.mark.parametrize(
        "forbidden_channel", ["SMS", "sms", "VOICE", "voice", "CALL", "PAGING"]
    )
    def test_sms_and_voice_are_strictly_rejected(self, forbidden_channel: str):
        """STRICT NEGATIVE CONSTRAINT: SMS and Voice are unconditionally rejected."""
        registry = ChannelAdapterRegistry()
        with pytest.raises(ChannelNotSupportedException):
            registry.get(forbidden_channel)


# ==============================================================================
# 8. Inline Contextual Alerts Tests
# ==============================================================================


class TestInlineContextualAlerts:
    """Verifies the six inline contextual alert types, visibility, and dismissals."""

    @pytest.mark.parametrize(
        "contextual_type",
        [
            ContextualAlertType.COST_INFORMATION,
            ContextualAlertType.FREE_TIER,
            ContextualAlertType.BUDGET,
            ContextualAlertType.FORECAST,
            ContextualAlertType.PRICING_CHANGE,
            ContextualAlertType.PRICING_UNAVAILABLE,
        ],
    )
    def test_all_six_contextual_alert_types_can_be_created_and_queried(
        self,
        alert_service: AlertService,
        tenant_ctx: TenantContext,
        contextual_type: ContextualAlertType,
    ):
        """All 6 inline contextual alerts can be published and filtered."""
        alert = alert_service.create_contextual_alert(
            alert_type=contextual_type,
            title=f"Context {contextual_type.value}",
            message=f"Guidance for {contextual_type.value}",
            context_entity_type="resource",
            context_entity_id="res-vm-01",
            tenant_context=tenant_ctx,
            visibility=ContextualAlertVisibility.RESOURCE_HEADER,
        )
        assert alert.id is not None
        assert alert.alert_type == contextual_type
        assert alert.is_dismissed is False

        # Query
        alerts = alert_service.list_contextual_alerts(
            tenant_context=tenant_ctx,
            context_entity_id="res-vm-01",
        )
        assert any(a.alert_type == contextual_type for a in alerts)

    def test_contextual_alert_dismissal(
        self,
        alert_service: AlertService,
        tenant_ctx: TenantContext,
    ):
        """Contextual alert can be dismissed by an authenticated actor."""
        alert = alert_service.create_contextual_alert(
            alert_type=ContextualAlertType.FREE_TIER,
            title="Free tier 80%",
            message="80% of Lambda invocations used",
            context_entity_type="billing_page",
            context_entity_id="billing-overview",
            tenant_context=tenant_ctx,
            dismissible=True,
        )
        dismissed = alert_service.dismiss_contextual_alert(
            alert.id, actor="user-operator", tenant_context=tenant_ctx
        )
        assert dismissed.is_dismissed is True
        assert dismissed.dismissed_by == "user-operator"
        assert dismissed.dismissed_at is not None

        # Excluded from default list
        active_list = alert_service.list_contextual_alerts(
            tenant_context=tenant_ctx, include_dismissed=False
        )
        assert not any(a.id == alert.id for a in active_list)

        # Included when include_dismissed=True
        full_list = alert_service.list_contextual_alerts(
            tenant_context=tenant_ctx, include_dismissed=True
        )
        assert any(a.id == alert.id for a in full_list)


# ==============================================================================
# 9. Tenant Isolation & 100% Repository TenantContext Enforcement
# ==============================================================================


class TestMultiTenantIsolation:
    """Verifies strict cross-tenant isolation and 100% TenantContext validation."""

    def test_repository_enforces_tenant_context(self):
        """Repository public methods reject None tenant_context."""
        repo = AlertRepository()
        with pytest.raises(MissingTenantContextException):
            repo.list(tenant_context=None)  # type: ignore

    def test_tenant_data_isolation(
        self,
        alert_service: AlertService,
        tenant_ctx: TenantContext,
        other_tenant_ctx: TenantContext,
    ):
        """Alerts created in Tenant A are never visible to Tenant B."""
        alert_a = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.BUDGET_THRESHOLD,
            severity=AlertSeverity.HIGH,
            title="Tenant A Budget Alert",
            description="Tenant A private budget",
            source="budget_engine",
            evidence=create_sample_evidence("Tenant A budget"),
        )
        saved_a = alert_service.raise_alert(alert_a, tenant_context=tenant_ctx, auto_dispatch=False)

        # Tenant A can see it
        assert alert_service.get_alert(saved_a.id, tenant_context=tenant_ctx) is not None

        # Tenant B CANNOT see it
        assert alert_service.get_alert(saved_a.id, tenant_context=other_tenant_ctx) is None

        # Tenant B's list is empty
        list_b = alert_service.list_alerts(tenant_context=other_tenant_ctx)
        assert len(list_b) == 0


# ==============================================================================
# 10. REST API Contracts Tests
# ==============================================================================


class TestAlertingRESTAPIContracts:
    """Verifies FastAPI endpoint contracts and HTTP status codes."""

    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self) -> dict[str, str]:
        return {
            "X-Tenant-ID": "tenant-api-test",
            "X-User-ID": "user-api-operator",
        }

    def test_api_create_and_get_alert(self, client: TestClient, auth_headers: dict[str, str]):
        """POST /api/v1/alerts creates alert; GET /api/v1/alerts/{id} retrieves it."""
        payload = {
            "alert_type": "UNEXPECTED_RESOURCE_CREATION",
            "severity": "HIGH",
            "title": "Unapproved GPU VM Created",
            "description": "g5.xlarge launched in unauthorized region",
            "source": "inventory_detector",
            "affected_resource_id": "i-gpu-999",
            "scope_id": "aws-acc-123",
            "evidence": {
                "summary": "GPU instance detected in us-west-1",
                "datapoints": [{"instance_type": "g5.xlarge", "region": "us-west-1"}],
                "records": [{"id": "i-gpu-999"}],
                "context": {"provider": "AWS"},
            },
        }
        res_create = client.post("/api/v1/alerts", json=payload, headers=auth_headers)
        assert res_create.status_code == 201
        created = res_create.json()
        assert created["id"] is not None
        assert created["status"] == "ACTIVE"
        alert_id = created["id"]

        # GET single alert
        res_get = client.get(f"/api/v1/alerts/{alert_id}", headers=auth_headers)
        assert res_get.status_code == 200
        assert res_get.json()["id"] == alert_id

    def test_api_acknowledge_and_resolve_alert(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        """POST /api/v1/alerts/{id}/acknowledge and /resolve transition lifecycle."""
        # Create alert first
        payload = {
            "alert_type": "MISSING_DATA",
            "severity": "WARNING",
            "title": "Missing telemetry interval",
            "description": "No data for 2 consecutive hours",
            "source": "telemetry_collector",
            "evidence": {
                "summary": "Gaps detected between 10:00 and 12:00",
                "datapoints": [{"gap_hours": 2}],
            },
        }
        res_create = client.post("/api/v1/alerts", json=payload, headers=auth_headers)
        alert_id = res_create.json()["id"]

        # Acknowledge
        res_ack = client.post(
            f"/api/v1/alerts/{alert_id}/acknowledge",
            json={"actor": "sre-lead", "reason": "Checking scraper agent"},
            headers=auth_headers,
        )
        assert res_ack.status_code == 200
        assert res_ack.json()["status"] == "ACKNOWLEDGED"

        # Resolve
        res_res = client.post(
            f"/api/v1/alerts/{alert_id}/resolve",
            json={"actor": "sre-lead", "reason": "Scraper agent restarted"},
            headers=auth_headers,
        )
        assert res_res.status_code == 200
        assert res_res.json()["status"] == "RESOLVED"

    def test_api_contextual_alerts_crud_and_dismiss(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        """POST /api/v1/alerts/contextual creates contextual alert; dismiss works."""
        payload = {
            "alert_type": "COST_INFORMATION",
            "title": "Unattached EBS Disks",
            "message": "3 unattached volumes costing $45/mo",
            "context_entity_type": "storage_summary",
            "context_entity_id": "ebs-summary",
            "visibility": "PAGE_INLINE",
            "severity": "INFO",
            "dismissible": True,
        }
        res_create = client.post("/api/v1/alerts/contextual", json=payload, headers=auth_headers)
        assert res_create.status_code == 201
        ctx_id = res_create.json()["id"]

        # List
        res_list = client.get("/api/v1/alerts/contextual", headers=auth_headers)
        assert res_list.status_code == 200
        assert res_list.json()["total"] >= 1

        # Dismiss
        res_dismiss = client.post(
            f"/api/v1/alerts/contextual/{ctx_id}/dismiss",
            json={"actor": "finops-user"},
            headers=auth_headers,
        )
        assert res_dismiss.status_code == 200
        assert res_dismiss.json()["is_dismissed"] is True

    def test_api_subscriptions_and_delivery_logs(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        """POST /api/v1/alerts/subscriptions creates subscription; GET lists delivery logs."""
        sub_payload = {
            "recipient": "webhook@internal.org",
            "channel": "WEBHOOK",
            "alert_types": ["BUDGET_THRESHOLD"],
            "severities": ["HIGH", "CRITICAL"],
        }
        res_sub = client.post(
            "/api/v1/alerts/subscriptions", json=sub_payload, headers=auth_headers
        )
        assert res_sub.status_code == 201
        sub_id = res_sub.json()["id"]

        # List subscriptions
        res_list = client.get("/api/v1/alerts/subscriptions", headers=auth_headers)
        assert res_list.status_code == 200
        assert any(s["id"] == sub_id for s in res_list.json()["items"])

        # Delete subscription
        res_del = client.delete(f"/api/v1/alerts/subscriptions/{sub_id}", headers=auth_headers)
        assert res_del.status_code == 204

        # List delivery logs
        res_logs = client.get("/api/v1/alerts/delivery-logs", headers=auth_headers)
        assert res_logs.status_code == 200


# ==============================================================================
# 11. Extended Alert Catalogue & Master Data Routing Tests (Prompt 31B, FR-560)
# ==============================================================================


class TestExtendedAlertCatalogueAndMasterDataRouting:
    """Verifies that AL-17 to AL-20 resolve from master data and inherit all behaviors without special casing."""

    def test_default_alert_catalogue_contains_twenty_entries(self):
        """FR-560: Alert catalogue contains all twenty canonical alert types (AL-01 to AL-20)."""
        catalogue = get_default_alert_catalogue()
        assert len(catalogue) == 20

        ids = [entry.id for entry in catalogue]
        expected_ids = [f"AL-{i:02d}" for i in range(1, 21)]
        assert ids == expected_ids

        # Every entry has mandatory master data fields
        for entry in catalogue:
            assert entry.id.startswith("AL-")
            assert len(entry.code) > 0
            assert len(entry.name) > 0
            assert entry.alert_type in AlertType
            assert entry.default_severity in AlertSeverity
            assert len(entry.description) > 0
            assert len(entry.trigger_condition) > 0
            assert len(entry.default_routing_roles) > 0
            assert entry.event_name.startswith("alert.")

    def test_catalogue_lookup_helpers(self):
        """Lookup by ID and lookup by AlertType resolve accurately from master data."""
        # By ID
        al17 = get_alert_definition_by_id("AL-17")
        assert al17 is not None
        assert al17.alert_type == AlertType.QUOTA_HEADROOM_LOW
        assert al17.code == "QUOTA_HEADROOM_LOW"
        assert al17.default_severity == AlertSeverity.WARNING
        assert "technical_owner" in al17.default_routing_roles
        assert "cloud_administrator" in al17.default_routing_roles

        al18 = get_alert_definition_by_id("AL-18")
        assert al18 is not None
        assert al18.alert_type == AlertType.COMMITMENT_EXPIRING
        assert "commitment_owner" in al18.default_routing_roles
        assert "procurement" in al18.default_routing_roles

        al19 = get_alert_definition_by_id("AL-19")
        assert al19 is not None
        assert al19.alert_type == AlertType.PROVISIONING_REQUEST_DECIDED
        assert al19.default_severity == AlertSeverity.INFO
        assert "requester" in al19.default_routing_roles

        al20 = get_alert_definition_by_id("AL-20")
        assert al20 is not None
        assert al20.alert_type == AlertType.ANALYTICAL_EXTRACT_LATE_OR_EMPTY
        assert al20.default_severity == AlertSeverity.INFO
        assert "platform_administrator" in al20.default_routing_roles

        # By Type
        assert get_alert_definition_by_type(AlertType.QUOTA_HEADROOM_LOW) is not None
        assert get_alert_definition_by_type(AlertType.COMMITMENT_EXPIRING) is not None
        assert get_alert_definition_by_type(AlertType.PROVISIONING_REQUEST_DECIDED) is not None
        assert get_alert_definition_by_type(AlertType.ANALYTICAL_EXTRACT_LATE_OR_EMPTY) is not None

        # Catalogue map
        cat_map = get_alert_catalogue_map()
        assert len(cat_map) == 20
        assert "AL-17" in cat_map
        assert "AL-20" in cat_map

    def test_master_data_routing_al_17_technical_owner_and_cloud_admin(
        self, alert_service: AlertService, tenant_ctx: TenantContext
    ):
        """AL-17 routes to technical owner and cloud administrator without code-side special casing."""
        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.QUOTA_HEADROOM_LOW,
            severity=AlertSeverity.WARNING,
            title="Compute Quota Headroom Low",
            description="Exhaustion predicted in 4 days",
            source="quota_engine",
            scope_id="sub-prod-01",
            evidence=create_sample_evidence("Quota consumed 94% with 4 days until exhaustion"),
        )
        res_meta = {"technical_owner": "tech-lead@company.internal"}
        scope_meta = {"cloud_administrator": "cloud-admin@company.internal"}

        raised = alert_service.raise_alert(
            alert,
            tenant_context=tenant_ctx,
            resource_metadata=res_meta,
            scope_metadata=scope_meta,
            auto_dispatch=False,
        )

        assert "tech-lead@company.internal" in raised.recipients
        assert "cloud-admin@company.internal" in raised.recipients
        assert len(raised.recipients) == 2
        assert raised.governance_exception_raised is False

    def test_master_data_routing_al_18_commitment_owner_and_procurement(
        self, alert_service: AlertService, tenant_ctx: TenantContext
    ):
        """AL-18 routes to commitment owner and procurement without code-side special casing."""
        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.COMMITMENT_EXPIRING,
            severity=AlertSeverity.WARNING,
            title="AWS 3-Year Reserved Instance Expiring",
            description="30 days until RI renewal date",
            source="pricing_engine",
            scope_id="acc-aws-prod",
            evidence=create_sample_evidence("RI ri-123456 expires on 2026-11-01"),
        )
        res_meta = {"commitment_owner": "finops-ri-owner@company.internal"}
        scope_meta = {"procurement": "cloud-procurement@company.internal"}

        raised = alert_service.raise_alert(
            alert,
            tenant_context=tenant_ctx,
            resource_metadata=res_meta,
            scope_metadata=scope_meta,
            auto_dispatch=False,
        )

        assert "finops-ri-owner@company.internal" in raised.recipients
        assert "cloud-procurement@company.internal" in raised.recipients
        assert len(raised.recipients) == 2
        assert raised.governance_exception_raised is False

    def test_master_data_routing_al_19_requester(
        self, alert_service: AlertService, tenant_ctx: TenantContext
    ):
        """AL-19 routes to requester without code-side special casing."""
        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.PROVISIONING_REQUEST_DECIDED,
            severity=AlertSeverity.INFO,
            title="Provisioning Request PR-982 Approved",
            description="Production cluster provisioning request was approved",
            source="governance_portal",
            evidence=create_sample_evidence("Approval granted by Architecture Review Board"),
        )
        res_meta = {"requester": "engineer-jane@company.internal"}

        raised = alert_service.raise_alert(
            alert,
            tenant_context=tenant_ctx,
            resource_metadata=res_meta,
            auto_dispatch=False,
        )

        assert raised.recipients == ["engineer-jane@company.internal"]
        assert raised.governance_exception_raised is False

    def test_master_data_routing_al_20_platform_administrator(
        self, alert_service: AlertService, tenant_ctx: TenantContext
    ):
        """AL-20 routes to platform administrator without code-side special casing."""
        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.ANALYTICAL_EXTRACT_LATE_OR_EMPTY,
            severity=AlertSeverity.INFO,
            title="Daily FOCUS Extract Delayed",
            description="Nightly export pipeline ran 3 hours past SLA",
            source="export_pipeline",
            evidence=create_sample_evidence("Extract job extract-2026-10-02 produced 0 rows"),
        )
        scope_meta = {"platform_administrator": "platform-ops@company.internal"}

        raised = alert_service.raise_alert(
            alert,
            tenant_context=tenant_ctx,
            scope_metadata=scope_meta,
            auto_dispatch=False,
        )

        assert raised.recipients == ["platform-ops@company.internal"]
        assert raised.governance_exception_raised is False

    def test_extended_alerts_fallback_to_admin_when_roles_unmapped(
        self, alert_service: AlertService, tenant_ctx: TenantContext
    ):
        """Extended alerts with empty metadata fall back to default admin and raise governance exception."""
        alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.QUOTA_HEADROOM_LOW,
            severity=AlertSeverity.WARNING,
            title="Quota Low Without Owner",
            description="No owner tags on unmapped scope",
            source="quota_engine",
            scope_id="sub-unmapped",
            evidence=create_sample_evidence("Quota headroom at 5%"),
        )
        raised = alert_service.raise_alert(
            alert,
            tenant_context=tenant_ctx,
            resource_metadata={},
            scope_metadata={},
            auto_dispatch=False,
        )
        assert raised.recipients in (["governance-admin@cloudlens.internal"], ["governance-admin@cloudlens.local"])
        assert raised.governance_exception_raised is True

    def test_extended_alerts_inherit_deduplication(
        self, alert_service: AlertService, tenant_ctx: TenantContext
    ):
        """AL-17 inherits alert deduplication without special casing."""
        evidence1 = create_sample_evidence("Cycle 1 quota 92%")
        alert1 = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.QUOTA_HEADROOM_LOW,
            severity=AlertSeverity.WARNING,
            title="EC2 vCPU Quota Low",
            description="92% consumed",
            source="quota_engine",
            scope_id="acc-aws-prod",
            affected_resource_id="quota-ec2-vcpu",
            evidence=evidence1,
        )
        r1 = alert_service.raise_alert(alert1, tenant_context=tenant_ctx, auto_dispatch=False)
        assert r1.repeat_count == 1

        evidence2 = create_sample_evidence("Cycle 2 quota 95%")
        alert2 = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.QUOTA_HEADROOM_LOW,
            severity=AlertSeverity.HIGH,  # Severity elevated as date approaches!
            title="EC2 vCPU Quota Critical",
            description="95% consumed",
            source="quota_engine",
            scope_id="acc-aws-prod",
            affected_resource_id="quota-ec2-vcpu",
            evidence=evidence2,
        )
        r2 = alert_service.raise_alert(alert2, tenant_context=tenant_ctx, auto_dispatch=False)

        # Reuses same active alert ID, increments occurrences
        assert r2.id == r1.id
        assert r2.repeat_count == 2
        assert r2.evidence.summary == "Cycle 2 quota 95%"

    def test_extended_alerts_inherit_scope_storm_grouping(
        self, alert_service: AlertService, tenant_ctx: TenantContext
    ):
        """AL-17 to AL-20 inherit scope storm grouping without special casing."""
        scope_id = "scope-quota-storm"

        # Raise 10 alerts in scope
        for i in range(10):
            alert = AlertEntity(
                tenant_id=tenant_ctx.tenant_id,
                alert_type=AlertType.QUOTA_HEADROOM_LOW,
                severity=AlertSeverity.WARNING,
                title=f"Quota {i} headroom low",
                description="Approaching capacity",
                source="quota_engine",
                scope_id=scope_id,
                affected_resource_id=f"quota-{i}",
                evidence=create_sample_evidence(f"Quota {i} at 92%"),
            )
            alert_service.raise_alert(alert, tenant_context=tenant_ctx, auto_dispatch=False)

        # 11th alert triggers scope storm grouping
        alert11 = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.COMMITMENT_EXPIRING,
            severity=AlertSeverity.WARNING,
            title="Commitment 11 expiring",
            description="Reservation ending",
            source="pricing_engine",
            scope_id=scope_id,
            affected_resource_id="ri-11",
            evidence=create_sample_evidence("RI-11 expiring"),
        )
        grouped_result = alert_service.raise_alert(
            alert11, tenant_context=tenant_ctx, auto_dispatch=False
        )

        assert grouped_result.alert_type == AlertType.SCOPE_STORM_GROUPED
        assert len(grouped_result.child_alert_ids) == 11

    def test_extended_alerts_inherit_quiet_hours_and_escalation(
        self, alert_service: AlertService, tenant_ctx: TenantContext
    ):
        """AL-19 (INFO) is suppressed during quiet hours; AL-17 (HIGH) bypasses quiet hours and escalates."""
        qh = QuietHoursConfig(
            enabled=True,
            start_time="22:00",
            end_time="08:00",
        )
        night_time = dt.datetime(2026, 10, 2, 23, 30, tzinfo=dt.UTC)

        sub = RecipientSubscription(
            tenant_id=tenant_ctx.tenant_id,
            recipient="oncall@company.internal",
            channel=NotificationChannel.EMAIL,
            quiet_hours=qh,
        )
        alert_service.create_subscription(sub, tenant_context=tenant_ctx)

        # 1. INFO alert (AL-19) during quiet hours -> Suppressed
        info_alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.PROVISIONING_REQUEST_DECIDED,
            severity=AlertSeverity.INFO,
            title="PR Decided During Quiet Hours",
            description="Informational event",
            source="governance_portal",
            evidence=create_sample_evidence("PR decided"),
        )
        routing_info = alert_service.router.resolve_recipients(
            info_alert, tenant_context=tenant_ctx, subscriptions=[sub], now=night_time
        )
        assert len(routing_info.recipients) == 0
        assert info_alert.quiet_hours_suppressed is True

        # 2. HIGH alert (AL-17) during quiet hours -> Bypasses quiet hours
        high_alert = AlertEntity(
            tenant_id=tenant_ctx.tenant_id,
            alert_type=AlertType.QUOTA_HEADROOM_LOW,
            severity=AlertSeverity.HIGH,  # High severity quota breach
            title="Urgent Quota Exhaustion",
            description="Exhaustion imminent within 12 hours",
            source="quota_engine",
            evidence=create_sample_evidence("vCPU quota at 99%"),
        )
        routing_high = alert_service.router.resolve_recipients(
            high_alert, tenant_context=tenant_ctx, subscriptions=[sub], now=night_time
        )
        assert high_alert.quiet_hours_suppressed is False
        assert "oncall@company.internal" in routing_high.recipients

        # 3. Escalation: simulate timeout elapsing on high alert
        r_high = alert_service.raise_alert(
            high_alert, tenant_context=tenant_ctx, auto_dispatch=False
        )
        r_high.created_at = night_time - dt.timedelta(seconds=4000)
        alert_service.repository.save(r_high, tenant_context=tenant_ctx)

        escalated = alert_service.evaluate_escalations(
            tenant_context=tenant_ctx, escalation_timeout_seconds=3600, now=night_time
        )
        assert any(a.id == r_high.id for a in escalated)
        refreshed = alert_service.get_alert(r_high.id, tenant_context=tenant_ctx)
        assert refreshed is not None
        assert refreshed.escalation_state == EscalationState.ESCALATED

    def test_webhook_outbound_event_names_for_extended_alerts(self, tenant_ctx: TenantContext):
        """Prompt 60 outbound event model: webhook dispatches correct event name headers for AL-17 to AL-20."""
        webhook_adapter = WebhookChannelAdapter()

        test_cases = [
            (AlertType.QUOTA_HEADROOM_LOW, "alert.quota_headroom_low"),
            (AlertType.COMMITMENT_EXPIRING, "alert.commitment_expiring"),
            (AlertType.PROVISIONING_REQUEST_DECIDED, "alert.provisioning_request_decided"),
            (AlertType.ANALYTICAL_EXTRACT_LATE_OR_EMPTY, "alert.analytical_extract_late_or_empty"),
        ]

        for alert_type, expected_event in test_cases:
            alert = AlertEntity(
                tenant_id=tenant_ctx.tenant_id,
                alert_type=alert_type,
                severity=AlertSeverity.WARNING,
                title=f"Test {alert_type.value}",
                description="Test description",
                source="test",
                evidence=create_sample_evidence(f"Evidence for {alert_type.value}"),
            )
            log = webhook_adapter.send(
                alert,
                "https://webhook.internal.org/alerts",
                tenant_context=tenant_ctx,
            )
            assert log.outcome == DeliveryOutcome.DELIVERED
            assert log.payload is not None
            headers = log.payload["headers"]
            assert headers["X-CloudLens-Event"] == expected_event
            assert log.payload["body"]["event"] == expected_event

    def test_api_alerts_catalogue_endpoint(self):
        """REST API endpoint GET /api/v1/alerts/catalogue returns all 20 master data entries."""
        client = TestClient(app)
        res = client.get("/api/v1/alerts/catalogue")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 20
        assert len(data["items"]) == 20

        # Check AL-17 to AL-20 are in response items
        items_by_id = {item["id"]: item for item in data["items"]}
        assert "AL-17" in items_by_id
        assert items_by_id["AL-17"]["code"] == "QUOTA_HEADROOM_LOW"
        assert items_by_id["AL-17"]["event_name"] == "alert.quota_headroom_low"
        assert items_by_id["AL-17"]["default_routing_roles"] == [
            "technical_owner",
            "cloud_administrator",
        ]

        assert "AL-18" in items_by_id
        assert items_by_id["AL-18"]["code"] == "COMMITMENT_EXPIRING"
        assert items_by_id["AL-18"]["event_name"] == "alert.commitment_expiring"

        assert "AL-19" in items_by_id
        assert items_by_id["AL-19"]["code"] == "PROVISIONING_REQUEST_DECIDED"
        assert items_by_id["AL-19"]["event_name"] == "alert.provisioning_request_decided"

        assert "AL-20" in items_by_id
        assert items_by_id["AL-20"]["code"] == "ANALYTICAL_EXTRACT_LATE_OR_EMPTY"
        assert items_by_id["AL-20"]["event_name"] == "alert.analytical_extract_late_or_empty"
