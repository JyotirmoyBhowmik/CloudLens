# ruff: noqa: E402
"""Pytest configuration and shared fixtures."""

import os
import sys
from pathlib import Path

# Add project root to sys.path so all monorepo packages are importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Test environment defaults: development environment with explicit memory secret store
os.environ.setdefault("CLOUDLENS_ENV", "development")
os.environ.setdefault("SECRET_STORE_BACKEND", "memory")

import pytest

from domain.alerting.repository import reset_alert_repository
from domain.alerting.service import reset_alert_service
from domain.analytics.repository import reset_analytics_repository
from domain.analytics.service import reset_analytics_service
from domain.audit.service import reset_audit_service
from domain.bootstrap.pre_identity import reset_pre_identity_bootstrap_service
from domain.bootstrap.superuser import reset_superuser_service
from domain.budgets.repository import reset_budget_repository
from domain.budgets.service import reset_budget_service
from domain.bulk_import.engine import reset_bulk_import_engine
from domain.bulk_import.repository import reset_bulk_import_repository
from domain.cost.calculation.engine import reset_calculation_engine
from domain.cost.calculation.estimator import reset_pre_deployment_estimator
from domain.cost.currency_service import reset_currency_service
from domain.cost.pipeline import reset_cost_pipeline
from domain.cost.reconciliation.engine import reset_cost_reconciliation_engine
from domain.cost.reconciliation.repository import reset_reconciliation_repository
from domain.cost.repository import reset_cost_repository
from domain.credentials.service import reset_credential_service
from domain.credentials.store import reset_secret_store
from domain.dashboards.service import reset_dashboard_service
from domain.demo.service import reset_demo_mode_service
from domain.dependency.repository import reset_dependency_repository
from domain.dependency.service import reset_dependency_service
from domain.explanation.service import reset_explanation_service
from domain.forecasting.repository import reset_forecast_repository
from domain.forecasting.service import reset_forecasting_service
from domain.hierarchy.service import reset_hierarchy_service
from domain.identity.service import get_identity_service, reset_identity_service
from domain.notification.repository import reset_notification_log_repository
from domain.overrides.service import reset_override_service
from domain.policy.repository import reset_policy_repository
from domain.policy.service import reset_policy_service
from domain.pricing.service import reset_pricing_service
from domain.provisioning.repository import reset_provisioning_repository
from domain.provisioning.service import reset_provisioning_gate_service
from domain.quotas.repository import reset_quota_repository
from domain.quotas.service import reset_quota_service
from domain.rbac.service import reset_rbac_service
from domain.remediation.itsm import reset_itsm_adapter
from domain.remediation.ledger import reset_realised_saving_ledger
from domain.remediation.repository import reset_remediation_repository
from domain.remediation.service import reset_remediation_service
from domain.reports.repository import reset_report_repository
from domain.reports.service import reset_report_service
from domain.resource_detail.service import reset_resource_detail_service
from domain.runtime.repository import reset_runtime_repository
from domain.runtime.service import reset_runtime_service
from domain.statements.repository import reset_statement_repository
from domain.statements.service import reset_statement_service
from domain.sync.repository import reset_sync_repositories
from domain.synthetic.demo_tenant import reset_demo_tenant_service
from domain.tenant.object_store import reset_tenant_object_storage
from domain.thresholds.repository import reset_threshold_repository
from domain.thresholds.service import reset_threshold_service
from domain.topology.service import reset_topology_service
from domain.usage.service import reset_usage_service
from domain.wizard.repository import reset_wizard_repository
from domain.workflows.repository import reset_workflow_repository
from domain.workflows.service import reset_workflow_service
from masterdata.service import reset_master_data_service
from masterdata.string_catalogue import reset_string_catalogue_service


@pytest.fixture(autouse=True)
def reset_all_singletons(request: pytest.FixtureRequest):
    """Autouse fixture ensuring pristine singleton and repository state for every test."""
    from api.cloudlens_api.main import app
    from db.session import get_db_session

    async def _mock_db_session():
        yield None

    is_realdb = bool(request.node.get_closest_marker("realdb"))
    if not is_realdb:
        app.dependency_overrides[get_db_session] = _mock_db_session

        from domain.identity.repository import reset_identity_repository
        from tests.fakes.identity import InMemoryIdentityRepository

        reset_identity_repository(InMemoryIdentityRepository())

        from domain.rbac.repository import reset_rbac_repository
        from tests.fakes.rbac import InMemoryRBACRepository

        reset_rbac_repository(InMemoryRBACRepository())

        from masterdata.repository import reset_master_data_repository
        from tests.fakes.masterdata import InMemoryMasterDataRepository

        reset_master_data_repository(InMemoryMasterDataRepository())

        from domain.config.feature_flags_repository import reset_feature_flag_repository
        from tests.fakes.feature_flags import InMemoryFeatureFlagRepository

        reset_feature_flag_repository(InMemoryFeatureFlagRepository())

        from domain.config.repository import reset_tenant_settings_repository
        from tests.fakes.tenant_settings import InMemoryTenantSettingsRepository

        reset_tenant_settings_repository(InMemoryTenantSettingsRepository())

        from domain.alerting.repository import reset_alert_repository
        from tests.fakes.alerting import (
            InMemoryAlertRepository,
            InMemoryContextualAlertRepository,
        )

        reset_alert_repository(InMemoryAlertRepository())

        from domain.alerting.contextual import get_contextual_alert_manager

        get_contextual_alert_manager(InMemoryContextualAlertRepository())

        from domain.cost.repository import reset_cost_repository
        from tests.fakes.cost import InMemoryCostFactRepository

        reset_cost_repository(InMemoryCostFactRepository())

        from domain.cost.reconciliation.repository import (
            reset_reconciliation_repository,
        )
        from tests.fakes.reconciliation import InMemoryReconciliationRepository

        reset_reconciliation_repository(InMemoryReconciliationRepository())

        from domain.budgets.repository import reset_budget_repository
        from tests.fakes.budgets import InMemoryBudgetRepository

        reset_budget_repository(InMemoryBudgetRepository())

        from domain.usage.repository import reset_usage_repository
        from tests.fakes.usage import InMemoryUsageRepository

        reset_usage_repository(InMemoryUsageRepository())

        from domain.pricing.repository import reset_pricing_repository
        from tests.fakes.pricing import InMemoryPricingRepository

        reset_pricing_repository(InMemoryPricingRepository(load_seed_data=True))

        from domain.catalogues.repository import reset_catalogue_repository
        from tests.fakes.catalogues import InMemoryCatalogueRepository

        reset_catalogue_repository(InMemoryCatalogueRepository(load_seeds=True))

        from domain.policy.repository import reset_policy_repository
        from tests.fakes.policy import InMemoryPolicyRepository

        reset_policy_repository(InMemoryPolicyRepository())

        from domain.provisioning.repository import reset_provisioning_repository
        from tests.fakes.provisioning import InMemoryProvisioningRepository

        reset_provisioning_repository(InMemoryProvisioningRepository())

        from domain.quotas.repository import reset_quota_repository
        from tests.fakes.quotas import InMemoryQuotaRepository

        reset_quota_repository(InMemoryQuotaRepository())

        from domain.runtime.repository import reset_runtime_repository
        from tests.fakes.runtime import InMemoryRuntimeRepository

        reset_runtime_repository(InMemoryRuntimeRepository())

        from domain.statements.repository import reset_statement_repository
        from tests.fakes.statements import InMemoryStatementRepository

        reset_statement_repository(InMemoryStatementRepository())

        from domain.remediation.repository import reset_remediation_repository
        from tests.fakes.remediation import InMemoryRemediationRepository

        reset_remediation_repository(InMemoryRemediationRepository())

        from domain.reports.repository import reset_report_repository
        from tests.fakes.reports import InMemoryReportRepository

        reset_report_repository(InMemoryReportRepository())

        from domain.workflows.repository import reset_workflow_repository
        from tests.fakes.workflows import InMemoryWorkflowRepository

        reset_workflow_repository(InMemoryWorkflowRepository())

        from domain.wizard.repository import reset_wizard_repository
        from tests.fakes.wizard import InMemoryWizardRepository

        reset_wizard_repository(InMemoryWizardRepository())

        from domain.thresholds.repository import reset_threshold_repository
        from tests.fakes.thresholds import InMemoryThresholdRepository

        reset_threshold_repository(InMemoryThresholdRepository())

        from domain.analytics.repository import reset_analytics_repository
        from tests.fakes.analytics import InMemoryAnalyticsRepository

        reset_analytics_repository(InMemoryAnalyticsRepository())

        from domain.forecasting.repository import reset_forecast_repository
        from tests.fakes.forecasting import InMemoryForecastRepository

        reset_forecast_repository(InMemoryForecastRepository())

        from domain.audit.repository import reset_audit_repository
        from tests.fakes.audit import InMemoryAuditRepository

        reset_audit_repository(InMemoryAuditRepository())

        from domain.hierarchy.repository import reset_hierarchy_repository
        from tests.fakes.hierarchy import InMemoryHierarchyRepository

        reset_hierarchy_repository(InMemoryHierarchyRepository())

        from domain.dependency.repository import reset_dependency_repository
        from tests.fakes.dependency import InMemoryDependencyRepository

        reset_dependency_repository(InMemoryDependencyRepository())

        from domain.notification.repository import (
            reset_notification_log_repository,
        )
        from tests.fakes.notification import InMemoryNotificationLogRepository

        reset_notification_log_repository(InMemoryNotificationLogRepository())

        from domain.bulk_import.repository import reset_bulk_import_repository
        from tests.fakes.bulk_import import InMemoryBulkImportRepository

        reset_bulk_import_repository(InMemoryBulkImportRepository())

        from domain.connectors.repository import reset_connector_repository
        from tests.fakes.connectors import InMemoryConnectorRepository

        reset_connector_repository(InMemoryConnectorRepository())

        from domain.credentials.store import reset_secret_store
        from tests.fakes.credentials import InMemorySecretStore

        reset_secret_store(InMemorySecretStore(mount_point="secret"))

        from domain.credentials.repository import reset_credential_repository
        from tests.fakes.credentials import InMemoryCredentialRepository

        reset_credential_repository(InMemoryCredentialRepository())

        from domain.sync.repository import reset_sync_repositories
        from tests.fakes.sync import (
            InMemoryConnectorScheduleRepository,
            InMemoryFirstSyncProgressRepository,
            InMemoryQuarantineRepository,
            InMemorySyncJobRepository,
        )

        reset_sync_repositories(
            sync_jobs=InMemorySyncJobRepository(),
            quarantine=InMemoryQuarantineRepository(),
            schedules=InMemoryConnectorScheduleRepository(),
            progress=InMemoryFirstSyncProgressRepository(),
        )
    else:
        app.dependency_overrides.pop(get_db_session, None)
        from domain.identity.repository import reset_identity_repository

        reset_identity_repository(None)

        from domain.rbac.repository import reset_rbac_repository

        reset_rbac_repository(None)

        from masterdata.repository import reset_master_data_repository

        reset_master_data_repository(None)

        from domain.config.feature_flags_repository import (
            reset_feature_flag_repository,
        )

        reset_feature_flag_repository(None)

        from domain.config.repository import reset_tenant_settings_repository

        reset_tenant_settings_repository(None)

        from domain.alerting.repository import reset_alert_repository

        reset_alert_repository(None)

        from domain.cost.repository import reset_cost_repository

        reset_cost_repository(None)

        from domain.cost.reconciliation.repository import (
            reset_reconciliation_repository,
        )

        reset_reconciliation_repository(None)

        from domain.budgets.repository import reset_budget_repository

        reset_budget_repository(None)

        from domain.usage.repository import reset_usage_repository

        reset_usage_repository(None)

        from domain.pricing.repository import reset_pricing_repository

        reset_pricing_repository(None)

        from domain.catalogues.repository import reset_catalogue_repository

        reset_catalogue_repository(None)

        from domain.policy.repository import reset_policy_repository

        reset_policy_repository(None)

        from domain.provisioning.repository import reset_provisioning_repository

        reset_provisioning_repository(None)

        from domain.quotas.repository import reset_quota_repository

        reset_quota_repository(None)

        from domain.runtime.repository import reset_runtime_repository

        reset_runtime_repository(None)

        from domain.statements.repository import reset_statement_repository

        reset_statement_repository(None)

        from domain.remediation.repository import reset_remediation_repository

        reset_remediation_repository(None)

        from domain.reports.repository import reset_report_repository

        reset_report_repository(None)

        from domain.workflows.repository import reset_workflow_repository

        reset_workflow_repository(None)

        from domain.wizard.repository import reset_wizard_repository

        reset_wizard_repository(None)

        from domain.thresholds.repository import reset_threshold_repository

        reset_threshold_repository(None)

        from domain.analytics.repository import reset_analytics_repository

        reset_analytics_repository(None)

        from domain.forecasting.repository import reset_forecast_repository

        reset_forecast_repository(None)

        from domain.audit.repository import reset_audit_repository

        reset_audit_repository(None)

        from domain.hierarchy.repository import reset_hierarchy_repository

        reset_hierarchy_repository(None)

        from domain.dependency.repository import reset_dependency_repository

        reset_dependency_repository(None)

        from domain.notification.repository import (
            reset_notification_log_repository,
        )

        reset_notification_log_repository(None)

        from domain.bulk_import.repository import reset_bulk_import_repository

        reset_bulk_import_repository(None)

        from domain.connectors.repository import reset_connector_repository

        reset_connector_repository(None)

        from domain.credentials.repository import reset_credential_repository

        reset_credential_repository(None)

        from domain.sync.repository import reset_sync_repositories

        reset_sync_repositories(None, None, None, None)

    reset_alert_service()
    reset_analytics_service()
    reset_audit_service()
    reset_pre_identity_bootstrap_service()
    reset_superuser_service()
    reset_budget_service()
    reset_bulk_import_engine()
    reset_calculation_engine()
    reset_pre_deployment_estimator()
    reset_currency_service()
    reset_cost_pipeline()
    reset_cost_reconciliation_engine()
    reset_credential_service()
    reset_dashboard_service()
    reset_demo_mode_service()
    reset_dependency_service()
    reset_explanation_service()
    reset_forecasting_service()
    reset_hierarchy_service()
    reset_identity_service()
    reset_override_service()
    reset_policy_service()
    reset_pricing_service()
    reset_provisioning_gate_service()
    reset_quota_service()
    reset_rbac_service()
    reset_itsm_adapter()
    reset_realised_saving_ledger()
    reset_remediation_service()
    reset_report_service()
    reset_resource_detail_service()
    reset_runtime_service()
    reset_statement_service()
    from connectors.sync.first_sync import reset_first_sync_service
    from connectors.sync.orchestrator import reset_sync_orchestrator
    from connectors.sync.scheduler import reset_sync_scheduler

    reset_sync_scheduler(None)
    reset_sync_orchestrator(None)
    reset_first_sync_service(None)
    reset_demo_tenant_service()
    reset_tenant_object_storage()
    reset_threshold_service()
    reset_topology_service()
    reset_usage_service()
    reset_workflow_service()
    reset_master_data_service()
    reset_string_catalogue_service()
    yield


@pytest.fixture
def make_auth_token():
    """Mints a real cryptographically signed JWT test token for testing (Prompt P01 Item 10)."""

    def _mint(
        tenant_id: str = "tenant-test",
        user_id: str = "usr-test",
        email: str = "test@cloudlens.internal",
        roles: list[object] | None = None,
        permissions: list[str] | None = None,
        ttl_seconds: int = 3600,
    ) -> str:
        identity_svc = get_identity_service()
        return identity_svc.token_engine.issue_access_token(
            user_id=user_id,
            tenant_id=tenant_id,
            email=email,
            roles=roles or [],
            permissions=permissions or [],
            session_id="test-session-1",
            token_family_id="test-family-1",
            ttl_seconds=ttl_seconds,
        )

    return _mint


@pytest.fixture
def auth_headers(make_auth_token):
    """Returns headers with a valid Bearer token minted by make_auth_token."""

    def _headers(
        tenant_id: str = "tenant-test",
        user_id: str = "usr-test",
        email: str = "test@cloudlens.internal",
        roles: list[object] | None = None,
        permissions: list[str] | None = None,
    ) -> dict[str, str]:
        token = make_auth_token(
            tenant_id=tenant_id,
            user_id=user_id,
            email=email,
            roles=roles,
            permissions=permissions,
        )
        return {"Authorization": f"Bearer {token}"}

    return _headers


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Enforces authoritative Prompt 42/42B level markers (levels 01-20 & phase2)."""
    for item in items:
        path_str = str(item.fspath).replace("\\", "/")

        if "tests/unit/" in path_str:
            item.add_marker(pytest.mark.level01)
        elif "tests/integration/" in path_str:
            item.add_marker(pytest.mark.level02)
        elif "tests/contracts/" in path_str:
            item.add_marker(pytest.mark.level03)
        elif "tests/connectors/" in path_str:
            item.add_marker(pytest.mark.level04)
        elif "tests/cloud_provider/" in path_str:
            item.add_marker(pytest.mark.level05)
        elif "tests/data_validation/" in path_str:
            item.add_marker(pytest.mark.level06)
        elif "tests/cost_reconciliation/" in path_str:
            item.add_marker(pytest.mark.level07)
        elif "tests/security/test_rbac" in path_str or "tests/rbac/" in path_str:
            item.add_marker(pytest.mark.level09)
        elif "tests/security/" in path_str:
            item.add_marker(pytest.mark.level08)
        elif "tests/perf/" in path_str:
            item.add_marker(pytest.mark.level10)
        elif "tests/load/" in path_str:
            item.add_marker(pytest.mark.level11)
        elif "tests/ui/" in path_str:
            item.add_marker(pytest.mark.level12)
        elif "tests/e2e/" in path_str:
            item.add_marker(pytest.mark.level13)
        elif "tests/dr/" in path_str:
            item.add_marker(pytest.mark.level14)
        elif "tests/upgrade/" in path_str:
            item.add_marker(pytest.mark.level15)
        elif "tests/regression/" in path_str:
            item.add_marker(pytest.mark.level16)
        elif "tests/acceptance/" in path_str or "tests/mandates/" in path_str:
            item.add_marker(pytest.mark.level17)
        elif "tests/masterdata/" in path_str:
            item.add_marker(pytest.mark.level18)
        elif "tests/workflow/" in path_str:
            item.add_marker(pytest.mark.level19)
        elif "tests/analytics/" in path_str:
            item.add_marker(pytest.mark.level20)

        if "test_database_real" in path_str:
            item.add_marker(pytest.mark.realdb)

        # Phase 2 (Prompts 57-61 / Addendum B / New Improvements)
        if any(
            p in path_str
            for p in [
                "tests/commitments/",
                "tests/planning/",
                "tests/lifecycle/",
                "tests/adoption/",
                "tests/integrations/",
                "tests/improvements/",
                "tests/control_tower/",
            ]
        ):
            item.add_marker(pytest.mark.phase2)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Enforces Guardrail 9 & Prompt P00 realdb test policy.

    When CLOUDLENS_REQUIRE_REALDB=1 (or running in CI), a skipped realdb test FAILS the run.
    """
    outcome = yield
    report = outcome.get_result()
    if report.skipped:
        require_realdb = (
            os.getenv("CLOUDLENS_REQUIRE_REALDB") == "1"
            or os.getenv("REQUIRE_REALDB") == "1"
            or os.getenv("CI", "").strip().lower() in ("true", "1")
            or os.getenv("GITHUB_ACTIONS", "").strip().lower() in ("true", "1")
        )
        if require_realdb and item.get_closest_marker("realdb"):
            report.outcome = "failed"
            skip_reason = getattr(report, "wasxfail", None) or str(report.longrepr)
            report.longrepr = (
                f"STRICT REALDB REQUIREMENT FAILURE: Test '{item.nodeid}' was skipped: {skip_reason}\n"
                f"Guardrail 9 & Prompt P00 dictate: When CLOUDLENS_REQUIRE_REALDB=1 or running in CI, "
                f"skipping realdb tests is strictly forbidden. Real PostgreSQL tests must RUN and PASS."
            )
