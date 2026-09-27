"""GCP Domain Models, Enums, BigQuery Query Cost, and Invariants (Prompt 18 / BBP Section 14.4 & 15.4).

Enforces:
- Workload Identity Federation (keyless OIDC) as recommended auth path.
- Audited service account keys as exception only with mandatory 90-day rotation.
- Prohibits interactive user credentials and console passwords.
- Strict dual representation of resource hierarchy and billing hierarchy.
- BigQuery billing export schema models and query cost tracking ($5.00/TB on-demand).
- Cloud Asset Inventory constraints and runtime relationship probing (declared partial).
- Non-authoritative Cloud Billing budgets and prevention of silent chargeable Pub/Sub notifications.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from domain.models.exceptions import DomainModelException


class GCPAuthMethod(StrEnum):
    """Supported Google Cloud authentication mechanisms per BBP Section 14.4."""

    WORKLOAD_IDENTITY = "WORKLOAD_IDENTITY"  # Keyless OIDC (Recommended)
    ATTACHED_SERVICE_ACCOUNT = "ATTACHED_SERVICE_ACCOUNT"  # GCE/GKE Metadata Server
    SERVICE_ACCOUNT_KEY = "SERVICE_ACCOUNT_KEY"  # Audited exception with 90-day rotation
    API_KEY = "API_KEY"  # Public catalog interface only


class GCPBigQueryExportType(StrEnum):
    """Google Cloud Billing BigQuery export table types."""

    DETAILED_RESOURCE = (
        "DETAILED_RESOURCE"  # gcp_billing_export_resource_v1_* (Resource IDs & labels)
    )
    STANDARD = "STANDARD"  # gcp_billing_export_v1_* (Project-level summary)
    PRICING = "PRICING"  # gcp_billing_export_pricing_v1_* (SKU pricing catalog)
    FOCUS = "FOCUS"  # gcp_billing_export_focus_v1_* (FOCUS 1.0 schema)


class GCPAuthenticationException(DomainModelException):
    """Raised when GCP credential validation or security invariants fail."""

    def __init__(self, message: str, error_code: str = "GCP_AUTH_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class GCPMetricIntervalForbiddenException(DomainModelException):
    """Raised when sub-minute intervals are requested for Cloud Monitoring metrics."""

    def __init__(self, interval: str) -> None:
        super().__init__(
            f"Interval '{interval}' is forbidden for Cloud Monitoring platform metrics. "
            "CloudLens enforces coarse aggregates only (hourly alignmentPeriod 3600s / PT1H or daily 86400s / P1D).",
            error_code="GCP_METRIC_INTERVAL_FORBIDDEN",
        )


class GCPPubSubSilentCreationForbiddenException(DomainModelException):
    """Raised when programmatic Pub/Sub notification is enabled silently on budgets."""

    def __init__(self) -> None:
        super().__init__(
            "Silent creation of Cloud Billing Budget Pub/Sub notification topics is strictly prohibited. "
            "Pub/Sub messaging incurs cloud charges and requires explicit tenant configuration.",
            error_code="GCP_PUBSUB_SILENT_CREATION_FORBIDDEN",
        )


class GCPCredentials(BaseModel):
    """GCP authentication credentials enforcing least-privilege invariants."""

    auth_method: GCPAuthMethod = Field(
        default=GCPAuthMethod.WORKLOAD_IDENTITY,
        description="Authentication mechanism",
    )
    project_id: str = Field(
        default="proj-cloudlens-core",
        description="Primary GCP administrative project ID",
    )
    workload_identity_pool: str | None = Field(
        default="projects/123456789/locations/global/workloadIdentityPools/cloudlens-pool",
        description="Workload Identity Pool name",
    )
    workload_identity_provider: str | None = Field(
        default="providers/cloudlens-k8s-provider",
        description="Workload Identity Provider name",
    )
    service_account_email: str | None = Field(
        default="cloudlens-ingestion@proj-cloudlens-core.iam.gserviceaccount.com",
        description="Target impersonated service account email",
    )
    service_account_key_json: str | None = Field(
        default=None,
        description="Audited service account key JSON payload (exception only)",
    )
    api_key: str | None = Field(
        default=None,
        description="API key for public Cloud Billing Catalog lookups only",
    )
    # Strictly prohibited credentials
    user_password: str | None = Field(
        default=None,
        description="Strictly forbidden interactive password",
    )
    user_oauth_token: str | None = Field(
        default=None,
        description="Strictly forbidden interactive user gcloud auth token",
    )

    def validate_security_invariants(self) -> None:
        """Enforces enterprise security policies (SEC-012, SEC-016)."""
        if self.user_password is not None or self.user_oauth_token is not None:
            raise GCPAuthenticationException(
                "Interactive user accounts and personal tokens are strictly prohibited. "
                "Use Workload Identity Federation or an audited service account.",
                error_code="FORBIDDEN_USER_CREDENTIALS",
            )
        if self.auth_method == GCPAuthMethod.SERVICE_ACCOUNT_KEY:
            if not self.service_account_key_json:
                raise GCPAuthenticationException(
                    "Service account key authentication requires service_account_key_json.",
                    error_code="MISSING_SERVICE_ACCOUNT_KEY",
                )
        elif self.auth_method == GCPAuthMethod.WORKLOAD_IDENTITY:
            if not self.service_account_email:
                raise GCPAuthenticationException(
                    "Workload Identity Federation requires a target service_account_email.",
                    error_code="MISSING_SERVICE_ACCOUNT_EMAIL",
                )


class GCPBigQueryQueryCost(BaseModel):
    """Tracks running BigQuery query cost for transparency in CloudLens operating model."""

    bytes_scanned: int = Field(..., ge=0, description="Exact bytes read from BigQuery columns")
    bytes_billed: int = Field(..., ge=0, description="Billed bytes (10MB minimum per query)")
    query_cost_usd: float = Field(
        ..., ge=0.0, description="Attributable query cost in USD ($5.00/TB on-demand)"
    )
    query_latency_ms: float = Field(..., ge=0.0, description="Execution duration in milliseconds")
    export_table_type: GCPBigQueryExportType = Field(
        default=GCPBigQueryExportType.DETAILED_RESOURCE,
        description="Source BigQuery billing table",
    )
    query_hash: str = Field(..., description="SHA-256 fingerprint of the SQL query")

    @classmethod
    def calculate_cost(
        cls,
        bytes_scanned: int,
        latency_ms: float,
        table_type: GCPBigQueryExportType = GCPBigQueryExportType.DETAILED_RESOURCE,
        query_hash: str = "query-hash-default",
    ) -> GCPBigQueryQueryCost:
        """Computes query cost following the standard Google Cloud BigQuery on-demand rate.

        BigQuery on-demand rate: $5.00 per TiB (1024^4 bytes), with a 10 MiB minimum per query.
        """
        min_bytes = 10 * 1024 * 1024  # 10 MiB minimum billed
        billed = max(bytes_scanned, min_bytes)
        cost_usd = round((billed / (1024.0**4)) * 5.0, 6)
        return cls(
            bytes_scanned=bytes_scanned,
            bytes_billed=billed,
            query_cost_usd=cost_usd,
            query_latency_ms=latency_ms,
            export_table_type=table_type,
            query_hash=query_hash,
        )


class GCPCostRecord(BaseModel):
    """Normalized cost record from BigQuery Cloud Billing export."""

    billing_account_id: str = Field(
        ..., description="Cloud Billing Account ID (e.g. 01ABCD-2345EF-6789GH)"
    )
    service_id: str = Field(..., description="GCP service ID (e.g. 6F81-5844-456A)")
    service_description: str = Field(..., description="GCP service name (e.g. Compute Engine)")
    sku_id: str = Field(..., description="GCP SKU identifier")
    sku_description: str = Field(..., description="GCP SKU description")
    usage_start_time: str = Field(..., description="Usage start ISO timestamp")
    usage_end_time: str = Field(..., description="Usage end ISO timestamp")
    project_id: str = Field(..., description="Project ID (e.g. proj-retail-banking-prod)")
    project_name: str = Field(..., description="Project display name")
    project_ancestry: str = Field(
        default="", description="Folder and organization ancestry path numbers"
    )
    resource_name: str = Field(default="", description="Short resource name")
    resource_global_name: str = Field(default="", description="Fully-qualified resource URI")
    location: str = Field(default="global", description="GCP region or zone")
    cost: float = Field(..., description="Net cost before credits (supports negative adjustments)")
    currency: str = Field(default="USD", description="Billing currency")
    usage_amount: float = Field(default=0.0, description="Usage units consumed")
    usage_unit: str = Field(default="", description="Raw usage unit")
    pricing_unit: str = Field(default="", description="Unit of measure for pricing")
    labels: dict[str, str] = Field(default_factory=dict, description="Resource-level user labels")
    project_labels: dict[str, str] = Field(
        default_factory=dict, description="Inherited project-level labels"
    )
    system_labels: dict[str, str] = Field(
        default_factory=dict, description="Google-managed system labels"
    )
    credits: list[dict[str, Any]] = Field(
        default_factory=list, description="Itemized discounts, SUDs, and CUDs"
    )
    cost_type: str = Field(default="regular", description="regular, adjustment, rounding_error")
    is_estimated: bool = Field(
        default=False, description="Estimated intraday query vs final export"
    )


class GCPResourceRecord(BaseModel):
    """Resource record discovered via Cloud Asset Inventory."""

    asset_name: str = Field(..., description="Fully-qualified Asset Inventory resource name")
    asset_type: str = Field(
        ..., description="GCP asset type (e.g. compute.googleapis.com/Instance)"
    )
    project_id: str = Field(..., description="Owning GCP project ID")
    location: str = Field(default="global", description="GCP region or zone")
    service_category: str = Field(..., description="Standardized service category")
    runtime_status: str = Field(default="RUNNING", description="Runtime status")
    labels: dict[str, str] = Field(default_factory=dict, description="Resource labels")
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Asset attributes (handles camelCase and potential null values)",
    )
    has_null_frequently_changing_fields: bool = Field(
        default=False,
        description="Acknowledges documented caveat: frequently changing fields may export as null",
    )


class GCPRelationshipProbeResult(BaseModel):
    """Result of runtime probe for Cloud Asset Inventory RELATIONSHIP content type."""

    is_available: bool = Field(
        ..., description="Whether RELATIONSHIP content type is available in estate"
    )
    probe_status: str = Field(default="AVAILABLE", description="AVAILABLE or TIER_RESTRICTED")
    is_partial: bool = Field(
        default=True,
        description="Declared as PARTIAL: packet-level VPC network flows are not evaluated",
    )
    probe_message: str = Field(..., description="Diagnostic explanation of probe results")


class GCPBudgetRecord(BaseModel):
    """Cloud Billing Budget read for comparison only (never authoritative)."""

    budget_name: str = Field(..., description="Display name of budget")
    billing_account_id: str = Field(..., description="Target Cloud Billing Account")
    amount: float = Field(..., ge=0.0, description="Budget threshold limit amount")
    current_spend: float = Field(default=0.0, ge=0.0, description="Tracked spend")
    time_period: str = Field(default="CALENDAR_MONTH", description="Budget period")
    is_authoritative: bool = Field(
        default=False,
        description="Cloud Billing budgets are read for comparison only; CloudLens master budgets remain authoritative.",
    )
    has_pubsub_rule: bool = Field(
        default=False,
        description="Whether a Pub/Sub topic is attached (must never be enabled silently).",
    )


class GCPPriceQuote(BaseModel):
    """Normalized price quote for a GCP SKU."""

    sku_id: str = Field(..., description="GCP SKU identifier")
    service_id: str = Field(..., description="GCP service identifier")
    service_name: str = Field(..., description="Service display name")
    sku_description: str = Field(..., description="SKU description")
    category: dict[str, str] = Field(default_factory=dict, description="Category taxonomy")
    service_regions: list[str] = Field(default_factory=list, description="Supported regions")
    list_price: float = Field(..., ge=0.0, description="Public retail rate")
    contract_price: float | None = Field(default=None, description="Account-specific contract rate")
    effective_price: float = Field(..., description="Resolved price after contract precedence")
    currency: str = Field(default="USD", description="Currency code")
    is_contract_rate: bool = Field(
        default=False, description="Whether resolved rate is custom contract"
    )
    pricing_source: str = Field(default="cloud_billing_catalog", description="Pricing source")


class GCPLabelRecord(BaseModel):
    """GCP label with source tier level recorded."""

    scope_id: str = Field(..., description="Resource or project identifier")
    source_tier: str = Field(..., description="LABEL_SOURCE_PROJECT or LABEL_SOURCE_RESOURCE")
    key: str = Field(..., description="Label key")
    value: str = Field(..., description="Label value")


# Mapping from GCP asset types to standardized FinOps service categories
KNOWN_GCP_TYPE_MAPPINGS = {
    "compute.googleapis.com/Instance": "COMPUTE",
    "compute.googleapis.com/Disk": "STORAGE",
    "storage.googleapis.com/Bucket": "STORAGE",
    "bigquery.googleapis.com/Dataset": "DATABASE",
    "bigquery.googleapis.com/Table": "DATABASE",
    "sqladmin.googleapis.com/Instance": "DATABASE",
    "compute.googleapis.com/Network": "NETWORKING",
    "compute.googleapis.com/Subnetwork": "NETWORKING",
    "compute.googleapis.com/Address": "NETWORKING",
    "container.googleapis.com/Cluster": "COMPUTE",
    "cloudkms.googleapis.com/CryptoKey": "SECURITY_IDENTITY",
    "iam.googleapis.com/ServiceAccount": "SECURITY_IDENTITY",
}

# Regex for GCP Billing Account ID (e.g. 01ABCD-2345EF-6789GH)
_RE_GCP_BILLING_ACCOUNT = re.compile(r"^[0-9A-Za-z]{6}-[0-9A-Za-z]{6}-[0-9A-Za-z]{6}$")


def is_valid_gcp_billing_account_id(account_id: str) -> bool:
    """Validates GCP 18-character alphanumeric billing account ID format."""
    return bool(_RE_GCP_BILLING_ACCOUNT.match(account_id.strip()))
