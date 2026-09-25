# Microsoft Azure Permission Reference

> **Provider**: Microsoft Azure  
> **Security Baseline**: Read-only, Least Privilege (SEC-012)  
> **Owning Connector**: `connectors/azure` (`Prompt 16`)

---

## 1. Authentication Mechanisms

| Mechanism | Description | Security Tier |
|:---|:---|:---:|
| **Entra ID Service Principal + Certificate** | App registration with asymmetric certificate credential (recommended) | **Primary** |
| **Workload Identity Federation** | OIDC federation with trusted Kubernetes or container runtime | **Supported** |
| **Managed Identity** | Azure-hosted system-assigned or user-assigned managed identity | **Supported** |
| **Client Secret (Key)** | Allowed only as audited exception with mandatory rotation | **Restricted** |
| **User Account Passwords** | Interactive user credentials | **Forbidden** |

---

## 2. Required Permissions by Capability Group

| Capability Group | Azure Built-in Role / Action | Required Scope | Capability Flag |
|:---|:---|:---|:---:|
| **Hierarchy Discovery** | `Reader` or `Management Group Reader` | Management Group / Subscription | `C-01` |
| **Resource Inventory** | `Reader` on Microsoft.Resources | Subscription / Resource Group | `C-02` |
| **Cost Ingestion** | `Cost Management Reader` | Billing Account / Subscription | `C-03` |
| **Usage Metrics** | `Monitoring Reader` | Subscription | `C-04` |
| **Pricing Discovery** | Public Retail Rates API (no auth required) | Global | `C-11` |
| **Quota & Limits** | `Reader` on Microsoft.Quota/quotas/read | Subscription | `C-18` |
