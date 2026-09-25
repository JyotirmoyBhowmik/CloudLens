"""Unit tests for Feature Flag Registry, Evaluation Service & Audit Hook."""

import pytest

from domain.config import (
    UnregisteredFeatureFlagError,
    feature_flag_service,
)
from masterdata.registries.feature_flags import FEATURE_FLAG_REGISTRY


@pytest.fixture(autouse=True)
def clean_flags():
    feature_flag_service.reset()
    yield
    feature_flag_service.reset()


def test_canonical_flag_registry_contains_mandatory_flags():
    """Verify core flags are properly declared in canonical registry."""
    assert "enable_oci_connector" in FEATURE_FLAG_REGISTRY
    assert "enable_azure_connector" in FEATURE_FLAG_REGISTRY
    assert "enable_aws_connector" in FEATURE_FLAG_REGISTRY
    assert "enable_gcp_connector" in FEATURE_FLAG_REGISTRY
    assert "strict_budget_enforcement" in FEATURE_FLAG_REGISTRY
    assert "enable_multi_currency_forecasting" in FEATURE_FLAG_REGISTRY


def test_unregistered_flag_raises_error():
    """Constraint: Do not create or evaluate flags without registering them."""
    with pytest.raises(UnregisteredFeatureFlagError) as exc_info:
        feature_flag_service.evaluate("non_existent_rogue_flag")
    assert "not registered in the canonical registry" in str(exc_info.value)

    with pytest.raises(UnregisteredFeatureFlagError):
        feature_flag_service.set_flag("unregistered_experiment", True)


def test_global_flag_evaluation_and_toggle_with_audit_trail():
    """Verify global toggle changes state and dispatches audit log entry."""
    flag_key = "enable_oci_connector"
    assert feature_flag_service.evaluate(flag_key) is False

    # Toggle flag globally
    audit_event = feature_flag_service.set_flag(
        flag_key=flag_key,
        enabled=True,
        changed_by="admin-user-01",
        reason="Enable OCI pilot trial",
    )
    assert audit_event.flag_key == flag_key
    assert audit_event.old_value is False
    assert audit_event.new_value is True
    assert audit_event.changed_by == "admin-user-01"

    # Evaluates to True
    assert feature_flag_service.evaluate(flag_key) is True

    # Audit log contains entry
    audit_history = feature_flag_service.get_audit_log(flag_key=flag_key)
    assert len(audit_history) == 1
    assert audit_history[0].reason == "Enable OCI pilot trial"


def test_tenant_specific_flag_override_and_isolation():
    """Verify tenant override overrides global setting and isolates other tenants."""
    flag_key = "strict_budget_enforcement"
    # Default is False globally
    assert feature_flag_service.evaluate(flag_key) is False

    # Override for tenant A
    feature_flag_service.set_flag(
        flag_key=flag_key,
        enabled=True,
        tenant_id="tenant-corp-a",
        changed_by="finops-lead",
        reason="Opt-in to automated hard stop",
    )

    # Tenant A evaluates to True
    assert feature_flag_service.evaluate(flag_key, tenant_id="tenant-corp-a") is True

    # Tenant B and global remain False
    assert feature_flag_service.evaluate(flag_key, tenant_id="tenant-corp-b") is False
    assert feature_flag_service.evaluate(flag_key) is False
