# Amazon Web Services (AWS) Permission Reference

> **Provider**: Amazon Web Services (AWS)  
> **Security Baseline**: Read-only, Least Privilege (SEC-012, SEC-016)  
> **Authoritative Specification**: `docs/permissions/aws.md`  
> **Connector Implementation**: `connectors/aws`

---

## 1. Authentication Mechanisms

| Mechanism | Description | Security Tier | Governance Policy |
| :--- | :--- | :---: | :--- |
| **Cross-Account IAM Role + External ID (`sts:AssumeRole`)** | Primary recommended authentication pattern. Assumes an IAM role from the CloudLens principal using a tenant-specific `ExternalId`. | **Primary (Recommended)** | Standard enterprise authentication pattern. Mitigates Confused Deputy attacks across multi-tenant boundaries. |
| **OIDC Web Identity Federation (`sts:AssumeRoleWithWebIdentity`)** | Keyless token exchange for container workloads (EKS IRSA / Pod Identity). | **Supported** | Recommended for Kubernetes-hosted CloudLens deployments. Zero long-lived credentials. |
| **AWS IAM Identity Center Federation** | Workforce SSO federation. | **Supported** | Permitted for enterprise federated identities. |
| **Audited IAM User Access Keys** | Static access key and secret access key. | **Restricted / Exception Only** | Permitted only as an audited exception with mandatory 90-day cryptographic rotation. Never the default. |
| **AWS Root User Credentials** | Root account email and password / access keys. | **Forbidden** | Strictly prohibited by governance policy. Never offered or accepted. |
| **Shared Static Long-Lived Passwords** | User console passwords. | **Forbidden** | Strictly prohibited. CloudLens interacts via machine-to-machine APIs only. |

---

## 2. Member-Account Cross-Account Access Model

In AWS multi-account estates, CloudLens uses a hub-and-spoke cross-account IAM role pattern:

```
[CloudLens Core Principal]
 (e.g. arn:aws:iam::111122223333:role/CloudLensIngestionWorker)
         |
         | 1. sts:AssumeRole (ExternalId="CL-TENANT-XYZ-EXTERNAL-ID")
         v
[Management Account] (arn:aws:iam::123456789012:role/CloudLensManagementRole)
  - Organizations Read: ListRoots, ListOrganizationalUnitsForParent, ListAccounts
  - BCM Data Exports / S3 Bucket Read: s3:GetObject, s3:ListBucket on CUR 2.0 S3 Bucket
  - Cost Explorer & Budgets: ce:GetCostAndUsage, budgets:ViewBudget
  - Cost Category Definitions: ce:ListCostCategoryDefinitions
         |
         | 2. sts:AssumeRole (ExternalId="CL-TENANT-XYZ-EXTERNAL-ID")
         v
[Member Account A] (arn:aws:iam::222233334444:role/CloudLensMemberRole)
  - Resource Inventory: tag:GetResources, config:BatchGetResourceConfig
  - CloudWatch Coarse Metrics: cloudwatch:GetMetricData
  - Structural Topology: ec2:DescribeNetworkInterfaces, ec2:DescribeVolumes
```

### Trust Policy on Management Account Role (`CloudLensManagementRole`):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "CL-TENANT-00000000-0000-0000-0000-000000000001"
        }
      }
    }
  ]
}
```

### Trust Policy on Member Account Role (`CloudLensMemberRole`):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "arn:aws:iam::111122223333:root",
          "arn:aws:iam::123456789012:role/CloudLensManagementRole"
        ]
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "CL-TENANT-00000000-0000-0000-0000-000000000001"
        }
      }
    }
  ]
}
```

---

## 3. Required Permissions Across Seventeen Capabilities

| Capability Flag | Capability Name | Minimum Required AWS IAM Actions | Required Scope | Technical & Business Consequence if Missing |
| :---: | :--- | :--- | :--- | :--- |
| `C-01` | **Authenticate** | `sts:AssumeRole` (or `sts:GetCallerIdentity`) | CloudLens Principal -> Target Account | Connection handshake fails; connector cannot authenticate to AWS or assume session. |
| `C-02` | **Validate Permissions** | `sts:GetCallerIdentity`, Actions check across target services | Target IAM Role | Capability pre-flight validation fails. Connector cannot verify operational readiness. |
| `C-03` | **Discover Organizations** | `organizations:DescribeOrganization`<br>`organizations:ListRoots` | Management Account | Top-level organization structure cannot be identified. |
| `C-04` | **Discover Accounts** | `organizations:ListAccounts`<br>`organizations:ListAccountsForParent` | Management Account | Member accounts cannot be enumerated under OUs. |
| `C-05` | **Discover Hierarchy** | `organizations:ListRoots`<br>`organizations:ListOrganizationalUnitsForParent`<br>`organizations:ListAccountsForParent` | Management Account | Canonical scope tree fails. Member accounts become isolated; OU inheritance and nesting are lost. |
| `C-06` | **Discover Resources** | `tag:GetResources`<br>`config:BatchGetResourceConfig`<br>`resource-explorer-2:Search` | Member Accounts | Multi-region inventory discovery fails. Unclassified resources cannot be mapped to cost. |
| `C-07` | **Discover Services** | Service enumeration (`ec2:DescribeRegions`, `pricing:DescribeServices`) | Member Account | Enabled AWS services across estate cannot be classified. |
| `C-08` | **Collect Cost (Bulk Exports)** | `s3:GetObject`<br>`s3:ListBucket`<br>`bcm-data-exports:GetExport` | Export S3 Bucket / Management Account | Scheduled CUR 2.0 / FOCUS bulk cost ingestion stalls. Spend reconciliation cannot function. |
| `C-09` | **Collect Cost (Query)** | `ce:GetCostAndUsage`<br>`ce:GetCostAndUsageWithResources` | Management Account | Interactive intraday cost analytics and fallback cost verification fail. |
| `C-10` | **Collect Usage (Metrics)** | `cloudwatch:GetMetricData`<br>`cloudwatch:ListMetrics` | Member Accounts | Operational telemetry unavailable. Compute rightsizing and idle detection disabled. |
| `C-11` | **Collect Pricing (Public)** | Public Price List Offer Files (`pricing:GetProducts`, `pricing:DescribeServices`) | Global (`us-east-1`) | Public list rate card cannot be updated for on-demand comparison. |
| `C-12` | **Collect Pricing (Negotiated)** | `pricing:GetProducts` with custom contract attributes / EDP | Management Account | Enterprise Discount Program (EDP) custom rates cannot be retrieved. |
| `C-13` | **Collect Tags & Cost Categories** | `tag:GetTagKeys`<br>`tag:GetTagValues`<br>`ce:ListCostCategoryDefinitions`<br>`ce:DescribeCostCategoryDefinition` | Member & Management Accounts | Tag governance and rule-based cost category attribution degraded. |
| `C-14` | **Discover Relationships** | `ec2:DescribeInstances`<br>`ec2:DescribeNetworkInterfaces`<br>`ec2:DescribeVolumes` | Member Accounts | Structural bindings (ENI to EC2, EBS to EC2, VPC subnets) fail. Capability declared partial. |
| `C-15` | **Collect Budgets** | `budgets:ViewBudget`<br>`budgets:DescribeBudgets` | Management / Member Accounts | AWS native budget tracking unavailable. Comparison against CloudLens master budgets fails. |
| `C-16` | **Health Status** | `sts:GetCallerIdentity` | Target IAM Role | Heartbeat probe fails; connector transitions to degraded state. |
| `C-17` | **Provider Metadata** | `ec2:DescribeRegions` | Global (`us-east-1`) | AWS partition, region catalog, and service availability metadata cannot load. |
| `C-18` | **Quota & Service Limits** | `servicequotas:GetServiceQuota`<br>`servicequotas:ListServiceQuotas` | Member Accounts | Regional vCPU and service limit headroom monitoring disabled. |
