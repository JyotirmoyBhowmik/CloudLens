# Oracle Cloud Infrastructure (OCI) Permission Reference

> **Provider**: Oracle Cloud Infrastructure (OCI)  
> **Security Baseline**: Read-only, Least Privilege (SEC-012)  
> **Owning Connector**: `connectors/oci` (`Prompt 19`)

---

## 1. Authentication Mechanisms

| Mechanism | Description | Security Tier |
|:---|:---|:---:|
| **Instance / Resource Principals** | OCI native instance identity (recommended for OCI-hosted) | **Primary** |
| **IAM User + API Signing Key (RSA)** | Dedicated automation user with public/private keypair | **Supported** |
| **Federated Identity via IDCS / IAM** | SAML 2.0 / OIDC identity federation | **Supported** |
| **User Account Passwords** | Interactive console credentials | **Forbidden** |

---

## 2. Required Permissions by Capability Group

| Capability Group | OCI Policy Statements | Required Scope | Capability Flag |
|:---|:---|:---|:---:|
| **Hierarchy Discovery** | `read compartments in tenancy` | Tenancy Root | `C-01` |
| **Resource Inventory** | `read all-resources in tenancy` | Tenancy / Compartment | `C-02` |
| **Cost Ingestion** | `read usage-reports in tenancy`, `read cost-reports in tenancy` | Tenancy Root | `C-03` |
| **Usage Metrics** | `read metrics in tenancy` | Tenancy Root | `C-04` |
| **Pricing Discovery** | Public rate card endpoints | Global | `C-11` |
| **Quota & Limits** | `read limits in tenancy` | Tenancy Root | `C-18` |
