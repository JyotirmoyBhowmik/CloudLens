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


# Canonical metadata catalogue for platform metrics
METRIC_DEFINITIONS: dict[str, MetricDefinition] = {
    "api_request_duration_seconds": MetricDefinition(
        name="api_request_duration_seconds",
        metric_type="Histogram",
        description="HTTP request execution duration in seconds",
        labels=("method", "endpoint", "status_code"),
        alert_condition="histogram_quantile(0.95, sum(rate(api_request_duration_seconds_bucket[5m])) by (le)) > 1.0",
        slo_target="p95 < 500ms; p99 < 1500ms",
    ),
    "api_requests_total": MetricDefinition(
        name="api_requests_total",
        metric_type="Counter",
        description="Cumulative count of HTTP requests processed by status",
        labels=("status",),
        alert_condition="rate(api_requests_total{status=~'5..'}[5m]) > 0.01",
        slo_target="HTTP 5xx rate < 0.05%",
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
        labels=("provider", "capability"),
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
        labels=("queue",),
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
    "secret_store_up": MetricDefinition(
        name="secret_store_up",
        metric_type="Gauge",
        description="Health status of external Vault / SecretStore (1 = healthy, 0 = unreachable)",
        labels=(),
        alert_condition="secret_store_up == 0 for 60s",
        slo_target="Availability > 99.99%",
    ),
    "task_failures_total": MetricDefinition(
        name="task_failures_total",
        metric_type="Counter",
        description="Cumulative count of background task execution failures",
        labels=(),
        alert_condition="increase(task_failures_total[15m]) >= 3",
        slo_target="Zero task failure streaks",
    ),
    "alerts_undelivered_total": MetricDefinition(
        name="alerts_undelivered_total",
        metric_type="Counter",
        description="Cumulative count of alerts that could not be delivered to notification channels",
        labels=(),
        alert_condition="increase(alerts_undelivered_total[10m]) > 0",
        slo_target="Delivery reliability > 99.99%",
    ),
    "security_events_total": MetricDefinition(
        name="security_events_total",
        metric_type="Counter",
        description="Cumulative count of critical platform security events by type",
        labels=("type",),
        alert_condition="increase(security_events_total[5m]) > 0",
        slo_target="Zero security events",
    ),
    "superuser_signins_total": MetricDefinition(
        name="superuser_signins_total",
        metric_type="Counter",
        description="Cumulative count of emergency / SUPER_ADMIN platform sign-ins",
        labels=(),
        alert_condition="increase(superuser_signins_total[5m]) > 0",
        slo_target="Audited superuser access",
    ),
    "cross_tenant_attempts_total": MetricDefinition(
        name="cross_tenant_attempts_total",
        metric_type="Counter",
        description="Cumulative count of intercepted cross-tenant access violation attempts",
        labels=(),
        alert_condition="increase(cross_tenant_attempts_total[1m]) > 0",
        slo_target="Zero cross-tenant violations",
    ),
    "collection_cost_usd": MetricDefinition(
        name="collection_cost_usd",
        metric_type="Gauge",
        description="Estimated cloud provider API / data egress collection cost incurred in USD",
        labels=("provider",),
        alert_condition="collection_cost_usd > budget",
        slo_target="Overhead < 1% of managed cloud spend",
    ),
    "build_info": MetricDefinition(
        name="build_info",
        metric_type="Gauge",
        description="Platform software build version, git commit, and environment metadata",
        labels=("version", "commit"),
        alert_condition="none",
        slo_target="Continuous version provenance",
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


def _get_or_create(cls, name: str, description: str, *args, registry: CollectorRegistry = REGISTRY, **kwargs):
    """Safely retrieves existing collector or registers new one to prevent duplication."""
    if hasattr(registry, "_names_to_collectors") and name in registry._names_to_collectors:
        return registry._names_to_collectors[name]
    return cls(name, description, *args, registry=registry, **kwargs)


class CloudLensMetrics:
    """Manages all Prometheus metrics instances registered with Prometheus client."""

    def __init__(self, registry: CollectorRegistry = REGISTRY) -> None:
        self.registry = registry

        # 1. api_request_duration_seconds
        self.api_request_duration_seconds = _get_or_create(
            Histogram,
            "api_request_duration_seconds",
            "HTTP request execution duration in seconds",
            ["method", "endpoint", "status_code"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=registry,
        )

        # 2. api_requests_total{status}
        self.api_requests_total = _get_or_create(
            Counter,
            "api_requests_total",
            "Cumulative count of HTTP requests processed by status",
            ["status"],
            registry=registry,
        )

        # 3. api_error_rate
        self.api_error_rate = _get_or_create(
            Gauge,
            "api_error_rate",
            "Ratio of HTTP 5xx responses over total requests",
            ["service"],
            registry=registry,
        )

        # 4. sync_job_duration_seconds
        self.sync_job_duration_seconds = _get_or_create(
            Histogram,
            "sync_job_duration_seconds",
            "Elapsed execution time of cloud provider connector sync jobs",
            ["provider", "connector_id", "status"],
            buckets=(1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1200.0, 3600.0),
            registry=registry,
        )

        # 5. sync_job_outcome_total
        self.sync_job_outcome_total = _get_or_create(
            Counter,
            "sync_job_outcome_total",
            "Cumulative count of completed connector sync jobs by outcome",
            ["provider", "connector_id", "outcome"],
            registry=registry,
        )

        # 6. connector_freshness_seconds{provider,capability}
        self.connector_freshness_seconds = _get_or_create(
            Gauge,
            "connector_freshness_seconds",
            "Elapsed seconds since last successful connector sync completion",
            ["provider", "capability"],
            registry=registry,
        )

        # 7. ingestion_rows_total
        self.ingestion_rows_total = _get_or_create(
            Counter,
            "ingestion_rows_total",
            "Cumulative count of canonical FOCUS-standard billing/inventory rows ingested",
            ["provider", "dataset_type"],
            registry=registry,
        )

        # 8. reconciliation_variance_ratio
        self.reconciliation_variance_ratio = _get_or_create(
            Gauge,
            "reconciliation_variance_ratio",
            "Discrepancy ratio between provider billed invoice total and calculated resource total",
            ["tenant_id", "provider"],
            registry=registry,
        )

        # 9. queue_depth{queue}
        self.queue_depth = _get_or_create(
            Gauge,
            "queue_depth",
            "Number of queued background jobs awaiting execution",
            ["queue"],
            registry=registry,
        )

        # 10. worker_saturation
        self.worker_saturation = _get_or_create(
            Gauge,
            "worker_saturation",
            "Worker concurrency utilization ratio (active tasks / worker pool size)",
            ["worker_node", "queue_name"],
            registry=registry,
        )

        # 11. db_replication_lag_seconds
        self.db_replication_lag_seconds = _get_or_create(
            Gauge,
            "db_replication_lag_seconds",
            "Replication delay between primary database and read replicas in seconds",
            ["replica_host"],
            registry=registry,
        )

        # 12. secret_store_up
        self.secret_store_up = _get_or_create(
            Gauge,
            "secret_store_up",
            "Health status of external Vault / SecretStore (1 = healthy, 0 = unreachable)",
            registry=registry,
        )

        # 13. task_failures_total
        self.task_failures_total = _get_or_create(
            Counter,
            "task_failures_total",
            "Cumulative count of background task execution failures",
            registry=registry,
        )

        # 14. alerts_undelivered_total
        self.alerts_undelivered_total = _get_or_create(
            Counter,
            "alerts_undelivered_total",
            "Cumulative count of alerts that could not be delivered to notification channels",
            registry=registry,
        )

        # 15. security_events_total{type}
        self.security_events_total = _get_or_create(
            Counter,
            "security_events_total",
            "Cumulative count of critical platform security events by type",
            ["type"],
            registry=registry,
        )

        # 16. superuser_signins_total
        self.superuser_signins_total = _get_or_create(
            Counter,
            "superuser_signins_total",
            "Cumulative count of emergency / SUPER_ADMIN platform sign-ins",
            registry=registry,
        )

        # 17. cross_tenant_attempts_total
        self.cross_tenant_attempts_total = _get_or_create(
            Counter,
            "cross_tenant_attempts_total",
            "Cumulative count of intercepted cross-tenant access violation attempts",
            registry=registry,
        )

        # 18. collection_cost_usd{provider}
        self.collection_cost_usd = _get_or_create(
            Gauge,
            "collection_cost_usd",
            "Estimated cloud provider API / data egress collection cost incurred in USD",
            ["provider"],
            registry=registry,
        )

        # 19. build_info{version,commit}
        self.build_info = _get_or_create(
            Gauge,
            "build_info",
            "Platform software build version, git commit, and environment metadata",
            ["version", "commit"],
            registry=registry,
        )

        # 20. threshold_evaluation_duration_seconds
        self.threshold_evaluation_duration_seconds = _get_or_create(
            Histogram,
            "threshold_evaluation_duration_seconds",
            "Duration of FinOps budget and cost spike threshold rule evaluation runs",
            ["tenant_id"],
            buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
            registry=registry,
        )

        # 21. notification_delivery_failures_total
        self.notification_delivery_failures_total = _get_or_create(
            Counter,
            "notification_delivery_failures_total",
            "Cumulative count of failed alert notifications across webhook, email, and Slack",
            ["channel_type", "reason"],
            registry=registry,
        )

        # 22. synthetic_journey_duration_seconds & outcome (IMP-05)
        self.synthetic_journey_duration_seconds = _get_or_create(
            Histogram,
            "synthetic_journey_duration_seconds",
            "Duration of end-to-end synthetic user journeys in seconds",
            ["status"],
            buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=registry,
        )
        self.synthetic_journey_outcome_total = _get_or_create(
            Counter,
            "synthetic_journey_outcome_total",
            "Cumulative count of synthetic user journeys by outcome",
            ["status"],
            registry=registry,
        )

        # Initialize defaults so every scrapable metric appears in the initial scrape exposition
        self._initialize_defaults()

    def _initialize_defaults(self) -> None:
        """Sets safe default exposition values so metrics appear in Prometheus scrapes immediately."""
        try:
            self.secret_store_up.set(1.0)
            self.build_info.labels(version="1.1.0", commit="main").set(1.0)
            self.api_error_rate.labels(service="cloudlens-api").set(0.0)
            self.reconciliation_variance_ratio.labels(tenant_id="demo-corp", provider="aws").set(0.0)
            self.connector_freshness_seconds.labels(provider="aws", capability="cost").set(0.0)
            self.queue_depth.labels(queue="celery").set(0.0)
            self.worker_saturation.labels(worker_node="worker-1", queue_name="celery").set(0.0)
            self.db_replication_lag_seconds.labels(replica_host="primary").set(0.0)
            self.collection_cost_usd.labels(provider="aws").set(0.0)

            self.api_requests_total.labels(status="200").inc(0)
            self.security_events_total.labels(type="unauthorized_access").inc(0)
            self.superuser_signins_total.inc(0)
            self.cross_tenant_attempts_total.inc(0)
            self.task_failures_total.inc(0)
            self.alerts_undelivered_total.inc(0)
            self.synthetic_journey_outcome_total.labels(status="SUCCESS").inc(0)
        except Exception:
            pass

    def scrape(self) -> bytes:
        """Generate Prometheus exposition text format bytes."""
        return generate_latest(self.registry)


# Global singleton metrics instance using default registry
metrics = CloudLensMetrics()


def record_synthetic_journey_metric(outcome_status: str, duration_seconds: float) -> None:
    """Records synthetic user journey outcome and duration to Prometheus (IMP-05)."""
    try:
        metrics.synthetic_journey_duration_seconds.labels(status=outcome_status).observe(duration_seconds)
        metrics.synthetic_journey_outcome_total.labels(status=outcome_status).inc()
    except Exception:
        pass
