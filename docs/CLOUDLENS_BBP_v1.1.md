# CloudLens Business Blueprint Specification (BBP v1.1)

> **Document Class**: Authoritative Business Blueprint & System Specification v1.1  
> **Release Authority**: Stage 17 Master Release, Prompt 62 (Closing Defects D-12, D-13, D-14)  
> **Supersedes**: BBP v1.0, Addenda A & B, and interim working drafts  
> **Status**: APPROVED, RECONCILED, AND AUTHORITATIVE  

---

## 1. Executive Summary & Version 1.1 Issuance

CloudLens is an enterprise multi-cloud FinOps governance platform providing single-pane-of-glass visibility, cost attribution, budget control, and remediation across **Amazon Web Services (AWS)**, **Microsoft Azure**, **Google Cloud Platform (GCP)**, and **Oracle Cloud Infrastructure (OCI)**.

This version 1.1 issuance reconciles all nineteen architectural amendments (**AM-01** through **AM-19**), folds all twelve domain addenda into the canonical specification, and corrects five stale counts present in earlier draft versions of the blueprint.

### 1.1 Core Metric Reconciliation (Closing Defects D-12, D-13, D-14)
The following five core counts have been corrected across the specification body, tables, and acceptance criteria:
1. **User Interface Screens**: Exactly **27 screens** in inventory (Section 31.3), expanded from 20 to incorporate dedicated screens for Demo Mode, Quota Management, Pre-Deployment Gates, Remediation Kanban, Showback Statements, Bulk Import Wizard, and Analytical Extract Manifests.
2. **Administrative Functions**: Exactly **29 administrative functions** (Section 32), expanded from 24 to include master data publishing, workflow delegation, import reversal, quota overrides, and break-glass auditing.
3. **Connector Capabilities**: Exactly **18 connector capabilities** (Section 26.1), incorporating the dedicated Service Quotas & Limit Discovery capability across all 4 cloud providers.
4. **Threshold Bases**: Exactly **11 threshold bases** (Section 21.3), adding multi-period compound consumption burn rate to the standard absolute, percentage, and forecast variance bases.
5. **Monitoring Types**: Exactly **15 monitoring types** (Section 19.1), adding Cloud Quota Headroom Saturation to compute, storage, egress, and database telemetry monitoring dimensions.

---

## 2. Master Requirement Register & Identifier Taxonomy

BBP v1.1 establishes thirteen authoritative requirement prefixes (**Prompt 00R Register**), cataloguing exactly 458 traceable requirements:

| Prefix | Domain Description | Count | Priority | Verification Tier |
|:---|:---|:---:|:---:|:---|
| **BR** | Business Requirements | 18 | High | Level 13 (End-to-End BP), Level 17 (Acceptance) |
| **FR** | Functional Requirements (Core) | 89 | Must | Level 02, Level 05, Level 09, Level 12 |
| **PR** | Pricing Requirements | 20 | Must | Level 01, Level 07, Level 10 |
| **CST** | Cost Calculation & Reconciliation | 32 | Must | Level 07 (100% Hand-Calculated Fixtures) |
| **USE** | Usage & Telemetry Metric Collection | 10 | Must | Level 06, Level 11, Level 13 |
| **RUN** | Runtime & Schedule Adherence | 10 | Should | Level 06, Level 13 (BP-15), Level 16 |
| **DEP** | Dependency & Topology Mapping | 18 | Should | Level 12, Level 13 (BP-16), Level 19 |
| **CON** | Multi-Cloud Connectors & Conformance | 32 | Must | Level 04 (Dual-Mode Connector Kit) |
| **API** | REST API Contracts & Envelope Standard | 66 | Must | Level 03 (OpenAPI Drift & Envelopes) |
| **SEC** | Security, RBAC & Isolation Controls | 30 | Critical | Level 08, Level 09, Level 17 |
| **NFR** | Non-Functional Performance & Scalability | 50 | Must | Level 10, Level 11, Level 14, Level 15 |
| **DR** | Disaster Recovery & Business Continuity | 7 | Critical | Level 14 (Automated DR Exercise) |
| **AC** | Quality Gate Acceptance Criteria | 76 | Must | Level 17 (Quality Gates), Level 18-20, Mandates |

---

## 3. Incorporation of Amendments (AM-01 through AM-19)

- **AM-01 (Master Data Authority)**: Centralized reference data package (`masterdata/`) governing all catalogues, dimensions, units, and roles.
- **AM-02 (Unit Conversions)**: Pure Decimal base unit conversion with banker's rounding (`ROUND_HALF_EVEN`) across GiB, TiB, vCPU-hours, and GB-seconds.
- **AM-03 (Currency Handling)**: Multi-currency conversion supporting ISO 4217, effective-dated rate cards, and rate provider disclosure.
- **AM-04 (FOCUS Normalisation)**: Mapping disparate billing schemas (AWS CUR 2.0, Azure Exports, GCP BigQuery, OCI CSV) to FinOps FOCUS 1.0 standard.
- **AM-05 (Schedule Adherence)**: Evaluating non-production running hours against declared runtime schedules, flagging out-of-hours waste.
- **AM-06 (Shared Cost Apportionment)**: Apportioning unallocated infrastructure, common services, and support charges across consumer scopes with visible basis.
- **AM-07 (Ingestion Latency & Lag)**: Dynamic lag compensation handling 24-72h cloud billing delay without false budget alerts.
- **AM-08 (Tagging Policy Governance)**: Enforcing mandatory tags (Owner, Environment, Application, Cost Centre) with non-compliant resource isolation.
- **AM-09 (Financial Detail Redaction)**: RBAC-driven redaction of pricing rates, markups, and unallocated amounts for non-financial personas.
- **AM-10 (Bi-Temporal Restatement)**: Maintaining `transaction_time` and `valid_time` to non-destructively restate prior period invoices without mutating history.
- **AM-11 (Anomaly Threshold Bands)**: Multi-band threshold evaluation (`NOMINAL`, `WARNING`, `CRITICAL`, `BREACHED`) with contextual explanation panels.
- **AM-12 (Approval Authority Matrix)**: Master-data routing of financial approvals by scope, environment, and monetary band (never named individuals).
- **AM-13 (4-State Measure Nulls)**: Explicit measure state typing (`NO_COST`, `NO_DATA`, `NOT_APPLICABLE`, `NOT_SUPPORTED`) to eliminate bare SQL nulls.
- **AM-14 (Read-Only IAM Privileges)**: Strict principle of least privilege; connectors require only read/list permissions; zero mutate/write rights accepted.
- **AM-15 (Open Analytical Extracts)**: Standardized Parquet/JSON-L extracts with partition manifests, cryptographic SHA-256 digests, and monotonic watermarks.
- **AM-16 (Automated Remediation Verification)**: Closed-loop task verification re-testing underlying conditions before closure; persistent faults reopen to `OPEN`.
- **AM-17 (Pre-Deployment Provisioning Gates)**: Evaluating proposed cloud infrastructure against budget, quota headroom, and dependency costs prior to creation.
- **AM-18 (Quota Headroom & Lead-Time Alerting)**: Proactive quota tracking projecting exhaustion dates adjusted for provider lead time and safety buffers.
- **AM-19 (Generic Bulk Import & Rollback)**: Complete dry-run validation reporting created, updated, skipped, and rejected rows with time-boxed atomic rollback.

---

## 4. Extended Domain Modules (Addenda A & B)

### 4.1 Master Data Management and Governance (Prompt 45)
Establishes master data as the authoritative system of record. Every system enumeration bridges to registered master files. Master data changes follow effective dating (`effective_from`, `effective_to`), enabling point-in-time state reconstruction for retroactive audits.

### 4.2 Mock Data and Demo Mode (Prompt 47 / Mandate M3)
Provides a 100% offline synthetic estate generator supporting 7 realistic FinOps scenarios:
1. Month-End Close & YoY Trend Review
2. Budget Overrun & Root-Cause Allocation
3. Unexpected Cost Surge & Anomaly Detection
4. Free-Tier Allowance Exhaustion Warning
5. Cost-Aware Provisioning Gate Review
6. Quota Headroom Saturation & Automated Ticket
7. BU Showback Statement & Line-Item Dispute

*Hard Safety Interlocks*:
- Demo Mode cannot be enabled on a tenant with live connectors.
- Live connectors cannot be attached to a Demo Mode tenant.
- Every response carries `X-CloudLens-Demo-Mode: true`.
- Every export carries `DEMONSTRATION SIMULATED DATA — NOT FOR OPERATIONAL USE`.

### 4.3 Workflow and Approval (Prompt 50)
A unified state engine supporting serial and parallel multi-tier approval chains. Approver resolution is master-data driven across roles, ownership hierarchies, and scope delegates. Every workflow execution supports timeout escalation and working-hours SLA tracking.

### 4.4 Remediation and Accountability (Prompt 51)
Operationalizes FinOps recommendations into tracked remediation tasks spanning 11 lifecycle states:
`DRAFT` $\rightarrow$ `OPEN` $\rightarrow$ `ASSIGNED` $\rightarrow$ `IN_PROGRESS` $\rightarrow$ `AWAITING_VERIFICATION` $\rightarrow$ `RESOLVED` $\rightarrow$ `VERIFIED` $\rightarrow$ `CLOSED` (with `DEFERRED`, `REJECTED`, `DUPLICATE` branches).
*Mandatory Rule*: Tasks are never closed on assignee's word alone; automated verification probes live telemetry. Persistent problems automatically reopen to `OPEN`.

### 4.5 Showback, Chargeback, and Statements (Prompt 52)
Generates monthly accounting packs across Business Units, Cost Centres, and Applications. Displays direct costs, shared apportionments, budget variance, and largest movements. Supports formal line-item dispute workflows and recipient acceptance tracking. MVP is strictly SHOWBACK (internal management information); chargeback ERP posting is prepared behind a Phase 2 feature flag.

### 4.6 Bulk Import and Data Onboarding (Prompt 53)
Enables bulk onboarding of cost centres, business units, budgets, and tag mappings via CSV/JSON. Mandates complete dry-run validation before mutation and provides a time-boxed atomic rollback mechanism with dependent-change conflict guards.

### 4.7 Quota Management (Prompt 54)
Monitors multi-cloud service quotas (e.g. AWS Service Quotas, Azure Subscriptions Limits, GCP Quotas). Computes daily consumption velocity, projects exhaustion dates, and accounts for provider lead time and safety margins to trigger proactive increase requests before capacity limits are hit.

### 4.8 Pre-Deployment Provisioning Gates (Prompt 55)
Provides cost estimation for prospective cloud deployments. Computes 4-dimensional budget impact (remaining budget, consumption %, projected utilisation, forecast effect) and checks quota and dependency costs. Governed by master gate triggers defaulting to `NOTIFY_ONLY` (opt-in approval gate).

### 4.9 Analytical Extract and Semantic Layer (Prompt 56)
Exports governed FinOps analytical data sets into open Parquet/JSON formats partitioned by tenant and billing period. Includes complete partition restatement capabilities, SHA-256 manifest signing, and strict 4-state null discipline.

### 4.10 Budget Planning and Scenario Modelling (Prompt 57)
Supports future-period budget planning cycles: bottom-up submission from scope leads, prior-year basis calculation, what-if scenario modelling, and executive top-down target setting reporting the gap between submissions and financial targets.

### 4.11 Commitment Renewal and Coverage Management (Prompt 58)
Tracks expiry dates and utilization for AWS Savings Plans / Reserved Instances, Azure Reservations, GCP CUDs, and OCI Commitments. Automatically calculates coverage vs utilization trends, alerts inside renewal decision windows, and generates evidence-based renewal recommendations (renew, upsize, downsize, lapse).

### 4.12 Resource Lifecycle and Decommissioning (Prompt 59)
Governs resource retirement through a formal lifecycle: `requested` $\rightarrow$ `provisioned` $\rightarrow$ `active` $\rightarrow$ `idle candidate` $\rightarrow$ `decommission proposed` $\rightarrow$ `decommission approved` $\rightarrow$ `stopped` $\rightarrow$ `pending deletion` $\rightarrow$ `deleted` $\rightarrow$ `retired`.
*Mandatory Rule*: Decommissioning proposals perform a cross-team dependency impact check; any affected downstream service requires explicit owner sign-off prior to deletion approval.

---

## 5. Non-Functional & Quality Standards

- **Availability**: 99.9% uptime with zero-downtime blue-green rolling upgrade path.
- **Mathematical Integrity**: 100% `Decimal` arithmetic with zero floating-point contamination. Cent-for-cent invoice reconciliation.
- **Security Posture**: Read-only cloud credentials (zero write permissions), OIDC token revocation, AES-256 encryption at rest, TLS 1.3 in transit.
- **Traceability**: All 458 requirements verified across 20 automated test levels and corporate mandates.
