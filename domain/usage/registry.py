"""Canonical Monitoring Type Catalogue and Cardinality Registry (Prompt 25 / BBP Section 19).

Enforces:
- Prompt 25: Fourteen canonical monitoring types (MT-01 to MT-14) + Quota Headroom (MT-15).
- Prompt 25: Cardinality discipline - collect only metrics required by monitoring type.
  "A storage resource collects storage metrics and not compute metrics."
  "Do not collect metrics a monitoring type does not require."
- Defaulting monitoring type from resource type catalogue.
"""

from __future__ import annotations

import logging
from typing import Final

from domain.models.exceptions import MonitoringTypeNotFoundException
from domain.usage.models import MonitoringType, MonitoringTypeDefinition

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Fourteen Canonical Monitoring Types (+ Quota Headroom) Definitions
# ==============================================================================

MONITORING_TYPE_DEFINITIONS: Final[dict[MonitoringType, MonitoringTypeDefinition]] = {
    MonitoringType.RUNTIME_BASED: MonitoringTypeDefinition(
        code="MT-01",
        type_name=MonitoringType.RUNTIME_BASED,
        display_name="Runtime-Based",
        description=(
            "Tracks time-driven resource execution states and utilization percentages "
            "for persistent compute nodes, host clusters, and active execution runtimes."
        ),
        allowable_metrics=[
            "cpu_utilization_avg",
            "memory_utilization_avg",
            "runtime_hours",
            "system_uptime_seconds",
            "instance_status_checks_passed",
        ],
        sample_resource_types=[
            "AWS::EC2::Instance",
            "Microsoft.Compute/virtualMachines",
            "compute.v1.instance",
            "oci.core.instance",
            "compute/virtual-machine",
        ],
    ),
    MonitoringType.VOLUME_BASED: MonitoringTypeDefinition(
        code="MT-02",
        type_name=MonitoringType.VOLUME_BASED,
        display_name="Volume-Based",
        description=(
            "Measures raw physical data volume and provisioned disk storage "
            "independent of object semantics, including disk IOPS and throughput."
        ),
        allowable_metrics=[
            "volume_provisioned_bytes",
            "volume_used_bytes",
            "volume_read_bytes",
            "volume_write_bytes",
            "volume_read_ops",
            "volume_write_ops",
            "volume_iops",
        ],
        sample_resource_types=[
            "AWS::EC2::Volume",
            "Microsoft.Compute/disks",
            "compute.v1.disk",
            "oci.core.volume",
            "storage/block-storage",
        ],
    ),
    MonitoringType.TRANSACTION_BASED: MonitoringTypeDefinition(
        code="MT-03",
        type_name=MonitoringType.TRANSACTION_BASED,
        display_name="Transaction-Based",
        description=(
            "Measures transaction and database operations, read/write throughput units, "
            "and atomic operation counters across relational and NoSQL engines."
        ),
        allowable_metrics=[
            "transaction_count",
            "query_execution_count",
            "read_capacity_units",
            "write_capacity_units",
            "database_connections_active",
            "transaction_latency_ms",
        ],
        sample_resource_types=[
            "AWS::RDS::DBInstance",
            "AWS::DynamoDB::Table",
            "Microsoft.Sql/servers/databases",
            "sqladmin.v1.instance",
            "oci.database.dbnode",
            "database/relational",
        ],
    ),
    MonitoringType.REQUEST_BASED: MonitoringTypeDefinition(
        code="MT-04",
        type_name=MonitoringType.REQUEST_BASED,
        display_name="Request-Based",
        description=(
            "Captures discrete function executions, serverless compute invocations, "
            "and event-triggered workloads billed on duration and invocation count."
        ),
        allowable_metrics=[
            "invocation_count",
            "execution_duration_ms",
            "request_count",
            "throttled_invocations",
            "error_invocations",
            "concurrency_allocated",
        ],
        sample_resource_types=[
            "AWS::Lambda::Function",
            "Microsoft.Web/sites/functions",
            "cloudfunctions.v1.function",
            "oci.functions.function",
            "serverless/function",
        ],
    ),
    MonitoringType.STORAGE_BASED: MonitoringTypeDefinition(
        code="MT-05",
        type_name=MonitoringType.STORAGE_BASED,
        display_name="Storage-Based",
        description=(
            "Tracks object and blob storage consumption, bucket byte counts, "
            "and storage tier transitions across cloud object stores."
        ),
        allowable_metrics=[
            "storage_allocated_bytes",
            "storage_used_bytes",
            "object_count",
            "storage_tier_standard_bytes",
            "storage_tier_archive_bytes",
            "storage_iops",
        ],
        sample_resource_types=[
            "AWS::S3::Bucket",
            "Microsoft.Storage/storageAccounts",
            "storage.v1.bucket",
            "oci.objectstorage.bucket",
            "storage/object-storage",
        ],
    ),
    MonitoringType.DATA_TRANSFER_BASED: MonitoringTypeDefinition(
        code="MT-06",
        type_name=MonitoringType.DATA_TRANSFER_BASED,
        display_name="Data-Transfer-Based",
        description=(
            "Measures bandwidth, edge caching egress, cross-region transfers, "
            "and internet transit volume across networking infrastructure."
        ),
        allowable_metrics=[
            "network_ingress_bytes",
            "network_egress_bytes",
            "cross_region_egress_bytes",
            "internet_egress_bytes",
            "cdn_cache_hit_ratio",
            "bandwidth_utilization_bps",
        ],
        sample_resource_types=[
            "AWS::CloudFront::Distribution",
            "AWS::EC2::NatGateway",
            "Microsoft.Network/trafficManagerProfiles",
            "network/cdn",
            "network/gateway",
        ],
    ),
    MonitoringType.USER_BASED: MonitoringTypeDefinition(
        code="MT-07",
        type_name=MonitoringType.USER_BASED,
        display_name="User-Based",
        description=(
            "Tracks active named users, virtual desktop instances, and seat-allocated "
            "workplace productivity subscriptions."
        ),
        allowable_metrics=[
            "active_users_count",
            "allocated_seats",
            "concurrent_sessions",
            "inactive_users_30d",
        ],
        sample_resource_types=[
            "AWS::WorkSpaces::Workspace",
            "Microsoft.DesktopVirtualization/hostPools",
            "workspace/virtual-desktop",
        ],
    ),
    MonitoringType.LICENCE_BASED: MonitoringTypeDefinition(
        code="MT-08",
        type_name=MonitoringType.LICENCE_BASED,
        display_name="Licence-Based",
        description=(
            "Tracks core and socket counts, enterprise license key allocations, "
            "and bring-your-own-license (BYOL) compliance metrics."
        ),
        allowable_metrics=[
            "allocated_cores",
            "active_licenses",
            "license_units_consumed",
            "byol_utilization_ratio",
        ],
        sample_resource_types=[
            "AWS::LicenseManager::LicenseConfiguration",
            "software/database-license",
            "software/os-license",
        ],
    ),
    MonitoringType.API_CALL_BASED: MonitoringTypeDefinition(
        code="MT-09",
        type_name=MonitoringType.API_CALL_BASED,
        display_name="API-Call-Based",
        description=(
            "Monitors API gateway call volumes, downstream route invocations, "
            "client latency percentiles, and HTTP error response ratios."
        ),
        allowable_metrics=[
            "api_call_count",
            "api_latency_ms",
            "client_error_count",
            "server_error_count",
            "api_cache_hit_count",
        ],
        sample_resource_types=[
            "AWS::ApiGateway::RestApi",
            "Microsoft.ApiManagement/service",
            "apigateway.v1.gateway",
            "api/gateway",
        ],
    ),
    MonitoringType.SCHEDULE_BASED: MonitoringTypeDefinition(
        code="MT-10",
        type_name=MonitoringType.SCHEDULE_BASED,
        display_name="Schedule-Based",
        description=(
            "Tracks operational adherence against business schedules (e.g. 9-to-5 weekdays), "
            "quantifying authorized hours versus out-of-schedule excess."
        ),
        allowable_metrics=[
            "scheduled_hours_active",
            "unauthorized_runtime_hours",
            "schedule_adherence_percent",
            "scheduled_shutdown_success",
        ],
        sample_resource_types=[
            "compute/scheduled-vm",
            "environment/non-prod-instance",
        ],
    ),
    MonitoringType.SEASONAL: MonitoringTypeDefinition(
        code="MT-11",
        type_name=MonitoringType.SEASONAL,
        display_name="Seasonal",
        description=(
            "Tracks usage with cyclical, monthly, or quarterly demand spikes, "
            "evaluating observed quantities against historical seasonal baselines."
        ),
        allowable_metrics=[
            "seasonal_volume_units",
            "peak_demand_units",
            "baseline_variance_percent",
            "cyclical_index",
        ],
        sample_resource_types=[
            "workload/retail-holiday-batch",
            "workload/quarterly-financial-close",
        ],
    ),
    MonitoringType.RESERVED_COMMITTED_USAGE: MonitoringTypeDefinition(
        code="MT-12",
        type_name=MonitoringType.RESERVED_COMMITTED_USAGE,
        display_name="Reserved / Committed Usage",
        description=(
            "Measures consumption coverage and commitment utilization for "
            "Reserved Instances, Savings Plans, and committed use discounts."
        ),
        allowable_metrics=[
            "committed_units_total",
            "committed_units_utilized",
            "coverage_percentage",
            "unutilized_units",
            "savings_realized_usd",
        ],
        sample_resource_types=[
            "commitment/reserved-instance",
            "commitment/savings-plan",
        ],
    ),
    MonitoringType.PROVIDER_SPECIFIC_DIMENSION: MonitoringTypeDefinition(
        code="MT-13",
        type_name=MonitoringType.PROVIDER_SPECIFIC_DIMENSION,
        display_name="Provider-Specific Dimension",
        description=(
            "Accommodates provider-proprietary billing constructs, credits, "
            "and custom cloud telemetry dimensions."
        ),
        allowable_metrics=[
            "provider_metric_units",
            "custom_dimension_value",
            "proprietary_credit_burn",
        ],
        sample_resource_types=[
            "oci/universal-credit-pool",
            "custom/provider-extension",
        ],
    ),
    MonitoringType.NOT_APPLICABLE: MonitoringTypeDefinition(
        code="MT-14",
        type_name=MonitoringType.NOT_APPLICABLE,
        display_name="Not Applicable",
        description=(
            "Designates structural or metadata resources that generate no billable usage. "
            "Zero metrics are collected to guarantee cardinality control."
        ),
        allowable_metrics=[],  # Strictly zero metrics!
        sample_resource_types=[
            "AWS::CloudFormation::Stack",
            "AWS::IAM::Role",
            "Microsoft.Resources/resourceGroups",
            "governance/resource-group",
            "network/virtual-network",
        ],
    ),
    MonitoringType.QUOTA_HEADROOM: MonitoringTypeDefinition(
        code="MT-15",
        type_name=MonitoringType.QUOTA_HEADROOM,
        display_name="Quota Headroom",
        description=(
            "Tracks service limits, provider quotas, and predicted exhaustion "
            "lead time across cloud provider subscriptions (Prompt 54 / USE-001)."
        ),
        allowable_metrics=[
            "quota_limit",
            "quota_current_usage",
            "quota_headroom_percent",
            "predicted_exhaustion_days",
        ],
        sample_resource_types=[
            "quota/service-limit",
            "provider/quota-boundary",
        ],
    ),
}


# ==============================================================================
# 2. Resource Type to Default Monitoring Type Mapping
# ==============================================================================

RESOURCE_TYPE_MONITORING_DEFAULTS: Final[dict[str, MonitoringType]] = {
    # Compute
    "compute/virtual-machine": MonitoringType.RUNTIME_BASED,
    "aws::ec2::instance": MonitoringType.RUNTIME_BASED,
    "microsoft.compute/virtualmachines": MonitoringType.RUNTIME_BASED,
    "compute.v1.instance": MonitoringType.RUNTIME_BASED,
    "oci.core.instance": MonitoringType.RUNTIME_BASED,
    "serverless/container": MonitoringType.RUNTIME_BASED,
    "aws::ecs::taskdefinition": MonitoringType.RUNTIME_BASED,
    "microsoft.containerinstance/containergroups": MonitoringType.RUNTIME_BASED,
    # Storage
    "storage/object-storage": MonitoringType.STORAGE_BASED,
    "aws::s3::bucket": MonitoringType.STORAGE_BASED,
    "microsoft.storage/storageaccounts": MonitoringType.STORAGE_BASED,
    "storage.v1.bucket": MonitoringType.STORAGE_BASED,
    "oci.objectstorage.bucket": MonitoringType.STORAGE_BASED,
    # Volume / Block Storage
    "storage/block-storage": MonitoringType.VOLUME_BASED,
    "aws::ec2::volume": MonitoringType.VOLUME_BASED,
    "microsoft.compute/disks": MonitoringType.VOLUME_BASED,
    "compute.v1.disk": MonitoringType.VOLUME_BASED,
    "oci.core.volume": MonitoringType.VOLUME_BASED,
    # Database
    "database/relational": MonitoringType.TRANSACTION_BASED,
    "database/nosql": MonitoringType.TRANSACTION_BASED,
    "aws::rds::dbinstance": MonitoringType.TRANSACTION_BASED,
    "aws::dynamodb::table": MonitoringType.TRANSACTION_BASED,
    "microsoft.sql/servers/databases": MonitoringType.TRANSACTION_BASED,
    "microsoft.documentdb/databaseaccounts": MonitoringType.TRANSACTION_BASED,
    "sqladmin.v1.instance": MonitoringType.TRANSACTION_BASED,
    "oci.database.dbnode": MonitoringType.TRANSACTION_BASED,
    # Serverless / Functions
    "serverless/function": MonitoringType.REQUEST_BASED,
    "aws::lambda::function": MonitoringType.REQUEST_BASED,
    "microsoft.web/sites/functions": MonitoringType.REQUEST_BASED,
    "cloudfunctions.v1.function": MonitoringType.REQUEST_BASED,
    "oci.functions.function": MonitoringType.REQUEST_BASED,
    # Network / Data Transfer
    "network/cdn": MonitoringType.DATA_TRANSFER_BASED,
    "network/gateway": MonitoringType.DATA_TRANSFER_BASED,
    "aws::cloudfront::distribution": MonitoringType.DATA_TRANSFER_BASED,
    "aws::ec2::natgateway": MonitoringType.DATA_TRANSFER_BASED,
    "microsoft.network/trafficmanagerprofiles": MonitoringType.DATA_TRANSFER_BASED,
    # API Gateway
    "api/gateway": MonitoringType.API_CALL_BASED,
    "aws::apigateway::restapi": MonitoringType.API_CALL_BASED,
    "microsoft.apimanagement/service": MonitoringType.API_CALL_BASED,
    "apigateway.v1.gateway": MonitoringType.API_CALL_BASED,
    # User / Workspaces
    "workspace/virtual-desktop": MonitoringType.USER_BASED,
    "aws::workspaces::workspace": MonitoringType.USER_BASED,
    "microsoft.desktopvirtualization/hostpools": MonitoringType.USER_BASED,
    # Governance / Zero-Usage Structural
    "governance/resource-group": MonitoringType.NOT_APPLICABLE,
    "microsoft.resources/resourcegroups": MonitoringType.NOT_APPLICABLE,
    "aws::cloudformation::stack": MonitoringType.NOT_APPLICABLE,
    "aws::iam::role": MonitoringType.NOT_APPLICABLE,
    "network/virtual-network": MonitoringType.NOT_APPLICABLE,
    "microsoft.network/virtualnetworks": MonitoringType.NOT_APPLICABLE,
}


# ==============================================================================
# 3. Cardinality Discipline & Query Functions
# ==============================================================================


def get_monitoring_type_definition(mtype: MonitoringType | str) -> MonitoringTypeDefinition:
    """Retrieves definition and allowable metric set for a monitoring type."""
    try:
        resolved = MonitoringType(mtype)
    except ValueError as err:
        raise MonitoringTypeNotFoundException(str(mtype)) from err

    definition = MONITORING_TYPE_DEFINITIONS.get(resolved)
    if not definition:
        raise MonitoringTypeNotFoundException(str(mtype))
    return definition


def list_monitoring_types() -> list[MonitoringTypeDefinition]:
    """Returns the ordered list of all fifteen canonical monitoring types."""
    return list(MONITORING_TYPE_DEFINITIONS.values())


def get_allowable_metrics(mtype: MonitoringType | str) -> set[str]:
    """Returns the strict set of allowable metrics for a monitoring type."""
    return set(get_monitoring_type_definition(mtype).allowable_metrics)


def is_metric_allowed(mtype: MonitoringType | str, metric_name: str) -> bool:
    """Evaluates whether a metric is permissible under a resource's monitoring type."""
    allowable = get_allowable_metrics(mtype)
    return metric_name in allowable


def filter_allowed_metrics(
    mtype: MonitoringType | str, proposed_metrics: list[str]
) -> tuple[list[str], list[str]]:
    """Partitions proposed metrics into (allowed, disallowed) sets based on monitoring type.

    Guarantees cardinality discipline: 'Collect only the metrics that the resource's
    monitoring type requires — nothing more.'
    """
    allowable = get_allowable_metrics(mtype)
    allowed: list[str] = []
    disallowed: list[str] = []

    for metric in proposed_metrics:
        if metric in allowable:
            allowed.append(metric)
        else:
            disallowed.append(metric)

    return allowed, disallowed


def get_default_monitoring_type_for_resource(
    native_type_name: str, canonical_type: str | None = None
) -> MonitoringType:
    """Resolves the default monitoring type for a resource type.

    Checks canonical_type first, then normalized native_type_name, defaulting conservatively.
    """
    if canonical_type:
        normalized_canonical = canonical_type.strip().lower()
        if normalized_canonical in RESOURCE_TYPE_MONITORING_DEFAULTS:
            return RESOURCE_TYPE_MONITORING_DEFAULTS[normalized_canonical]

    normalized_native = native_type_name.strip().lower()
    if normalized_native in RESOURCE_TYPE_MONITORING_DEFAULTS:
        return RESOURCE_TYPE_MONITORING_DEFAULTS[normalized_native]

    # Heuristic category fallback
    if any(k in normalized_native for k in ["instance", "vm", "virtualmachine", "server"]):
        return MonitoringType.RUNTIME_BASED
    if any(k in normalized_native for k in ["bucket", "blob", "object"]):
        return MonitoringType.STORAGE_BASED
    if any(k in normalized_native for k in ["disk", "volume"]):
        return MonitoringType.VOLUME_BASED
    if any(k in normalized_native for k in ["database", "sql", "table"]):
        return MonitoringType.TRANSACTION_BASED
    if any(k in normalized_native for k in ["group", "role", "policy", "vnet", "vpc"]):
        return MonitoringType.NOT_APPLICABLE

    return MonitoringType.PROVIDER_SPECIFIC_DIMENSION
