# Microsoft Azure Permission Reference

> **Provider**: Microsoft Azure  
> **Security Baseline**: Read-only, Least Privilege (SEC-012, SEC-016)  
> **Authoritative Specification**: `docs/permissions/azure.md`  
> **Connector Implementation**: `connectors/azure`

---

## 1. Authentication Mechanisms

| Mechanism | Description | Security Tier | Governance Policy |
| :--- | :--- | :---: | :--- |
| **Entra ID Service Principal + Asymmetric Certificate** | Client assertion signed with RSA-2048/SHA-256 certificate | **Primary (Recommended)** | Standard enterprise authentication pattern. Certificates rotated every 12 months. |
| **Workload Identity Federation (OIDC via AKS / Container Runtime)** | Keyless token exchange using RFC 7523 federated identity credentials | **Supported** | Recommended for Kubernetes and container workloads. Zero persistent secret storage. |
| **System-Assigned / User-Assigned Managed Identity** | Azure IMDS metadata endpoint token acquisition (`2018-02-01`) | **Supported** | Permitted for in-Azure CloudLens deployments. |
| **Audited Client Secret** | Application secret string | **Restricted / Secondary** | Allowed only with explicit administrative exception and mandatory 90-day rotation policy. |
| **Interactive User Account Passwords (ROPC)** | Username and password credential | **Forbidden** | Strictly prohibited by enterprise security policy. Never offered or accepted. |
| **Subscription Owner or Contributor Full Roles** | Mutating broad administrative privilege | **Forbidden** | Strictly prohibited. Only read-level roles (Reader, Cost Management Reader) may be granted. |

---

## 2. Required Permissions by Capability Group

Every capability implemented by the Azure Connector requires explicit least-privilege permissions. CloudLens strictly adheres to read-only access.

| Capability Flag | Capability Name | Minimum Required Azure RBAC Permissions / Actions | Minimum Required Built-in Role | Required Scope | Technical & Business Consequence if Missing |
| :---: | :--- | :--- | :--- | :--- | :--- |
| `C-01` | **Authenticate** | `Microsoft.Resources/subscriptions/read` (or tenant identity validation) | Reader | Tenant / Management Group | Connection fails; connector cannot authenticate to Entra ID or establish session. |
| `C-02` | **Validate Permissions** | Actions check across target management groups and subscriptions | Reader | Management Group / Subscription | Capability pre-flight validation fails. Connector cannot determine operational status. |
| `C-03` | **Discover Organizations** | `Microsoft.Management/managementGroups/read` | Management Group Reader | Tenant Root Management Group | Top-level tenant management organization cannot be enumerated. |
| `C-04` | **Discover Accounts** | `Microsoft.Resources/subscriptions/read` | Reader | Management Group / Root | Subscriptions cannot be enumerated under parent management groups. |
| `C-05` | **Discover Hierarchy** | `Microsoft.Management/managementGroups/read`<br>`Microsoft.Management/managementGroups/descendants/read`<br>`Microsoft.Resources/subscriptions/read` | Management Group Reader | Root Management Group or Subtree | Scope tree hierarchy discovery fails. Subscriptions become isolated units; ancestor path and grouping are lost. |
| `C-06` | **Discover Resources (Resource Graph)** | `Microsoft.ResourceGraph/resources/action` (or Reader across scopes) | Reader | Management Group / Subscriptions | Cross-subscription resource inventory cannot be collected via Resource Graph. |
| `C-07` | **Discover Services** | `Microsoft.Resources/subscriptions/providers/read` | Reader | Subscription | Enabled Azure resource provider namespaces cannot be identified. |
| `C-08` | **Collect Cost (Bulk Exports)** | `Microsoft.CostManagement/exports/read`<br>`Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read` | Cost Management Reader + Storage Blob Data Reader | Billing Account / Billing Profile / Subscription + Export Storage Account | Scheduled Cost Management Exports (FOCUS 1.0, ActualCost) cannot be ingested. Batch FinOps cost reporting stalls. |
| `C-09` | **Collect Cost (Query Fallback)** | `Microsoft.CostManagement/query/action` (or `Microsoft.CostManagement/query/read`) | Cost Management Reader | Billing Account / Billing Profile / Management Group / Subscription | Interactive on-demand cost queries and fallback cost collection fail. |
| `C-10` | **Collect Usage (Metrics)** | `Microsoft.Insights/metrics/read`<br>`Microsoft.Insights/metricDefinitions/read` | Monitoring Reader | Subscription / Resource Group | Utilization metrics unavailable. Rightsizing, idle detection, and CPU/memory analytics cannot function. |
| `C-11` | **Collect Pricing (Retail)** | Unauthenticated public API (`https://prices.azure.com/api/retail/prices`) | None (Anonymous) | Global Public Endpoint | Public list rate card cannot be retrieved for baseline comparisons. |
| `C-12` | **Collect Pricing (Negotiated)** | `Microsoft.Billing/billingAccounts/priceSheets/read`<br>`Microsoft.Consumption/pricesheets/read` | Billing Reader / Enrollment Reader | Billing Account / Billing Profile / Enterprise Enrollment | Custom enterprise discount sheets cannot be downloaded. Platform falls back to standard retail rates. |
| `C-13` | **Collect Tags** | `Microsoft.Resources/tags/read`<br>`Microsoft.Resources/subscriptions/resourceGroups/read` | Reader | Subscription / Resource Group / Resource | Multi-tier tag inventory cannot be extracted. Tag compliance and cost attribution by tags are degraded. |
| `C-14` | **Discover Relationships** | `Microsoft.ResourceGraph/resources/action` | Reader | Subscription / Management Group | Topology dependency extraction (NICs, disks, parent-child, `managedBy`) fails. Relationship capability is marked partial. |
| `C-15` | **Collect Budgets** | `Microsoft.CostManagement/budgets/read` | Cost Management Reader | Subscription / Resource Group / Management Group | Azure native budget tracking unavailable. Comparison against CloudLens master budgets cannot be performed. |
| `C-16` | **Health Status** | `GET https://management.azure.com/subscriptions?api-version=2020-01-01` | Reader | Subscription | Live heartbeat health check fails. Connector transitions to degraded state. |
| `C-17` | **Provider Metadata** | `Microsoft.Resources/providers/read` | Reader | Subscription | Azure region list, API version catalogues, and provider capabilities metadata cannot be loaded. |
| `C-18` | **Quota & Service Limits** | `Microsoft.Quota/quotas/read`<br>`Microsoft.Quota/quotaLimits/read` | Reader | Subscription | Regional quota headroom tracking disabled; cannot alert on impending compute or vCPU quota exhaustion. |

---

## 3. Recommended Built-In Role Matrix

To grant CloudLens the necessary least-privilege read access without creating custom role definitions, assign the following built-in roles at the **Root Management Group** (or target Management Group subtree) and the **Cost Export Storage Account**:

1. **Management Group Scope**:
   - `Reader` (`acdd72a7-3385-48ef-bd42-f606fba81ae7`): Provides read access across management groups, subscriptions, resource groups, and resource metadata.
   - `Cost Management Reader` (`72fafb9e-0641-4937-9268-a42530c97a09`): Provides read access to cost exports, queries, and budgets.
   - `Monitoring Reader` (`43d0b873-4d7d-4112-98b6-3ed31a440e60`): Provides read access to Azure Monitor metrics and utilization data.
2. **Billing Account / Enrollment Scope** (for EA / MCA negotiated pricing):
   - `Billing Reader` or `Enrollment Reader`: Enables negotiated Price Sheet downloads.
3. **Storage Account Scope** (holding Cost Management Scheduled Exports):
   - `Storage Blob Data Reader` (`2a2b9908-6ea1-4ae2-8e65-a410df84e7d1`): Enables reading exported billing blobs (FOCUS or ActualCost CSV/Parquet).
