# Google Cloud Platform (GCP) Permission Reference

> **Provider**: Google Cloud Platform (GCP)  
> **Security Baseline**: Read-only, Least Privilege (SEC-012)  
> **Authoritative Specification**: `docs/permissions/gcp.md`

---

## 1. Authentication Mechanisms

| Mechanism | Description | Security Tier |
|:---|:---|:---:|
| **Workload Identity Federation (Keyless OIDC)** | Primary recommended authentication pattern | **Primary** |
| **Service Account Attached to Compute / GKE Workload Identity** | Supported secondary authentication pattern | **Supported** |
| **Audited Service Account Key JSON (Mandatory 90-day rotation)** | Supported secondary authentication pattern | **Supported** |
| **Interactive User Credentials (gcloud auth)** | Strictly prohibited by governance policy | **Forbidden** |
| **roles/owner or roles/editor Project Privileges** | Strictly prohibited by governance policy | **Forbidden** |

---

## 2. Required Permissions by Capability Group

| Capability Flag | Capability Group | Minimum Required Permissions | Required Scope | Consequence if Not Granted |
|:---:|:---|:---|:---|:---|
| `C-01` | **Hierarchy Discovery** | `resourcemanager.organizations.get`<br>`resourcemanager.folders.list`<br>`resourcemanager.folders.get`<br>`resourcemanager.projects.list`<br>`resourcemanager.projects.get` | Organization or Target Folder Subtree ('roles/resourcemanager.organizationViewer') | GCP Organization folder hierarchy discovery fails. Projects must be mapped manually without parent inheritance. |
| `C-02` | **Resource Inventory** | `cloudasset.assets.searchAllResources`<br>`cloudasset.assets.list` | Organization or Project ('roles/cloudasset.viewer') | Cloud Asset Inventory disabled. Orphan disks, unattached external IPs, and Compute instances cannot be tracked. |
| `C-03` | **Cost & Billing Ingestion** | `bigquery.jobs.create`<br>`bigquery.tables.getData`<br>`bigquery.tables.get` | Project holding Cloud Billing BigQuery Export Dataset ('roles/bigquery.dataViewer') | BigQuery Cloud Billing export cannot be queried. All GCP cost attribution, CUD discount tracking, and SKU-level spend analysis fail. |
| `C-04` | **Usage Metrics** | `monitoring.timeSeries.list`<br>`monitoring.metricDescriptors.list` | Project Metrics Scope ('roles/monitoring.viewer') | Cloud Monitoring metrics unavailable. Idle VM recommendations and GKE node pool utilization benchmarking are disabled. |
| `C-11` | **Pricing Discovery** | `cloudbilling.services.list`<br>`cloudbilling.skus.list` | Global Cloud Catalog API | GCP SKU catalog synchronization disabled; real-time pricing dimension lookups unavailable. |
| `C-18` | **Quota & Service Limits** | `serviceusage.quotas.get`<br>`serviceusage.services.get` | Project ('roles/servicemanagement.quotaViewer') | GCP quota tracking disabled. Warnings for CPU, IP, or GPU exhaustion cannot be emitted. |
