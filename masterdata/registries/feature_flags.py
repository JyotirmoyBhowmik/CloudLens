"""CloudLens Feature Flag Registry - Canonical Master Data.

STRICT RULE: All feature flags must be registered here prior to evaluation or toggling.
Unregistered flags are strictly forbidden to prevent orphaned flags or hidden behavioral branches.
"""

from pydantic import BaseModel, Field


class FeatureFlagDefinition(BaseModel):
    """Metadata describing a registered feature flag."""

    key: str = Field(description="Unique snake_case flag identifier")
    name: str = Field(description="Human-readable flag name")
    description: str = Field(
        description="Detailed explanation of the behavior controlled by this flag"
    )
    default_enabled: bool = Field(
        default=False, description="Default toggle state if no override exists"
    )
    stage: str = Field(default="beta", description="Maturity stage: alpha, beta, ga, deprecated")
    category: str = Field(
        default="general", description="Logical area: connector, finops, governance, general"
    )


# Canonical registered flags
CANONICAL_FEATURE_FLAGS: list[FeatureFlagDefinition] = [
    FeatureFlagDefinition(
        key="enable_oci_connector",
        name="Oracle Cloud Infrastructure Connector",
        description="Enables discovery, inventory, and cost ingestion from OCI tenancies",
        default_enabled=False,
        stage="beta",
        category="connector",
    ),
    FeatureFlagDefinition(
        key="enable_azure_connector",
        name="Microsoft Azure Connector",
        description="Enables discovery, inventory, and cost ingestion from Azure Subscriptions",
        default_enabled=True,
        stage="ga",
        category="connector",
    ),
    FeatureFlagDefinition(
        key="enable_aws_connector",
        name="Amazon Web Services Connector",
        description="Enables discovery, inventory, and cost ingestion from AWS Accounts",
        default_enabled=True,
        stage="ga",
        category="connector",
    ),
    FeatureFlagDefinition(
        key="enable_gcp_connector",
        name="Google Cloud Platform Connector",
        description="Enables discovery, inventory, and cost ingestion from GCP Projects",
        default_enabled=True,
        stage="ga",
        category="connector",
    ),
    FeatureFlagDefinition(
        key="enable_multi_currency_forecasting",
        name="Multi-Currency ML Forecasting",
        description="Enables cross-currency currency exchange projection in ARIMA and linear spend forecasts",
        default_enabled=False,
        stage="alpha",
        category="finops",
    ),
    FeatureFlagDefinition(
        key="strict_budget_enforcement",
        name="Strict Budget Enforcement",
        description="Automatically triggers workflow webhooks and block signals when spend reaches 100% of budget",
        default_enabled=False,
        stage="beta",
        category="governance",
    ),
    FeatureFlagDefinition(
        key="enable_anomaly_detection",
        name="Cost Anomaly Machine Learning Detection",
        description="Runs daily statistical z-score outlier detection over resource-level spend time series",
        default_enabled=True,
        stage="ga",
        category="finops",
    ),
    FeatureFlagDefinition(
        key="enable_raw_metrics_export",
        name="Raw Telemetry Export",
        description="Permits asynchronous raw 1-minute runtime telemetry export to customer S3 buckets",
        default_enabled=False,
        stage="beta",
        category="finops",
    ),
    FeatureFlagDefinition(
        key="enable_amortised_cost_basis",
        name="Amortised Cost Spreading",
        description="Enables spreading upfront reservation and savings plan commitments across billing cycles",
        default_enabled=True,
        stage="ga",
        category="finops",
    ),
]

FEATURE_FLAG_REGISTRY: dict[str, FeatureFlagDefinition] = {
    flag.key: flag for flag in CANONICAL_FEATURE_FLAGS
}
