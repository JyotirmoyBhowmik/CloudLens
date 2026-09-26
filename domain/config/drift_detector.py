"""Configuration Drift Detector (Prompt 48 Item 39).

Enforces:
1. Compares the running configuration against shipped defaults.
2. Reports every deviation so support can tell instantly whether an issue
   is a product defect or a configuration choice.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from domain.config.layers import ConfigLayer, ConfigProvenance
from domain.config.resolver import ConfigurationResolver, config_resolver
from domain.config.surface import SystemConfig
from domain.config.tenant_settings import TenantSettings


class SettingDriftEntry(BaseModel):
    """Specification of an individual configuration deviation from shipped defaults."""

    key: str = Field(description="Dotted configuration key, e.g. 'database.pool_size'")
    shipped_default_value: Any = Field(description="Baseline shipped default value")
    effective_value: Any = Field(description="Current effective running value")
    overriding_layer: str = Field(
        description="Layer responsible for drift ('environment' or 'tenant')"
    )
    description: str = Field(description="Setting description")
    is_secret: bool = Field(description="Whether the parameter is a sensitive credential")
    tenant_id: str | None = Field(default=None, description="Tenant scope if tenant-specific")


class ConfigurationDriftReport(BaseModel):
    """Diagnostic comparison of running configuration against factory baseline."""

    generated_at: str = Field(description="Inspection timestamp in ISO 8601 UTC")
    tenant_id: str | None = Field(default=None, description="Scope tenant identifier")
    total_settings_evaluated: int = Field(description="Total count of parameters evaluated")
    drift_count: int = Field(description="Number of parameters deviating from factory baseline")
    clean_count: int = Field(
        description="Number of parameters adhering strictly to factory baseline"
    )
    is_drift_detected: bool = Field(
        description="True if one or more parameters deviate from defaults"
    )
    drift_percentage: float = Field(description="Percentage of configuration that has drifted")
    diagnosis: str = Field(description="High-level operational support diagnosis")
    deviations: list[SettingDriftEntry] = Field(
        default_factory=list, description="List of all detected deviations"
    )


class ConfigurationDriftEngine:
    """Detects configuration drift against platform factory defaults."""

    def __init__(self, resolver: ConfigurationResolver | None = None) -> None:
        self._resolver = resolver or config_resolver
        self._default_system = SystemConfig()
        self._default_tenant = TenantSettings(tenant_id="default")

    def _get_shipped_default(self, key: str, tenant_id: str | None = None) -> Any:
        parts = key.split(".")
        # System section
        if len(parts) == 2 and hasattr(self._default_system, parts[0]):
            sub = getattr(self._default_system, parts[0])
            if hasattr(sub, parts[1]):
                return getattr(sub, parts[1])

        # Tenant section
        if tenant_id is not None:
            if len(parts) == 2 and hasattr(self._default_tenant, parts[0]):
                sub = getattr(self._default_tenant, parts[0])
                if hasattr(sub, parts[1]):
                    return getattr(sub, parts[1])
            if len(parts) == 1 and hasattr(self._default_tenant, key):
                return getattr(self._default_tenant, key)

        return None

    def detect_drift(
        self,
        tenant_id: str | None = None,
        mask_secrets: bool = True,
    ) -> ConfigurationDriftReport:
        """Compares current running configuration with shipped factory defaults.

        Prompt 48 Item 39: Reports every deviation so support can tell instantly
        whether a problem is a product defect or a configuration choice.
        """
        provenances: list[ConfigProvenance] = self._resolver.inspect_all(
            tenant_id=tenant_id,
            mask_secrets=mask_secrets,
        )

        deviations: list[SettingDriftEntry] = []
        clean_count = 0

        for prov in provenances:
            shipped_val = self._get_shipped_default(prov.key, tenant_id=tenant_id)

            # Check if layer is not BUILTIN_DEFAULT or unmasked/effective value differs
            is_overridden = prov.layer != ConfigLayer.BUILTIN_DEFAULT

            if is_overridden:
                display_default = "******" if (prov.is_secret and mask_secrets) else shipped_val
                deviations.append(
                    SettingDriftEntry(
                        key=prov.key,
                        shipped_default_value=display_default,
                        effective_value=prov.effective_value,
                        overriding_layer=prov.layer.value,
                        description=prov.description,
                        is_secret=prov.is_secret,
                        tenant_id=prov.tenant_id,
                    )
                )
            else:
                clean_count += 1

        total = len(provenances)
        drift_count = len(deviations)
        drift_pct = round((drift_count / total * 100.0), 2) if total > 0 else 0.0
        has_drift = drift_count > 0

        diagnosis = (
            f"DRIFT_DETECTED: {drift_count} of {total} settings ({drift_pct}%) deviate from shipped defaults. "
            "Inspect deviations to isolate operational choices from core bugs."
            if has_drift
            else "CLEAN: All running configuration settings conform 100% to factory shipped defaults."
        )

        return ConfigurationDriftReport(
            generated_at=datetime.now(UTC).isoformat(),
            tenant_id=tenant_id,
            total_settings_evaluated=total,
            drift_count=drift_count,
            clean_count=clean_count,
            is_drift_detected=has_drift,
            drift_percentage=drift_pct,
            diagnosis=diagnosis,
            deviations=deviations,
        )
