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


class ConnectorSettings(BaseModel):
    """Configuration surface for provider connectors, rate limiting, and circuit breakers (Prompt 14)."""

    default_page_size: int = Field(
        default=100,
        description="Default pagination batch size for connector discovery and collection operations",
    )
    max_page_size: int = Field(
        default=1000,
        description="Maximum bounded page size permitted across all connector calls",
    )
    default_hourly_quota: int = Field(
        default=10000,
        description="Default hourly API request quota per connector",
    )
    default_rate_limit_per_second: float = Field(
        default=50.0,
        description="Token bucket default replenishment rate (tokens per second)",
    )
    default_burst_capacity: float = Field(
        default=50.0,
        description="Token bucket maximum burst allowance",
    )
    circuit_breaker_failure_threshold: int = Field(
        default=5,
        description="Consecutive failure count triggering circuit breaker OPEN state",
    )
    circuit_breaker_recovery_timeout_seconds: float = Field(
        default=30.0,
        description="Cooldown duration before circuit breaker attempts HALF_OPEN probe",
    )
    circuit_breaker_success_threshold: int = Field(
        default=2,
        description="Consecutive successful probes required to reset circuit breaker to CLOSED",
    )
    adaptive_concurrency_min: int = Field(
        default=1,
        description="Minimum concurrent requests under extreme throttling",
    )
    adaptive_concurrency_max: int = Field(
        default=16,
        description="Maximum concurrent requests allowed during stable operations",
    )
    adaptive_concurrency_initial: int = Field(
        default=8,
        description="Initial concurrency ceiling on connector startup",
    )


class SyncScheduleSettings(BaseModel):
    """Synchronization intervals, restatement windows, and warning thresholds (Prompt 15 Item 98)."""

    inventory_interval_hours: int = Field(
        default=4,
        description="Default inventory incremental sync interval in hours (recommended 4-6h)",
    )
    inventory_full_sync_interval_hours: int = Field(
        default=24,
        description="Daily full inventory reconciliation sync interval in hours",
    )
    cost_interval_hours: int = Field(
        default=6,
        description="Cost ingestion cadence in the open period in hours (recommended 4-8h)",
    )
    cost_restatement_lookback_days: int = Field(
        default=3,
        description="Look-back window in days for cost restatement and late-arriving billing records (3-7 days)",
    )
    usage_interval_hours: int = Field(
        default=1,
        description="Usage metrics collection interval in hours (hourly to daily)",
    )
    pricing_interval_hours: int = Field(
        default=168,
        description="Pricing public catalog refresh interval in hours (weekly = 168h)",
    )
    pricing_on_demand_unknown_sku: bool = Field(
        default=True,
        description="Whether to perform on-demand lookup upon encountering an unknown SKU",
    )
    relationships_interval_hours: int = Field(
        default=24,
        description="Resource graph and dependency relationship discovery interval in hours (daily)",
    )
    provider_budgets_interval_hours: int = Field(
        default=24,
        description="Provider-native budget and quota synchronization interval in hours (daily)",
    )
    max_sync_lag_warning_hours: int = Field(
        default=24,
        description="Sync freshness threshold in hours before an operator staleness warning is flagged",
    )
    # Cadence validation thresholds (warn if interval is unlikely to yield new data)
    min_cost_interval_hours: int = Field(
        default=4,
        description="Minimum cost sync interval before issuing a cadence warning (provider billing exports update ~3x/day)",
    )
    min_pricing_interval_hours: int = Field(
        default=24,
        description="Minimum pricing sync interval before issuing a cadence warning (catalogs update weekly)",
    )
    min_budget_interval_hours: int = Field(
        default=6,
        description="Minimum provider budget sync interval before issuing a cadence warning",
    )


class WizardSettings(BaseModel):
    """Configuration and pre-completion estimation multipliers for onboarding wizard (Prompt 15 Items 100, 103)."""

    include_future_scopes_default: bool = Field(
        default=True,
        description="Default setting for automatically including newly discovered scopes",
    )
    default_estimated_resource_multiplier: int = Field(
        default=150,
        description="Estimated average cloud resources per discovered scope for pre-completion sizing",
    )
    estimated_seconds_per_scope: int = Field(
        default=12,
        description="Estimated initial discovery synchronization duration per scope in seconds",
    )
    estimated_metric_calls_per_resource: int = Field(
        default=5,
        description="Estimated metric API calls per resource during monitoring runs",
    )
    estimated_provider_cost_per_10k_calls: float = Field(
        default=0.01,
        description="Estimated cloud provider monitoring API cost per 10,000 requests in USD",
    )
    session_expiry_days: int = Field(
        default=7,
        description="Onboarding wizard saved draft session lifetime in days",
    )


class DataValidationSettings(BaseModel):
    """Data integrity and monetary sanity check thresholds for ingestion validation (Prompt 15 Item 99)."""

    max_single_line_item_amount: float = Field(
        default=1000000.0,
        description="Maximum single cost line item amount in reporting currency before flagging monetary sanity failure",
    )
    min_single_line_item_amount: float = Field(
        default=-50000.0,
        description="Minimum credit or refund single line item amount allowed before quarantine",
    )
    max_records_per_scope_warning: int = Field(
        default=500000,
        description="Sanity threshold for single scope record count in an individual ingestion cycle",
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
    connector_settings: ConnectorSettings = Field(default_factory=ConnectorSettings)
    sync_schedule_settings: SyncScheduleSettings = Field(default_factory=SyncScheduleSettings)
    wizard_settings: WizardSettings = Field(default_factory=WizardSettings)
    data_validation_settings: DataValidationSettings = Field(default_factory=DataValidationSettings)
    is_demo_mode: bool = Field(
        default=False,
        description="Flag indicating if tenant is operating in synthetic Demo Mode with simulated data",
    )
    demo_scenario: str | None = Field(
        default=None,
        description="Active named demo scenario if in demo mode",
    )
    # Authentication & Session Settings (Prompt 10)
    jit_provisioning_enabled: bool = Field(
        default=False,
        description="Whether Just-In-Time user provisioning is enabled for OIDC/SAML sign-in",
    )
    group_to_role_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Tenant-specific IdP group to canonical SystemRole mapping",
    )
    access_token_ttl_seconds: int = Field(
        default=900,
        description="Access token lifespan in seconds (15 minutes default)",
    )
    refresh_token_ttl_seconds: int = Field(
        default=86400,
        description="Refresh token lifespan in seconds (24 hours default)",
    )
    session_idle_timeout_seconds: int = Field(
        default=1800,
        description="Idle session timeout in seconds (30 minutes default)",
    )
    session_absolute_lifetime_seconds: int = Field(
        default=28800,
        description="Absolute maximum session duration in seconds (8 hours default)",
    )
    step_up_token_ttl_seconds: int = Field(
        default=300,
        description="Step-up authentication elevated claim validity duration in seconds (5 minutes default)",
    )
    max_break_glass_accounts: int = Field(
        default=2,
        description="Strictly limited maximum count of local break-glass emergency accounts per tenant",
    )


class TenantSettingsStore:
    """Delegating accessor for dynamic tenant settings (Prompt P03).

    Backed by PostgreSQL via TenantSettingsRepository; eliminates in-memory dicts.
    """

    def get(self, tenant_id: str) -> TenantSettings:
        """Retrieve effective tenant settings from repository."""
        from domain.config.repository import get_tenant_settings_repository
        return get_tenant_settings_repository().get_sync(tenant_id)

    def update(self, tenant_id: str, new_settings: dict) -> TenantSettings:
        """Update tenant settings dynamically in repository."""
        from domain.config.repository import get_tenant_settings_repository
        return get_tenant_settings_repository().update_sync(tenant_id, new_settings)

    def update_settings(self, tenant_id: str, settings: TenantSettings) -> None:
        """Sets or replaces tenant settings in repository."""
        from domain.config.repository import get_tenant_settings_repository
        get_tenant_settings_repository().save_sync(settings)

    def set(self, tenant_id: str, settings: TenantSettings) -> None:
        """Alias for update_settings."""
        self.update_settings(tenant_id, settings)

    def reset(self, tenant_id: str | None = None) -> None:
        """Reset settings for testing."""
        from domain.config.repository import get_tenant_settings_repository
        repo = get_tenant_settings_repository()
        if hasattr(repo, "reset"):
            repo.reset(tenant_id)


# Backward-compatible delegator (internal dict singleton removed)
tenant_settings_store = TenantSettingsStore()

