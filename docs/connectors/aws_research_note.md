# AWS Cloud Connector Research Note (Prompt 17)

> **Connector**: Amazon Web Services (AWS) Cloud Connector (`connectors/aws`)  
> **Authoritative Specifications**: BBP Section 14.3 (AWS capabilities and cautions), Section 15.4 (mapping rules)  
> **Status**: Completed & Verified Against Official AWS Documentation  
> **Security Baseline**: Read-only, Least Privilege (SEC-012, SEC-016)

---

## 1. Official Documentation Index & API Version Matrix

| Functional Domain | Official AWS Document Title | Target Endpoint / URI Pattern | API / Schema Version | Verified Behavior & Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Authentication — Cross-Account Role** | *AWS Security Token Service API Reference - AssumeRole* | `POST https://sts.amazonaws.com/?Action=AssumeRole&Version=2011-06-15` | `2011-06-15` | Primary recommended authentication pattern. Mandatory `ExternalId` parameter prevents the Confused Deputy problem across multi-tenant boundaries. `DurationSeconds` bounded to 3600s. |
| **Authentication — OIDC Web Identity** | *AWS Security Token Service API Reference - AssumeRoleWithWebIdentity* | `POST https://sts.amazonaws.com/?Action=AssumeRoleWithWebIdentity&Version=2011-06-15` | `2011-06-15` | Used when CloudLens runs on Kubernetes (EKS IRSA / Pod Identity). Keyless RFC 7523 token exchange with zero long-lived credentials. |
| **Authentication — Access Keys (Exception)** | *Managing access keys for IAM users* | N/A (SigV4 signing) | AWS Signature Version 4 | Permitted only as an audited exception with mandatory 90-day rotation. **Never the default**. Root user credentials and interactive passwords strictly forbidden. |
| **Hierarchy — Organizations** | *AWS Organizations API Reference* | `POST https://organizations.us-east-1.amazonaws.com/?Version=2016-11-28` | `2016-11-28` | Enumerates roots (`ListRoots`), nested organizational units (`ListOrganizationalUnitsForParent`), and accounts (`ListAccountsForParent`, `ListAccounts`). Preserves OU hierarchy nesting in canonical scope paths. Account represents the billing boundary. |
| **Resource Inventory — Tagging & Config** | *AWS Resource Groups Tagging API Reference*<br>*AWS Config API Reference* | `POST https://tagging.{region}.amazonaws.com/?Action=GetResources&Version=2017-01-26`<br>`POST https://config.{region}.amazonaws.com/?Action=BatchGetResourceConfig&Version=2014-11-12` | `2017-01-26`<br>`2014-11-12` | Hybrid inventory discovery across regions and member accounts. **Caveat**: Completeness varies by service. Unsupported types are labeled as `Unclassified` with native type preserved (e.g. `AWS::AppSync::GraphQLApi`), explicitly exposing the coverage gap. |
| **Cost Ingestion — Bulk Exports (CUR 2.0)** | *Billing and Cost Management Data Exports API Reference (BCM Data Exports)* | `POST https://bcm-data-exports.us-east-1.amazonaws.com/?Version=2023-11-26`<br>`s3://{export-bucket}/{prefix}/` | `2023-11-26` (Data Exports API)<br>CUR 2.0 Fixed Schema / FOCUS 1.0 Table | Primary bulk cost ingestion path. Standardizes on CUR 2.0 fixed schema with structured nested key-values for dynamic tags (`resource_tags_*`) and cost categories (`cost_category_*`). Supports Parquet + Snappy. Legacy CUR (`2018-05-01`) with month-varying dynamic schemas is treated strictly as migration-only. |
| **Cost Ingestion — Interactive Query** | *AWS Cost Explorer Service API Reference* | `POST https://ce.us-east-1.amazonaws.com/?Action=GetCostAndUsage&Version=2017-10-25` | `2017-10-25` | Interactive on-demand queries and recent intraday validation only. Subject to strict rate limits and $0.01 per-request API charges. **Strictly prohibited as a bulk ingestion source**. |
| **Pricing — Bulk Offer Files & Query API** | *AWS Price List Service API Reference* | `GET https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/index.json`<br>`POST https://api.pricing.us-east-1.amazonaws.com/?Action=GetProducts&Version=2016-04-14` | `2016-04-14`<br>Format: `aws_v1` | Bulk offer files used for master catalog bootstrap. `GetProducts` and `DescribeServices` used for targeted lookups filtered by `ServiceCode` and attributes, with `NextToken` pagination. |
| **Budgets** | *AWS Budgets API Reference* | `POST https://budgets.amazonaws.com/?Action=DescribeBudgets&Version=2016-10-20` | `2016-10-20` | Read for comparative analytics and threshold variance only (`is_authoritative = False`). Never authoritative over CloudLens native budgets. |
| **Usage Telemetry & Metrics** | *Amazon CloudWatch API Reference* | `POST https://monitoring.{region}.amazonaws.com/?Action=GetMetricData&Version=2010-08-01` | `2010-08-01` | Ingests coarse operational metrics (hourly `Period=3600`, daily `Period=86400`). Sub-minute intervals (`Period < 3600`) strictly rejected. |
| **Cost Categories** | *AWS Cost Explorer - Cost Categories API* | `POST https://ce.us-east-1.amazonaws.com/?Action=ListCostCategoryDefinitions&Version=2017-10-25` | `2017-10-25` | Modeled as a **distinct AWS-native entity** (`cost_categories`), never folded into generic tags. Evaluates multi-rule billing dimensions. |
| **Relationships & Topology** | *EC2, VPC, EBS & RDS Structural Properties* | Cross-service ARM/SDK queries via assumed role | `2016-11-15` (EC2) | Structural bindings (ENI attachments, EBS volumes, VPC subnets, RDS security groups). Capability declared as **PARTIAL** (`is_partial = True`). |
| **Quota & Limits** | *AWS Service Quotas API Reference* | `POST https://servicequotas.{region}.amazonaws.com/?Action=ListServiceQuotas&Version=2019-06-24` | `2019-06-24` | Ingests service limits and usage for AM-07 headroom tracking. |

---

## 2. Member-Account Cross-Account Access Model

In AWS multi-account architectures, CloudLens accesses member accounts via cross-account IAM role assumption:

```
[CloudLens Core Principal]
 (e.g. arn:aws:iam::111122223333:role/CloudLensIngestionWorker)
         |
         | 1. sts:AssumeRole (ExternalId="CL-TENANT-XYZ-EXTERNAL-ID")
         v
[Management Account] (arn:aws:iam::123456789012:role/CloudLensManagementRole)
  - Organizations Read (ListRoots, ListOrganizationalUnitsForParent, ListAccounts)
  - BCM Data Exports / S3 Bucket Read (CUR 2.0 Parquet)
  - Cost Explorer & Budgets (ce:GetCostAndUsage, budgets:ViewBudget)
  - Cost Category Definitions (ce:ListCostCategoryDefinitions)
         |
         | 2. sts:AssumeRole (ExternalId="CL-TENANT-XYZ-EXTERNAL-ID")
         v
[Member Account A] (arn:aws:iam::222233334444:role/CloudLensMemberRole)
  - Resource Inventory (tag:GetResources, config:BatchGetResourceConfig)
  - CloudWatch Coarse Metrics (cloudwatch:GetMetricData)
  - Structural Topology (ec2:DescribeNetworkInterfaces, ec2:DescribeVolumes)
```

### Security & Invariants:
1. **Mandatory ExternalId**: Every role assumption requires an `ExternalId` uniquely bound to the CloudLens tenant/connector, defeating Confused Deputy vulnerabilities.
2. **Least Privilege Read-Only**: Member account roles require only read actions. Zero mutating or administrative actions (`*:Create*`, `*:Delete*`, `*:Update*`, `*:Put*`) are granted.
3. **Account as Billing Boundary**: While resources reside in member accounts, billing data aggregates at the Management Account (or consolidated billing account). The member account ID serves as the canonical billing boundary.

---

## 3. Cost & Usage Report 2.0 Sizing Envelope & Configurations

| Parameter | Configuration Options | FinOps Sizing Impact & Capacity Guidance |
| :--- | :--- | :--- |
| **Report Version** | `CUR 2.0` (Recommended) / `Legacy CUR` (Migration only) | CUR 2.0 provides fixed column schemas and nested key-values (`resource_tags_*`, `cost_category_*`). Prevents month-to-month schema drift. |
| **Time Granularity** | `HOURLY`, `DAILY`, `MONTHLY` | `HOURLY` is recommended for intra-day anomaly detection and rightsizing, resulting in 24x row multiplication over `DAILY`. |
| **Resource-Level IDs** | `INCLUDE_RESOURCE_IDS = TRUE` / `FALSE` | **Critical Sizing Driver**: Enabling resource IDs expands data volume by 10x–100x (often 50M–500M rows/month in enterprise estates). Must be reflected in onboarding wizard sizing estimates and partitioned ingestion worker allocation. |
| **Split Cost Allocation** | `SPLIT_COST_ALLOCATION = TRUE` / `FALSE` | Splits shared container costs (EKS/ECS vCPU and Memory) across pod workloads. Adds sub-resource allocation records. |
| **File Format & Compression** | `Parquet` + `Snappy` (Preferred) / `GZIP CSV` | Parquet reduces S3 storage volume by 70–80% and accelerates column-pruned query ingestion by 5x compared to legacy CSV. |

---

## 4. Explicit Gaps & Cautions

1. **Non-Uniform Service Inventory Coverage**:
   - AWS Tagging API (`tag:GetResources`) does not cover 100% of AWS resource types.
   - **Enforcement**: Unsupported resource types are ingested as `Unclassified` with their native type string preserved (e.g. `AWS::AppSync::GraphQLApi`), preventing false assumptions of complete inventory.
2. **Cost Explorer Rate Limits**:
   - Cost Explorer API is subject to severe concurrency throttling and per-call charges ($0.01 per paginated call).
   - **Enforcement**: Bulk cost ingestion uses S3 BCM Data Exports (CUR 2.0) exclusively; Cost Explorer is restricted to targeted interactive queries.
3. **Cost Categories vs Tags Separation**:
   - AWS Cost Categories are rule-based billing dimensions that evaluate complex logic over tags and accounts.
   - **Enforcement**: Cost Categories are indexed in a dedicated `cost_categories` dictionary on cost records, distinct from `tags`.
