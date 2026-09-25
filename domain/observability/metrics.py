"""CloudLens Canonical Prometheus Metric Registry.

Registers all 12 platform metrics required by Prompt 03 Item 21.
Exposes Prometheus-compatible scrapable endpoints.
"""

from dataclasses import dataclass

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


@dataclass(frozen=True)
class MetricDefinition:
    """Documentation and alert condition metadata for a platform metric."""

    name: str
    metric_type: str
    description: str
    labels: tuple[str, ...]
    alert_condition: str
    slo_target: str


# Canonical metadata catalogue for all 12 metrics
METRIC_DEFINITIONS: dict[str, MetricDefinition] = {
    "api_request_duration_seconds": MetricDefinition(
        name="api_request_duration_seconds",
        metric_type="Histogram",
        description="HTTP request execution duration in seconds",
        labels=("method", "endpoint", "status_code"),
        alert_condition="histogram_quantile(0.95, sum(rate(api_request_duration_seconds_bucket[5m])) by (le)) > 1.0",
        slo_target="p95 < 500ms; p99 < 1500ms",
    ),
    "api_error_rate": MetricDefinition(
        name="api_error_rate",
        metric_type="Gauge",
        description="Ratio of HTTP 5xx responses over total requests",
        labels=("service",),
        alert_condition="api_error_rate > 0.01 (1% error rate over 5m)",
        slo_target="Error rate < 0.05%",
    ),
    "sync_job_duration_seconds": MetricDefinition(
        name="sync_job_duration_seconds",
        metric_type="Histogram",
        description="Elapsed execution time of cloud provider connector sync jobs",
        labels=("provider", "connector_id", "status"),
        alert_condition="histogram_quantile(0.90, sum(rate(sync_job_duration_seconds_bucket[15m])) by (le)) > 900",
        slo_target="p90 < 10 minutes",
    ),
    "sync_job_outcome_total": MetricDefinition(
        name="sync_job_outcome_total",
        metric_type="Counter",
        description="Cumulative count of completed connector sync jobs by outcome",
        labels=("provider", "connector_id", "outcome"),
        alert_condition="rate(sync_job_outcome_total{outcome='failed'}[15m]) > 0.05",
        slo_target="Sync success rate > 99.5%",
    ),
    "connector_freshness_seconds": MetricDefinition(
        name="connector_freshness_seconds",
        metric_type="Gauge",
        description="Elapsed seconds since last successful connector sync completion",
        labels=("provider", "connector_id"),
        alert_condition="connector_freshness_seconds > 86400 (24h staleness)",
        slo_target="Freshness < 4 hours",
    ),
    "ingestion_rows_total": MetricDefinition(
        name="ingestion_rows_total",
        metric_type="Counter",
        description="Cumulative count of canonical FOCUS-standard billing/inventory rows ingested",
        labels=("provider", "dataset_type"),
        alert_condition="rate(ingestion_rows_total[1h]) == 0 for scheduled active tenant",
        slo_target="Continuous ingestion during sync windows",
    ),
    "reconciliation_variance_ratio": MetricDefinition(
        name="reconciliation_variance_ratio",
        metric_type="Gauge",
        description="Discrepancy ratio between provider billed invoice total and calculated resource total",
        labels=("tenant_id", "provider"),
        alert_condition="reconciliation_variance_ratio > 0.01 (Variance > 1%)",
        slo_target="Variance < 0.1%",
    ),
    "queue_depth": MetricDefinition(
        name="queue_depth",
        metric_type="Gauge",
        description="Number of queued background jobs awaiting execution",
        labels=("queue_name",),
        alert_condition="queue_depth > 1000 for > 10m",
        slo_target="Queue depth < 100",
    ),
    "worker_saturation": MetricDefinition(
        name="worker_saturation",
        metric_type="Gauge",
        description="Worker concurrency utilization ratio (active tasks / worker pool size)",
        labels=("worker_node", "queue_name"),
        alert_condition="worker_saturation > 0.85 for > 15m",
        slo_target="Saturation < 70%",
    ),
    "db_replication_lag_seconds": MetricDefinition(
        name="db_replication_lag_seconds",
        metric_type="Gauge",
        description="Replication delay between primary database and read replicas in seconds",
        labels=("replica_host",),
        alert_condition="db_replication_lag_seconds > 60",
        slo_target="Lag < 5 seconds",
    ),
    "threshold_evaluation_duration_seconds": MetricDefinition(
        name="threshold_evaluation_duration_seconds",
        metric_type="Histogram",
        description="Duration of FinOps budget and cost spike threshold rule evaluation runs",
        labels=("tenant_id",),
        alert_condition="histogram_quantile(0.95, sum(rate(threshold_evaluation_duration_seconds_bucket[10m])) by (le)) > 30",
        slo_target="p95 < 10 seconds",
    ),
    "notification_delivery_failures_total": MetricDefinition(
        name="notification_delivery_failures_total",
        metric_type="Counter",
        description="Cumulative count of failed alert notifications across webhook, email, and Slack",
        labels=("channel_type", "reason"),
        alert_condition="rate(notification_delivery_failures_total[5m]) > 0.1",
        slo_target="Delivery reliability > 99.9%",
    ),
}


class CloudLensMetrics:
    """Manages all Prometheus metrics instances registered with Prometheus client."""

    def __init__(self, registry: CollectorRegistry = REGISTRY) -> None:
        self.registry = registry

        # 1. api_request_duration_seconds
        self.api_request_duration_seconds = Histogram(
            "api_request_duration_seconds",
            "HTTP request execution duration in seconds",
            ["method", "endpoint", "status_code"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=registry,
        )

        # 2. api_error_rate
        self.api_error_rate = Gauge(
            "api_error_rate",
            "Ratio of HTTP 5xx responses over total requests",
            ["service"],
            registry=registry,
        )

        # 3. sync_job_duration_seconds
        self.sync_job_duration_seconds = Histogram(
            "sync_job_duration_seconds",
            "Elapsed execution time of cloud provider connector sync jobs",
            ["provider", "connector_id", "status"],
            buckets=(1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1200.0, 3600.0),
            registry=registry,
        )

        # 4. sync_job_outcome_total
        self.sync_job_outcome_total = Counter(
            "sync_job_outcome_total",
            "Cumulative count of completed connector sync jobs by outcome",
            ["provider", "connector_id", "outcome"],
            registry=registry,
        )

        # 5. connector_freshness_seconds
        self.connector_freshness_seconds = Gauge(
            "connector_freshness_seconds",
            "Elapsed seconds since last successful connector sync completion",
            ["provider", "connector_id"],
            registry=registry,
        )

        # 6. ingestion_rows_total
        self.ingestion_rows_total = Counter(
            "ingestion_rows_total",
            "Cumulative count of canonical FOCUS-standard billing/inventory rows ingested",
            ["provider", "dataset_type"],
            registry=registry,
        )

        # 7. reconciliation_variance_ratio
        self.reconciliation_variance_ratio = Gauge(
            "reconciliation_variance_ratio",
            "Discrepancy ratio between provider billed invoice total and calculated resource total",
            ["tenant_id", "provider"],
            registry=registry,
        )

        # 8. queue_depth
        self.queue_depth = Gauge(
            "queue_depth",
            "Number of queued background jobs awaiting execution",
            ["queue_name"],
            registry=registry,
        )

        # 9. worker_saturation
        self.worker_saturation = Gauge(
            "worker_saturation",
            "Worker concurrency utilization ratio (active tasks / worker pool size)",
            ["worker_node", "queue_name"],
            registry=registry,
        )

        # 10. db_replication_lag_seconds
        self.db_replication_lag_seconds = Gauge(
            "db_replication_lag_seconds",
            "Replication delay between primary database and read replicas in seconds",
            ["replica_host"],
            registry=registry,
        )

        # 11. threshold_evaluation_duration_seconds
        self.threshold_evaluation_duration_seconds = Histogram(
            "threshold_evaluation_duration_seconds",
            "Duration of FinOps budget and cost spike threshold rule evaluation runs",
            ["tenant_id"],
            buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
            registry=registry,
        )

        # 12. notification_delivery_failures_total
        self.notification_delivery_failures_total = Counter(
            "notification_delivery_failures_total",
            "Cumulative count of failed alert notifications across webhook, email, and Slack",
            ["channel_type", "reason"],
            registry=registry,
        )

    def scrape(self) -> bytes:
        """Generate Prometheus exposition text format bytes."""
        return generate_latest(self.registry)


# Global singleton metrics instance using default registry
metrics = CloudLensMetrics()
