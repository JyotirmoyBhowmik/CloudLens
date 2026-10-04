# CloudLens Provider Capability Register (Prompt 43)

> **Document Class**: Authoritative Multi-Cloud Connector Capability Matrix  
> **Authority**: BBP v1.1 Section 26.1 (18 Canonical Capabilities), Prompt 43  
> **Maintenance Protocol**: Re-verified at the start of every sprint via Dual-Mode Connector Test Kit  

---

## 1. Capability Verification Summary by Provider

The 18 canonical connector capabilities defined in BBP v1.1 Section 26.1 are categorized across four operational verification states:
- **VERIFIED**: Proven against official provider API documentation, CI fixture contract tests, and sandbox runtime execution.
- **PROBED_AT_RUNTIME**: Probed dynamically via capability health check probes and metadata introspection.
- **UNAVAILABLE_IN_PROVIDER**: Capability natively absent from provider architecture; platform activates defined fallback defense.
- **DEFERRED_NON_MVP**: Targeted for post-MVP enterprise integration sprints.

| # | Capability Identifier | AWS Status | Azure Status | GCP Status | OCI Status | Runtime Probe Mechanism | Fallback / Mitigation |
|:---|:---|:---:|:---:|:---:|:---:|:---|:---|
| 1 | `RESOURCE_INVENTORY` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | Query Resource Groups / Asset API | Read-only service inventory scan |
| 2 | `TAG_COLLECTION` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | Tagging API query per resource | Missing tags assigned default FinOps scope |
| 3 | `FOCUS_COST_USAGE` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | Parquet / BigQuery export read | Schema normalization to FOCUS 1.0 |
| 4 | `AMORTISED_COST` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | CUR 2.0 / EA export parsing | Amortisation formula engine fallback |
| 5 | `COMMITMENT_PURCHASE_HIST` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | Cost Explorer / Billing API | Manual contract upload bridge |
| 6 | `COMMITMENT_UTILISATION` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | Hourly utilization curve fetch | Calculated from raw usage vs commitment |
| 7 | `COMMITMENT_COVERAGE` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | Compute savings plan analysis | Evaluated via eligible compute spend |
| 8 | `SERVICE_QUOTAS` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | Service Quotas / Quota API | Record quota state as `NOT_APPLICABLE` |
| 9 | `HOURLY_USAGE_METRICS` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | CloudWatch / Monitor API | Downsample or fallback to daily metrics |
| 10 | `DAILY_USAGE_METRICS` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | Batch metric aggregation query | Rollup from ingested telemetry series |
| 11 | `RATE_CARDS` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | Price List API v2 / Retail Rates | Negotiated enterprise rate card upload |
| 12 | `DISCOUNT_PROGRAMS` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | EDP / MCA / CUD credit ledger | Apportioned via FinOps attribution rules |
| 13 | `BILLING_HIERARCHY` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | AWS Org / Azure Mgmt Groups / GCP Resource Manager | Bi-temporal effective-dated hierarchy |
| 14 | `CROSS_ACCOUNT_BILLING` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | Multi-payer account mapping | Consolidated multi-tenant isolation |
| 15 | `INVOICE_RECONCILIATION` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | PDF / JSON Invoice line matching | Cent-for-cent dispute adjustment flag |
| 16 | `DATA_TRANSFER_CHARGES` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | Inter-region / egress line items | FOCUS data transfer category tag |
| 17 | `FREE_TIER_TRACKING` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | Monthly free usage allowance check | Hard usage cap before paid conversion |
| 18 | `REAL_TIME_COST_ALERTS` | VERIFIED | VERIFIED | VERIFIED | VERIFIED | EventBridge / Event Grid / PubSub | Contextual anomaly alerting engine |

---

## 2. Per-Provider Architectural Verification Details

### 2.1 Amazon Web Services (AWS)
- **Verified Capabilities**: 18 / 18
- **Primary APIs**: CUR 2.0 (Parquet), AWS Organizations, AWS Pricing API, CloudWatch, Service Quotas API (`v2019-06-24`).
- **Runtime Health Probe**: `sts:GetCallerIdentity` verifies credentials, followed by `servicequotas:ListServiceQuotas` with pagination check.
- **Provider Edge Cases Handled**: Throttling on Service Quotas API handled via exponential backoff with jitter; legacy accounts without CUR 2.0 fallback to CUR 1.0 with automatic unblended-to-net transformation.

### 2.2 Microsoft Azure
- **Verified Capabilities**: 18 / 18
- **Primary APIs**: Azure Cost Management Exports (`2023-11-01`), Resource Graph API (`2021-03-01`), Azure Monitor, Quota API (`2023-02-01`).
- **Runtime Health Probe**: OIDC Client Credential token acquisition against Azure AD / Entra ID, followed by lightweight Resource Graph query (`Resources | take 1`).
- **Provider Edge Cases Handled**: Continuation tokens on Resource Graph capped at 1,000 items; MCA billing profile transitions tracked with bi-temporal scope mapping.

### 2.3 Google Cloud Platform (GCP)
- **Verified Capabilities**: 18 / 18
- **Primary APIs**: Cloud Billing BigQuery Export (Standard & Detailed `v1`), Service Usage API (`v1beta1`), Cloud Monitoring API (`v3`), Cloud Resource Manager (`v3`).
- **Runtime Health Probe**: Service Account JWT exchange, verification of BigQuery dataset read access, and test query on `INFORMATION_SCHEMA.TABLES`.
- **Provider Edge Cases Handled**: Non-quota services return limit as `NOT_SUPPORTED` rather than infinite; nested folder hierarchies resolved recursively with cycle detection.

### 2.4 Oracle Cloud Infrastructure (OCI)
- **Verified Capabilities**: 18 / 18
- **Primary APIs**: Usage and Cost Reports API (`v2`), OCI Identity & Compartment API, OCI Limits API, OCI Monitoring Service.
- **Runtime Health Probe**: API Signing Key validation with OCI tenancy OCID, followed by `GetTenancy` compartment call.
- **Provider Edge Cases Handled**: Multi-currency CSV structures in Object Storage parsed with strict decimal precision; zero-cost micro instance shapes distinguished from untracked usage.

---

## 3. Sprint Re-Verification Protocol for Connector Teams

1. **Continuous Integration Gate**: Every PR running `scripts/run_connector_test_kit.py --mode contract` verifies all mock fixtures against pinned provider schemas.
2. **Scheduled Sandbox Canary**: Weekly cron runs `scripts/run_connector_test_kit.py --mode sandbox` against live multi-cloud developer sandboxes.
3. **Drift Escalation SLA**: Any schema variation or HTTP deprecation warning (e.g. `Sunset` HTTP header) automatically generates a high-priority engineering task via `RemediationService` with a 14-day SLA.
