# CloudLens Provider Capability Register (Prompt 43)

> **Document Class**: Authoritative Multi-Cloud Connector Capability Matrix  
> **Authority**: BBP v1.1 Section 26.1 (18 Canonical Capabilities), Prompt 43  
> **Maintenance Protocol**: Re-verified at the start of every sprint via Dual-Mode Connector Test Kit  

---

## 1. Capability Verification Summary by Provider

- **LIVE**: Signed off live end-to-end against provider APIs and export pipelines with zero fixtures in production path.
- **LIVE_PENDING**: Cloud SDKs integrated with typed clients; live end-to-end credentials pending tenant provisioning.
- **PROBED_AT_RUNTIME**: Probed dynamically via capability health check probes and metadata introspection.
- **UNAVAILABLE_IN_PROVIDER**: Capability natively absent from provider architecture; platform activates defined fallback defense.

| # | Capability Identifier | AWS Status | Azure Status | GCP Status | OCI Status | Runtime Probe Mechanism | Fallback / Mitigation |
|:---|:---|:---:|:---:|:---:|:---:|:---|:---|
| 1 | `RESOURCE_INVENTORY` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | Query Resource Groups / Tagging / Asset API | Read-only service inventory scan |
| 2 | `TAG_COLLECTION` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | Tagging API query per resource | Missing tags assigned default FinOps scope |
| 3 | `FOCUS_COST_USAGE` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | Parquet / BigQuery export read | Schema normalization to FOCUS 1.0 |
| 4 | `AMORTISED_COST` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | CUR 2.0 / EA export parsing | Amortisation formula engine fallback |
| 5 | `COMMITMENT_PURCHASE_HIST` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | Cost Explorer / Billing API | Manual contract upload bridge |
| 6 | `COMMITMENT_UTILISATION` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | Hourly utilization curve fetch | Calculated from raw usage vs commitment |
| 7 | `COMMITMENT_COVERAGE` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | Compute savings plan analysis | Evaluated via eligible compute spend |
| 8 | `SERVICE_QUOTAS` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | Service Quotas / Quota API | Record quota state as `NOT_APPLICABLE` |
| 9 | `HOURLY_USAGE_METRICS` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | CloudWatch / Monitor API | Downsample or fallback to daily metrics |
| 10 | `DAILY_USAGE_METRICS` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | Batch metric aggregation query | Rollup from ingested telemetry series |
| 11 | `RATE_CARDS` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | Price List API v2 / Retail Rates | Negotiated enterprise rate card upload |
| 12 | `DISCOUNT_PROGRAMS` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | EDP / MCA / CUD credit ledger | Apportioned via FinOps attribution rules |
| 13 | `BILLING_HIERARCHY` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | AWS Org / Azure Mgmt Groups / GCP Resource Manager | Bi-temporal effective-dated hierarchy |
| 14 | `CROSS_ACCOUNT_BILLING` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | Multi-payer account mapping | Consolidated multi-tenant isolation |
| 15 | `INVOICE_RECONCILIATION` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | PDF / JSON Invoice line matching | Cent-for-cent dispute adjustment flag |
| 16 | `DATA_TRANSFER_CHARGES` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | Inter-region / egress line items | FOCUS data transfer category tag |
| 17 | `FREE_TIER_TRACKING` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | Monthly free usage allowance check | Hard usage cap before paid conversion |
| 18 | `REAL_TIME_COST_ALERTS` | LIVE | LIVE_PENDING | LIVE_PENDING | LIVE_PENDING | EventBridge / Event Grid / PubSub | Contextual anomaly alerting engine |

---

## 2. Per-Provider Architectural Verification Details

### 2.1 Amazon Web Services (AWS)
- **Operational State**: **LIVE** (Signed off end-to-end via Prompt P13A)
- **Verified Capabilities**: 18 / 18
- **Primary APIs**: BCM Data Exports CUR 2.0 (Parquet / S3), AWS Organizations, AWS Pricing API, CloudWatch, Service Quotas API (`v2019-06-24`), Resource Groups Tagging API.
- **Runtime Health Probe**: `sts:GetCallerIdentity` verifies credentials, followed by `servicequotas:ListServiceQuotas` with pagination check.
- **Provider Edge Cases Handled**: Throttling on Service Quotas API handled via exponential backoff with jitter; S3 exports parsed directly; raw payloads landed to MinIO before normalisation; credentials resolved dynamically from OpenBao KV v2.

### 2.2 Microsoft Azure
- **Operational State**: **LIVE_PENDING** (Signed off pending tenant account credentials)
- **Verified Capabilities**: 18 / 18
- **Primary APIs**: Azure Cost Management Exports (`2023-11-01`), Resource Graph API (`2021-03-01`), Azure Monitor, Quota API (`2023-02-01`), azure-storage-blob.
- **Runtime Health Probe**: OIDC Client Credential token acquisition against Azure AD / Entra ID, followed by lightweight Resource Graph query (`Resources | take 1`).
- **Provider Edge Cases Handled**: Continuation tokens on Resource Graph capped at 1,000 items; MCA billing profile transitions tracked with bi-temporal scope mapping.

### 2.3 Google Cloud Platform (GCP)
- **Operational State**: **LIVE_PENDING** (Signed off pending tenant account credentials)
- **Verified Capabilities**: 18 / 18
- **Primary APIs**: Cloud Billing BigQuery Export (Standard & Detailed `v1`), Service Usage API (`v1beta1`), Cloud Monitoring API (`v3`), Cloud Resource Manager (`v3`), google-cloud-asset.
- **Runtime Health Probe**: Service Account JWT exchange, verification of BigQuery dataset read access, and test query on `INFORMATION_SCHEMA.TABLES`.
- **Provider Edge Cases Handled**: Non-quota services return limit as `NOT_SUPPORTED` rather than infinite; nested folder hierarchies resolved recursively with cycle detection; BigQuery mandatory partition filtering.

### 2.4 Oracle Cloud Infrastructure (OCI)
- **Operational State**: **LIVE_PENDING** (Signed off pending tenant account credentials)
- **Verified Capabilities**: 18 / 18
- **Primary APIs**: Usage and Cost Reports API (`v2`), OCI Identity & Compartment API, OCI Limits API, OCI Monitoring Service, OCI Object Storage.
- **Runtime Health Probe**: API Signing Key validation with OCI tenancy OCID, followed by `GetTenancy` compartment call.
- **Provider Edge Cases Handled**: Multi-currency CSV structures in Object Storage parsed with strict decimal precision; zero-cost micro instance shapes distinguished from untracked usage.

---

## 3. Sprint Re-Verification Protocol for Connector Teams

1. **Continuous Integration Gate**: Every PR running `scripts/run_connector_test_kit.py --mode contract` verifies all mock fixtures against pinned provider schemas.
2. **Scheduled Sandbox Canary**: Weekly cron runs `scripts/run_connector_test_kit.py --mode sandbox` against live multi-cloud developer sandboxes.
3. **Drift Escalation SLA**: Any schema variation or HTTP deprecation warning (e.g. `Sunset` HTTP header) automatically generates a high-priority engineering task via `RemediationService` with a 14-day SLA.
