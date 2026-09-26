# Oracle Cloud Infrastructure (OCI) Permission Reference

> **Provider**: Oracle Cloud Infrastructure (OCI)  
> **Security Baseline**: Read-only, Least Privilege (SEC-012)  
> **Authoritative Specification**: `docs/permissions/oci.md`

---

## 1. Authentication Mechanisms

| Mechanism | Description | Security Tier |
|:---|:---|:---:|
| **Instance / Resource Principals (for OCI-hosted nodes)** | Primary recommended authentication pattern | **Primary** |
| **IAM User + API Signing RSA Keypair (4096-bit PEM)** | Supported secondary authentication pattern | **Supported** |
| **Federated Identity via IDCS / IAM (SAML 2.0)** | Supported secondary authentication pattern | **Supported** |
| **Console User Account Passwords** | Strictly prohibited by governance policy | **Forbidden** |
| **Tenancy Administrator Group Membership** | Strictly prohibited by governance policy | **Forbidden** |

---

## 2. Required Permissions by Capability Group

| Capability Flag | Capability Group | Minimum Required Permissions | Required Scope | Consequence if Not Granted |
|:---:|:---|:---|:---|:---|
| `C-01` | **Hierarchy Discovery** | `read compartments in tenancy` | Tenancy Root | OCI Compartment tree traversal fails. Compartments and sub-compartments cannot be mapped or allocated. |
| `C-02` | **Resource Inventory** | `read all-resources in tenancy` | Tenancy Root / Target Compartment | OCI Search and Resource inventory disabled. OCI Compute shapes, block volumes, and Autonomous Databases cannot be catalogued. |
| `C-03` | **Cost & Billing Ingestion** | `read usage-reports in tenancy`<br>`read cost-reports in tenancy` | Tenancy Root Object Storage (Usage Report Bucket) | OCI daily cost and usage reports cannot be downloaded. FOCUS cost facts cannot be computed. |
| `C-04` | **Usage Metrics** | `read metrics in tenancy` | Tenancy Root | OCI Monitoring service query disabled. Compute OCPU and RAM utilization metrics unavailable. |
| `C-11` | **Pricing Discovery** | `Public rate card API endpoints (anonymous GET /metering/api/v1/commercial/ratecard)` | Global | Universal Credits (UCC) rate evaluation disabled; standard public rates applied. |
| `C-18` | **Quota & Service Limits** | `read limits in tenancy` | Tenancy Root | OCI Service Limit and quota tracking disabled. |
