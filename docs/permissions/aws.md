# Amazon Web Services (AWS) Permission Reference

> **Provider**: Amazon Web Services (AWS)  
> **Security Baseline**: Read-only, Least Privilege (SEC-012)  
> **Authoritative Specification**: `docs/permissions/aws.md`

---

## 1. Authentication Mechanisms

| Mechanism | Description | Security Tier |
|:---|:---|:---:|
| **Cross-Account IAM Role + External ID (sts:AssumeRole)** | Primary recommended authentication pattern | **Primary** |
| **OIDC Web Identity Federation (EKS / Workload)** | Supported secondary authentication pattern | **Supported** |
| **AWS IAM Identity Center Federation** | Supported secondary authentication pattern | **Supported** |
| **Audited IAM User Access Keys (Mandatory 90-day rotation)** | Supported secondary authentication pattern | **Supported** |
| **AWS Root User Credentials** | Strictly prohibited by governance policy | **Forbidden** |
| **Shared Static Long-Lived Passwords** | Strictly prohibited by governance policy | **Forbidden** |

---

## 2. Required Permissions by Capability Group

| Capability Flag | Capability Group | Minimum Required Permissions | Required Scope | Consequence if Not Granted |
|:---:|:---|:---|:---|:---|
| `C-01` | **Hierarchy Discovery** | `organizations:DescribeOrganization`<br>`organizations:ListAccounts`<br>`organizations:ListRoots`<br>`organizations:ListOrganizationalUnitsForParent`<br>`organizations:ListAccountsForParent` | AWS Organizations Management Account or Delegated Administrator | CloudLens cannot discover multi-account hierarchy; accounts must be added individually. Scope inheritance, OU-based cost allocation, and parent tag inheritance cannot function. |
| `C-02` | **Resource Inventory** | `resource-explorer-2:Search`<br>`tag:GetResources`<br>`tag:GetTagKeys`<br>`tag:GetTagValues` | AWS Account or Multi-Region Resource Explorer Aggregator | Inventory discovery disabled. CloudLens cannot identify orphan resources, unallocated workloads, or evaluate resource-level tag hygiene policies. |
| `C-03` | **Cost & Billing Ingestion** | `ce:GetCostAndUsage`<br>`ce:GetCostAndUsageWithResources`<br>`s3:GetObject on CUR/Cost & Usage Report S3 Bucket`<br>`s3:ListBucket on CUR S3 Bucket` | Billing / Management Account with CUR export target bucket | Billed cost ingestion fails completely. Spend analytics, FOCUS 1.0 normalization, and financial reconciliation cannot operate. |
| `C-04` | **Usage Metrics & Right-Sizing** | `cloudwatch:GetMetricData`<br>`cloudwatch:ListMetrics` | Target AWS Account | Utilization telemetry unavailable. Idle compute detection, right-sizing recommendations, and anomaly correlation with utilization curves are disabled. |
| `C-11` | **Pricing Discovery** | `pricing:GetProducts`<br>`pricing:DescribeServices` | Global endpoint ('us-east-1') | Public rate card lookup disabled. CloudLens falls back to cached baseline prices; on-demand rate comparison and spot pricing analytics may become stale. |
| `C-18` | **Quota & Service Limits** | `servicequotas:GetServiceQuota`<br>`servicequotas:ListServiceQuotas` | Target AWS Account | Service quota tracking disabled. Platform cannot alert when resource provisioning approaches account limits or hard API throttles. |
