"""Unit tests for CloudLens Layered Configuration Model & Tenant Settings."""

import os

from domain.config import (
    ConfigLayer,
    SystemConfig,
    config_resolver,
    tenant_settings_store,
)


def test_builtin_system_config_defaults():
    """Verify built-in defaults are properly initialized across all 11 surfaces."""
    cfg = SystemConfig()
    assert cfg.database.host == "localhost"
    assert cfg.database.port == 5432
    assert cfg.cache.port == 6379
    assert cfg.queue.default_queue == "cloudlens_tasks"
    assert cfg.object_storage.bucket_name == "cloudlens-data"
    assert cfg.secret_store.backend_type == "vault"
    assert cfg.identity_provider.client_id == "cloudlens-api"
    assert cfg.notification_channels.email_smtp_port == 587
    assert cfg.observability.service_name == "cloudlens-platform"
    assert cfg.rate_limits.default_requests_per_minute == 600
    assert cfg.pagination.default_page_size == 50
    assert cfg.pagination.max_page_size == 250
    assert cfg.export_limits.max_export_file_size_mb == 50


def test_configuration_inspector_shows_provenance_and_masks_secrets():
    """Acceptance: Inspector shows effective value, layer provenance, and masks secrets."""
    # 1. Unmasked public setting
    prov_host = config_resolver.resolve_provenance("database.host", mask_secrets=True)
    assert prov_host.key == "database.host"
    assert prov_host.effective_value == "localhost"
    assert prov_host.layer == ConfigLayer.BUILTIN_DEFAULT
    assert prov_host.is_secret is False

    # 2. Sensitive secret setting
    prov_pwd = config_resolver.resolve_provenance("database.password", mask_secrets=True)
    assert prov_pwd.key == "database.password"
    assert prov_pwd.effective_value == "******"  # Masked!
    assert prov_pwd.layer == ConfigLayer.BUILTIN_DEFAULT
    assert prov_pwd.is_secret is True

    # 3. Full inspection list
    all_settings = config_resolver.inspect_all(mask_secrets=True)
    assert len(all_settings) > 20
    for s in all_settings:
        if s.is_secret:
            assert s.effective_value in ("******", "[NOT SET]")


def test_environment_override_layer_provenance():
    """Verify Layer 2 (ENVIRONMENT) overrides BUILTIN_DEFAULT and sets layer provenance."""
    env_key = "CLOUDLENS_DATABASE__POOL_SIZE"
    os.environ[env_key] = "42"
    try:
        prov = config_resolver.resolve_provenance("database.pool_size")
        assert prov.effective_value == 42
        assert prov.layer == ConfigLayer.ENVIRONMENT
    finally:
        os.environ.pop(env_key, None)

    # After clearing env var, reverts to BUILTIN_DEFAULT
    prov_revert = config_resolver.resolve_provenance("database.pool_size")
    assert prov_revert.effective_value == 10
    assert prov_revert.layer == ConfigLayer.BUILTIN_DEFAULT


def test_tenant_threshold_change_takes_effect_immediately_without_restart():
    """Acceptance: Changing a threshold default in tenant configuration changes behaviour

    with no code change and no restart.
    """
    tenant_id = "tenant-finops-alpha"
    tenant_settings_store.reset(tenant_id)

    # Initial state: default threshold (80.0%)
    prov_initial = config_resolver.resolve_provenance(
        "threshold_defaults.budget_alert_threshold_percentage",
        tenant_id=tenant_id,
    )
    assert prov_initial.effective_value == 80.0
    assert prov_initial.layer == ConfigLayer.BUILTIN_DEFAULT

    # Hot-reload update: Tenant config changes threshold to 72.5%
    tenant_settings_store.update(
        tenant_id,
        {"threshold_defaults": {"budget_alert_threshold_percentage": 72.5}},
    )

    # Immediate query: effective value is updated dynamically with TENANT layer provenance!
    prov_updated = config_resolver.resolve_provenance(
        "threshold_defaults.budget_alert_threshold_percentage",
        tenant_id=tenant_id,
    )
    assert prov_updated.effective_value == 72.5
    assert prov_updated.layer == ConfigLayer.TENANT
    assert prov_updated.tenant_id == tenant_id

    # Another tenant still sees default (80.0%)
    other_prov = config_resolver.resolve_provenance(
        "threshold_defaults.budget_alert_threshold_percentage",
        tenant_id="tenant-beta",
    )
    assert other_prov.effective_value == 80.0
    assert other_prov.layer == ConfigLayer.BUILTIN_DEFAULT
