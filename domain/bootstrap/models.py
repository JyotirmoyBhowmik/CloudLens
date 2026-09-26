"""Pydantic Models for System Pre-Identity Bootstrap (Prompt 49A).

Enforces:
- Structured, typed verification report with complete seed versions and catalogue counts.
- Strict non-usable declaration (is_interactively_usable=False).
- Defect D-01 closure: explicit pre-identity stage with zero identities/credentials.
"""

from datetime import UTC, datetime
from typing import Any

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


class SuperuserActivationToken(BaseModel):
    """One-time, time-limited single-use activation credential establishment token (Prompt 49B Item 17)."""

    token: str = Field(..., description="Secret activation token string")
    superuser_email: str = Field(..., description="Target superuser identity email")
    expires_at: datetime = Field(..., description="Expiration timestamp in UTC")
    is_used: bool = Field(default=False, description="True once successfully redeemed")
    issued_to_channel: str = Field(..., description="Configured security contact address")
    activation_link: str = Field(..., description="Complete activation link URL")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Issuance timestamp"
    )


class IdentityVerificationReport(BaseModel):
    """Authoritative Identity Verification Report (Prompt 49B Item 20).

    Confirms:
    1. Exactly one superuser exists with email resolved from master data.
    2. Super Admin role and unrestricted scope across all tenants confirmed.
    3. Mandatory and non-disableable MFA enforced.
    4. No initial password shipped or defaulted; established at first use via activation flow.
    5. Activation link issued to configured security channel.
    6. Break-glass paths enumerated with a count of exactly one.
    7. Protection invariants enforced: immutable account, downgrade prevented, audit non-excludable.
    8. Delegation rule tracking: initial operational handover to Platform Administrator.
    """

    status: str = Field(
        default="PROVISIONED",
        description="Superuser status: PROVISIONED, ACTIVATED, or HANDED_OVER",
    )
    is_interactively_usable: bool = Field(
        default=True,
        description="True: single named superuser identity exists and can achieve signed-in administrative state",
    )
    superuser_email: str = Field(
        ..., description="Superuser identity email resolved from master data"
    )
    superuser_exists: bool = Field(default=True, description="True if superuser entity is created")
    role: str = Field(
        default="GLOBAL_ADMIN", description="Assigned role: Super Admin (GLOBAL_ADMIN)"
    )
    unrestricted_scope: bool = Field(
        default=True, description="Unrestricted platform-wide scope confirmed"
    )
    mfa_enforced: bool = Field(
        default=True, description="True: Multi-Factor Authentication is mandatory"
    )
    mfa_disableable: bool = Field(
        default=False, description="False: Multi-Factor Authentication cannot be disabled"
    )
    has_password: bool = Field(
        default=False,
        description="False prior to activation; no initial password shipped or embedded",
    )
    activation_link_issued: bool = Field(
        default=True, description="True: One-time single-use activation link issued"
    )
    activation_channel: str = Field(..., description="Configured security delivery address")
    break_glass_count: int = Field(
        default=1, description="Count of break-glass paths (strictly exactly 1 per AM-05)"
    )
    break_glass_paths: list[str] = Field(
        default_factory=list,
        description="Enumerated break-glass identities (strictly single superuser)",
    )
    immutable_controls: dict[str, Any] = Field(
        default_factory=lambda: {
            "cannot_be_deleted": True,
            "cannot_be_downgraded": True,
            "audit_exclusion_blocked": True,
            "elevated_audit_retention_days": 2555,
        },
        description="Immutable superuser protection invariants",
    )
    delegation_rule: dict[str, Any] = Field(
        default_factory=lambda: {
            "max_consecutive_routine_days": 3,
            "consecutive_routine_days": 0,
            "delegation_completed": False,
        },
        description="Delegation and routine-use tracking metadata",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="ISO 8601 timestamp of identity verification report",
    )
    correlation_id: str = Field(
        default="", description="Trace correlation ID of verification execution"
    )
