# CloudLens Operational Dashboards

This document outlines the five canonical starter operational dashboards defined for CloudLens per **Prompt 03 Item 23** and **BBP Section 43**.

All dashboard definitions are versioned in `ops/dashboards/*.json` and are compatible with open-source Grafana and Prometheus.

---

## 1. API Health & Latency Dashboard (`api_health.json`)
- **Target Audience**: Platform Engineering, API Operations
- **Panels**:
  1. **API Request Rate (QPS)**: `sum(rate(api_request_duration_seconds_count[1m])) by (method, endpoint)`
  2. **Latency Percentiles**: p50, p95, and p99 evaluated over a 5m sliding window (`api_request_duration_seconds_bucket`).
  3. **API Error Rate Gauge**: Visual gauge tracking ratio of 5xx server errors (`api_error_rate`).
  4. **HTTP Status Codes Breakdown**: Segmented timeseries by status code (200, 400, 401, 403, 404, 500).

---

## 2. Connector Sync Health Dashboard (`sync_health.json`)
- **Target Audience**: FinOps Data Engineers, Cloud Integration Specialists
- **Panels**:
  1. **Sync Jobs by Outcome**: Timeseries of completed jobs broken down by provider (`azure`, `aws`, `gcp`, `oci`) and outcome (`success` vs `failed`).
  2. **Sync Duration Heatmap / p90**: `sync_job_duration_seconds` quantile analysis alerting if sync exceeds 15 minutes.
  3. **Failure Ratio**: High-level alert gauge displaying proportion of failed sync executions over the last 15 minutes.

---

## 3. Ingestion Volume & Variance Dashboard (`ingestion_volume.json`)
- **Target Audience**: Data Operations, Financial Controllers
- **Panels**:
  1. **FOCUS Ingested Rows/Sec**: Ingestion throughput across canonical billing and inventory datasets (`ingestion_rows_total`).
  2. **Cumulative Rows Ingested**: Counter stat panel displaying total volume by cloud provider.
  3. **Reconciliation Variance Ratio**: Discrepancy ratio tracking delta between cloud invoice total and resource summation (`reconciliation_variance_ratio`). Alerts when variance exceeds 1%.

---

## 4. Task Queue Depth & Saturation Dashboard (`queue_depth.json`)
- **Target Audience**: Site Reliability Engineering (SRE), Platform Operations
- **Panels**:
  1. **Celery Task Queue Depth**: Real-time gauge of tasks waiting in Redis brokers (`queue_depth`).
  2. **Worker Concurrency Saturation**: Ratio of busy Celery worker slots to pool capacity (`worker_saturation`). Alerts when saturation exceeds 85% for > 15 minutes.

---

## 5. Data Freshness & Database Health Dashboard (`data_freshness.json`)
- **Target Audience**: FinOps Operations, Database Administrators
- **Panels**:
  1. **Connector Data Freshness Lag**: Elapsed seconds since last successful ingest (`connector_freshness_seconds`). Alerts if data is older than 24 hours.
  2. **PostgreSQL Replication Lag**: Latency in seconds between primary and read replicas (`db_replication_lag_seconds`).
  3. **Threshold Evaluation Latency**: FinOps budget and cost spike rule evaluation duration (`threshold_evaluation_duration_seconds`).
  4. **Notification Delivery Failure Rate**: Rate of failed notifications across Webhook, Email, and Slack (`notification_delivery_failures_total`).
