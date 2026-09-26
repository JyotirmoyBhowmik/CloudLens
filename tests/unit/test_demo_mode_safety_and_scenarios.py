"""Unit and Integration Tests for Demo Mode Safety, Watermarking, and Scenarios (Prompt 47 Items 30-33).

Validates:
- Safety Interlock 1: Cannot enable Demo Mode on tenant with active live connectors.
- Safety Interlock 2: Cannot attach live cloud connectors to a tenant in Demo Mode.
- Safety Interlock 3: Disabling Demo Mode requires explicit confirm_purge=True, purging data and recording AuditEvent.
- Persistent banner message on all screens.
- Watermark engine on JSON, CSV, and export headers.
- One-command reset: purge, reseed, reload in single action.
- All 7 named demonstration scenarios loaded in single command/click.
- REST API contract for all demo mode endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.config.tenant_settings import TenantSettingsStore
from domain.demo import (
    DEMO_BANNER_TEXT,
    EXPORT_WATERMARK,
    DemoModeService,
    DemoScenario,
)
from domain.models.exceptions import DemoModeSafetyException
from domain.synthetic.mock_generator import DeterministicMockEstateGenerator


@pytest.fixture
def clean_demo_service() -> DemoModeService:
    """Provides a fresh isolated DemoModeService instance for safety tests."""
    tenant_store = TenantSettingsStore()
    generator = DeterministicMockEstateGenerator(seed=42)
    return DemoModeService(tenant_store=tenant_store, generator=generator)


@pytest.fixture
def client() -> TestClient:
    """Test client for FastAPI app."""
    return TestClient(app)


class TestDemoModeSafetyInterlocks:
    """Tests the hard enterprise safety interlocks protecting production from mock contamination."""

    def test_interlock_1_refuses_demo_mode_if_live_connectors_exist(
        self, clean_demo_service: DemoModeService
    ):
        """Safety Rule: Cannot enable Demo Mode on a tenant with active live connectors."""
        tenant_id = "T-PROD-LIVE"
        # Register a live cloud connector
        clean_demo_service.register_connector(
            tenant_id=tenant_id,
            connector_id="conn-aws-prod-01",
            provider_name="aws",
            is_live=True,
        )

        assert clean_demo_service.has_live_connectors(tenant_id) is True

        # Attempt to enable demo mode must raise DemoModeSafetyException
        with pytest.raises(DemoModeSafetyException) as exc_info:
            clean_demo_service.enable_demo_mode(
                tenant_id=tenant_id,
                scenario=DemoScenario.MONTH_END_REVIEW,
                actor_id="admin@cloudlens.internal",
            )
        assert "Cannot enable Demo Mode on tenant 'T-PROD-LIVE'" in str(exc_info.value)
        assert exc_info.value.error_code == "DEMO_MODE_SAFETY_VIOLATION"

    def test_interlock_2_refuses_live_connector_addition_in_demo_mode(
        self, clean_demo_service: DemoModeService
    ):
        """Safety Rule: Live connectors cannot be added to a tenant in Demo Mode."""
        tenant_id = "T-DEMO-SAFE"
        # Enable demo mode successfully first
        clean_demo_service.enable_demo_mode(
            tenant_id=tenant_id,
            scenario=DemoScenario.GOVERNANCE_CLEANUP,
            actor_id="admin@cloudlens.internal",
        )

        status = clean_demo_service.get_status(tenant_id)
        assert status.is_demo_mode is True
        assert status.can_attach_live_connector is False

        # Attempt to register a live connector must fail
        with pytest.raises(DemoModeSafetyException) as exc_info:
            clean_demo_service.register_connector(
                tenant_id=tenant_id,
                connector_id="conn-azure-prod-01",
                provider_name="azure",
                is_live=True,
            )
        assert "Cannot attach live cloud connector" in str(exc_info.value)

        # Simulator connector (is_live=False) is permitted
        clean_demo_service.register_connector(
            tenant_id=tenant_id,
            connector_id="conn-sim-azure-01",
            provider_name="simulator-azure",
            is_live=False,
        )
        assert len(clean_demo_service.get_connectors(tenant_id)) == 1

    def test_interlock_3_disable_requires_confirm_purge_and_records_audit_trail(
        self, clean_demo_service: DemoModeService
    ):
        """Safety Rule: Disabling Demo Mode requires explicit confirm_purge=True, writes AuditEvent."""
        tenant_id = "T-DEMO-DISABLE"
        clean_demo_service.enable_demo_mode(
            tenant_id=tenant_id,
            scenario=DemoScenario.BUDGET_BREACH_INVESTIGATION,
            actor_id="admin@cloudlens.internal",
        )

        # 1. Attempt to disable without confirm_purge must raise DemoModeSafetyException
        with pytest.raises(DemoModeSafetyException) as exc_info:
            clean_demo_service.disable_demo_mode(
                tenant_id=tenant_id,
                confirm_purge=False,
                actor_id="admin@cloudlens.internal",
            )
        assert "confirm_purge=True" in str(exc_info.value)

        # 2. Disable with confirm_purge=True succeeds
        status = clean_demo_service.disable_demo_mode(
            tenant_id=tenant_id,
            confirm_purge=True,
            actor_id="security-officer@cloudlens.internal",
        )
        assert status.is_demo_mode is False
        assert status.banner_message is None
        assert clean_demo_service.get_estate(tenant_id) is None

        # 3. Compliance audit trail must contain recorded event
        audit_events = clean_demo_service.get_audit_trail(tenant_id)
        assert len(audit_events) >= 1
        last_event = audit_events[-1]
        assert last_event.tenant_id == tenant_id
        assert last_event.action == "DEMO_MODE_DISABLED_AND_PURGED"
        assert last_event.actor_id == "security-officer@cloudlens.internal"


class TestDemoModeFeaturesAndWatermarks:
    """Tests persistent banner, watermarking engine, and one-command reset."""

    def test_persistent_banner_and_status(self, clean_demo_service: DemoModeService):
        """Validates persistent banner on status check."""
        tenant_id = "T-DEMO-BANNER"
        clean_demo_service.enable_demo_mode(tenant_id=tenant_id)

        status = clean_demo_service.get_status(tenant_id)
        assert status.is_demo_mode is True
        assert status.banner_message == DEMO_BANNER_TEXT
        assert "DEMO MODE ACTIVE" in status.banner_message

    def test_export_watermarking_engine(self, clean_demo_service: DemoModeService):
        """Validates mandatory watermarks on exported content (Item 30)."""
        tenant_id = "T-DEMO-WM"
        clean_demo_service.enable_demo_mode(tenant_id=tenant_id)

        # 1. Dict watermarking
        sample_dict = {"total_cost": "15000.00", "currency": "USD"}
        wm_dict = clean_demo_service.apply_watermark(sample_dict, tenant_id=tenant_id)
        assert wm_dict["_watermark"] == EXPORT_WATERMARK
        assert wm_dict["_demo_mode"] is True

        # 2. List watermarking
        sample_list = [{"id": 1}, {"id": 2}]
        wm_list = clean_demo_service.apply_watermark(sample_list, tenant_id=tenant_id)
        assert wm_list[0]["_watermark"] == EXPORT_WATERMARK

        # 3. CSV string watermarking
        csv_data = "id,name,cost\n1,vm1,10.00\n"
        wm_csv = clean_demo_service.apply_watermark(csv_data, tenant_id=tenant_id, format="csv")
        assert wm_csv.startswith(f"# WATERMARK: {EXPORT_WATERMARK}\n")

    def test_one_command_demo_reset(self, clean_demo_service: DemoModeService):
        """Validates one-command demo reset: purge, reseed, reload (Item 31)."""
        tenant_id = "T-DEMO-RESET"
        clean_demo_service.enable_demo_mode(tenant_id=tenant_id)

        result = clean_demo_service.reset_demo(
            tenant_id=tenant_id,
            scenario=DemoScenario.UNEXPECTED_COST_INCREASE,
            seed=101,
        )

        assert result.status == "COMPLETED"
        assert result.tenant_id == tenant_id
        assert result.scenario == "Unexpected Cost Increase"
        assert result.reseeded_resources > 0
        assert result.reseeded_cost_facts > 0
        assert len(result.manifest_hash) == 64  # SHA256 hex string
        assert result.elapsed_seconds < 2.0

        # Verify estate is queryable
        estate = clean_demo_service.get_estate(tenant_id)
        assert estate is not None
        assert estate.manifest.seed == 101


class TestDemoScenarios:
    """Validates all 7 named demonstration scenarios (Item 32)."""

    def test_all_seven_named_scenarios_available(self, clean_demo_service: DemoModeService):
        """Validates that exactly 7 scenarios are registered with full metadata."""
        scenarios = clean_demo_service.get_scenarios()
        assert len(scenarios) == 7

        scenario_names = {sc.scenario.value for sc in scenarios}
        expected_names = {
            "Month-End Review",
            "Budget Breach Investigation",
            "Unexpected Cost Increase",
            "Governance Clean-Up",
            "Onboarding a New Provider",
            "Reconciliation Variance",
            "Free-Tier Exhaustion",
        }
        assert scenario_names == expected_names

        for sc in scenarios:
            assert sc.title
            assert sc.description
            assert sc.focus_story
            assert len(sc.key_metrics) >= 1

    def test_load_each_named_scenario(self, clean_demo_service: DemoModeService):
        """Validates that all 7 scenarios can be loaded in one click/call."""
        tenant_id = "T-DEMO-SCENARIOS"
        for sc_enum in DemoScenario:
            info = clean_demo_service.load_scenario(tenant_id=tenant_id, scenario=sc_enum)
            assert info.scenario == sc_enum
            status = clean_demo_service.get_status(tenant_id)
            assert status.active_scenario == sc_enum.value


class TestDemoModeRestApi:
    """Integration tests for Demo Mode REST API endpoints."""

    def test_rest_api_demo_lifecycle(self, client: TestClient):
        """Tests complete demo mode REST API flow."""
        tenant = "T-API-DEMO"

        # 1. Enable Demo Mode
        resp = client.post(
            "/api/v1/system/demo/mode/enable",
            json={"tenant_id": tenant, "scenario": "Month-End Review"},
            headers={"X-Actor-ID": "admin@cloudlens.internal"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_demo_mode"] is True
        assert data["active_scenario"] == "Month-End Review"
        assert "DEMO MODE ACTIVE" in data["banner_message"]

        # 2. Get Status
        resp = client.get(f"/api/v1/system/demo/mode/status?tenant_id={tenant}")
        assert resp.status_code == 200
        assert resp.json()["is_demo_mode"] is True

        # 3. List Scenarios
        resp = client.get("/api/v1/system/demo/scenarios")
        assert resp.status_code == 200
        scenarios = resp.json()
        assert len(scenarios) == 7

        # 4. Load Specific Scenario
        resp = client.post(
            "/api/v1/system/demo/scenarios/load",
            json={"tenant_id": tenant, "scenario": "Budget Breach Investigation"},
        )
        assert resp.status_code == 200
        assert resp.json()["scenario"] == "Budget Breach Investigation"

        # 5. One-Command Reset
        resp = client.post(
            f"/api/v1/system/demo/reset?tenant_id={tenant}&scenario=Governance%20Clean-Up&seed=42"
        )
        assert resp.status_code == 200
        reset_res = resp.json()
        assert reset_res["status"] == "COMPLETED"
        assert reset_res["reseeded_resources"] > 0

        # 6. Export Demo Data as JSON with watermark
        resp = client.get(f"/api/v1/system/demo/export?tenant_id={tenant}&format=json&entity=costs")
        assert resp.status_code == 200
        assert resp.headers.get("x-cloudlens-demo-mode") == "true"
        assert resp.headers.get("x-cloudlens-watermark") == EXPORT_WATERMARK
        export_json = resp.json()
        assert export_json[0]["_watermark"] == EXPORT_WATERMARK

        # 7. Export Demo Data as CSV with watermark
        resp = client.get(f"/api/v1/system/demo/export?tenant_id={tenant}&format=csv&entity=costs")
        assert resp.status_code == 200
        assert resp.headers.get("x-cloudlens-demo-mode") == "true"
        assert resp.text.startswith(f"# WATERMARK: {EXPORT_WATERMARK}\n")

        # 8. Disable Demo Mode without confirm_purge fails
        resp = client.post(
            f"/api/v1/system/demo/mode/disable?tenant_id={tenant}&confirm_purge=false",
            headers={"X-Actor-ID": "admin@cloudlens.internal"},
        )
        assert resp.status_code == 400

        # 9. Disable Demo Mode with confirm_purge succeeds
        resp = client.post(
            f"/api/v1/system/demo/mode/disable?tenant_id={tenant}&confirm_purge=true",
            headers={"X-Actor-ID": "admin@cloudlens.internal"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_demo_mode"] is False
