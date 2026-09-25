# Reconciled Pricing Dimension Catalogue (29 Dimensions)

> **Closes Defect D-06** — Harmonizes Master Brief Section 00.7 (29 dimensions), BBP Section 18.2 (21 condensed rows), and Prompt 07 (AM-14).

## 1. Reconciliation Analysis

The Master Brief (Section 00.7) listed **29 pricing items**, whereas BBP Table 18-2 tabulated **21 rows** due to condensation:
- BBP row 1 collapsed `per-second`, `per-minute`, and `per-hour` into a single line.
- BBP row 13 merged `reservation` and `commitment` without discrete spend-based `savings plan` tracking.
- BBP used high-level category groupings (`Storage consumption`, `Compute consumption`) rather than granular units: `per-TB`, `per-CPU`, `per-vCPU-hour`, `per-node-hour`.
- BBP omitted message-based (`per-message`) and operation-based (`per-operation`) units.
- Three items in the brief (`sustained-use pricing`, `promotional pricing`, `region-specific pricing`) function as **Pricing Qualifiers / Modifiers** rather than standalone dimensional metric units.

### Authoritative Reconciled Classification (Exact Count: 29)
- **Category A: Consumption / Unit Dimensions (18)**: Rate × Quantity consumption units.
- **Category B: Structural Pricing Models (8)**: Contractual, commitment, tiered, and bounded charge structures.
- **Category C: Pricing Qualifiers & Modifiers (3)**: Geographic, duration, and promotional curve adjustments.

## 2. Reconciled Dimension Catalogue

| Code | Dimension Name | Category | Canonical Unit | Aggregation | Default Threshold Basis | Example Services Across 4 Providers | Reconciliation Notes |
|:---|:---|:---|:---|:---:|:---|:---|:---|
| **DIM-01** | **Per-second** | Consumption Unit | `seconds` | sum | Runtime seconds / hours | AWS Lambda, GCP Cloud Run, Azure Container Instances (per-sec duration) | BBP Section 18.2 row 1 merged second/minute/hour; reconciled to discrete atomic unit. |
| **DIM-02** | **Per-minute** | Consumption Unit | `minutes` | sum | Runtime minutes / hours | Azure Container Apps, Amazon Connect voice minutes, Twilio telephony | Added from Master Brief; discrete unit for sub-hourly services. |
| **DIM-03** | **Per-hour** | Consumption Unit | `hours` | sum | Runtime hours | Amazon EC2, Azure Virtual Machines, GCP Compute Engine, OCI Compute | Standard compute and instance runtime measurement unit. |
| **DIM-04** | **Per-instance** | Consumption Unit | `instance-hours / instance-months` | sum | Instance count | AWS NAT Gateway, Azure Bastion, GCP Cloud NAT, OCI Load Balancer | Fixed provisioned appliance / managed gateway unit. |
| **DIM-05** | **Per-request** | Consumption Unit | `requests` | sum | Request volume | Amazon S3 GET/PUT, Azure Blob Operations, Google Cloud Storage operations | Object storage and serverless invocation requests. |
| **DIM-06** | **Per-API-call** | Consumption Unit | `calls` | sum | Call volume | Amazon API Gateway, Azure API Management, Google Cloud Endpoints | Managed API calls and cognitive/AI invocation endpoints. |
| **DIM-07** | **Per-transaction** | Consumption Unit | `transactions` | sum | Transaction volume | Amazon Aurora Serverless ACU, Cosmos DB RU/s, Google Cloud Spanner | Database and transaction processing operations. |
| **DIM-08** | **Per-message** | Consumption Unit | `messages` | sum | Message volume | Amazon SQS, Azure Service Bus, GCP Pub/Sub, OCI Streaming | Added from Master Brief; event and message ingestion units. |
| **DIM-09** | **Per-operation** | Consumption Unit | `operations` | sum | Operation volume | AWS KMS crypto operations, Azure Key Vault ops, DynamoDB Read/Write Units | Added from Master Brief; cryptographic and granular table operations. |
| **DIM-10** | **Per-GB** | Consumption Unit | `GB` | sum | Volume / Throughput | AWS Transit Gateway data processed, Azure Event Hubs ingress, Cloud NAT data | Data processed / transient data volume. |
| **DIM-11** | **Per-GB-month** | Consumption Unit | `GB-month` | last | Capacity (Storage) | Amazon EBS, Azure Managed Disks, Google Persistent Disk, OCI Block Volume | Standard storage persistence over time. |
| **DIM-12** | **Per-TB** | Consumption Unit | `TB / TB-month` | sum | Capacity / Query Volume | Google BigQuery data scanned, AWS Athena TB scanned, Snowflake storage | Added from Master Brief; high-volume analytical query and petabyte storage unit. |
| **DIM-13** | **Per-data-transfer-unit** | Consumption Unit | `GB / TB egress` | sum | Transfer volume | AWS Internet Egress, Azure Egress, GCP Inter-region Data Transfer, OCI Egress | Cross-region, cross-AZ, and internet outbound data movement. |
| **DIM-14** | **Per-CPU** | Consumption Unit | `cores / OCPUs` | sum | Core count | OCI OCPU, Bare Metal Cores, VMware Cloud on AWS, Dedicated Hosts | Added from Master Brief; physical and socket-level processor allocations. |
| **DIM-15** | **Per-vCPU-hour** | Consumption Unit | `vCPU-hours` | sum | Consumption units | AWS Fargate vCPU-hours, Azure Container Instances vCPU-hours, Cloud Run vCPU-seconds | Added from Master Brief; serverless and containerized virtual CPU execution. |
| **DIM-16** | **Per-node-hour** | Consumption Unit | `node-hours` | sum | Node count / hours | Amazon EKS managed nodes, Azure AKS node pools, Google GKE Standard, Amazon Redshift | Added from Master Brief; managed cluster worker node runtime. |
| **DIM-17** | **Per-user** | Consumption Unit | `users / seats` | last | Seat count | Amazon QuickSight Authors, Azure DevOps Basic, Microsoft 365, Power BI Pro | User-based seat licensing. |
| **DIM-18** | **Per-licence** | Consumption Unit | `licences / cores` | last | Licence count | Red Hat Enterprise Linux on Cloud, SUSE Linux, SQL Server BYOL / per-core | Software licensing and bring-your-own-licence models. |
| **DIM-19** | **Subscription** | Structural Pricing Model | `period fee` | sum | Presence and renewal | AWS Enterprise Support, Azure Support Plans, Marketplace SaaS monthly subscriptions | Fixed recurring monthly or annual platform fees. |
| **DIM-20** | **Commitment** | Structural Pricing Model | `committed units / term` | last | Coverage and utilisation | AWS Compute Savings Plans, Azure Savings Plans, Google Committed Use Contracts | Contractual minimum spend or capacity agreements. |
| **DIM-21** | **Reservation** | Structural Pricing Model | `reserved instances / term` | last | Coverage and utilisation | AWS Reserved Instances (1-yr/3-yr), Azure Reserved VM Instances, OCI Reserved Capacity | Pre-purchased capacity reservations. |
| **DIM-22** | **Savings plan** | Structural Pricing Model | `hourly spend commitment ($/hr)` | last | Spend utilisation | AWS EC2 Instance Savings Plans, AWS SageMaker Savings Plans, Azure Savings Plan for Compute | Spend-based flexible compute commitment. |
| **DIM-23** | **Minimum commitment** | Structural Pricing Model | `floor amount` | max | Under-consumption risk | Enterprise Agreement annual minimums, Snowflake annual capacity commits | Contractual floor spend requirements. |
| **DIM-24** | **Tiered pricing** | Structural Pricing Model | `tiered units with tier breaks` | sum | Tier boundary proximity | AWS S3 Standard Storage (First 50 TB, Next 450 TB, Over 500 TB) | Graduated rate scales where incremental usage falls into cheaper price brackets. |
| **DIM-25** | **Volume pricing** | Structural Pricing Model | `volume discount bracket` | sum | Discount realisation | CloudFront high-volume traffic tiers, Twilio volume discounts | All-units discount triggered when total usage exceeds volume thresholds. |
| **DIM-26** | **Free tier** | Structural Pricing Model | `allowance units` | sum | Allowance exhaustion | AWS Always Free (Lambda 1M req), Azure Free Services (750 hrs B1s), GCP Free Tier, OCI Always Free | Included monthly allowance before billable rates activate. |
| **DIM-27** | **Sustained-use pricing** | Pricing Qualifier / Modifier | `percentage modifier` | average | Runtime discount curve | Google Cloud Compute Engine Sustained Use Discounts (SUD) | Automated discount applied dynamically as monthly VM running percentage increases. |
| **DIM-28** | **Promotional pricing** | Pricing Qualifier / Modifier | `promotional rate / credit offset` | sum | Promotion expiry / credit depletion | New service trial periods, promotional SKU discounts, AWS Activate credits | Time-limited discounted rates or vendor credit mechanisms. |
| **DIM-29** | **Region-specific pricing** | Pricing Qualifier / Modifier | `regional multiplier / rate card` | last | Regional variance | AWS us-east-1 vs ap-south-1 VM pricing, Azure East US vs West Europe rate variance | Geographic rate variance for identical SKUs across provider datacenter regions. |

## 3. Consistency Guarantee Across Artifacts

1. **Requirement Register**: 29 dimensions referenced in PR-016 and catalogue definitions.
2. **BBP Section 18.2**: Replaced 21-row table with this 29-item taxonomy in BBP v1.1 (Prompt 62).
3. **Prompt 07 (Catalogues)**: Seeds exactly these 29 catalogue entries (`DIM-01` to `DIM-29`) under AM-14.
