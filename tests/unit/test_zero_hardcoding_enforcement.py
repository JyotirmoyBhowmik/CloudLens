"""Unit & integration tests for Prompt 48: Zero hard-coding enforcement & configuration audit.

Verifies:
1. Hard-coded thresholds, statuses, colours, labels, and roles fail with messages naming the master.
2. Allow-list mechanism requires both named reason and reviewer; invalid annotations fail build.
3. Allow-listed literals are recorded and published in the Exception Register.
4. Enumeration bridge fails on master code without code path or code value absent from master.
5. Changing user-facing labels in STRING_CATALOGUE requires zero deployment.
6. Configuration audit report accounts for every effective setting with source layer provenance.
7. Configuration drift detector isolates deviations against factory defaults.
8. REST API endpoints for audit reports, drift detector, and string catalogue return verified responses.
"""

import ast
from enum import Enum

import pytest
from starlette.testclient import TestClient

from api.cloudlens_api.main import app
from domain.config import (
    ConfigurationAuditEngine,
    ConfigurationDriftEngine,
    tenant_settings_store,
)
from masterdata import (
    EnumerationBridge,
    MasterDataService,
    StringCatalogueService,
    reset_master_data_service,
    t,
)
from scripts.check_no_hardcoded_constants import (
    ZeroHardCodingVisitor,
)


@pytest.fixture
def master_service() -> MasterDataService:
    reset_master_data_service()
    return MasterDataService(auto_seed=True)


@pytest.fixture
def client(master_service: MasterDataService) -> TestClient:
    _ = master_service
    return TestClient(app)


# ==============================================================================
# 1. Static Analysis: Introducing Hard-Coded Literals Fails Build Naming Master
# ==============================================================================


def test_hardcoded_threshold_fails_naming_master():
    """Acceptance: Introducing a hard-coded threshold fails build with message naming master/config."""
    code = """
def check_threshold(spend: float, budget: float) -> bool:
    threshold = 0.9  # VIOLATION: Hardcoded 0.9 threshold
    return (spend / budget) > threshold
"""
    lines = code.splitlines()
    tree = ast.parse(code)
    visitor = ZeroHardCodingVisitor("api/test_mod.py", lines)
    visitor.visit(tree)

    assert len(visitor.violations) > 0
    v = visitor.violations[0]
    assert v.literal_value == "0.9"
    # Acceptance: message must name the master or config key it should come from
    assert (
        "threshold_defaults" in v.target_master.lower() or "threshold_defaults" in v.reason.lower()
    )
    assert "configuration" in v.reason.lower()


def test_hardcoded_status_string_fails_naming_master():
    """Acceptance: Introducing a hard-coded status string fails build naming RUNTIME_STATUS master."""
    code = """
def check_status(resource_status: str) -> bool:
    return resource_status == "RUNNING"  # VIOLATION: Hardcoded status string
"""
    lines = code.splitlines()
    tree = ast.parse(code)
    visitor = ZeroHardCodingVisitor("api/worker_check.py", lines)
    visitor.visit(tree)

    assert len(visitor.violations) > 0
    v = visitor.violations[0]
    assert v.literal_value == "RUNNING"
    # Acceptance: message must name RUNTIME_STATUS
    assert "RUNTIME_STATUS" in v.target_master
    assert "RuntimeStatus" in v.reason or "RUNTIME_STATUS" in v.reason


def test_hardcoded_colour_fails_naming_master():
    """Acceptance: Introducing a hard-coded colour fails build naming THEME_COLOUR master."""
    code = """
def get_card_style() -> dict:
    card_color = "#10b981"  # VIOLATION: Hardcoded hex colour literal
    return {"color": card_color}
"""
    lines = code.splitlines()
    tree = ast.parse(code)
    visitor = ZeroHardCodingVisitor("api/ui_render.py", lines)
    visitor.visit(tree)

    assert len(visitor.violations) > 0
    v = visitor.violations[0]
    assert v.literal_value == "#10b981"
    # Acceptance: message must name THEME_COLOUR
    assert "THEME_COLOUR" in v.target_master


def test_hardcoded_user_facing_label_fails_naming_string_catalogue():
    """Acceptance: Introducing a hard-coded user-facing label fails naming STRING_CATALOGUE."""
    code = """
def get_nav_metadata():
    display_label = "Resource Inventory"  # VIOLATION: Hardcoded user-facing label
    return {"label": display_label}
"""
    lines = code.splitlines()
    tree = ast.parse(code)
    visitor = ZeroHardCodingVisitor("api/nav.py", lines)
    visitor.visit(tree)

    assert len(visitor.violations) > 0
    v = visitor.violations[0]
    assert v.literal_value == "Resource Inventory"
    # Acceptance: message must name STRING_CATALOGUE
    assert "STRING_CATALOGUE" in v.target_master


def test_hardcoded_role_string_fails_naming_master():
    """Acceptance: Introducing a hard-coded role name fails naming ROLE master or ScopeRole."""
    code = """
def enforce_admin_boundary():
    required_role = "GLOBAL_ADMIN"  # VIOLATION: Hardcoded role string
    return required_role
"""
    lines = code.splitlines()
    tree = ast.parse(code)
    visitor = ZeroHardCodingVisitor("api/auth.py", lines)
    visitor.visit(tree)

    assert len(visitor.violations) > 0
    v = visitor.violations[0]
    assert v.literal_value == "GLOBAL_ADMIN"
    assert "ROLE" in v.target_master or "ScopeRole" in v.target_master


# ==============================================================================
# 2. Allow-List Mechanism & Exception Register
# ==============================================================================


def test_allow_list_annotation_without_reviewer_or_reason_fails_build():
    """Rule 35: A literal allow-list annotation missing reason or reviewer FAILS the build."""
    code = """
# Missing reviewer!
threshold = 0.9  # no-hardcode-allow: reason="Emergency patch"
"""
    lines = code.splitlines()
    tree = ast.parse(code)
    visitor = ZeroHardCodingVisitor("api/bad_allow.py", lines)
    visitor.visit(tree)

    # Must fail because reviewer is omitted
    assert len(visitor.violations) > 0
    assert any("reviewer" in v.reason for v in visitor.violations)


def test_allow_list_annotation_with_valid_reason_and_reviewer_succeeds_and_publishes():
    """Rule 35: A literal permitted with valid reason and reviewer is approved and entered in register."""
    code = """
# no-hardcode-allow: reason="Legacy seed benchmark multiplier", reviewer="lead-architect"
threshold = 0.9
"""
    lines = code.splitlines()
    tree = ast.parse(code)
    visitor = ZeroHardCodingVisitor("api/good_allow.py", lines)
    visitor.visit(tree)

    # Violations should be zero
    assert len(visitor.violations) == 0
    # Must be recorded in allowed exceptions
    assert len(visitor.allowed_exceptions) == 1
    entry = visitor.allowed_exceptions[0]
    assert entry.literal_value == "0.9"
    assert entry.reason == "Legacy seed benchmark multiplier"
    assert entry.reviewer == "lead-architect"


# ==============================================================================
# 3. Enumeration Bridge: Master <-> Code Bidirectional Parity
# ==============================================================================


def test_enumeration_bridge_clean_state_passes(master_service: MasterDataService):
    """Item 36: Clean state across all bound enums passes 100%."""
    bridge = EnumerationBridge(master_service=master_service)
    res = bridge.validate(raise_on_failure=False)
    assert res.is_valid is True
    assert res.total_violations == 0
    assert res.total_bindings_checked >= 6


def test_enumeration_bridge_master_without_code_path_fails(master_service: MasterDataService):
    """Acceptance: Adding a value to a master without a code path fails the build."""
    # Add new unmapped status code directly to RUNTIME_STATUS master
    master_service.create_record(
        master_type="RUNTIME_STATUS",
        code="HIBERNATING",
        display_name="Hibernating Instance",
        created_by="infra_admin",
        force_publish=True,
    )

    bridge = EnumerationBridge(master_service=master_service)
    res = bridge.validate(raise_on_failure=False)
    assert res.is_valid is False
    assert res.total_violations > 0
    assert any(
        "Master value 'HIBERNATING' added to master 'RUNTIME_STATUS'" in v for v in res.violations
    )
    assert any("without corresponding code path in RuntimeStatus" in v for v in res.violations)


def test_enumeration_bridge_code_referencing_value_absent_from_master_fails(
    master_service: MasterDataService,
):
    """Acceptance: Referencing a value in an enum absent from a master fails the build."""

    class DivergentStatusEnum(str, Enum):
        RUNNING = "RUNNING"
        STOPPED = "STOPPED"
        PHANTOM_STATE = "PHANTOM_STATE"  # Value does not exist in RUNTIME_STATUS master

    custom_bindings = {DivergentStatusEnum: "RUNTIME_STATUS"}
    bridge = EnumerationBridge(master_service=master_service, bindings=custom_bindings)
    res = bridge.validate(raise_on_failure=False)

    assert res.is_valid is False
    assert any(
        "references value 'PHANTOM_STATE' absent from master 'RUNTIME_STATUS'" in v
        for v in res.violations
    )


# ==============================================================================
# 4. Externalised String Catalogue: Zero-Deployment Label Changes
# ==============================================================================


def test_changing_user_facing_label_requires_no_deployment(master_service: MasterDataService):
    """Acceptance: Changing any user-facing label requires no deployment."""
    service = StringCatalogueService(master_service)

    # 1. Initial resolution of navigation label
    initial_text = service.resolve_string("UI_NAV_INVENTORY")
    assert initial_text == "Resource Inventory"

    # 2. Update string in master data with ZERO CODE CHANGE and NO RESTART
    rec = master_service.get_record("STRING_CATALOGUE", "UI_NAV_INVENTORY")
    assert rec is not None
    attrs = dict(rec.attributes)
    attrs["template"] = "Global Estate & Multi-Cloud Inventory"
    master_service.update_record(
        master_type="STRING_CATALOGUE",
        code="UI_NAV_INVENTORY",
        display_name="Updated Estate Inventory Title",
        attributes=attrs,
        changed_by="brand_manager",
        change_reason="Rebranding navigation item",
        force_publish=True,
    )

    # 3. Dynamic resolution immediately reflects change with no deployment!
    updated_text = service.resolve_string("UI_NAV_INVENTORY")
    assert updated_text == "Global Estate & Multi-Cloud Inventory"

    # 4. Interpolated template resolution
    alert_msg = service.resolve_string(
        "ALERT_BUDGET_EXCEEDED",
        params={"cost_centre": "CC-1001", "consumption_pct": "95"},
    )
    assert "Cost Centre 'CC-1001'" in alert_msg
    assert "95%" in alert_msg

    # 5. Convenience t() function
    t_msg = t("UI_NAV_DASHBOARD")
    assert t_msg == "Executive Dashboard"


# ==============================================================================
# 5. Configuration Audit Report
# ==============================================================================


def test_configuration_audit_report_accounts_for_every_setting_with_layer_provenance():
    """Acceptance: The configuration audit report accounts for every effective setting with its source layer."""
    engine = ConfigurationAuditEngine()
    report = engine.generate_audit_report(tenant_id="tenant-audit-corp", mask_secrets=True)

    assert report.total_effective_settings > 20
    assert report.layer_breakdown["builtin_default"] > 0
    assert len(report.entries) == report.total_effective_settings

    # Verify every entry exposes required provenance metadata
    for entry in report.entries:
        assert entry.key != ""
        assert entry.effective_value is not None
        assert entry.source_layer in ("builtin_default", "environment", "tenant")
        assert entry.master_or_config_source != ""
        assert entry.last_changed_at != ""
        assert entry.last_changed_by != ""

    # Test markdown report rendering
    md = report.to_markdown()
    assert "# CloudLens Configuration Audit Report" in md
    assert "| Setting Key | Effective Value | Source Layer |" in md


# ==============================================================================
# 6. Configuration Drift Detector
# ==============================================================================


def test_configuration_drift_detector_detects_deviations_and_cleans():
    """Item 39: Detects deviations against factory defaults and reports clean status."""
    engine = ConfigurationDriftEngine()

    # 1. Clean state without modifications
    tenant_settings_store.reset()
    clean_report = engine.detect_drift(tenant_id="tenant-clean-test")
    # All settings should be clean defaults
    assert clean_report.clean_count > 20
    assert clean_report.drift_count == 0
    assert clean_report.is_drift_detected is False
    assert "CLEAN" in clean_report.diagnosis

    # 2. Modify a setting at tenant layer
    tenant_settings_store.update(
        "tenant-clean-test",
        {
            "threshold_defaults": {
                "budget_alert_threshold_percentage": 92.5,  # Deviates from default 80.0
            }
        },
    )

    # 3. Drift detector immediately isolates operational deviation!
    drift_report = engine.detect_drift(tenant_id="tenant-clean-test")
    assert drift_report.is_drift_detected is True
    assert drift_report.drift_count >= 1
    assert any(
        d.key == "threshold_defaults.budget_alert_threshold_percentage"
        for d in drift_report.deviations
    )

    drifted_entry = next(
        d
        for d in drift_report.deviations
        if d.key == "threshold_defaults.budget_alert_threshold_percentage"
    )
    assert drifted_entry.shipped_default_value == 80.0
    assert drifted_entry.effective_value == 92.5
    assert drifted_entry.overriding_layer == "tenant"
    assert "DRIFT_DETECTED" in drift_report.diagnosis


# ==============================================================================
# 7. REST API Endpoints Verification
# ==============================================================================


def test_api_config_audit_and_drift_and_string_endpoints(client: TestClient):
    """Tests new endpoints for audit report, drift detection, and string resolution."""
    # 1. GET /api/v1/config/audit-report
    res_audit = client.get("/api/v1/config/audit-report")
    assert res_audit.status_code == 200
    audit_data = res_audit.json()
    assert audit_data["total_effective_settings"] > 20
    assert "layer_breakdown" in audit_data

    # 2. GET /api/v1/config/drift
    res_drift = client.get("/api/v1/config/drift")
    assert res_drift.status_code == 200
    drift_data = res_drift.json()
    assert "is_drift_detected" in drift_data
    assert "diagnosis" in drift_data

    # 3. POST /api/v1/masterdata/strings/resolve
    res_str = client.post(
        "/api/v1/masterdata/strings/resolve",
        json={"key": "UI_NAV_DASHBOARD", "locale": "en_US"},
    )
    assert res_str.status_code == 200
    assert res_str.json()["resolved_text"] == "Executive Dashboard"

    # 4. GET /api/v1/masterdata/strings/resolve
    res_str_get = client.get("/api/v1/masterdata/strings/resolve?key=UI_NAV_DASHBOARD")
    assert res_str_get.status_code == 200
    assert res_str_get.json()["resolved_text"] == "Executive Dashboard"
