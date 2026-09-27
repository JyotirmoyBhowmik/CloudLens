# Google Cloud Platform (GCP) Cloud Connector Research Note (Prompt 18)

> **Connector**: Google Cloud Platform (GCP) Cloud Connector (`connectors/gcp`)  
> **Authoritative Specifications**: BBP Section 14.4 (GCP capabilities and cautions), Section 15.4 (mapping rules)  
> **Status**: Verified Against Official Google Cloud Platform Documentation  
> **Security Baseline**: Read-only, Least Privilege (SEC-012, SEC-016)

---

## 1. Official Documentation Index & API Version Matrix

| Functional Domain | Official Google Cloud Document Title | Target Endpoint / URI Pattern | API / Schema Version | Verified Behavior & Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Authentication — Workload Identity** | *Workload Identity Federation Documentation* | `POST https://sts.googleapis.com/v1/token`<br>`POST https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{EMAIL}:generateAccessToken` | `v1` | Recommended primary authentication mechanism. Keyless OIDC token exchange (RFC 7523 / RFC 8693) for Kubernetes (GKE Workload Identity, EKS, or container runtimes). Zero downloaded service account keys. |
| **Authentication — Service Account Keys (Exception)** | *Creating and managing service account keys* | `POST https://oauth2.googleapis.com/token` (JWT Bearer assertion) | `v1` / RFC 7523 | Supported only where federation is impossible. Enforces mandatory 90-day key rotation. **Interactive user credentials (`gcloud auth`) and full mutating `roles/owner` or `roles/editor` are strictly prohibited**. |
| **Hierarchy Discovery — Resource vs Billing** | *Cloud Resource Manager API Reference*<br>*Cloud Billing API Reference* | `GET https://cloudresourcemanager.googleapis.com/v3/organizations/{orgId}`<br>`GET https://cloudresourcemanager.googleapis.com/v3/folders`<br>`GET https://cloudresourcemanager.googleapis.com/v3/projects`<br>`GET https://cloudbilling.googleapis.com/v1/projects/{projectId}/billingInfo` | `v3` (Resource Manager)<br>`v1` (Cloud Billing) | **Strict Separation**: The resource hierarchy (`organizations/{id}` -> `folders/{id}` -> `projects/{id}`) and the billing hierarchy (`billingAccounts/{id}`) are distinct and represented separately. Preserves folder nesting in canonical scope paths. Links billing account via `ProjectBillingInfo`. **Billing hierarchy is never merged into resource hierarchy**. |
| **Resource Inventory — Asset Inventory** | *Cloud Asset Inventory API Reference* | `GET https://cloudasset.googleapis.com/v1/{scope}/assets:searchAllResources`<br>`POST https://cloudasset.googleapis.com/v1/{scope}/assets:export` | `v1` | Primary inventory source. Handles documented constraints: export destinations restricted to GCS and BigQuery; frequently changing fields may export as null; field casing differs (REST camelCase vs BigQuery snake_case); organization-scope restrictions; minimum interval between repeated exports. |
| **Relationships & Topology Probe** | *Viewing Relationships between Assets (Cloud Asset Inventory)* | `GET https://cloudasset.googleapis.com/v1/{scope}/assets:searchAllResources?contentType=RELATIONSHIP` | `v1` | **Runtime Probe**: Availability depends on service tier and asset type. Probed dynamically at runtime; declared as **PARTIAL** (`is_partial = True`) in capability profile. |
| **Cost Ingestion — BigQuery Export** | *Cloud Billing data export to BigQuery* | `POST https://bigquery.googleapis.com/bigquery/v2/projects/{projectId}/queries` | `v2` (BigQuery REST API)<br>Schema: Standard, Detailed (`resource_v1`), Pricing, FOCUS | Ingests from 4 BigQuery export tables. Detailed export (`gcp_billing_export_resource_v1_*`) is used for resource-level attribution. **Query Cost Visibility**: Computes query bytes billed ($5.00/TB on-demand pricing) and surfaces running query cost to the platform. **Onboarding Warning**: Billing export is NOT retrospective; history begins strictly at enablement. |
| **Pricing — Cloud Billing Catalog** | *Cloud Billing Catalog API Reference* | `GET https://cloudbilling.googleapis.com/v1/services`<br>`GET https://cloudbilling.googleapis.com/v1/services/{serviceId}/skus` | `v1` | Public catalog lists services and SKUs with list prices, geographic taxonomy, and pricing expressions. Supports API keys and `pageToken` pagination. Account-specific contract pricing path takes strict precedence over public catalog. |
| **Budgets** | *Cloud Billing Budget API Reference* | `GET https://billingbudgets.googleapis.com/v1/billingAccounts/{billingAccountId}/budgets` | `v1` | Ingests budgets for comparative variance reporting only (`is_authoritative = False`). **Pub/Sub notification channels incur cloud charges and must NOT be enabled silently**. |
| **Usage Telemetry & Metrics** | *Cloud Monitoring API Reference* | `GET https://monitoring.googleapis.com/v3/projects/{projectId}/timeSeries` | `v3` | Collects coarse operational metrics (hourly `alignmentPeriod=3600s`, daily `alignmentPeriod=86400s`). Sub-minute intervals (`alignmentPeriod < 3600s`) strictly rejected. |
| **Service Discovery** | *Service Usage API Reference* | `GET https://serviceusage.googleapis.com/v1/projects/{projectId}/services?filter=state:ENABLED` | `v1` | Enumerates active and enabled APIs/services per project. |
| **Labels & Tags** | *Creating and managing labels* | Project metadata and Cloud Asset Inventory labels | `v1` | Collects labels recording source level (`LABEL_SOURCE_PROJECT` vs `LABEL_SOURCE_RESOURCE`). |

---

## 2. Resource Hierarchy vs Billing Hierarchy Dual Representation

In Google Cloud, resource management and billing are orthogonal:

```
[Resource Hierarchy]                          [Billing Hierarchy]
Organization: organizations/1092837465          Cloud Billing Account:
    |                                           billingAccounts/01ABCD-2345EF-6789GH
    +-- Folder: folders/9876543210 (Core)               |
    |       |                                           | (1:N Billing Association)
    |       +-- Project: proj-retail-banking-prod  <----+
    |       |       |
    |       |       +-- VM: gcp-vm-core-bank-prod-01
    |       |       +-- GCS: gcp-gcs-customer-statements-prod
    |       |
    |       +-- Project: proj-ai-analytics         <----+
    |               |
    |               +-- BigQuery: bq-features
    |
    +-- Project: proj-unmapped-sandbox             <----+ (Can link to same or different BA)
```

### Architectural Principles:
1. **Never Merge the Hierarchies**: Merging the billing account into the folder tree causes split-brain ancestry because projects in different folders can share the same billing account, and projects can be moved between folders without changing billing accounts.
2. **Linked Scope Modeling**: Projects belong to the resource folder ancestry (`scope_path = /org/folder/project`), while carrying a `linked_billing_account_id` attribute pointing to the billing hierarchy.
3. **Billing Boundary**: Billing facts aggregate at the Cloud Billing Account level, while cost attribution decomposes by project and resource labels.

---

## 3. BigQuery Billing Ingestion & Running Query Cost Visibility

CloudLens queries the customer's BigQuery billing dataset. Because BigQuery on-demand queries incur provider charges ($5.00 per TB scanned), query cost must be accounted for and surfaced:

- **Query Metrics Captured**:
  - `bytes_scanned`: Exact bytes read from table columns.
  - `bytes_billed`: Billed bytes (minimum 10 MB per query per BigQuery pricing model).
  - `query_cost_usd`: Calculated using canonical BigQuery rate ($\text{bytes\_billed} / 10^{12} \times \$5.00$).
  - `query_latency_ms`: Execution duration.
  - `export_table_type`: `DETAILED_RESOURCE`, `STANDARD`, `PRICING`, or `FOCUS`.
- **Query Optimization**: Queries partition-prune using `_PARTITIONDATE` or `export_time` to prevent unbounded scans.

---

## 4. Documented Constraints & Cautions

1. **Billing Export History is Not Retrospective**:
   - Google Cloud Billing exports only records created *after* the export is enabled. No historical billing records exist in BigQuery prior to enablement.
   - **Enforcement**: Surfaced as a permanent warning in the Onboarding Wizard and pre-completion estimates.
2. **Chargeable Pub/Sub Notifications**:
   - Cloud Billing Budget Pub/Sub topics incur messaging and streaming costs.
   - **Enforcement**: Programmatic Pub/Sub notification must never be provisioned silently.
3. **Asset Inventory Relationship Availability**:
   - `RELATIONSHIP` content type in Cloud Asset Inventory is not universally available for all asset types or service tiers.
   - **Enforcement**: Probed dynamically at runtime; connector declares capability as `PARTIAL` (`is_partial = True`).
4. **Cloud Monitoring Coarse Aggregates**:
   - High-frequency metrics generate excessive API calls and billing.
   - **Enforcement**: Enforces hourly (`3600s` / `PT1H`) or daily (`86400s` / `P1D`) alignment periods; sub-minute requests are rejected.
