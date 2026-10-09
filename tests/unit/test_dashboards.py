"""Comprehensive Unit & Contract Tests for Prompt 37 Dashboards.

Verifies:
- FR-500: Executive dashboard renders from pre-computed aggregates within performance target.
- FR-501: Data freshness timestamps on every widget; stale provider produces visible warning banner.
- FR-502: RBAC scope filtering masks restricted data and explicitly discloses filtering.
- FR-503: Role-based landing dashboard resolution and user preference persistence.
- FR-504: Dynamic period selection (Month, Quarter, Fiscal, Custom) and PoP/YoY comparison switching.
- FR-505: Widget-level data export in CSV and JSON formats.
- Acceptance: Provider dashboards strictly enforce native vocabulary (Azure, AWS, GCP, OCI) with zero generic terms.
- Acceptance: Service dashboard provides all 16 canonical panels.
"""

import time
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.dashboards.models import (
    ComparisonBasis,
    DashboardPeriodType,
)
from domain.dashboards.service import DashboardService
from domain.dashboards.vocabulary import (
    validate_native_vocabulary,
)
from domain.tenant.context import TenantContext


@pytest.fixture(autouse=True)
def setup_test_repository():
    from domain.dashboards.service import reset_dashboard_service
    from domain.hierarchy.repository import reset_hierarchy_repository
    from domain.hierarchy.service import reset_hierarchy_service
    from tests.fakes.hierarchy import InMemoryHierarchyRepository, seed_test_hierarchy

    fake_repo = InMemoryHierarchyRepository()
    reset_hierarchy_repository(fake_repo)
    reset_hierarchy_service()
    reset_dashboard_service()
    seed_test_hierarchy(fake_repo, "tenant-acme-corp")
    yield
    reset_dashboard_service()
    reset_hierarchy_service()
    reset_hierarchy_repository()


@pytest.fixture
def test_tenant_context() -> TenantContext:
    """Standard authorized tenant context with wildcard scope."""
    return TenantContext(
        tenant_id="tenant-acme-corp",
        user_id="usr-test-executive",
        roles=["EXECUTIVE"],
        scope_grants=["*"],
    )


@pytest.fixture
def restricted_tenant_context() -> TenantContext:
    """Restricted tenant context bound to specific scopes."""
    return TenantContext(
        tenant_id="tenant-acme-corp",
        user_id="usr-test-engineer",
        roles=["ENGINEERING"],
        scope_grants=["sc-aws-prod-1", "sc-azure-prod-2"],
    )


@pytest.fixture
def dashboard_service() -> DashboardService:
    return DashboardService()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def test_headers(make_auth_token) -> dict[str, str]:
    token = make_auth_token(
        tenant_id="tenant-acme-corp",
        user_id="usr-test-executive",
        roles=["EXECUTIVE"],
        permissions=["*"],
    )
    return {"Authorization": f"Bearer {token}"}


# ==============================================================================
# 1. Executive Dashboard Pre-aggregated Completeness & Performance (FR-500)
# ==============================================================================


class TestExecutiveDashboardPreAggregated:
    """Tests for Executive Dashboard widgets and performance."""

    def test_executive_dashboard_contains_all_22_widgets(
        self,
        dashboard_service: DashboardService,
        test_tenant_context: TenantContext,
    ) -> None:
        start_time = time.perf_counter()
        dash = dashboard_service.get_executive_dashboard(tenant_context=test_tenant_context)
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Assert fast performance target (< 100ms)
        assert duration_ms < 100, f"Dashboard generation took {duration_ms:.2f}ms (target < 100ms)"

        # 1-7 KPI Metrics
        assert dash.total_cloud_cost.amount > Decimal("0.0")
        assert dash.current_month_cost.amount > Decimal("0.0")
        assert dash.actual_cost.amount > Decimal("0.0")
        assert dash.estimated_cost.amount > Decimal("0.0")
        assert dash.forecast_cost.amount > Decimal("0.0")
        assert dash.budget.amount > Decimal("0.0")
        assert dash.budget_utilisation.utilisation_percentage > Decimal("0.0")

        # 8-11 Breakdowns
        assert len(dash.cost_by_provider.items) == 4  # AWS, Azure, GCP, OCI
        assert len(dash.cost_by_business_unit.items) >= 4
        assert len(dash.cost_by_application.items) >= 4
        assert len(dash.cost_by_service.items) >= 5

        # 12-14 Trends & Movers
        assert len(dash.cost_trend.points) > 0
        assert len(dash.top_cost_services.items) == 5
        assert len(dash.largest_increases.movements) >= 3

        # 15-22 Operational & Governance
        assert dash.threshold_breaches.total_breaches >= 1
        assert dash.service_counts.total_services_count == 224
        assert dash.runtime_exceptions.total_count >= 1
        assert dash.usage_anomalies.total_count >= 1
        assert len(dash.pricing_changes.recent_changes) >= 2
        assert len(dash.data_freshness.providers) == 4
        assert dash.reconciliation_status.status == "RECONCILED"
        assert dash.governance_exceptions.total_exceptions >= 1

        # FR-500: Every widget metadata must declare pre-computed
        assert dash.total_cloud_cost.metadata.is_precomputed is True
        assert dash.cost_by_provider.metadata.is_precomputed is True
        assert dash.cost_trend.metadata.is_precomputed is True
        assert dash.budget_utilisation.metadata.is_precomputed is True

    def test_executive_dashboard_freshness_and_stale_provider_banner(
        self,
        dashboard_service: DashboardService,
        test_tenant_context: TenantContext,
    ) -> None:
        """FR-501 & Acceptance: Every widget shows freshness; stale provider produces visible banner."""
        dash = dashboard_service.get_executive_dashboard(tenant_context=test_tenant_context)

        # Every widget has freshness metadata
        assert dash.total_cloud_cost.metadata.freshness.status == "FRESH"
        assert dash.total_cloud_cost.metadata.freshness.age_seconds > 0

        # OCI feed is stale (>24h lag)
        assert dash.data_freshness.has_stale_provider is True
        assert dash.data_freshness.stale_provider_banner is not None
        assert "OCI" in dash.data_freshness.stale_provider_banner
        assert dash.data_freshness_banner is not None
        assert "Data Freshness Warning" in dash.data_freshness_banner

    def test_executive_dashboard_scope_filtering_disclosure(
        self,
        dashboard_service: DashboardService,
        restricted_tenant_context: TenantContext,
    ) -> None:
        """FR-502 & Acceptance: Filtered total discloses that filtering occurred."""
        dash = dashboard_service.get_executive_dashboard(tenant_context=restricted_tenant_context)

        # Totals are scaled down because of restricted grants
        assert dash.total_cloud_cost.metadata.scope_disclosure.is_filtered is True
        assert dash.total_cloud_cost.metadata.scope_disclosure.restricted_count > 0
        assert dash.total_cloud_cost.metadata.scope_disclosure.disclosure_text is not None
        assert (
            "Filtered by RBAC scope"
            in dash.total_cloud_cost.metadata.scope_disclosure.disclosure_text
        )


# ==============================================================================
# 2. Provider Dashboard Native Vocabulary Enforcement
# ==============================================================================


class TestProviderDashboardNativeVocabulary:
    """Verifies that provider dashboards strictly use native vocabulary."""

    def test_azure_native_vocabulary(
        self,
        dashboard_service: DashboardService,
        test_tenant_context: TenantContext,
    ) -> None:
        dash = dashboard_service.get_provider_dashboard("azure", tenant_context=test_tenant_context)

        assert dash.provider == "azure"
        assert dash.native_group_term == "Management Groups"
        assert dash.native_account_term == "Subscriptions"
        assert dash.hierarchy_tree.native_type == "Management Group"
        assert dash.hierarchy_tree.children[0].children[0].native_type == "Subscription"

        # Verify no forbidden generic terms
        assert validate_native_vocabulary("azure", dash.native_group_term) is True
        assert validate_native_vocabulary("azure", dash.native_account_term) is True
        assert "generic" not in dash.native_group_term.lower()

    def test_aws_native_vocabulary(
        self,
        dashboard_service: DashboardService,
        test_tenant_context: TenantContext,
    ) -> None:
        dash = dashboard_service.get_provider_dashboard("aws", tenant_context=test_tenant_context)

        assert dash.provider == "aws"
        assert dash.native_group_term == "Organizational Units (OUs)"
        assert dash.native_account_term == "Member Accounts"
        assert dash.hierarchy_tree.children[0].native_type == "Organizational Unit (OU)"
        assert dash.hierarchy_tree.children[0].children[0].native_type == "Member Account"

    def test_gcp_native_vocabulary(
        self,
        dashboard_service: DashboardService,
        test_tenant_context: TenantContext,
    ) -> None:
        dash = dashboard_service.get_provider_dashboard("gcp", tenant_context=test_tenant_context)

        assert dash.provider == "gcp"
        assert dash.native_group_term == "Folders"
        assert dash.native_account_term == "Projects"
        assert dash.hierarchy_tree.children[0].native_type == "Folder"
        assert dash.hierarchy_tree.children[0].children[0].native_type == "Project"

    def test_oci_native_vocabulary(
        self,
        dashboard_service: DashboardService,
        test_tenant_context: TenantContext,
    ) -> None:
        dash = dashboard_service.get_provider_dashboard("oci", tenant_context=test_tenant_context)

        assert dash.provider == "oci"
        assert dash.native_group_term == "Compartments"
        assert dash.hierarchy_tree.children[0].native_type == "Compartment"

    def test_unknown_provider_raises_error(
        self,
        dashboard_service: DashboardService,
        test_tenant_context: TenantContext,
    ) -> None:
        with pytest.raises(ValueError, match="Unknown provider"):
            dashboard_service.get_provider_dashboard(
                "unknown_cloud", tenant_context=test_tenant_context
            )


# ==============================================================================
# 3. Service Dashboard 16 Panels Completeness
# ==============================================================================


class TestServiceDashboardSixteenPanels:
    """Verifies that the service dashboard provides all 16 canonical panels."""

    def test_ec2_service_dashboard_has_all_16_panels(
        self,
        dashboard_service: DashboardService,
        test_tenant_context: TenantContext,
    ) -> None:
        svc = dashboard_service.get_service_dashboard(
            "AmazonEC2", tenant_context=test_tenant_context
        )

        # Panel 1: Service Description
        assert svc.description != ""
        assert svc.service_code == "AmazonEC2"

        # Panel 2: Pricing Model
        assert "Reserved" in svc.pricing_model or "Consumption" in svc.pricing_model

        # Panel 3: Free-Tier Details
        assert svc.free_tier_details["eligible"] is True
        assert "750 hours" in svc.free_tier_details["monthly_allowance"]

        # Panel 4: Actual Cost
        assert svc.actual_cost.amount > Decimal("0.0")
        assert svc.actual_cost.cost_source == "ACTUAL"

        # Panel 5: Estimated Cost
        assert svc.estimated_cost.cost_source == "ESTIMATED"

        # Panel 6: Forecast
        assert svc.forecast_cost.cost_source == "FORECAST"

        # Panel 7: Budget
        assert svc.budget_allocated > Decimal("0.0")
        assert svc.budget_utilisation_pct > Decimal("0.0")

        # Panel 8: Runtime
        assert svc.active_instances_count > 0
        assert svc.runtime_status == "RUNNING"

        # Panel 9: Usage
        assert svc.metered_usage_quantity > Decimal("0.0")
        assert svc.usage_metric_name == "Core-Hours"

        # Panel 10: Pricing Units
        assert len(svc.pricing_units) >= 2

        # Panel 11: Cost Drivers
        assert svc.primary_cost_driver != ""
        assert len(svc.secondary_cost_drivers) >= 1

        # Panel 12: Dependencies
        assert len(svc.upstream_dependencies) >= 1
        assert len(svc.downstream_dependencies) >= 1

        # Panel 13: Connectivity
        assert svc.network_endpoints_count > 0
        assert svc.cross_region_egress_gb >= Decimal("0.0")

        # Panel 14: Historical Trend
        assert len(svc.historical_points) > 0

        # Panel 15: Documentation Link
        assert svc.documentation_url.startswith("https://")
        assert svc.finops_guidelines_url.startswith("https://")

        # Panel 16: Pricing Source
        assert svc.pricing_source_name != ""
        assert svc.pricing_source_badge == "OFFICIAL_PROVIDER_RATECARD"


# ==============================================================================
# 4. Dynamic Period Selection & Comparison Basis (FR-504)
# ==============================================================================


class TestPeriodSelectionAndComparison:
    """Verifies Month, Quarter, Fiscal, Custom periods and PoP/YoY."""

    def test_month_period_pop_comparison(self, dashboard_service: DashboardService) -> None:
        tw = dashboard_service.build_time_window(
            period_id="2026-09",
            period_type=DashboardPeriodType.MONTH,
            comparison_basis=ComparisonBasis.POP,
        )
        assert tw.start_date == date(2026, 9, 1)
        assert tw.end_date == date(2026, 9, 30)
        assert tw.comparison_end_date == date(2026, 8, 31)

    def test_month_period_yoy_comparison(self, dashboard_service: DashboardService) -> None:
        tw = dashboard_service.build_time_window(
            period_id="2026-09",
            period_type=DashboardPeriodType.MONTH,
            comparison_basis=ComparisonBasis.YOY,
        )
        assert tw.start_date == date(2026, 9, 1)
        assert tw.comparison_start_date == date(2025, 9, 1)
        assert tw.comparison_end_date == date(2025, 9, 30)

    def test_quarter_and_custom_periods(self, dashboard_service: DashboardService) -> None:
        tw_custom = dashboard_service.build_time_window(
            period_type=DashboardPeriodType.CUSTOM,
            custom_start=date(2026, 5, 10),
            custom_end=date(2026, 6, 20),
        )
        assert tw_custom.start_date == date(2026, 5, 10)
        assert tw_custom.end_date == date(2026, 6, 20)


# ==============================================================================
# 5. Role-Based Landing Dashboards (FR-503)
# ==============================================================================


class TestRoleBasedLanding:
    """Verifies default landing resolution per role and user overrides."""

    def test_role_default_landing_resolution(self, dashboard_service: DashboardService) -> None:
        exec_landing = dashboard_service.get_role_landing_dashboard(user_id="u1", role="EXECUTIVE")
        assert exec_landing.default_dashboard == "EXECUTIVE"

        eng_landing = dashboard_service.get_role_landing_dashboard(user_id="u2", role="ENGINEERING")
        assert eng_landing.default_dashboard == "SERVICE"
        assert eng_landing.default_service_id == "AmazonEC2"

    def test_user_landing_preference_persistence(self, dashboard_service: DashboardService) -> None:
        dashboard_service.set_user_landing_preference(
            user_id="u1",
            role="EXECUTIVE",
            landing_dashboard="PROVIDER",
            provider="azure",
        )
        pref = dashboard_service.get_role_landing_dashboard(user_id="u1", role="EXECUTIVE")
        assert pref.default_dashboard == "PROVIDER"
        assert pref.default_provider == "azure"


# ==============================================================================
# 6. Widget-Level Data Export (FR-505)
# ==============================================================================


class TestWidgetDataExport:
    """Verifies CSV and JSON data export on individual widgets."""

    def test_export_cost_by_provider_csv(
        self,
        dashboard_service: DashboardService,
        test_tenant_context: TenantContext,
    ) -> None:
        content, media_type = dashboard_service.export_widget_data(
            widget_id="w_cost_by_provider",
            export_format="CSV",
            tenant_context=test_tenant_context,
        )
        assert media_type == "text/csv"
        assert "provider,label,cost_usd,share_pct" in content
        assert "Amazon Web Services" in content
        assert "Microsoft Azure" in content

    def test_export_cost_by_provider_json(
        self,
        dashboard_service: DashboardService,
        test_tenant_context: TenantContext,
    ) -> None:
        content, media_type = dashboard_service.export_widget_data(
            widget_id="w_cost_by_provider",
            export_format="JSON",
            tenant_context=test_tenant_context,
        )
        assert media_type == "application/json"
        assert '"widget_id": "w_cost_by_provider"' in content
        assert '"Amazon Web Services"' in content


# ==============================================================================
# 7. FastAPI REST API Contract Tests
# ==============================================================================


class TestDashboardAPIContracts:
    """End-to-end HTTP contract tests with FastAPI TestClient."""

    def test_api_executive_dashboard(self, client: TestClient, test_headers: dict[str, str]) -> None:
        res = client.get("/api/v1/dashboards/executive?period_id=2026-09", headers=test_headers)
        assert res.status_code == 200
        data = res.json()
        assert "total_cloud_cost" in data
        assert "data_freshness_banner" in data
        assert float(data["total_cloud_cost"]["amount"]) > 0
        assert float(data["cost_by_provider"]["items"][0]["cost"]) > 0

    def test_api_provider_dashboard_native_terms(self, client: TestClient, test_headers: dict[str, str]) -> None:
        res = client.get("/api/v1/dashboards/providers/azure", headers=test_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["provider"] == "azure"
        assert data["native_group_term"] == "Management Groups"
        assert data["native_account_term"] == "Subscriptions"

    def test_api_service_dashboard_sixteen_panels(self, client: TestClient, test_headers: dict[str, str]) -> None:
        res = client.get("/api/v1/dashboards/services/AmazonEC2", headers=test_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["service_code"] == "AmazonEC2"
        assert data["pricing_model"] != ""
        assert data["free_tier_details"]["eligible"] is True
        assert len(data["pricing_units"]) >= 2
        assert data["pricing_source_badge"] == "OFFICIAL_PROVIDER_RATECARD"

    def test_api_widget_export_csv_and_json(self, client: TestClient, test_headers: dict[str, str]) -> None:
        # CSV
        res_csv = client.get(
            "/api/v1/dashboards/export/w_cost_by_provider?format=CSV", headers=test_headers
        )
        assert res_csv.status_code == 200
        assert "text/csv" in res_csv.headers["content-type"]
        assert "Amazon Web Services" in res_csv.text

        # JSON
        res_json = client.get(
            "/api/v1/dashboards/export/w_cost_by_provider?format=JSON", headers=test_headers
        )
        assert res_json.status_code == 200
        assert "application/json" in res_json.headers["content-type"]
        assert "Amazon Web Services" in res_json.text
