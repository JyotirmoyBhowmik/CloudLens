"""CloudLens Tenant-Level Settings Surface & Accessor.

Defines the tenant-level configuration surface:
1. reporting_currency (ISO 4217)
2. fiscal_calendar (start month)
3. default_time_zone (IANA time zone string)
4. retention_profile (raw metrics, daily aggregates, audit logs)
5. cost_basis_default (billed or amortised)
6. forecast_method_default (linear, exponential, arima)
7. threshold_defaults (budget alerts, cost spikes, idle CPU, anomaly z-scores)
8. approval_limits (auto, manager, director)

Supports hot-reloading with zero restart and no code change.
"""

from typing import Literal

from pydantic import BaseModel, Field


class RetentionProfile(BaseModel):
    """Retention periods in days for historical data."""

    raw_metrics_retention_days: int = Field(
        default=90,
        description="Retention duration for granular unaggregated runtime telemetry (days)",
    )
    daily_aggregates_retention_days: int = Field(
        default=730,
        description="Retention duration for roll-up daily cost and usage aggregates (days)",
    )
    audit_log_retention_days: int = Field(
        default=1095,
        description="Compliance retention duration for audit trail and access logs (days)",
    )


class ThresholdDefaults(BaseModel):
    """FinOps governance, alerting, and rightsizing threshold percentages."""

    budget_alert_threshold_percentage: float = Field(
        default=80.0,
        description="Percentage of allocated budget consumed before firing amber warning alert",
    )
    cost_spike_threshold_percentage: float = Field(
        default=20.0,
        description="Day-over-day cost increase percentage that qualifies as an anomalous spend spike",
    )
    idle_cpu_threshold_percentage: float = Field(
        default=5.0,
        description="Average CPU utilisation percentage below which a resource is considered idle",
    )
    anomaly_z_score_threshold: float = Field(
        default=2.5,
        description="Statistical standard deviations from baseline cost curve to flag anomaly",
    )


class ApprovalLimits(BaseModel):
    """Financial delegation approval limits in reporting currency."""

    auto_approval_limit_amount: float = Field(
        default=1000.0,
        description="Maximum cost impact auto-approved without human sign-off",
    )
    manager_approval_limit_amount: float = Field(
        default=10000.0,
        description="Maximum cost threshold signable by Engineering Manager",
    )
    director_approval_limit_amount: float = Field(
        default=50000.0,
        description="Maximum cost threshold signable by Cloud Director",
    )


class TenantSettings(BaseModel):
    """Canonical tenant configuration profile."""

    tenant_id: str = Field(description="Unique tenant identifier")
    reporting_currency: str = Field(
        default="USD",
        description="Canonical ISO 4217 reporting currency for aggregation and display",
    )
    fiscal_calendar_start_month: int = Field(
        default=1,
        ge=1,
        le=12,
        description="Month numbering (1-12) marking the start of the corporate fiscal year",
    )
    default_time_zone: str = Field(
        default="UTC",
        description="Canonical IANA timezone identifier (e.g. 'UTC', 'America/New_York')",
    )
    cost_basis_default: Literal["billed", "amortised"] = Field(
        default="billed",
        description="Default cost presentation model ('billed' for invoices, 'amortised' for RI/SP spreading)",
    )
    forecast_method_default: Literal["linear", "exponential", "arima"] = Field(
        default="linear",
        description="Default statistical algorithm for spend forecasting",
    )
    retention_profile: RetentionProfile = Field(default_factory=RetentionProfile)
    threshold_defaults: ThresholdDefaults = Field(default_factory=ThresholdDefaults)
    approval_limits: ApprovalLimits = Field(default_factory=ApprovalLimits)


class TenantSettingsStore:
    """In-memory and persistent accessor for dynamic tenant settings.

    Guarantees hot-reloading: changes take effect immediately without code change or restart.
    """

    def __init__(self) -> None:
        self._tenants: dict[str, TenantSettings] = {}

    def get(self, tenant_id: str) -> TenantSettings:
        """Retrieve effective tenant settings, initializing with defaults if not present."""
        if tenant_id not in self._tenants:
            self._tenants[tenant_id] = TenantSettings(tenant_id=tenant_id)
        return self._tenants[tenant_id]

    def update(self, tenant_id: str, new_settings: dict) -> TenantSettings:
        """Update tenant settings dynamically in-place."""
        current = self.get(tenant_id)
        current_data = current.model_dump()

        # Deep merge updates
        for key, value in new_settings.items():
            if (
                key in current_data
                and isinstance(current_data[key], dict)
                and isinstance(value, dict)
            ):
                current_data[key].update(value)
            else:
                current_data[key] = value

        updated = TenantSettings.model_validate(current_data)
        self._tenants[tenant_id] = updated
        return updated

    def reset(self, tenant_id: str | None = None) -> None:
        """Reset settings for testing."""
        if tenant_id:
            self._tenants.pop(tenant_id, None)
        else:
            self._tenants.clear()


# Global singleton tenant settings store
tenant_settings_store = TenantSettingsStore()
