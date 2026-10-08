"""CloudLens Configuration, Tenant Settings & Feature Flag Endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.cloudlens_api.tenant_context import require_auth
from db.session import get_db_session
from domain.config import (
    ConfigProvenance,
    ConfigurationAuditEngine,
    ConfigurationAuditReport,
    ConfigurationDriftEngine,
    ConfigurationDriftReport,
    UnregisteredFeatureFlagError,
    config_resolver,
    feature_flag_service,
)
from domain.config.repository import (
    TenantSettingsRepository,
    get_tenant_settings_repository,
)
from domain.config.tenant_settings import TenantSettings
from domain.tenant.context import TenantContext

router = APIRouter(prefix="/api/v1", tags=["Configuration & Feature Flags"])


class FeatureToggleRequest(BaseModel):
    """Payload to mutate a feature flag state."""

    enabled: bool = Field(description="New toggle state")
    tenant_id: str | None = Field(default=None, description="Optional tenant scope")
    changed_by: str | None = Field(default=None, description="Principal modifying the flag")
    reason: str = Field(default="Administrative update", description="Audit rationale")
    step_up_token: str | None = Field(default=None, description="Step-up session token for global flags")


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
    tc: TenantContext = Depends(require_auth),
) -> list[ConfigProvenance]:
    """Inspect all configuration settings with layer provenance (BUILTIN_DEFAULT, ENVIRONMENT, TENANT).

    All secrets (passwords, tokens, keys) are automatically masked for security.
    """
    eff_tenant = tc.effective_tenant_id if (not tc.is_superuser and not tc.has_capability("platform.operate")) else (tenant_id or tc.effective_tenant_id)
    return config_resolver.inspect_all(tenant_id=eff_tenant, mask_secrets=True)


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
    tc: TenantContext = Depends(require_auth),
) -> ConfigProvenance:
    """Inspect provenance and effective value of a single configuration setting."""
    eff_tenant = tc.effective_tenant_id if (not tc.is_superuser and not tc.has_capability("platform.operate")) else (tenant_id or tc.effective_tenant_id)
    try:
        return config_resolver.resolve_provenance(
            setting_key, tenant_id=eff_tenant, mask_secrets=True
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
    tc: TenantContext = Depends(require_auth),
) -> ConfigurationAuditReport:
    """Returns comprehensive configuration audit report accounting for every effective setting."""
    eff_tenant = tc.effective_tenant_id if (not tc.is_superuser and not tc.has_capability("platform.operate")) else (tenant_id or tc.effective_tenant_id)
    engine = ConfigurationAuditEngine()
    return engine.generate_audit_report(tenant_id=eff_tenant, mask_secrets=True)


@router.get(
    "/config/drift",
    response_model=ConfigurationDriftReport,
    summary="Configuration drift detector (Prompt 48 Item 39)",
)
async def get_configuration_drift(
    tenant_id: str | None = Query(
        default=None, description="Optional tenant ID to evaluate tenant configuration drift"
    ),
    tc: TenantContext = Depends(require_auth),
) -> ConfigurationDriftReport:
    """Compares running configuration against shipped defaults and reports all deviations."""
    eff_tenant = tc.effective_tenant_id if (not tc.is_superuser and not tc.has_capability("platform.operate")) else (tenant_id or tc.effective_tenant_id)
    engine = ConfigurationDriftEngine()
    return engine.detect_drift(tenant_id=eff_tenant, mask_secrets=True)


# --- Tenant Settings Endpoints ---


@router.get(
    "/tenants/{tenant_id}/settings", response_model=TenantSettings, summary="Get tenant settings"
)
async def get_tenant_settings(
    tenant_id: str,
    tc: TenantContext = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
    repo: TenantSettingsRepository = Depends(get_tenant_settings_repository),
) -> TenantSettings:
    """Retrieve effective tenant settings profile."""
    if tenant_id != tc.effective_tenant_id and not (tc.is_superuser or tc.has_capability("platform.operate")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access settings of another tenant without super administrator privileges.",
        )
    return await repo.get(tenant_id, session=session)


@router.put(
    "/tenants/{tenant_id}/settings", response_model=TenantSettings, summary="Update tenant settings"
)
async def update_tenant_settings(
    tenant_id: str,
    payload: TenantSettingsUpdateRequest,
    tc: TenantContext = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
    repo: TenantSettingsRepository = Depends(get_tenant_settings_repository),
) -> TenantSettings:
    """Dynamically update tenant configuration (e.g. threshold defaults)."""
    if tenant_id != tc.effective_tenant_id and not (tc.is_superuser or tc.has_capability("platform.operate")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify settings of another tenant without super administrator privileges.",
        )
    tc.require_capability("tenants:settings:write")
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    return await repo.update(tenant_id, update_data, session=session)


# --- Feature Flag Endpoints ---


@router.get("/features", summary="List all registered feature flags")
async def list_features(
    tenant_id: str | None = Query(
        default=None, description="Optional tenant ID to evaluate tenant overrides"
    ),
    tc: TenantContext = Depends(require_auth),
) -> list[dict[str, Any]]:
    """List all registered canonical feature flags and their effective states."""
    eff_tenant = tc.effective_tenant_id if (not tc.is_superuser and not tc.has_capability("platform.operate")) else (tenant_id or tc.effective_tenant_id)
    return feature_flag_service.list_flags(tenant_id=eff_tenant)


@router.get("/features/{flag_key}/evaluate", summary="Evaluate a feature flag")
async def evaluate_feature(
    flag_key: str,
    tenant_id: str | None = Query(default=None, description="Optional tenant ID"),
    tc: TenantContext = Depends(require_auth),
) -> dict[str, Any]:
    """Evaluate whether a registered feature flag is enabled globally or for a specific tenant."""
    eff_tenant = tc.effective_tenant_id if (not tc.is_superuser and not tc.has_capability("platform.operate")) else (tenant_id or tc.effective_tenant_id)
    try:
        enabled = feature_flag_service.evaluate(flag_key, tenant_id=eff_tenant)
        definition = feature_flag_service.get_definition(flag_key)
        return {
            "flag_key": flag_key,
            "name": definition.name,
            "enabled": enabled,
            "tenant_id": eff_tenant,
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
    x_step_up_token: str | None = Header(default=None, alias="X-Step-Up-Token"),
    tc: TenantContext = Depends(require_auth),
) -> dict[str, Any]:
    """Toggle a feature flag globally or for a tenant with mandatory audit event logging."""
    is_global = payload.tenant_id is None or payload.tenant_id.strip() in ("", "global")
    if is_global:
        if not (tc.is_superuser or tc.has_capability("platform.operate")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Toggling global feature flags requires 'platform.operate' capability.",
            )
        step_up = payload.step_up_token or x_step_up_token
        if not step_up or str(step_up).strip() == "":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Step-up authentication required to toggle global feature flags.",
            )
        target_tenant = None
    else:
        if not (tc.is_superuser or tc.has_capability("platform.operate")) and payload.tenant_id != tc.effective_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot toggle feature flags for another tenant.",
            )
        tc.require_capability("features:toggle")
        target_tenant = payload.tenant_id if (tc.is_superuser or tc.has_capability("platform.operate")) else tc.effective_tenant_id

    actor_id = tc.email or tc.user_id
    try:
        audit_event = feature_flag_service.set_flag(
            flag_key=flag_key,
            enabled=payload.enabled,
            tenant_id=target_tenant,
            changed_by=actor_id,
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
    tc: TenantContext = Depends(require_auth),
) -> list[dict[str, Any]]:
    """Retrieve full audit log history of all feature flag modifications."""
    eff_tenant = tc.effective_tenant_id if (not tc.is_superuser and not tc.has_capability("platform.operate")) else (tenant_id or tc.effective_tenant_id)
    events = feature_flag_service.get_audit_log(flag_key=flag_key, tenant_id=eff_tenant)
    return [e.model_dump() for e in events]
