# Microsoft Azure Permission Reference

> **Provider**: Microsoft Azure  
> **Security Baseline**: Read-only, Least Privilege (SEC-012)  
> **Authoritative Specification**: `docs/permissions/azure.md`

---

## 1. Authentication Mechanisms

| Mechanism | Description | Security Tier |
|:---|:---|:---:|
| **Entra ID Service Principal + Asymmetric Certificate** | Primary recommended authentication pattern | **Primary** |
| **Workload Identity Federation (OIDC via AKS / Container Runtime)** | Supported secondary authentication pattern | **Supported** |
| **System-Assigned / User-Assigned Managed Identity (Azure hosted)** | Supported secondary authentication pattern | **Supported** |
| **Audited Client Secret (Mandatory 90-day rotation exception)** | Supported secondary authentication pattern | **Supported** |
| **Interactive User Account Passwords** | Strictly prohibited by governance policy | **Forbidden** |
| **Subscription Owner or Contributor Full Roles** | Strictly prohibited by governance policy | **Forbidden** |

---

## 2. Required Permissions by Capability Group

| Capability Flag | Capability Group | Minimum Required Permissions | Required Scope | Consequence if Not Granted |
|:---:|:---|:---|:---|:---|
| `C-01` | **Hierarchy Discovery** | `Microsoft.Management/managementGroups/read`<br>`Microsoft.Management/managementGroups/descendants/read`<br>`Microsoft.Resources/subscriptions/read` | Root Management Group or Target Management Group Subtree | Azure Management Group and Subscription hierarchy discovery fails. Subscriptions must be connected as isolated islands; cross-subscription grouping and inheritance are lost. |
| `C-02` | **Resource Inventory** | `Microsoft.Resources/subscriptions/resourceGroups/read`<br>`Microsoft.Resources/resources/read` | Subscription or Target Resource Group | Azure resource inventory disabled. Infrastructure assets, virtual machines, and storage accounts cannot be tracked or attributed to cost centers. |
| `C-03` | **Cost & Billing Ingestion** | `Microsoft.CostManagement/exports/read`<br>`Microsoft.Consumption/usageDetails/read`<br>`Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read (on export blob)` | Enrollment / Billing Account / Subscription holding scheduled Cost Export | Azure Cost Management data export cannot be read. Cost facts and amortized reservation reporting cannot be generated. |
| `C-04` | **Usage Metrics** | `Microsoft.Insights/metrics/read`<br>`Microsoft.Insights/metricDefinitions/read` | Subscription / Resource | Azure Monitor metrics unavailable. Idle CPU detection, VM rightsizing, and memory underutilization insights cannot function. |
| `C-11` | **Pricing Discovery** | `Public Retail Rates API (anonymous GET /api/v1/prices)` | Global | Custom enterprise discount sheet evaluation disabled; standard retail list prices used. |
| `C-18` | **Quota & Service Limits** | `Microsoft.Quota/quotas/read`<br>`Microsoft.Quota/quotaLimits/read` | Subscription | Azure regional quota monitoring disabled. Quota headroom alerts cannot be raised. |
