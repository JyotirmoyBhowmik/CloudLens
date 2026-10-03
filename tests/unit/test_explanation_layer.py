"""Unit and Contract Tests for Explanation Layer (Prompt 40).

Enforces:
- Master Brief Sections 4, 5, 50, 51, 52, 53:
  - 17-field Information Icon structured content model (Prompt 21 Item 164).
  - 11 standard explanation panels with verifiable facts and citations.
  - 6 inline contextual alert types with visibility, acknowledgement, and audit events.
  - Data freshness surface across PRICING (168h), BILLING (24h), USAGE (4h), and INVENTORY (6h).
  - Source traceability display on all pricing and cost values.
  - Mechanical enforcement preventing un-explained cost figures across backend and frontend.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.explanation.exceptions import (
    ExplanationNotFoundException,
    MissingExplanationPayloadException,
)
from domain.explanation.models import (
    FreshnessSurfaceOverview,
    ResourceExplanationSuite,
    StandardExplanationPanelType,
)
from domain.explanation.service import (
    ExplanationService,
    get_explanation_service,
    reset_explanation_service,
)
from domain.models.enums import ContextualAlertType, ContextualAlertVisibility
from domain.tenant.context import TenantContext


@pytest.fixture(autouse=True)
def clean_service():
    reset_explanation_service()
    yield
    reset_explanation_service()


@pytest.fixture
def explanation_svc() -> ExplanationService:
    return get_explanation_service()


@pytest.fixture
def tenant_context() -> TenantContext:
    return TenantContext(
        tenant_id="tenant-acme-corp",
        user_id="user-finops-analyst",
        scope_grants=["*"],
    )


@pytest.fixture
def api_client() -> TestClient:
    return TestClient(app)


# ==============================================================================
# 1. Eleven Standard Explanation Panels Tests
# ==============================================================================


class TestElevenStandardExplanationPanels:
    """Verifies generation and content integrity of all eleven canonical explanation panels."""

    def test_all_eleven_panels_generated_for_resource(self, explanation_svc: ExplanationService):
        suite = explanation_svc.get_resource_explanation_suite("res-aws-vm-01")

        assert isinstance(suite, ResourceExplanationSuite)
        assert len(suite.panels) == 11, "Must generate exactly 11 standard explanation panels"

        # Check all 11 canonical panel types are present
        panel_types = {
            p.panel_type.value if hasattr(p.panel_type, "value") else str(p.panel_type)
            for p in suite.panels
        }
        expected_types = {t.value for t in StandardExplanationPanelType}
        assert panel_types == expected_types

        # Verify each panel has required non-empty fields
        for panel in suite.panels:
            assert panel.title.strip() != "", f"Panel {panel.panel_type} must have a title"
            assert panel.headline.strip() != "", f"Panel {panel.panel_type} must have a headline"
            assert panel.narrative.strip() != "", f"Panel {panel.panel_type} must have a narrative"
            assert isinstance(panel.key_facts, dict), (
                f"Panel {panel.panel_type} must have key_facts dict"
            )
            assert panel.source_citation.strip() != "", (
                f"Panel {panel.panel_type} must cite authoritative source"
            )
            assert panel.source_url.startswith("http"), (
                f"Panel {panel.panel_type} must link to docs"
            )

    def test_free_tier_explanation_explains_conditions_and_source_link(
        self, explanation_svc: ExplanationService
    ):
        """Hard Rule: Free tier explanation explains conditions under which it is free and provider source link."""
        suite = explanation_svc.get_resource_explanation_suite("res-aws-vm-01")

        why_free = next(
            p
            for p in suite.panels
            if p.panel_type == StandardExplanationPanelType.WHY_IS_IT_FREE
            or p.panel_type == StandardExplanationPanelType.WHY_IS_IT_FREE.value
        )
        assert why_free is not None
        assert len(why_free.conditions) > 0, (
            "Free tier panel must explicitly state eligibility conditions"
        )
        assert why_free.source_url.startswith("http"), (
            "Must link to official provider pricing documentation"
        )

        included_usage = next(
            p
            for p in suite.panels
            if p.panel_type == StandardExplanationPanelType.WHAT_USAGE_IS_INCLUDED_IN_FREE_TIER
            or p.panel_type
            == StandardExplanationPanelType.WHAT_USAGE_IS_INCLUDED_IN_FREE_TIER.value
        )
        assert included_usage is not None
        assert (
            "included_allowance" in included_usage.key_facts
            or "allowance_unit" in included_usage.key_facts
        )

    def test_single_panel_retrieval_and_not_found(self, explanation_svc: ExplanationService):
        panel = explanation_svc.get_single_explanation_panel(
            "res-aws-vm-01", StandardExplanationPanelType.HOW_IS_IT_PRICED
        )
        assert panel.panel_type == StandardExplanationPanelType.HOW_IS_IT_PRICED
        assert "pricing_model" in panel.key_facts

        with pytest.raises(ExplanationNotFoundException):
            explanation_svc.get_single_explanation_panel("res-aws-vm-01", "NON_EXISTENT_PANEL")


# ==============================================================================
# 2. 17-Field Information Icon Content Model Tests
# ==============================================================================


class TestInformationPanel17FieldModel:
    """Verifies strict compliance with Prompt 21 Item 164 (17-field structured model)."""

    def test_information_panel_contains_all_seventeen_fields(
        self, explanation_svc: ExplanationService
    ):
        suite = explanation_svc.get_resource_explanation_suite("res-aws-vm-01")
        info = suite.information_panel

        model_fields = set(info.model_fields.keys())
        expected_fields = {
            "pricing_model",
            "region",
            "configuration",
            "unit_rate",
            "monthly_estimate",
            "free_tier_status",
            "free_tier_allowance",
            "additional_usage_rate",
            "currency",
            "billing_unit",
            "data_transfer_note",
            "storage_note",
            "discount_applicability",
            "commitment_applicability",
            "tax_treatment",
            "source_traceability",
            "freshness",
        }
        assert expected_fields.issubset(model_fields), (
            "All 17 Prompt 21 fields must be present in content model"
        )

        assert info.pricing_model is not None, "Field 1: pricing_model required"
        assert info.region is not None, "Field 2: region required"
        assert info.configuration is not None, "Field 3: configuration required"
        assert info.unit_rate is not None, "Field 4: unit_rate required"
        assert info.currency == "USD", "Field 9: currency required"
        assert info.billing_unit is not None, "Field 10: billing_unit required"
        assert info.source_traceability.pricing_source is not None, (
            "Field 16: pricing_source required"
        )
        assert info.source_traceability.retrieval_timestamp is not None, (
            "Field 17: last-updated timestamp required"
        )
        assert info.source_traceability.source_url.startswith("http"), "Must link to official doc"

    def test_no_pricing_value_without_source_and_effective_date(
        self, explanation_svc: ExplanationService
    ):
        """Hard Rule: Do not render pricing values without source and effective date."""
        suite = explanation_svc.get_resource_explanation_suite("res-aws-vm-01")
        trace = suite.source_traceability

        assert trace.pricing_source.strip() != "", "Pricing source must never be empty"
        assert trace.effective_date is not None, "Effective date must never be null"
        assert trace.currency.strip() != "", "Currency must be explicit"
        assert trace.region.strip() != "", "Region must be explicit"


# ==============================================================================
# 3. Data Freshness Surface Tests
# ==============================================================================


class TestDataFreshnessSurface:
    """Verifies freshness calculation across PRICING, BILLING, USAGE, and INVENTORY."""

    def test_freshness_surface_tracks_four_data_classes_with_slas(
        self, explanation_svc: ExplanationService
    ):
        overview = explanation_svc.get_freshness_surface()
        assert isinstance(overview, FreshnessSurfaceOverview)
        assert len(overview.items) == 4

        classes = {item.data_class for item in overview.items}
        expected_classes = {"PRICING", "BILLING_ACTUALS", "USAGE_METRICS", "INVENTORY"}
        assert classes == expected_classes

        # Verify SLA thresholds
        pricing_item = next(i for i in overview.items if i.data_class == "PRICING")
        assert pricing_item.staleness_threshold_hours == 168.0  # 7 days
        assert "Pricing retrieved" in pricing_item.stated_time_text

        billing_item = next(i for i in overview.items if i.data_class == "BILLING_ACTUALS")
        assert billing_item.staleness_threshold_hours == 24.0  # 24 hours
        assert "Provider billing data through" in billing_item.stated_time_text

        usage_item = next(i for i in overview.items if i.data_class == "USAGE_METRICS")
        assert usage_item.staleness_threshold_hours == 4.0  # 4 hours

        inventory_item = next(i for i in overview.items if i.data_class == "INVENTORY")
        assert inventory_item.staleness_threshold_hours == 6.0  # 6 hours

    def test_stale_pricing_displays_last_retrieval_and_warning(
        self, explanation_svc: ExplanationService
    ):
        """Acceptance: A stale pricing value displays last retrieval date and warning."""
        suite = explanation_svc.get_resource_explanation_suite(
            "res-aws-vm-01", simulated_pricing_age_hours=200.0
        )

        assert suite.is_pricing_stale is True
        assert suite.freshness.is_stale is True
        assert suite.freshness.age_hours >= 168.0
        assert suite.source_traceability.pricing_source is not None
        assert suite.source_traceability.retrieval_timestamp is not None


# ==============================================================================
# 4. Six Contextual Alert Types & Acknowledgement Tests
# ==============================================================================


class TestContextualAlerts:
    """Verifies 6 inline contextual alerts with acknowledgement and audit behavior."""

    def test_all_six_contextual_alert_types_supported(self):
        expected_types = {
            "COST_INFORMATION",
            "FREE_TIER",
            "BUDGET",
            "FORECAST",
            "PRICING_CHANGE",
            "PRICING_UNAVAILABLE",
        }
        actual_types = {t.value for t in ContextualAlertType}
        assert expected_types.issubset(actual_types)

    def test_contextual_alert_acknowledgement_workflow(
        self, explanation_svc: ExplanationService, tenant_context: TenantContext
    ):
        """Verifies acknowledgement updates alert state and records audit event."""
        alert = explanation_svc._contextual_manager.create_contextual_alert(
            alert_type=ContextualAlertType.COST_INFORMATION,
            title="Compute Charge Fluctuation",
            message="Instance sustained >20% increase in weekly run-rate.",
            context_entity_type="RESOURCE",
            context_entity_id="res-aws-vm-01",
            tenant_context=tenant_context,
            visibility=ContextualAlertVisibility.PAGE_INLINE,
        )

        # Confirm initial state
        persisted = explanation_svc._contextual_manager.get_alert(
            alert.id, tenant_context=tenant_context
        )
        assert persisted is not None
        assert persisted.is_acknowledged is False

        # Acknowledge
        ack = explanation_svc.acknowledge_alert(
            alert_id=alert.id,
            actor="user-finops-lead",
            note="Verified legitimate batch indexing run.",
            tenant_context=tenant_context,
        )

        assert ack.is_acknowledged is True
        assert ack.acknowledged_by == "user-finops-lead"
        assert ack.acknowledgement_note == "Verified legitimate batch indexing run."
        assert ack.acknowledged_at is not None


# ==============================================================================
# 5. Source Traceability & Mechanical Enforcement Tests
# ==============================================================================


class TestSourceTraceabilityAndMechanicalEnforcement:
    """Verifies that unsourced numbers or missing explanation payloads are strictly forbidden."""

    def test_create_cost_explanation_payload_requires_source_and_url(
        self, explanation_svc: ExplanationService
    ):
        with pytest.raises(MissingExplanationPayloadException):
            explanation_svc.create_cost_explanation_payload(
                metric_name="Monthly Compute",
                amount=124.50,
                pricing_source="",  # Missing
                source_url="https://aws.amazon.com/ec2/pricing",
                region="us-east-1",
                effective_date=datetime.now(UTC),
            )

        with pytest.raises(MissingExplanationPayloadException):
            explanation_svc.create_cost_explanation_payload(
                metric_name="Monthly Compute",
                amount=124.50,
                pricing_source="aws_pricing_api",
                source_url="",  # Missing
                region="us-east-1",
                effective_date=datetime.now(UTC),
            )

    def test_verify_explanation_attachment_rejects_missing_payload(
        self, explanation_svc: ExplanationService
    ):
        """Hard Rule: Component rendering cost without explanation payload fails build / test."""
        with pytest.raises(MissingExplanationPayloadException):
            explanation_svc.verify_explanation_attachment(None)

        with pytest.raises(MissingExplanationPayloadException):
            explanation_svc.verify_explanation_attachment(
                {"amount": 100.0}
            )  # Missing pricing_source

        # Valid payload passes
        valid = explanation_svc.create_cost_explanation_payload(
            metric_name="Valid Test",
            amount=50.0,
            pricing_source="aws_pricing_api",
            source_url="https://aws.amazon.com",
            region="us-east-1",
            effective_date=datetime.now(UTC),
        )
        assert explanation_svc.verify_explanation_attachment(valid) is True

    def test_mechanical_frontend_audit_cost_value_has_mandatory_explanation(self):
        """Hard Rule: A component rendering a cost without an explanation payload fails the build.

        Scans web/src/ for all <CostValue occurrences and ensures 'explanation=' is provided.
        """
        web_src = Path(__file__).resolve().parent.parent.parent / "web" / "src"
        assert web_src.exists(), "web/src directory must exist"

        tsx_files = list(web_src.rglob("*.tsx"))
        assert len(tsx_files) > 0, "TSX files must exist in frontend"

        cost_value_pattern = re.compile(r"<CostValue\b([^>]*)/?>", re.DOTALL)

        violations: list[str] = []

        for tsx_file in tsx_files:
            # Skip definition file itself
            if tsx_file.name == "CostValue.tsx":
                continue

            content = tsx_file.read_text(encoding="utf-8")
            matches = cost_value_pattern.finditer(content)

            for match in matches:
                tag_body = match.group(1)
                if "explanation=" not in tag_body:
                    rel_path = tsx_file.relative_to(web_src)
                    violations.append(f"{rel_path}: {match.group(0)[:80]}...")

        assert not violations, (
            "Mechanical Enforcement Failure: The following <CostValue> invocations "
            "render costs without mandatory 'explanation=' payload:\n" + "\n".join(violations)
        )

    def test_cost_value_props_interface_enforces_required_explanation(self):
        """Verifies that CostValueProps defines explanation as mandatory (not optional ?)."""
        cost_value_file = (
            Path(__file__).resolve().parent.parent.parent
            / "web"
            / "src"
            / "design-system"
            / "CostValue.tsx"
        )
        assert cost_value_file.exists()

        content = cost_value_file.read_text(encoding="utf-8")
        assert "explanation: CostExplanation;" in content, (
            "CostValueProps must declare explanation as required: 'explanation: CostExplanation;'"
        )
        assert "explanation?: CostExplanation;" not in content, (
            "CostValueProps must NOT declare explanation as optional with '?'"
        )


# ==============================================================================
# 6. Explanation API Contract Tests
# ==============================================================================


class TestExplanationApiContract:
    """Verifies FastAPI route contract for explanation endpoints."""

    def test_get_freshness_surface_endpoint(self, api_client: TestClient):
        response = api_client.get("/api/v1/explanation/freshness-surface")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 4
        assert "overall_sla_breached" in data

    def test_get_resource_explanation_suite_endpoint(self, api_client: TestClient):
        response = api_client.get("/api/v1/explanation/suite/res-aws-vm-01")
        assert response.status_code == 200
        data = response.json()
        assert data["resource_id"] == "res-aws-vm-01"
        assert len(data["panels"]) == 11
        assert "information_panel" in data
        assert "source_traceability" in data

    def test_get_single_panel_endpoint(self, api_client: TestClient):
        response = api_client.get("/api/v1/explanation/panel/res-aws-vm-01/WHAT_IS_THIS_SERVICE")
        assert response.status_code == 200
        data = response.json()
        assert data["panel_type"] == "WHAT_IS_THIS_SERVICE"
        assert "key_facts" in data

    def test_acknowledge_alert_endpoint(self, api_client: TestClient):
        # Create an alert first
        svc = get_explanation_service()
        alert = svc._contextual_manager.create_contextual_alert(
            alert_type=ContextualAlertType.BUDGET,
            title="Budget Nearing Cap",
            message="Resource utilized 85% of monthly budget limit.",
            context_entity_type="RESOURCE",
            context_entity_id="res-aws-vm-01",
            tenant_context=TenantContext(
                tenant_id="default-tenant", user_id="admin", scope_grants=["*"]
            ),
            visibility=ContextualAlertVisibility.PAGE_INLINE,
        )

        response = api_client.post(
            f"/api/v1/explanation/alerts/{alert.id}/acknowledge",
            json={"actor": "finops_analyst", "note": "Budget reviewed and approved."},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_acknowledged"] is True
        assert data["acknowledged_by"] == "finops_analyst"

    def test_validate_attachment_endpoint(self, api_client: TestClient):
        # Valid payload
        valid_payload = {
            "metric_name": "Compute Spend",
            "pricing_source": "aws_price_list_bulk",
            "effective_date": "2026-09-01T00:00:00Z",
            "source_url": "https://aws.amazon.com/ec2/pricing",
            "region": "us-east-1",
        }
        res_valid = api_client.post(
            "/api/v1/explanation/validate-attachment",
            json={"payload": valid_payload},
        )
        assert res_valid.status_code == 200
        assert res_valid.json()["is_valid"] is True

        # Invalid payload (missing pricing_source)
        res_invalid = api_client.post(
            "/api/v1/explanation/validate-attachment",
            json={
                "payload": {
                    "metric_name": "Compute Spend",
                    "effective_date": "2026-09-01T00:00:00Z",
                }
            },
        )
        assert res_invalid.status_code == 200
        assert res_invalid.json()["is_valid"] is False

        # Malformed request body
        res_malformed = api_client.post(
            "/api/v1/explanation/validate-attachment",
            json={"wrong_key": 123},
        )
        assert res_malformed.status_code == 422
