"""Comprehensive Unit & Contract Tests for Pre-Identity System Bootstrap (Prompt 49A).

Enforces:
- Clean database reaches fully seeded state with zero users, zero credentials, zero grants.
- Every catalogue count matches the reconciled figures from Prompt 00R.
- Re-running the bootstrap changes nothing (idempotent).
- Policy catalogue is disabled except connector health.
- Provider capabilities include C-18 quota headroom (AM-07).
- Verification report explicitly declares system is not yet interactively usable.
- Decouples pre-identity foundation from authentication (closes Defect D-01).
"""

import pytest
from fastapi.testclient import TestClient

from api.cloudlens_api.main import app
from domain.bootstrap import (
    PreIdentityBootstrapService,
    reset_pre_identity_bootstrap_service,
)
from domain.config.tenant_settings import TenantSettingsStore
from domain.models.enums import ProviderCapability, SystemRole
from masterdata import reset_master_data_service
from masterdata.service import MasterDataService


@pytest.fixture
def clean_bootstrap_service() -> PreIdentityBootstrapService:
    """Fixture providing a fresh isolated PreIdentityBootstrapService."""
    reset_master_data_service()
    reset_pre_identity_bootstrap_service()
    mdm = MasterDataService(auto_seed=False)
    tenant_store = TenantSettingsStore()
    return PreIdentityBootstrapService(
        master_data_service=mdm,
        tenant_store=tenant_store,
    )


@pytest.fixture
def client() -> TestClient:
    """Fixture providing FastAPI test client."""
    reset_master_data_service()
    reset_pre_identity_bootstrap_service()
    return TestClient(app)


# ==============================================================================
# 1. Acceptance: Clean Database Reaches Fully Seeded Pre-Identity State
# ==============================================================================


def test_clean_database_reaches_fully_seeded_pre_identity_state(
    clean_bootstrap_service: PreIdentityBootstrapService,
):
    """A clean system reaches a fully seeded state with NO user, NO credential and NO grant."""
    report = clean_bootstrap_service.bootstrap(correlation_id="test-corr-p49a-01")

    assert report.status == "INITIALIZED"
    assert report.is_already_initialized is False
    assert report.is_interactively_usable is False

    # Mandatory Zero Discipline
    assert report.identities_count == 0
    assert report.credentials_count == 0
    assert report.grants_count == 0

    # System Tenant Initialized
    assert report.tenant_id == "tenant-system"
    assert report.tenant_name == "CloudLens System Tenant"
    assert report.reporting_currency == "USD"
    assert report.fiscal_calendar_code == "FC_STANDARD_JAN"
    assert report.fiscal_calendar_start_month == 1
    assert report.time_zone == "UTC"
    assert report.retention_profile["raw_metrics_retention_days"] == 90
    assert report.retention_profile["daily_aggregates_retention_days"] == 730
    assert report.retention_profile["audit_log_retention_days"] == 1095


# ==============================================================================
# 2. Acceptance: Reconciled Catalogue Counts Match Prompt 00R Baseline
# ==============================================================================


def test_catalogue_counts_match_reconciled_figures_from_prompt_00r(
    clean_bootstrap_service: PreIdentityBootstrapService,
):
    """Every catalogue count matches the reconciled figures from Prompt 00R."""
    report = clean_bootstrap_service.bootstrap()

    cats = report.catalogues_populated
    # Prompt 00R: Reconciles 29 pricing dimensions
    assert cats["pricing_dimensions"] == 29
    # Units catalogue: 21 canonical units
    assert cats["units"] == 21
    # System metrics: 8 core metrics
    assert cats["metrics"] == 8
    # Resource types: 11 canonical types
    assert cats["resource_types"] == 11
    # Service categories: 11 FOCUS 1.0 categories
    assert cats["service_categories"] == 11
    # Core canonical services: 5 services
    assert cats["services"] == 5
    # Default threshold templates: 6 templates
    assert cats["threshold_templates"] == 6
    # Default budget templates: 4 templates
    assert cats["budget_templates"] == 4
    # Governance policies: 6 policies
    assert cats["policies"] == 6


# ==============================================================================
# 3. Acceptance: Policy Catalogue Disabled Except Connector Health
# ==============================================================================


def test_policy_catalogue_disabled_except_connector_health(
    clean_bootstrap_service: PreIdentityBootstrapService,
):
    """Policy catalogue is seeded disabled except connector health."""
    clean_bootstrap_service.bootstrap()
    mdm = clean_bootstrap_service._mdm

    policies = mdm.list_records("POLICY")
    assert len(policies) == 6

    connector_pol = next((p for p in policies if p.code == "POL_CONNECTOR_HEALTH"), None)
    assert connector_pol is not None
    assert connector_pol.is_active is True
    assert connector_pol.attributes.get("enabled") is True

    # All other policies must be disabled
    disabled_policies = [p for p in policies if p.code != "POL_CONNECTOR_HEALTH"]
    assert len(disabled_policies) == 5
    for p in disabled_policies:
        assert p.is_active is False
        assert p.attributes.get("enabled") is False


# ==============================================================================
# 4. Acceptance: Permission Catalogue and Nine Built-in Role Definitions
# ==============================================================================


def test_nine_builtin_roles_and_permissions_defined_as_master_data(
    clean_bootstrap_service: PreIdentityBootstrapService,
):
    """Creates the role definitions only; creates no user, assigns no grant, issues no credential."""
    report = clean_bootstrap_service.bootstrap()
    mdm = clean_bootstrap_service._mdm

    # Permissions
    assert report.permission_count >= 28
    permissions = mdm.list_records("PERMISSION")
    assert len(permissions) == report.permission_count

    # Nine Built-in Roles
    assert len(report.roles_defined) == 9
    roles = mdm.list_records("ROLE")
    assert len(roles) == 9

    expected_role_codes = {role.value for role in SystemRole}
    seeded_role_codes = {r.code for r in roles}
    assert expected_role_codes == seeded_role_codes

    # Verify GlobalAdmin has full permissions
    global_admin = next(r for r in roles if r.code == "GLOBAL_ADMIN")
    assert "config:write" in global_admin.attributes["allowed_permissions"]
    assert "features:toggle" in global_admin.attributes["allowed_permissions"]
    assert "tenants:settings:write" in global_admin.attributes["allowed_permissions"]

    # Verify FinOpsViewer is restricted
    finops_viewer = next(r for r in roles if r.code == "FINOPS_VIEWER")
    viewer_perms = set(finops_viewer.attributes["allowed_permissions"])
    assert "config:read" in viewer_perms
    assert "billing:read" in viewer_perms
    assert "config:write" not in viewer_perms
    assert "features:toggle" not in viewer_perms
    assert "tenants:settings:write" not in viewer_perms


# ==============================================================================
# 5. Acceptance: Provider Registration & Capability C-18 Quota
# ==============================================================================


def test_provider_registration_and_c18_quota_capability(
    clean_bootstrap_service: PreIdentityBootstrapService,
):
    """Registers providers and capability profiles including C-18 quota as added by AM-07."""
    report = clean_bootstrap_service.bootstrap()
    mdm = clean_bootstrap_service._mdm

    caps = mdm.list_records("PROVIDER_CAPABILITY")
    assert len(caps) == 6
    cap_codes = {c.code for c in caps}
    assert cap_codes == {
        ProviderCapability.C01_HIERARCHY.value,
        ProviderCapability.C02_INVENTORY.value,
        ProviderCapability.C03_COST.value,
        ProviderCapability.C04_USAGE.value,
        ProviderCapability.C11_PRICING.value,
        ProviderCapability.C18_QUOTA.value,
    }

    c18 = next(c for c in caps if c.code == "C-18")
    assert c18.attributes.get("added_by") == "AM-07"

    # All cloud providers must include C-18
    for cloud in ["AWS", "AZURE", "GCP", "OCI"]:
        assert cloud in report.providers_registered
        assert "C-18" in report.providers_registered[cloud]


# ==============================================================================
# 6. Acceptance: Idempotency (Re-running Changes Nothing)
# ==============================================================================


def test_bootstrap_idempotency_rerun_changes_nothing(
    clean_bootstrap_service: PreIdentityBootstrapService,
):
    """Re-running on an initialised system changes nothing and reports already initialised."""
    report1 = clean_bootstrap_service.bootstrap()
    assert report1.status == "INITIALIZED"
    assert report1.is_already_initialized is False

    # Second run
    report2 = clean_bootstrap_service.bootstrap()
    assert report2.status == "ALREADY_INITIALISED"
    assert report2.is_already_initialized is True
    assert report2.tenant_id == report1.tenant_id
    assert report2.roles_defined == report1.roles_defined
    assert report2.first_audit_event_id == report1.first_audit_event_id
    assert report2.identities_count == 0

    # Third run
    report3 = clean_bootstrap_service.bootstrap()
    assert report3.status == "ALREADY_INITIALISED"


# ==============================================================================
# 7. Acceptance: Audit Stream Initialised With Bootstrap Record
# ==============================================================================


def test_audit_stream_initialised_with_bootstrap_as_first_record(
    clean_bootstrap_service: PreIdentityBootstrapService,
):
    """Initialises the audit stream and writes the bootstrap itself as the first audit record."""
    report = clean_bootstrap_service.bootstrap(correlation_id="corr-audit-test")

    assert report.audit_stream_initialized is True
    assert report.first_audit_event_id.startswith("aud-boot-")

    audits = clean_bootstrap_service._audit_records
    assert len(audits) == 1
    rec = audits[0]
    assert rec["id"] == report.first_audit_event_id
    assert rec["action"] == "BOOTSTRAP_PRE_IDENTITY_INITIALIZED"
    assert rec["actor_id"] == "SYSTEM_BOOTSTRAP"
    assert rec["entity_type"] == "SYSTEM"
    assert rec["entity_id"] == "CLOUDLENS_PLATFORM"
    assert rec["correlation_id"] == "corr-audit-test"
    assert rec["payload_after"]["closes_defect"] == "D-01"


# ==============================================================================
# 8. Acceptance: Verification Report Plainly Declares Non-Usable State
# ==============================================================================


def test_verification_report_plainly_declares_non_usable_interactively(
    clean_bootstrap_service: PreIdentityBootstrapService,
):
    """Verification report states plainly that the system is not yet interactively usable."""
    report = clean_bootstrap_service.bootstrap()

    assert report.is_interactively_usable is False
    assert "not yet interactively usable" in report.status_statement
    assert "Prompt 49B" in report.status_statement


# ==============================================================================
# 9. API REST Route Verification
# ==============================================================================


def test_api_bootstrap_endpoints(client: TestClient):
    """Verifies REST endpoints for triggering and inspecting pre-identity bootstrap."""
    # 1. Trigger pre-identity bootstrap
    res = client.post(
        "/api/v1/system/bootstrap/pre-identity",
        headers={"X-Correlation-ID": "test-api-boot-01"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in {"INITIALIZED", "ALREADY_INITIALISED"}
    assert data["is_interactively_usable"] is False
    assert data["identities_count"] == 0
    assert data["catalogues_populated"]["pricing_dimensions"] == 29

    # 2. Check status endpoint
    res_status = client.get("/api/v1/system/bootstrap/pre-identity/status")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["is_interactively_usable"] is False
    assert len(status_data["roles_defined"]) == 9
