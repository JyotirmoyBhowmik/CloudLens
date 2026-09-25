# CloudLens Platform Metric Registry

This document records the canonical Prometheus metrics registered across the CloudLens estate per **BBP Section 43 (Observability)**, **NFR-080 to NFR-085**, and **Prompt 03 Item 21**.

Every metric is exposed via the standard Prometheus scrapable `/metrics` endpoint in open text format.

---

## Metric Catalogue

| Metric Name | Type | Labels | Description | SLO / SLA Target | PromQL Alert Condition |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `api_request_duration_seconds` | Histogram | `method`, `endpoint`, `status_code` | HTTP request execution duration in seconds | p95 < 500ms<br>p99 < 1500ms | `histogram_quantile(0.95, sum(rate(api_request_duration_seconds_bucket[5m])) by (le)) > 1.0` |
| `api_error_rate` | Gauge | `service` | Ratio of HTTP 5xx responses over total requests | Error rate < 0.05% | `api_error_rate > 0.01` |
| `sync_job_duration_seconds` | Histogram | `provider`, `connector_id`, `status` | Elapsed time of cloud provider connector sync jobs | p90 < 10m | `histogram_quantile(0.90, sum(rate(sync_job_duration_seconds_bucket[15m])) by (le)) > 900` |
| `sync_job_outcome_total` | Counter | `provider`, `connector_id`, `outcome` | Cumulative count of completed sync jobs by outcome | Success rate > 99.5% | `rate(sync_job_outcome_total{outcome="failed"}[15m]) > 0.05` |
| `connector_freshness_seconds` | Gauge | `provider`, `connector_id` | Elapsed seconds since last successful connector sync | Freshness < 4h | `connector_freshness_seconds > 86400` |
| `ingestion_rows_total` | Counter | `provider`, `dataset_type` | Cumulative count of canonical FOCUS rows ingested | Continuous during active sync | `rate(ingestion_rows_total[1h]) == 0` |
| `reconciliation_variance_ratio` | Gauge | `tenant_id`, `provider` | Discrepancy ratio between billed invoice and resource totals | Variance < 0.1% | `reconciliation_variance_ratio > 0.01` |
| `queue_depth` | Gauge | `queue_name` | Number of queued background jobs awaiting execution | Queue depth < 100 | `queue_depth > 1000` |
| `worker_saturation` | Gauge | `worker_node`, `queue_name` | Worker concurrency utilization ratio | Saturation < 70% | `worker_saturation > 0.85` |
| `db_replication_lag_seconds` | Gauge | `replica_host` | Replication delay between primary DB and read replicas | Lag < 5s | `db_replication_lag_seconds > 60` |
| `threshold_evaluation_duration_seconds` | Histogram | `tenant_id` | Duration of FinOps budget and cost spike threshold rule evaluation runs | p95 < 10s | `histogram_quantile(0.95, sum(rate(threshold_evaluation_duration_seconds_bucket[10m])) by (le)) > 30` |
| `notification_delivery_failures_total` | Counter | `channel_type`, `reason` | Cumulative count of failed alert notifications across webhook, email, Slack | Reliability > 99.9% | `rate(notification_delivery_failures_total[5m]) > 0.1` |

---

## Scraping & Ingestion Architecture

- **Format**: Prometheus text-based exposition format v0.0.4.
- **Port / Endpoint**: `:8000/metrics` (API) and `:9090` (Prometheus server scrape target).
- **Security**: In production environments, `/metrics` is protected by internal VPC network security groups and mutual TLS / bearer token authentication.
- **Cardinality Protection**: Labels are strictly bounded to enumerated sets (`provider`, `channel_type`, `outcome`, `method`) to prevent high-cardinality label explosions.
