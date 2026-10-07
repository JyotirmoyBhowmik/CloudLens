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
def reset_all_singletons():
    """Autouse fixture ensuring pristine singleton and repository state for every test."""
    reset_alert_repository()
    reset_alert_service()
    reset_analytics_repository()
    reset_analytics_service()
    reset_audit_service()
    reset_pre_identity_bootstrap_service()
    reset_superuser_service()
    reset_budget_repository()
    reset_budget_service()
    reset_bulk_import_engine()
    reset_bulk_import_repository()
    reset_calculation_engine()
    reset_pre_deployment_estimator()
    reset_currency_service()
    reset_cost_pipeline()
    reset_cost_reconciliation_engine()
    reset_reconciliation_repository()
    reset_cost_repository()
    reset_credential_service()
    reset_secret_store()
    reset_dashboard_service()
    reset_demo_mode_service()
    reset_dependency_repository()
    reset_dependency_service()
    reset_explanation_service()
    reset_forecast_repository()
    reset_forecasting_service()
    reset_hierarchy_service()
    reset_identity_service()
    reset_notification_log_repository()
    reset_override_service()
    reset_policy_repository()
    reset_policy_service()
    reset_pricing_service()
    reset_provisioning_repository()
    reset_provisioning_gate_service()
    reset_quota_repository()
    reset_quota_service()
    reset_rbac_service()
    reset_itsm_adapter()
    reset_realised_saving_ledger()
    reset_remediation_repository()
    reset_remediation_service()
    reset_report_repository()
    reset_report_service()
    reset_resource_detail_service()
    reset_runtime_repository()
    reset_runtime_service()
    reset_statement_repository()
    reset_statement_service()
    reset_sync_repositories()
    reset_demo_tenant_service()
    reset_tenant_object_storage()
    reset_threshold_repository()
    reset_threshold_service()
    reset_topology_service()
    reset_usage_service()
    reset_wizard_repository()
    reset_workflow_repository()
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
