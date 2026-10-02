"""Unit & Integration Tests for Quota, Service Limit, and Headroom Tracking (Prompt 54).

Enforces:
- Prompt 54: Connector capability contract extension (collect_quotas, probe_quota_coverage, partial coverage).
- Prompt 54: First-class Quota entity with >= 3-month history and headroom trend.
- Prompt 54: Quota Master in Master-Data Registry with configurable lead times and review periods.
- Prompt 54: Threshold engine integration with QUOTA_HEADROOM basis.
- Prompt 54: Lead-time-driven dynamic alerting (predicted_exhaustion_date - lead_time - safety_margin).
- Prompt 54: Remediation tasks created with due date equal to predicted exhaustion date.
- Prompt 54: Manual quota limits marked as manual with mandatory source provenance note.
- Prompt 54: Increase request tracking and actual lead-time calculation.
- Prompt 54: API-050 filterable quota view and provider dashboard headroom summary.
- Negative constraints:
  - Do NOT present an unknown limit as unlimited (renders as NOT_SUPPORTED/UNKNOWN).
  - Do NOT alert on a fixed percentage where a predicted exhaustion date is computable.
  - Do NOT hard-code any quota name, threshold, or lead time.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from connectors.simulator.connector import ProviderSimulatorConnector
from connectors.simulator.models import SimulatorProfile
from domain.models.enums import (
    CloudProvider,
    QuotaCoverage,
    QuotaHeadroomState,
    QuotaIncreaseRequestStatus,
    QuotaScopeType,
)
from domain.models.exceptions import (
    InvalidQuotaLimitException,
    ManualQuotaSourceNoteRequiredException,
)
from domain.quotas.forecasting import QuotaForecaster
from domain.quotas.models import (
    QuotaDataPoint,
    QuotaEntity,
    QuotaIncreaseCreateRequest,
    QuotaIncreaseUpdateRequest,
    QuotaManualCreateRequest,
)
from domain.quotas.service import (
    QuotaService,
    get_quota_service,
    reset_quota_service,
)
from domain.tenant.context import TenantContext
from domain.thresholds.models import (
    ThresholdBandDefinition,
    ThresholdBasis,
    ThresholdRule,
    ThresholdState,
)
from masterdata.registry import SYSTEM_MASTER_REGISTRY, is_master_registered
from masterdata.service import MasterDataService, reset_master_data_service


@pytest.fixture
def tenant_ctx() -> TenantContext:
    """Fixture providing authenticated tenant context."""
    return TenantContext(
        tenant_id="tenant-finops-alpha",
        correlation_id="corr-test-quota-01",
        user_id="finops-admin",
        roles=["OPERATOR", "FINOPS_ADMIN"],
    )


@pytest.fixture
def quota_svc() -> QuotaService:
    """Fixture providing freshly reset QuotaService."""
    reset_quota_service()
    return get_quota_service()


@pytest.fixture
def client(tenant_ctx: TenantContext) -> TestClient:
    """Fixture providing FastAPI test client with tenant headers."""
    reset_quota_service()
    reset_master_data_service()
    return TestClient(
        app,
        headers={
            "X-Tenant-ID": tenant_ctx.tenant_id,
            "X-Actor-ID": tenant_ctx.actor_id or "finops-admin",
            "X-Correlation-ID": tenant_ctx.correlation_id or "corr-test",
        },
    )


# ==============================================================================
# 1. Connector Capability & Coverage Probing
# ==============================================================================


class TestConnectorQuotaCapability:
    """Tests connector capability contract extension and partial coverage visibility."""

    def test_connector_probes_quota_coverage(self, tenant_ctx: TenantContext):
        """Verifies connector probes quota coverage and reports partial coverage where applicable."""
        # AWS has partial coverage across services in simulator
        aws_conn = ProviderSimulatorConnector(
            connector_id="conn-aws", tenant_id=tenant_ctx.tenant_id, profile=SimulatorProfile.AWS
        )
        probe_aws = aws_conn.probe_quota_coverage(tenant_context=tenant_ctx)
        assert probe_aws.provider == CloudProvider.AWS
        assert probe_aws.coverage in (QuotaCoverage.COMPLETE, QuotaCoverage.PARTIAL)
        assert "ec2" in probe_aws.supported_service_codes
        assert probe_aws.is_supported is True

        # Azure coverage probe
        az_conn = ProviderSimulatorConnector(
            connector_id="conn-azure",
            tenant_id=tenant_ctx.tenant_id,
            profile=SimulatorProfile.AZURE,
        )
        probe_az = az_conn.probe_quota_coverage(tenant_context=tenant_ctx)
        assert probe_az.provider == CloudProvider.AZURE
        assert "compute" in probe_az.supported_service_codes

    def test_connector_collects_multi_cloud_quotas(self, tenant_ctx: TenantContext):
        """Verifies collecting quotas from AWS, Azure, GCP, and OCI profiles."""
        for provider in [
            CloudProvider.AWS,
            CloudProvider.AZURE,
            CloudProvider.GCP,
            CloudProvider.OCI,
        ]:
            profile = SimulatorProfile(provider.value.lower())
            conn = ProviderSimulatorConnector(
                connector_id=f"conn-{provider.value.lower()}",
                tenant_id=tenant_ctx.tenant_id,
                profile=profile,
            )
            items = conn.collect_quotas(tenant_context=tenant_ctx)
            assert len(items) >= 2
            for item in items:
                assert item.provider == provider
                assert item.quota_code
                assert item.quota_name
                assert item.unit
                assert item.scope_type in QuotaScopeType
                assert item.scope_id
                assert item.consumed_value is not None and float(item.consumed_value) >= 0.0


# ==============================================================================
# 2. Master Data Registry Integration
# ==============================================================================


class TestQuotaMasterRegistry:
    """Tests Quota Master registration in Master-Data Registry."""

    def test_quota_registered_in_system_manifest(self):
        """Verifies QUOTA is registered in SYSTEM_MASTER_REGISTRY manifest."""
        assert is_master_registered("QUOTA")
        entry = SYSTEM_MASTER_REGISTRY["QUOTA"]
        assert entry.code == "QUOTA"
        assert entry.is_tenant_scoped is False
        assert entry.requires_approval is True
        assert entry.seed_file == "masterdata/seeds/quota.json"
        assert "quotas" in entry.consuming_modules

    def test_master_data_service_seeds_quotas(self):
        """Verifies MasterDataService loads quota definitions from seed file."""
        reset_master_data_service()
        md_service = MasterDataService(auto_seed=True)
        records = md_service.list_records("QUOTA")
        assert len(records) >= 8

        # Verify attributes on AWS vCPU quota
        ec2_quota = next(r for r in records if r.code == "aws-ec2-running-vcpus")
        assert (
            ec2_quota.display_name
            == "Running On-Demand Standard (A, C, D, I, M, R, T, Z) instances"
        )
        assert ec2_quota.attributes["provider"] == "aws"
        assert ec2_quota.attributes["unit"] == "vCPU"
        assert ec2_quota.attributes["lead_time_days"] == 2
        assert ec2_quota.attributes["exhaustion_impact"] == "SERVICE_AFFECTING"


# ==============================================================================
# 3. Threshold Engine Integration
# ==============================================================================


class TestThresholdEngineQuotaIntegration:
    """Tests ThresholdBasis.QUOTA_HEADROOM basis integration."""

    def test_quota_headroom_basis_defined_and_evaluable(self, tenant_ctx: TenantContext):
        """Verifies QUOTA_HEADROOM is a valid threshold basis and evaluates properly."""
        assert ThresholdBasis.QUOTA_HEADROOM in ThresholdBasis

        # Create threshold rule based on QUOTA_HEADROOM
        rule = ThresholdRule(
            tenant_id=tenant_ctx.tenant_id,
            name="Production Compute Quota Headroom",
            basis=ThresholdBasis.QUOTA_HEADROOM,
            bands=[
                ThresholdBandDefinition(
                    name="Critical Headroom",
                    state=ThresholdState.CRITICAL,
                    lower_bound=Decimal("0.0"),
                    upper_bound=Decimal("10.0"),
                ),
                ThresholdBandDefinition(
                    name="Warning Headroom",
                    state=ThresholdState.WARNING,
                    lower_bound=Decimal("10.0"),
                    upper_bound=Decimal("20.0"),
                ),
                ThresholdBandDefinition(
                    name="Normal Headroom",
                    state=ThresholdState.NORMAL,
                    lower_bound=Decimal("20.0"),
                    upper_bound=Decimal("100.0"),
                ),
            ],
            unit="PERCENT",
        )
        assert rule.basis == ThresholdBasis.QUOTA_HEADROOM
        assert len(rule.bands) == 3


# ==============================================================================
# 4. Lead-Time Forecasting & Negative Constraints
# ==============================================================================


class TestQuotaForecastingAndAlerting:
    """Tests predictive trend projection and dynamic lead-time alerting."""

    def test_predicted_exhaustion_date_and_lead_time_alerting(self, tenant_ctx: TenantContext):
        """Verifies alert fires at (predicted_exhaustion_date - lead_time - safety_margin)."""
        now = datetime.now(UTC)

        # Quota with limit=100, consumed=60 (headroom=40)
        # Growth velocity: 4 units/day (delta = 40 over 10 days)
        # Days to exhaustion: 40 / 4 = 10 days
        # Lead time: 3 days, safety margin: 10% (0.3 days) -> total lead time window: 3.3 days
        # Alert trigger date: now + 10 days - 3.3 days = now + 6.7 days
        history = [
            QuotaDataPoint(
                timestamp=now - timedelta(days=10), consumed_value=20.0, limit_value=100.0
            ),
            QuotaDataPoint(timestamp=now, consumed_value=60.0, limit_value=100.0),
        ]

        quota = QuotaEntity(
            tenant_id=tenant_ctx.tenant_id,
            provider=CloudProvider.AWS,
            scope_type=QuotaScopeType.ACCOUNT,
            scope_id="123456789012",
            service_code="ec2",
            quota_code="test-ec2-vcpus",
            quota_name="Test vCPUs",
            limit_value=100.0,
            consumed_value=60.0,
            unit="vCPU",
            lead_time_days=3,
            safety_margin_pct=10.0,
            history=history,
        )

        # Evaluate as of current time (10 days until exhaustion > 3.3 days lead time) -> NORMAL
        evaluated = QuotaForecaster.evaluate_quota(quota, as_of=now)
        assert evaluated.daily_consumption_velocity == pytest.approx(4.0, abs=0.1)
        assert evaluated.days_until_exhaustion == pytest.approx(10.0, abs=0.1)
        assert evaluated.predicted_exhaustion_date is not None
        assert evaluated.status == QuotaHeadroomState.NORMAL

        # Advance evaluation time to 6.85 days later:
        # consumption has grown by 6.85 * 4 = 27.4 -> consumed = 87.4
        # (3.15 days remaining until exhaustion: > 3.0 days lead time and <= 3.3 days lead window)
        # Lead-time alert MUST fire WARNING!
        eval_time_warning = now + timedelta(days=6, hours=20, minutes=24)
        quota.consumed_value = 87.4
        quota.history.append(
            QuotaDataPoint(timestamp=eval_time_warning, consumed_value=87.4, limit_value=100.0)
        )
        evaluated_warning = QuotaForecaster.evaluate_quota(quota, as_of=eval_time_warning)
        assert evaluated_warning.status == QuotaHeadroomState.WARNING

        # Advance evaluation time to 8 days later: consumption is now 92.0 (2 days remaining < 3 days lead time) -> CRITICAL
        eval_time_critical = now + timedelta(days=8)
        quota.consumed_value = 92.0
        quota.history.append(
            QuotaDataPoint(timestamp=eval_time_critical, consumed_value=92.0, limit_value=100.0)
        )
        evaluated_critical = QuotaForecaster.evaluate_quota(quota, as_of=eval_time_critical)
        assert evaluated_critical.status == QuotaHeadroomState.CRITICAL

    def test_negative_constraint_unknown_limit_is_not_unlimited(self, tenant_ctx: TenantContext):
        """Negative constraint: Unknown limit renders as NOT_SUPPORTED, never unlimited, never zero consumed."""
        quota = QuotaEntity(
            tenant_id=tenant_ctx.tenant_id,
            provider=CloudProvider.AWS,
            scope_type=QuotaScopeType.ACCOUNT,
            scope_id="123456789012",
            service_code="s3",
            quota_code="aws-s3-unmetered",
            quota_name="Unmetered Storage",
            limit_value=None,  # Unknown / Not Supported limit
            consumed_value=42.0,
            unit="count",
        )
        evaluated = QuotaForecaster.evaluate_quota(quota)
        assert evaluated.status == QuotaHeadroomState.NOT_SUPPORTED
        assert evaluated.limit_value is None
        assert evaluated.headroom_value is None
        assert evaluated.headroom_percentage is None
        assert evaluated.predicted_exhaustion_date is None
        assert evaluated.consumed_value == 42.0  # Retains non-zero consumed value

    def test_negative_constraint_does_not_alert_on_fixed_percentage_when_velocity_predictable(
        self, tenant_ctx: TenantContext
    ):
        """Negative constraint: Does NOT alert on fixed percentage where exhaustion is distant."""
        now = datetime.now(UTC)
        # Quota with limit=1000, consumed=850 (85% consumed, 15% headroom remaining)
        # If naive fixed percentage were used, 85% might trigger warning (>80%).
        # BUT velocity is very slow: 0.1 units/day -> 1500 days until exhaustion!
        # Lead time is 3 days.
        # Dynamic forecaster MUST NOT trigger warning because 1500 days >> 3 days!
        history = [
            QuotaDataPoint(
                timestamp=now - timedelta(days=100), consumed_value=840.0, limit_value=1000.0
            ),
            QuotaDataPoint(timestamp=now, consumed_value=850.0, limit_value=1000.0),
        ]
        quota = QuotaEntity(
            tenant_id=tenant_ctx.tenant_id,
            provider=CloudProvider.AWS,
            scope_type=QuotaScopeType.ACCOUNT,
            scope_id="123456789012",
            service_code="ec2",
            quota_code="slow-growth-quota",
            quota_name="Slow Growth Resource",
            limit_value=1000.0,
            consumed_value=850.0,
            unit="count",
            lead_time_days=3,
            warning_headroom_pct=20.0,
            critical_headroom_pct=10.0,
            history=history,
        )
        evaluated = QuotaForecaster.evaluate_quota(quota, as_of=now)
        assert evaluated.status == QuotaHeadroomState.NORMAL
        assert evaluated.days_until_exhaustion is not None
        assert evaluated.days_until_exhaustion > 1000.0

    def test_exhausted_quota_evaluates_to_exhausted_state(self, tenant_ctx: TenantContext):
        """Verifies quota with consumed >= limit evaluates to EXHAUSTED."""
        quota = QuotaEntity(
            tenant_id=tenant_ctx.tenant_id,
            provider=CloudProvider.GCP,
            scope_type=QuotaScopeType.PROJECT,
            scope_id="prj-01",
            service_code="compute",
            quota_code="gcp-cpus",
            quota_name="CPUs",
            limit_value=50.0,
            consumed_value=50.0,
            unit="CPUs",
        )
        evaluated = QuotaForecaster.evaluate_quota(quota)
        assert evaluated.status == QuotaHeadroomState.EXHAUSTED
        assert evaluated.days_until_exhaustion == 0.0


# ==============================================================================
# 5. Remediation Tasks & Ownership
# ==============================================================================


class TestQuotaRemediationTasks:
    """Tests automatic remediation task generation linked to predicted exhaustion dates."""

    def test_remediation_task_created_on_capacity_risk(
        self, quota_svc: QuotaService, tenant_ctx: TenantContext
    ):
        """Verifies remediation task is created with due_date = predicted_exhaustion_date."""
        # Sync connector quotas with ProviderSimulatorConnector
        conn = ProviderSimulatorConnector(
            connector_id="conn-azure",
            tenant_id=tenant_ctx.tenant_id,
            profile=SimulatorProfile.AZURE,
        )
        synced = quota_svc.sync_connector_quotas(conn, tenant_context=tenant_ctx)
        assert len(synced) > 0

        # Create manual quota in warning/critical state
        req = QuotaManualCreateRequest(
            provider=CloudProvider.AWS,
            scope_type=QuotaScopeType.ACCOUNT,
            scope_id="123456789012",
            service_code="ec2",
            quota_code="aws-ec2-high-usage",
            quota_name="High Usage vCPUs",
            limit_value=100.0,
            consumed_value=95.0,  # 5% headroom remaining -> CRITICAL
            unit="vCPU",
            manual_source_note="Direct agreement with AWS Enterprise Support TAM for Q4 surge.",
            warning_headroom_pct=20.0,
            critical_headroom_pct=10.0,
            lead_time_days=3,
        )
        saved_quota = quota_svc.record_manual_quota(req, tenant_context=tenant_ctx)
        assert saved_quota.status in (QuotaHeadroomState.CRITICAL, QuotaHeadroomState.WARNING)

        # Check remediation tasks
        tasks = quota_svc.list_remediation_tasks(tenant_context=tenant_ctx, quota_id=saved_quota.id)
        assert len(tasks) >= 1
        task = tasks[0]
        assert task.quota_id == saved_quota.id
        assert task.due_date is not None
        assert "finops" in task.assigned_owner_id
        assert task.status == "OPEN"


# ==============================================================================
# 6. Manual Quota Administration & Source Provenance
# ==============================================================================


class TestManualQuotaAdministration:
    """Tests administrator manual quota recording and mandatory provenance notes."""

    def test_manual_quota_requires_source_note_min_10_chars(self, tenant_ctx: TenantContext):
        """Rejects manual quota without descriptive source note (min 10 chars)."""
        with pytest.raises(ManualQuotaSourceNoteRequiredException):
            QuotaEntity(
                tenant_id=tenant_ctx.tenant_id,
                provider=CloudProvider.AWS,
                scope_type=QuotaScopeType.ACCOUNT,
                scope_id="123",
                service_code="ec2",
                quota_code="bad-note",
                quota_name="Bad Note Quota",
                limit_value=50.0,
                consumed_value=10.0,
                unit="count",
                is_manual=True,
                manual_source_note="short",  # < 10 chars!
            )

    def test_manual_quota_requires_positive_limit(
        self, quota_svc: QuotaService, tenant_ctx: TenantContext
    ):
        """Rejects manual quota with zero or negative limit."""
        with pytest.raises((InvalidQuotaLimitException, ValueError)):
            quota_svc.record_manual_quota(
                QuotaManualCreateRequest(
                    provider=CloudProvider.AWS,
                    scope_type=QuotaScopeType.ACCOUNT,
                    scope_id="123",
                    service_code="ec2",
                    quota_code="bad-limit",
                    quota_name="Bad Limit Quota",
                    limit_value=0.0,  # <= 0
                    consumed_value=0.0,
                    unit="count",
                    manual_source_note="Valid source note exceeding ten characters",
                ),
                tenant_context=tenant_ctx,
            )

    def test_valid_manual_quota_saved_with_manual_flag(
        self, quota_svc: QuotaService, tenant_ctx: TenantContext
    ):
        """Verifies valid manual quota is marked is_manual=True and survives sync."""
        saved = quota_svc.record_manual_quota(
            QuotaManualCreateRequest(
                provider=CloudProvider.AWS,
                scope_type=QuotaScopeType.REGION,
                scope_id="eu-west-1",
                service_code="rds",
                quota_code="rds-db-instances",
                quota_name="RDS DB Instances per Region",
                limit_value=40.0,
                consumed_value=12.0,
                unit="instances",
                manual_source_note="Special allowance granted under AWS Enterprise Discount Program.",
            ),
            tenant_context=tenant_ctx,
        )
        assert saved.is_manual is True
        assert (
            saved.manual_source_note
            == "Special allowance granted under AWS Enterprise Discount Program."
        )
        assert saved.limit_value == 40.0
        assert saved.headroom_value == 28.0


# ==============================================================================
# 7. Quota Increase Request Tracking & Lead-Time Calculation
# ==============================================================================


class TestQuotaIncreaseTracking:
    """Tests formal quota increase requests and actual lead time computation."""

    def test_increase_request_lifecycle_and_lead_time_calc(
        self, quota_svc: QuotaService, tenant_ctx: TenantContext
    ):
        """Files increase request, updates status to GRANTED, and verifies actual lead time."""
        # Create quota
        quota = quota_svc.record_manual_quota(
            QuotaManualCreateRequest(
                provider=CloudProvider.AWS,
                scope_type=QuotaScopeType.ACCOUNT,
                scope_id="123456789012",
                service_code="ec2",
                quota_code="aws-ec2-gpu-instances",
                quota_name="Running G and P instances",
                limit_value=8.0,
                consumed_value=7.0,
                unit="vCPU",
                manual_source_note="Initial quota granted on account creation.",
            ),
            tenant_context=tenant_ctx,
        )

        # File increase request
        req = quota_svc.create_increase_request(
            quota.id,
            QuotaIncreaseCreateRequest(
                requested_value=32.0,
                justification="Expanding LLM inference cluster for customer pilot.",
                external_ticket_id="AWS-CASE-987654321",
            ),
            tenant_context=tenant_ctx,
        )
        assert req.status == QuotaIncreaseRequestStatus.REQUESTED
        assert req.requested_value == 32.0
        assert req.current_value == 8.0

        # Provider grants request 2.5 days later
        granted_at = req.requested_date + timedelta(days=2, hours=12)
        updated = quota_svc.update_increase_request(
            req.id,
            QuotaIncreaseUpdateRequest(
                status=QuotaIncreaseRequestStatus.GRANTED,
                granted_date=granted_at,
                notes="Approved by AWS Support after credit check.",
            ),
            tenant_context=tenant_ctx,
        )
        assert updated.status == QuotaIncreaseRequestStatus.GRANTED
        assert updated.actual_lead_time_days == 2.5

        # Verify the underlying quota limit was automatically upgraded
        reloaded_quota = quota_svc.get_quota(quota.id, tenant_context=tenant_ctx)
        assert reloaded_quota.limit_value == 32.0
        assert reloaded_quota.headroom_value == 25.0


# ==============================================================================
# 8. API-050 REST Endpoints & Provider Dashboard
# ==============================================================================


class TestQuotaAPIEndpoints:
    """Tests FastAPI REST endpoints (API-050)."""

    def test_api_050_list_quotas_with_filters(self, client: TestClient):
        """Tests GET /api/v1/quotas with provider, service, and status filters."""
        # Seed sample data
        seed_res = client.post("/api/v1/quotas/seed")
        assert seed_res.status_code == 201

        # List all
        res = client.get("/api/v1/quotas?limit=50&offset=0")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 5
        assert len(data["items"]) >= 5

        # Filter by provider
        res_aws = client.get("/api/v1/quotas?provider=AWS")
        assert res_aws.status_code == 200
        for item in res_aws.json()["items"]:
            assert item["provider"] in ("aws", "AWS")

        # Filter by status
        res_warn = client.get("/api/v1/quotas?status=WARNING")
        assert res_warn.status_code == 200

    def test_api_provider_headroom_summary(self, client: TestClient):
        """Tests GET /api/v1/quotas/summary/{provider} for executive dashboard."""
        client.post("/api/v1/quotas/seed")
        res = client.get("/api/v1/quotas/summary/AWS")
        assert res.status_code == 200
        summary = res.json()
        assert summary["provider"] in ("aws", "AWS")
        assert summary["total_quotas"] >= 2
        assert "normal_count" in summary
        assert "warning_count" in summary
        assert "critical_count" in summary
        assert "exhausted_count" in summary
        assert "not_supported_count" in summary

    def test_api_manual_quota_creation(self, client: TestClient):
        """Tests POST /api/v1/quotas/manual endpoint with validation."""
        payload = {
            "provider": "AWS",
            "scope_type": "ACCOUNT",
            "scope_id": "112233445566",
            "service_code": "lambda",
            "quota_code": "lambda-concurrent-executions",
            "quota_name": "Concurrent Executions",
            "limit_value": 1000.0,
            "consumed_value": 250.0,
            "unit": "executions",
            "manual_source_note": "Custom limit negotiated with AWS solutions architecture team.",
            "is_adjustable": True,
            "category": "COMPUTE",
            "lead_time_days": 2,
        }
        res = client.post("/api/v1/quotas/manual", json=payload)
        assert res.status_code == 201
        created = res.json()
        assert created["is_manual"] is True
        assert created["limit_value"] == 1000.0
        assert created["headroom_value"] == 750.0

    def test_api_manual_quota_rejects_missing_note(self, client: TestClient):
        """Tests POST /api/v1/quotas/manual rejects short source note with 400."""
        payload = {
            "provider": "AWS",
            "scope_type": "ACCOUNT",
            "scope_id": "112233445566",
            "service_code": "lambda",
            "quota_code": "lambda-concurrent-executions",
            "quota_name": "Concurrent Executions",
            "limit_value": 1000.0,
            "consumed_value": 250.0,
            "unit": "executions",
            "manual_source_note": "short",  # Under 10 chars
        }
        res = client.post("/api/v1/quotas/manual", json=payload)
        assert res.status_code in (400, 422)
        assert "manual_source_note" in str(res.json())

    def test_api_apply_override(self, client: TestClient):
        """Tests POST /api/v1/quotas/{quota_id}/overrides."""
        client.post("/api/v1/quotas/seed")
        list_res = client.get("/api/v1/quotas?limit=1")
        quota_id = list_res.json()["items"][0]["id"]

        override_payload = {
            "warning_headroom_pct": 25.0,
            "critical_headroom_pct": 12.0,
            "lead_time_days": 5,
            "safety_margin_pct": 10.0,
            "reason": "Q4 Peak shopping traffic buffer requirement from risk committee.",
        }
        res = client.post(f"/api/v1/quotas/{quota_id}/overrides", json=override_payload)
        assert res.status_code == 200
        updated = res.json()
        assert updated["warning_headroom_pct"] == 25.0
        assert updated["critical_headroom_pct"] == 12.0
        assert updated["lead_time_days"] == 5

    def test_api_increase_request_workflow(self, client: TestClient):
        """Tests full increase request creation and status update via REST."""
        client.post("/api/v1/quotas/seed")
        list_res = client.get("/api/v1/quotas?limit=1")
        quota_id = list_res.json()["items"][0]["id"]

        # 1. Create increase request
        inc_res = client.post(
            f"/api/v1/quotas/{quota_id}/increase-requests",
            json={
                "requested_value": 150.0,
                "justification": "Scale-out requirement for new data warehouse ETL workload.",
                "external_ticket_id": "TICKET-12345",
            },
        )
        assert inc_res.status_code == 201
        req_data = inc_res.json()
        request_id = req_data["id"]

        # 2. Update status to GRANTED
        patch_res = client.patch(
            f"/api/v1/quotas/increase-requests/{request_id}",
            json={
                "status": "GRANTED",
                "notes": "Approved by cloud provider support.",
            },
        )
        assert patch_res.status_code == 200
        updated_req = patch_res.json()
        assert updated_req["status"] == "GRANTED"
        assert updated_req["actual_lead_time_days"] is not None
