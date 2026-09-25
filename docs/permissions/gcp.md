# Google Cloud Platform (GCP) Permission Reference

> **Provider**: Google Cloud Platform (GCP)  
> **Security Baseline**: Read-only, Least Privilege (SEC-012)  
> **Owning Connector**: `connectors/gcp` (`Prompt 18`)

---

## 1. Authentication Mechanisms

| Mechanism | Description | Security Tier |
|:---|:---|:---:|
| **Workload Identity Federation** | Keyless token exchange via OIDC (recommended) | **Primary** |
| **Service Account Attached to Compute** | GCE / GKE instance metadata identity | **Supported** |
| **Service Account JSON Key File** | Permitted with strict audit and mandatory 90-day rotation | **Restricted** |
| **User Account Credentials (gcloud auth)** | Interactive user credentials | **Forbidden** |

---

## 2. Required Permissions by Capability Group

| Capability Group | GCP Predefined Role | Required Scope | Capability Flag |
|:---|:---|:---|:---:|
| **Hierarchy Discovery** | `roles/resourcemanager.organizationViewer` | Organization / Folder | `C-01` |
| **Resource Inventory** | `roles/cloudasset.viewer` | Organization / Project | `C-02` |
| **Cost Ingestion** | `roles/bigquery.dataViewer` on Billing Export | Project holding Export Dataset | `C-03` |
| **Usage Metrics** | `roles/monitoring.viewer` | Project / Metrics Scope | `C-04` |
| **Pricing Discovery** | Cloud Catalog API (Public API Key / Service Account) | Global | `C-11` |
| **Quota & Limits** | `roles/servicemanagement.quotaViewer` | Organization / Project | `C-18` |
