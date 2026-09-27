"""AWS Domain Models, Enums, CUR 2.0 Configurations, and Sizing Envelope (Prompt 17 / BBP Section 14.3 & 15.4).

Enforces:
- Cross-account IAM role assumption with mandatory ExternalId.
- OIDC web identity federation and audited access key exceptions.
- AWS Organizations hierarchy with nested OUs and Account billing boundary.
- CUR 2.0 fixed schema vs legacy CUR migration path.
- Resource-level inclusion sizing envelope and capacity planning calculation.
- AWS Cost Categories modeled as distinct entities, not merged into tags.
- Non-uniform inventory coverage with Unclassified typing for unsupported resources.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from domain.models.exceptions import DomainModelException


class AWSAuthMethod(StrEnum):
    """Supported AWS authentication mechanisms per BBP Section 14.3."""

    ASSUME_ROLE = "ASSUME_ROLE"  # Cross-account IAM role assumption + ExternalId (Recommended)
    OIDC_FEDERATION = "OIDC_FEDERATION"  # EKS IRSA / Kubernetes Pod Identity
    IDENTITY_CENTER = "IDENTITY_CENTER"  # AWS IAM Identity Center (SSO)
    ACCESS_KEYS = "ACCESS_KEYS"  # Audited exception only with mandatory 90-day rotation


class CURTimeGranularity(StrEnum):
    """BCM Data Exports CUR 2.0 time granularity options."""

    HOURLY = "HOURLY"
    DAILY = "DAILY"
    MONTHLY = "MONTHLY"


class CURCompression(StrEnum):
    """CUR 2.0 export delivery compression options."""

    PARQUET_SNAPPY = "PARQUET_SNAPPY"
    GZIP_CSV = "GZIP_CSV"


class AWSAuthenticationException(DomainModelException):
    """Raised when AWS credential validation or role assumption security invariants fail."""

    def __init__(self, message: str, error_code: str = "AWS_AUTH_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class AWSMetricIntervalForbiddenException(DomainModelException):
    """Raised when sub-minute intervals are requested for coarse CloudWatch metrics."""

    def __init__(self, interval: str) -> None:
        super().__init__(
            f"Interval '{interval}' is forbidden for AWS platform metrics. "
            "CloudLens enforces coarse aggregates only (hourly PT1H / Period 3600 or daily P1D / Period 86400).",
            error_code="AWS_METRIC_INTERVAL_FORBIDDEN",
        )


class AWSCredentials(BaseModel):
    """AWS authentication credentials enforcing least-privilege invariants."""

    role_arn: str | None = Field(
        default=None,
        description="Target cross-account IAM role ARN (e.g. arn:aws:iam::123456789012:role/CloudLensRole)",
    )
    external_id: str | None = Field(
        default=None,
        description="Mandatory cryptographic ExternalId string preventing Confused Deputy attacks",
    )
    role_session_name: str = Field(
        default="CloudLensSession",
        description="STS session identifier",
    )
    auth_method: AWSAuthMethod = Field(
        default=AWSAuthMethod.ASSUME_ROLE,
        description="Authentication mechanism",
    )
    web_identity_token_path: str | None = Field(
        default=None,
        description="File path or token string for OIDC web identity federation",
    )
    access_key_id: str | None = Field(
        default=None,
        description="Audited IAM user access key (exception only)",
    )
    secret_access_key: str | None = Field(
        default=None,
        description="Audited IAM user secret key (exception only)",
    )
    # Strictly prohibited credentials
    root_email: str | None = Field(
        default=None,
        description="Strictly forbidden root user email (must remain null)",
    )
    user_password: str | None = Field(
        default=None,
        description="Strictly forbidden console password (must remain null)",
    )
    management_account_id: str = Field(
        default="112233445566",
        description="AWS Organizations Management Account ID (12 digits)",
    )

    def validate_security_invariants(self) -> None:
        """Enforces enterprise security policies (SEC-012, SEC-016)."""
        if self.root_email is not None:
            raise AWSAuthenticationException(
                "AWS Root user credentials are strictly forbidden. Use Cross-Account IAM Role assumption.",
                error_code="FORBIDDEN_ROOT_CREDENTIALS",
            )
        if self.user_password is not None:
            raise AWSAuthenticationException(
                "Interactive user console passwords are strictly forbidden in CloudLens.",
                error_code="FORBIDDEN_USER_PASSWORD",
            )
        if self.auth_method == AWSAuthMethod.ASSUME_ROLE:
            if not self.role_arn:
                raise AWSAuthenticationException(
                    "Cross-account role assumption requires a valid target role_arn.",
                    error_code="MISSING_ROLE_ARN",
                )
            if not self.external_id:
                raise AWSAuthenticationException(
                    "Mandatory ExternalId is required for cross-account role assumption to prevent Confused Deputy attacks.",
                    error_code="MISSING_EXTERNAL_ID",
                )
        elif self.auth_method == AWSAuthMethod.ACCESS_KEYS:
            if not self.access_key_id or not self.secret_access_key:
                raise AWSAuthenticationException(
                    "Access key authentication requires both access_key_id and secret_access_key.",
                    error_code="MISSING_ACCESS_KEYS",
                )


class AWSCURConfiguration(BaseModel):
    """BCM Data Exports CUR 2.0 table configuration with FinOps sizing awareness."""

    export_name: str = Field(default="CloudLens-CUR-2-0", description="Data export table name")
    s3_bucket: str = Field(
        default="cloudlens-cur-exports-prod", description="Target S3 delivery bucket"
    )
    s3_prefix: str = Field(default="cur2/reports", description="S3 object prefix")
    time_granularity: CURTimeGranularity = Field(
        default=CURTimeGranularity.HOURLY,
        description="Time granularity (HOURLY recommended for intraday FinOps)",
    )
    include_resource_ids: bool = Field(
        default=True,
        description="Enables resource-level granularity (drives 10x-100x row volume expansion)",
    )
    include_split_cost_allocation_data: bool = Field(
        default=True,
        description="Enables ECS/EKS container workload cost split allocation",
    )
    compression: CURCompression = Field(
        default=CURCompression.PARQUET_SNAPPY,
        description="Parquet with Snappy compression for query performance",
    )
    is_cur_2_0: bool = Field(
        default=True,
        description="CUR 2.0 with fixed column schema and nested map structures",
    )

    def estimate_sizing_envelope(self, resource_count: int) -> dict[str, float | int | str]:
        """Calculates pre-completion sizing estimates and worker ingestion capacity guidance.

        Enabling resource-level granularity multiplies rows by 10x–100x compared to summary level.
        """
        days_per_month = 30
        hours_per_day = 24
        # Multiplier factor when resource IDs are enabled
        granularity_multiplier = (
            hours_per_day if self.time_granularity == CURTimeGranularity.HOURLY else 1
        )
        resource_multiplier = 10 if self.include_resource_ids else 1
        split_multiplier = 1.3 if self.include_split_cost_allocation_data else 1.0

        estimated_monthly_rows = int(
            resource_count
            * days_per_month
            * granularity_multiplier
            * resource_multiplier
            * split_multiplier
        )

        # Average compressed row size in Parquet (approx 80 bytes/row) vs GZIP CSV (approx 250 bytes/row)
        bytes_per_row = 80 if self.compression == CURCompression.PARQUET_SNAPPY else 250
        estimated_storage_gb = round((estimated_monthly_rows * bytes_per_row) / (1024**3), 2)

        return {
            "estimated_monthly_rows": estimated_monthly_rows,
            "estimated_storage_gb": estimated_storage_gb,
            "granularity": self.time_granularity.value,
            "resource_ids_enabled": self.include_resource_ids,
            "recommended_ingestion_workers": max(1, int(estimated_storage_gb // 5) + 1),
            "sizing_guidance": (
                f"With resource_ids={self.include_resource_ids} and granularity={self.time_granularity.value}, "
                f"estimated volume is ~{estimated_monthly_rows:,} rows/mo (~{estimated_storage_gb} GB). "
                f"Provision {max(1, int(estimated_storage_gb // 5) + 1)} partitioned ingestion workers."
            ),
        }


class AWSCostCategoryRecord(BaseModel):
    """AWS Cost Category modeled as a distinct AWS-native concept, not merged into tags."""

    category_name: str = Field(
        ..., description="Cost category name (e.g. Environment, BusinessUnit)"
    )
    category_value: str = Field(..., description="Assigned value (e.g. Production, CoreBanking)")
    rule_version: str = Field(
        default="CostCategoryExpression.v1", description="Cost category rule version"
    )
    is_inherited: bool = Field(
        default=False, description="Whether rule was inherited from parent organization"
    )


class AWSCostRecord(BaseModel):
    """Normalized cost record from CUR 2.0 / FOCUS exports or Cost Explorer."""

    line_item_id: str = Field(..., description="Line item unique identifier")
    payer_account_id: str = Field(..., description="Payer/Management Account ID (12 digits)")
    usage_account_id: str = Field(..., description="Usage/Member Account ID (12 digits)")
    product_code: str = Field(..., description="AWS product code (e.g. AmazonEC2, AmazonS3)")
    usage_type: str = Field(..., description="Usage type identifier")
    operation: str = Field(..., description="AWS API operation (e.g. RunInstances)")
    resource_id: str = Field(default="", description="Resource ARN or identifier")
    availability_zone: str = Field(default="us-east-1a", description="AZ identifier")
    start_time: str = Field(..., description="Usage start ISO timestamp")
    end_time: str = Field(..., description="Usage end ISO timestamp")
    usage_quantity: float = Field(default=0.0, description="Consumed units")
    unblended_rate: float = Field(default=0.0, description="Unit rate")
    unblended_cost: float = Field(..., description="Billed amount")
    currency: str = Field(default="USD", description="Billing currency")
    pricing_unit: str = Field(default="Hrs", description="Unit of measure")
    tags: dict[str, str] = Field(default_factory=dict, description="Resource user tags")
    # Cost Categories are modeled as distinct AWS-native entities, NOT merged into tags
    cost_categories: dict[str, str] = Field(
        default_factory=dict,
        description="AWS-native Cost Categories evaluated at billing time",
    )
    is_estimated: bool = Field(
        default=False,
        description="Whether cost was query-estimated (Cost Explorer) vs finalized export",
    )


class AWSResourceRecord(BaseModel):
    """Discovered AWS resource record acknowledging non-uniform service coverage."""

    arn: str = Field(..., description="Full Amazon Resource Name")
    resource_id: str = Field(..., description="Resource native identifier")
    account_id: str = Field(..., description="Owning member account ID")
    region: str = Field(..., description="AWS deployment region")
    service: str = Field(..., description="AWS service code (e.g. ec2, s3, rds)")
    native_type: str = Field(..., description="Native AWS resource type (e.g. AWS::EC2::Instance)")
    service_category: str = Field(..., description="Standardized service category")
    runtime_status: str = Field(default="RUNNING", description="Runtime status")
    tags: dict[str, str] = Field(default_factory=dict, description="Resource tags")
    # Non-uniform coverage indicator
    is_unclassified: bool = Field(
        default=False,
        description="Marked as Unclassified when service coverage is partial or unsupported in Tagging API",
    )
    classification_reason: str | None = Field(
        default=None,
        description="Reason why resource was marked as Unclassified",
    )
    properties: dict[str, str | int | float | bool | list[str] | dict[str, str] | None] = Field(
        default_factory=dict,
        description="Structural properties",
    )


class AWSBudgetRecord(BaseModel):
    """AWS native budget read for comparison only (never authoritative)."""

    budget_name: str = Field(..., description="AWS budget name")
    account_id: str = Field(..., description="Target AWS account ID")
    budget_limit: float = Field(..., ge=0.0, description="Budget threshold limit amount")
    time_unit: str = Field(
        default="MONTHLY", description="Budget cycle (MONTHLY, QUARTERLY, ANNUALLY)"
    )
    current_spend: float = Field(
        default=0.0, ge=0.0, description="Actual spend tracked by AWS Budgets"
    )
    forecasted_spend: float | None = Field(default=None, description="Forecasted spend")
    is_authoritative: bool = Field(
        default=False,
        description="AWS native budgets are read for comparison only; CloudLens master budgets remain authoritative.",
    )


class AWSRelationshipRecord(BaseModel):
    """Structural resource relationship derived from AWS configuration properties."""

    source_arn: str = Field(..., description="Source resource ARN (e.g. EC2 instance)")
    target_arn: str = Field(..., description="Target resource ARN (e.g. ENI or EBS volume)")
    relationship_type: str = Field(
        ..., description="Relationship type (NETWORK_INTERFACE, STORAGE_VOLUME, VPC_SUBNET)"
    )
    is_structural_only: bool = Field(
        default=True,
        description="Structural property bindings only; dynamic network packet routing is not evaluated.",
    )


# Regex for AWS 12-digit account ID
_RE_AWS_ACCOUNT = re.compile(r"^\d{12}$")
_RE_AWS_OU = re.compile(r"^ou-[a-z0-9]{4,10}-[a-z0-9]{8,32}$")
_RE_AWS_ROOT = re.compile(r"^r-[a-z0-9]{4,10}$")


def is_valid_aws_account_id(account_id: str) -> bool:
    """Validates 12-digit AWS account ID format."""
    return bool(_RE_AWS_ACCOUNT.match(account_id.strip()))


# Mapping from AWS native resource types to standardized service categories
# Unsupported or uncommon services default to Unclassified
KNOWN_AWS_TYPE_MAPPINGS = {
    "AWS::EC2::Instance": "COMPUTE",
    "AWS::Lambda::Function": "COMPUTE",
    "AWS::ECS::Cluster": "COMPUTE",
    "AWS::EKS::Cluster": "COMPUTE",
    "AWS::S3::Bucket": "STORAGE",
    "AWS::EBS::Volume": "STORAGE",
    "AWS::EFS::FileSystem": "STORAGE",
    "AWS::RDS::DBInstance": "DATABASE",
    "AWS::DynamoDB::Table": "DATABASE",
    "AWS::EC2::VPC": "NETWORKING",
    "AWS::EC2::Subnet": "NETWORKING",
    "AWS::EC2::NetworkInterface": "NETWORKING",
    "AWS::KMS::Key": "SECURITY_IDENTITY",
    "AWS::IAM::Role": "SECURITY_IDENTITY",
}
