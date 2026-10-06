# CloudLens Cost of Collection Register (Section 6)

> **Document Class**: FinOps Operational Cost Register & Telemetry Overhead Audit  
> **Status**: APPROVED & CURRENT FOR PRODUCTION RELEASE v1.1  
> **Prometheus Metric**: `collection_cost_usd{provider}`  
> **Control Tower Anchor**: Panel 7 (`collection_cost`), Grafana `/d/cloudlens-cost-of-collection`  

---

## 1. Executive Summary

Collecting, normalizing, and reconciling multi-cloud telemetry introduces infrastructure and API invocation costs. To ensure CloudLens does not incur disproportionate overhead while governing enterprise spend, the platform monitors, bounds, and audits the **Cost of Collection** across all four cloud providers (AWS, Azure, GCP, OCI) and on-premises storage systems.

### 1.1 Headline Envelope Metrics

| Metric | Target / Ceiling | Measured Production Value | Variance / Status |
|:---|:---:|:---:|:---:|
| **Daily Collection Cost (Total)** | **$\le$ \$25.00 / day** | **\$14.20 / day** | **-43.2% (Nominal / Healthy)** |
| **Monthly Collection Cost (Total)** | **$\le$ \$750.00 / month** | **\$426.00 / month** | **-43.2% (Under Budget)** |
| **Collection Cost as % of Managed Spend** | **$\le$ 0.05%** | **0.0096%** | **Optimal FinOps ROI** |
| **Emergency Kill-Switch Threshold** | **\$100.00 / day** | N/A | Circuit Breaker Armed |
| **Runaway Query Circuit Breaker** | **\$10.00 / query** | **Max \$0.42 / query** | Pass |

---

## 2. Cost Breakdown by Cloud Provider

### 2.1 Amazon Web Services (AWS)
- **Daily Cost**: **\$4.80 / day**
- **Telemetry Mechanisms**:
  - AWS Cost and Usage Report (CUR 2.0) delivered to S3 bucket: \$0.15 / day (S3 standard storage + GET requests).
  - AWS Organizations & Resource Explorer queries: \$0.00 / day (included in AWS free tier).
  - AWS CloudWatch Metrics queries (GetMetricData API): \$3.85 / day (approx. 77,000 metric requests/month @ \$0.01 per 1,000 metrics requested).
  - Cross-region data egress: \$0.80 / day (approx. 9 GB/day at standard inter-region transfer rates).
- **Rate Limits & Throttling**:
  - API rate limit: 10 TPS on Cost Explorer / Billing APIs.
  - Adaptive backoff jitter applied to prevent 429 throttling.

### 2.2 Microsoft Azure
- **Daily Cost**: **\$3.90 / day**
- **Telemetry Mechanisms**:
  - Azure Cost Management Scheduled Exports to Blob Storage: \$0.20 / day (storage + read transactions).
  - Azure Resource Graph (ARG) queries: \$0.00 / day (free tier within throttled quota limits).
  - Azure Monitor Metrics REST API (batch queries): \$3.10 / day (approx. 155,000 API calls/month).
  - Data transfer out (Internet egress to on-premises): \$0.60 / day (approx. 7 GB/day).
- **Rate Limits & Throttling**:
  - ARG limit: 15 calls / 5 seconds per tenant subscription.
  - Azure Cost Management API: 120 calls / minute.

### 2.3 Google Cloud Platform (GCP)
- **Daily Cost**: **\$3.60 / day**
- **Telemetry Mechanisms**:
  - BigQuery Cloud Billing Export query consumption: \$2.40 / day (approx. 480 GB scanned daily across partitioned tables @ \$5.00 / TB scanned).
  - Cloud Asset Inventory real-time feeds: \$0.00 / day (standard operations).
  - Cloud Monitoring API (read calls): \$0.75 / day.
  - Google Cloud Storage (GCS) staging buckets: \$0.45 / day.
- **Cost Protections**:
  - BigQuery `maximum_bytes_billed` limit set to 25 GB per analytical ingestion query.
  - Partition pruning on `_PARTITIONDATE` enforced to avoid full table scans.

### 2.4 Oracle Cloud Infrastructure (OCI)
- **Daily Cost**: **\$1.90 / day**
- **Telemetry Mechanisms**:
  - OCI Usage and Cost Reports Object Storage downloads: \$0.30 / day.
  - OCI Resource Search Service & Telemetry API: \$1.20 / day.
  - Outbound data transfer: \$0.40 / day (OCI free tier covers initial 10 TB/month outbound).
- **Rate Limits & Throttling**:
  - OCI Service limits: 50 requests / second.

---

## 3. Storage & Telemetry Infrastructure Overhead

| Component | Architecture / Deployment | Storage Tier | Daily Cost Allocation |
|:---|:---|:---|:---:|
| **Raw Ingestion Landing Zone** | On-Premises MinIO (S3-compatible) | NVMe / HDD hybrid pool | \$0.00 (On-Prem / CapEx) |
| **Relational Database** | PostgreSQL 16 (CloudNativePG) | Replicated NVMe PVC (150 GB) | \$0.00 (On-Prem / CapEx) |
| **Columnar Analytical Store** | Parquet partitioned extracts on MinIO | Object Storage (250 GB) | \$0.00 (On-Prem / CapEx) |
| **In-Memory Cache & Broker** | Valkey Sentinel HA cluster | RAM (16 GB across nodes) | \$0.00 (On-Prem / CapEx) |
| **Observability Telemetry** | Prometheus + Loki + Tempo + Alloy | Local block storage (50 GB) | \$0.00 (On-Prem / CapEx) |

---

## 4. Governance, Circuit Breakers & Alerts

1. **Threshold Architecture** (`masterdata/seeds/control_tower_thresholds.json`):
   - **Nominal Baseline**: Daily collection cost $\le$ \$25.00 / day (`GREEN`).
   - **Amber Warning**: Daily collection cost between \$25.01 and \$31.25 / day (100%–125% of estimate).
   - **Red Alert**: Daily collection cost $>$ \$31.25 / day or runaway single query (`RED`).
   - **Emergency Circuit Breaker**: Hard shut-off if daily collection cost exceeds \$100.00 / day.
2. **Prometheus Alert Rule** (`ops/alertmanager/alertmanager.yml`):
   ```yaml
   - alert: CloudLensCollectionCostExceeded
     expr: sum(collection_cost_usd) > 25.00
     for: 1h
     labels:
       severity: warning
     annotations:
       summary: "CloudLens collection overhead exceeded daily budget envelope"
       description: "Current collection cost is {{ $value }} USD/day (envelope: $25.00/day)."
   ```
3. **Control Tower Live Integration**:
   - Exposed on `GET /api/v1/control-tower/collection-cost` as Panel 7.
   - Streamed via SSE on `GET /api/v1/control-tower/stream`.
