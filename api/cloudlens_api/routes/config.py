"""CloudLens Configuration, Tenant Settings & Feature Flag Endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from domain.config import (
    ConfigProvenance,
    ConfigurationAuditEngine,
    ConfigurationAuditReport,
    ConfigurationDriftEngine,
    ConfigurationDriftReport,
    UnregisteredFeatureFlagError,
    config_resolver,
    feature_flag_service,
    tenant_settings_store,
)
from domain.config.tenant_settings import TenantSettings

router = APIRouter(prefix="/api/v1", tags=["Configuration & Feature Flags"])


class FeatureToggleRequest(BaseModel):
    """Payload to mutate a feature flag state."""

    enabled: bool = Field(description="New toggle state")
    tenant_id: str | None = Field(default=None, description="Optional tenant scope")
    changed_by: str = Field(default="system-admin", description="Principal modifying the flag")
    reason: str = Field(default="Administrative update", description="Audit rationale")


class TenantSettingsUpdateRequest(BaseModel):
    """Payload to update tenant configuration settings."""

    reporting_currency: str | None = None
    fiscal_calendar_start_month: int | None = None
    default_time_zone: str | None = None
    cost_basis_default: str | None = None
    forecast_method_default: str | None = None
    retention_profile: dict[str, int] | None = None
    threshold_defaults: dict[str, float] | None = None
    approval_limits: dict[str, float] | None = None


# --- Configuration Inspector Endpoints ---


@router.get(
    "/config/inspector",
    response_model=list[ConfigProvenance],
    summary="Inspect all effective settings",
)
async def inspect_all_configurations(
    tenant_id: str | None = Query(
        default=None, description="Optional tenant ID to include tenant-layer settings"
    ),
) -> list[ConfigProvenance]:
    """Inspect all configuration settings with layer provenance (BUILTIN_DEFAULT, ENVIRONMENT, TENANT).

    All secrets (passwords, tokens, keys) are automatically masked for security.
    """
    return config_resolver.inspect_all(tenant_id=tenant_id, mask_secrets=True)


@router.get(
    "/config/inspector/{setting_key:path}",
    response_model=ConfigProvenance,
    summary="Inspect specific setting",
)
async def inspect_setting(
    setting_key: str,
    tenant_id: str | None = Query(
        default=None, description="Optional tenant ID for tenant-scoped settings"
    ),
) -> ConfigProvenance:
    """Inspect provenance and effective value of a single configuration setting."""
    try:
        return config_resolver.resolve_provenance(
            setting_key, tenant_id=tenant_id, mask_secrets=True
        )
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuration setting '{setting_key}' was not found.",
        ) from None


@router.get(
    "/config/audit-report",
    response_model=ConfigurationAuditReport,
    summary="Configuration audit report with layer provenance (Prompt 48 Item 38)",
)
async def get_configuration_audit_report(
    tenant_id: str | None = Query(
        default=None, description="Optional tenant ID to include tenant-layer settings"
    ),
) -> ConfigurationAuditReport:
    """Returns comprehensive configuration audit report accounting for every effective setting.

    Acceptance: The configuration audit report accounts for every effective setting with its source layer.
    """
    engine = ConfigurationAuditEngine()
    return engine.generate_audit_report(tenant_id=tenant_id, mask_secrets=True)


@router.get(
    "/config/drift",
    response_model=ConfigurationDriftReport,
    summary="Configuration drift detector (Prompt 48 Item 39)",
)
async def get_configuration_drift(
    tenant_id: str | None = Query(
        default=None, description="Optional tenant ID to evaluate tenant configuration drift"
    ),
) -> ConfigurationDriftReport:
    """Compares running configuration against shipped defaults and reports all deviations."""
    engine = ConfigurationDriftEngine()
    return engine.detect_drift(tenant_id=tenant_id, mask_secrets=True)


# --- Tenant Settings Endpoints ---


@router.get(
    "/tenants/{tenant_id}/settings", response_model=TenantSettings, summary="Get tenant settings"
)
async def get_tenant_settings(tenant_id: str) -> TenantSettings:
    """Retrieve effective tenant settings profile."""
    return tenant_settings_store.get(tenant_id)


@router.put(
    "/tenants/{tenant_id}/settings", response_model=TenantSettings, summary="Update tenant settings"
)
async def update_tenant_settings(
    tenant_id: str,
    payload: TenantSettingsUpdateRequest,
) -> TenantSettings:
    """Dynamically update tenant configuration (e.g. threshold defaults).

    Takes effect immediately across the platform with zero downtime, no restart, and no code change.
    """
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    return tenant_settings_store.update(tenant_id, update_data)


# --- Feature Flag Endpoints ---


@router.get("/features", summary="List all registered feature flags")
async def list_features(
    tenant_id: str | None = Query(
        default=None, description="Optional tenant ID to evaluate tenant overrides"
    ),
) -> list[dict[str, Any]]:
    """List all registered canonical feature flags and their effective states."""
    return feature_flag_service.list_flags(tenant_id=tenant_id)


@router.get("/features/{flag_key}/evaluate", summary="Evaluate a feature flag")
async def evaluate_feature(
    flag_key: str,
    tenant_id: str | None = Query(default=None, description="Optional tenant ID"),
) -> dict[str, Any]:
    """Evaluate whether a registered feature flag is enabled globally or for a specific tenant."""
    try:
        enabled = feature_flag_service.evaluate(flag_key, tenant_id=tenant_id)
        definition = feature_flag_service.get_definition(flag_key)
        return {
            "flag_key": flag_key,
            "name": definition.name,
            "enabled": enabled,
            "tenant_id": tenant_id,
            "stage": definition.stage,
        }
    except UnregisteredFeatureFlagError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post("/features/{flag_key}/toggle", summary="Toggle a feature flag")
async def toggle_feature(
    flag_key: str,
    payload: FeatureToggleRequest,
) -> dict[str, Any]:
    """Toggle a feature flag globally or for a tenant with mandatory audit event logging."""
    try:
        audit_event = feature_flag_service.set_flag(
            flag_key=flag_key,
            enabled=payload.enabled,
            tenant_id=payload.tenant_id,
            changed_by=payload.changed_by,
            reason=payload.reason,
        )
        return {
            "message": f"Feature flag '{flag_key}' updated successfully.",
            "audit_event": audit_event.model_dump(),
        }
    except UnregisteredFeatureFlagError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/features/audit-log", summary="Get feature flag change audit log")
async def get_feature_audit_log(
    flag_key: str | None = Query(default=None, description="Filter by flag key"),
    tenant_id: str | None = Query(default=None, description="Filter by tenant ID"),
) -> list[dict[str, Any]]:
    """Retrieve full audit log history of all feature flag modifications."""
    events = feature_flag_service.get_audit_log(flag_key=flag_key, tenant_id=tenant_id)
    return [e.model_dump() for e in events]
