"""Pydantic Models for System Pre-Identity Bootstrap (Prompt 49A).

Enforces:
- Structured, typed verification report with complete seed versions and catalogue counts.
- Strict non-usable declaration (is_interactively_usable=False).
- Defect D-01 closure: explicit pre-identity stage with zero identities/credentials.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class MasterSeedSummary(BaseModel):
    """Execution and version summary for a seeded master data category."""

    master_code: str = Field(description="Unique master type code in the registry manifest")
    record_count: int = Field(description="Number of system records seeded")
    applied_version: int = Field(default=1, description="Version number of applied seed")
    seed_file: str = Field(description="Repository seed file path")


class PreIdentityVerificationReport(BaseModel):
    """Authoritative pre-identity verification report (Prompt 49A Item 14).

    Confirms:
    1. System tenant created from bootstrap master.
    2. All global masters seeded with recorded versions.
    3. Permission catalogue and nine role definitions created.
    4. Default templates, catalogues and provider registrations matching Prompt 00R.
    5. Audit stream initialised with first audit record.
    6. System is not yet usable interactively (zero users, credentials, or grants).
    """

    status: str = Field(
        description="Bootstrap outcome: INITIALIZED, ALREADY_INITIALISED, or FAILED"
    )
    is_already_initialized: bool = Field(
        default=False, description="True if bootstrap detected prior execution and ran idempotently"
    )
    is_interactively_usable: bool = Field(
        default=False,
        description="Explicitly False: no identities exist; authentication & admin belong to Prompt 49B",
    )
    tenant_id: str = Field(description="System tenant unique identifier")
    tenant_name: str = Field(description="System tenant display name")
    reporting_currency: str = Field(description="System tenant reporting currency")
    fiscal_calendar_code: str = Field(description="System tenant fiscal calendar reference")
    fiscal_calendar_start_month: int = Field(description="Month marking start of fiscal year")
    time_zone: str = Field(description="Canonical default timezone")
    retention_profile: dict[str, int] = Field(
        description="Data retention limits (raw telemetry, daily aggregates, audit logs) in days"
    )
    cost_basis_default: str = Field(description="Default cost presentation basis")
    forecast_method_default: str = Field(description="Default spend forecasting algorithm")
    masters_seeded: dict[str, MasterSeedSummary] = Field(
        default_factory=dict,
        description="Summary of seeded masters with counts and applied versions",
    )
    roles_defined: list[str] = Field(
        default_factory=list, description="List of nine built-in role definitions created"
    )
    permission_count: int = Field(description="Total permissions seeded in permission catalogue")
    catalogues_populated: dict[str, int] = Field(
        default_factory=dict, description="Reconciled item counts per enterprise catalogue"
    )
    providers_registered: dict[str, list[str]] = Field(
        default_factory=dict, description="Registered cloud providers with capability profiles"
    )
    audit_stream_initialized: bool = Field(
        default=False, description="True if first audit record was written"
    )
    first_audit_event_id: str = Field(description="Unique ID of bootstrap audit event")
    identities_count: int = Field(
        default=0, description="Explicit count of user identities (must be 0 in Prompt 49A)"
    )
    credentials_count: int = Field(
        default=0, description="Explicit count of credentials (must be 0 in Prompt 49A)"
    )
    grants_count: int = Field(
        default=0, description="Explicit count of scope grants (must be 0 in Prompt 49A)"
    )
    status_statement: str = Field(description="Plain-text human-readable readiness declaration")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="ISO 8601 timestamp of bootstrap completion",
    )
    correlation_id: str = Field(description="Trace correlation ID for bootstrap execution")
