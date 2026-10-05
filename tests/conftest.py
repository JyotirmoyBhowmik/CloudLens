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
from domain.identity.service import reset_identity_service
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



