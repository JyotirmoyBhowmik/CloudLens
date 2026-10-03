"""Domain Models, Enums, and Schemas for Reporting and Export Engine (Prompt 35 / BBP Section 36).

Enforces:
- 14 MVP report types (RPT-01 to RPT-14) plus 5 pricing reports (RPT-15 to RPT-19).
- Phase 2 flag-gated reports (Unusual Consumption, Idle Resources).
- Report parameters: period, scope, provider, grouping, currency, cost basis, unallocated inclusion.
- Complete Provenance Footer: generation time, per-provider freshness, cost basis, currency policy, requester identity, access filtering disclosure.
- Asynchronous generation jobs with time-limited download tokens.
- Flag-gated recurring report schedules.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.models.base import CanonicalEntity


class ReportCategory(StrEnum):
    """Business domain category for reporting."""

    FINANCIAL = "FINANCIAL"
    OPERATIONAL = "OPERATIONAL"
    ARCHITECTURE = "ARCHITECTURE"
    GOVERNANCE = "GOVERNANCE"
    PRICING = "PRICING"
    SECURITY = "SECURITY"
    AUDIT = "AUDIT"


class ExportFormat(StrEnum):
    """Supported export presentation and data formats."""

    PDF = "PDF"
    XLSX = "XLSX"
    CSV = "CSV"
    JSON = "JSON"
    PARQUET = "PARQUET"


class ReportCode(StrEnum):
    """Canonical report identification codes (BBP Section 36: RPT-01 to RPT-19)."""

    # MVP Report Set (14)
    RPT_01_MONTHLY_COST = "RPT-01"
    RPT_02_PROVIDER_COST = "RPT-02"
    RPT_03_SERVICE_COST = "RPT-03"
    RPT_04_BUDGET_VARIANCE = "RPT-04"
    RPT_05_SPEND_FORECAST = "RPT-05"
    RPT_06_USAGE_TELEMETRY = "RPT-06"
    RPT_07_RUNTIME_COMPLIANCE = "RPT-07"
    RPT_08_DEPENDENCY_CHAIN = "RPT-08"
    RPT_09_GOVERNANCE_EXCEPTIONS = "RPT-09"
    RPT_10_CONNECTOR_STATUS = "RPT-10"
    RPT_11_EXECUTIVE_SUMMARY = "RPT-11"
    RPT_12_RECONCILIATION = "RPT-12"
    RPT_13_ACCESS_REVIEW = "RPT-13"
    RPT_14_AUDIT_EXTRACT = "RPT-14"

    # Pricing-Specific Reports (5)
    RPT_15_PRICING_RATES = "RPT-15"
    RPT_16_FREE_TIER_USAGE = "RPT-16"
    RPT_17_COST_DRIVERS = "RPT-17"
    RPT_18_PRICING_CHANGES = "RPT-18"
    RPT_19_DATA_FRESHNESS = "RPT-19"

    # Phase 2 Flag-Gated Reports (2)
    RPT_P2_UNUSUAL_CONSUMPTION = "RPT-P2-UNUSUAL"
    RPT_P2_IDLE_RESOURCES = "RPT-P2-IDLE"


class ReportParameters(BaseModel):
    """Parameterisation specification for report generation."""

    model_config = ConfigDict(extra="ignore")

    period: str | None = Field(default=None, description="Billing period format YYYY-MM")
    scope_id: str | None = Field(default=None, description="Target scope ID for RBAC and filtering")
    provider: str | None = Field(
        default=None, description="Cloud provider filter (AWS, AZURE, GCP, OCI)"
    )
    grouping: str | None = Field(
        default=None, description="Aggregation dimension (provider, service, scope, owner)"
    )
    currency: str = Field(default="USD", description="Target currency code (e.g. USD, EUR, GBP)")
    cost_basis: str = Field(
        default="BILLED", description="Cost basis: BILLED, EFFECTIVE, LIST, CONTRACTED"
    )
    include_unallocated: bool = Field(
        default=False, description="Whether unallocated costs are included"
    )
    custom_filters: dict[str, Any] = Field(
        default_factory=dict, description="Additional report-specific filters"
    )


class ReportProvenance(BaseModel):
    """Mandatory provenance footer state on every platform report (Prompt 35)."""

    generation_time: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC),
        description="Exact UTC timestamp when report was generated",
    )
    data_freshness_per_provider: dict[str, str] = Field(
        default_factory=dict,
        description="Last successful ingestion timestamp per cloud provider",
    )
    cost_basis: str = Field(..., description="Cost basis applied (BILLED, EFFECTIVE, etc.)")
    currency_policy: str = Field(
        ..., description="Currency policy disclosure (e.g. USD native without conversion)"
    )
    requester_identity: str = Field(..., description="User ID or email identity of the requester")
    access_filtering_occurred: bool = Field(
        default=False,
        description="True if results were filtered based on caller scope grants",
    )
    filtering_disclosure: str | None = Field(
        default=None,
        description="Explanatory statement when access filtering has occurred",
    )

    def format_footer_text(self) -> str:
        """Formats provenance footer into human-readable text."""
        lines = [
            f"Generated At (UTC): {self.generation_time.isoformat()}",
            f"Requester Identity: {self.requester_identity}",
            f"Cost Basis: {self.cost_basis} | Currency Policy: {self.currency_policy}",
            f"Provider Data Freshness: {', '.join(f'{k}: {v}' for k, v in self.data_freshness_per_provider.items()) or 'N/A'}",
        ]
        if self.access_filtering_occurred:
            lines.append(f"ACCESS FILTERING DISCLOSURE: {self.filtering_disclosure}")
        return "\n".join(lines)


class ReportDefinition(BaseModel):
    """Catalogue metadata for an available report template."""

    id: str = Field(..., description="Machine template key (e.g. tpl-cost-monthly)")
    code: ReportCode = Field(..., description="Catalogue code (e.g. RPT-01)")
    name: str = Field(..., description="Human-readable title")
    description: str = Field(..., description="Detailed description of report contents and purpose")
    category: ReportCategory = Field(..., description="Functional domain category")
    supported_formats: list[ExportFormat] = Field(
        default_factory=lambda: [
            ExportFormat.PDF,
            ExportFormat.XLSX,
            ExportFormat.CSV,
            ExportFormat.JSON,
        ],
        description="Permitted export formats",
    )
    default_grouping: str = Field(default="service", description="Default grouping dimension")
    is_phase_2: bool = Field(
        default=False, description="Whether report is gated behind Phase 2 flag"
    )
    phase_2_flag: str | None = Field(default=None, description="Feature flag key if Phase 2 gated")


class ReportData(BaseModel):
    """Raw structured data payload produced by report generators before export formatting."""

    template_id: str
    report_code: str
    title: str
    subtitle: str
    category: str
    period: str
    columns: list[str]
    rows: list[dict[str, Any]]
    summary: dict[str, Any] = Field(default_factory=dict)
    provenance: ReportProvenance
    row_count: int = 0


class ReportJob(CanonicalEntity):
    """Lifecycle record for an asynchronous report generation job."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    template_id: str = Field(..., description="Report template ID")
    format: ExportFormat = Field(..., description="Export format requested")
    parameters: ReportParameters = Field(default_factory=ReportParameters)
    status: str = Field(default="PENDING", description="PENDING, PROCESSING, COMPLETED, FAILED")
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    completed_at: dt.datetime | None = Field(default=None)
    download_token: str | None = Field(
        default=None, description="Secure time-limited download token"
    )
    download_url: str | None = Field(
        default=None, description="Relative URL to download generated artifact"
    )
    expires_at: dt.datetime | None = Field(
        default=None, description="TTL timestamp when download token expires"
    )
    row_count: int = 0
    file_size_bytes: int = 0
    error_message: str | None = None
    output_filename: str = Field(default="report.csv")
    provenance: ReportProvenance | None = None


class ScheduledReport(CanonicalEntity):
    """Recurring report delivery schedule (Phase 2 feature-flagged)."""

    tenant_id: str = Field(..., description="Organization tenant ID")
    template_id: str = Field(..., description="Target report template")
    parameters: ReportParameters = Field(default_factory=ReportParameters)
    format: ExportFormat = Field(default=ExportFormat.PDF)
    cron_expression: str = Field(
        ..., description="Standard 5-part cron expression (e.g. 0 8 1 * *)"
    )
    recipients: list[str] = Field(default_factory=list, description="Target email recipients")
    storage_destination: str | None = Field(
        default=None, description="Optional object storage URI (s3://, gs://, az://)"
    )
    is_active: bool = Field(default=True)
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    last_run_at: dt.datetime | None = None
    next_run_at: dt.datetime | None = None
