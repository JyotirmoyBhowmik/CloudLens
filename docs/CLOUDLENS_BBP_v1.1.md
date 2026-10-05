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

## 33. Role-Based Access Control (RBAC) & Scope Matrix (Prompt R-ROLES)

### 33.1 The Canonical BBP Nine System Roles
Access authority within CloudLens is partitioned across exactly nine built-in system roles sourced from authoritative master data (`masterdata/seeds/role.json`) and synchronized via `EnumerationBridge`:

1. **SUPER_ADMIN** (`Platform Superuser`): Unrestricted platform-wide administrative authority across all tenants. Holds `platform.observe`, `platform.operate`, and `platform.act_as`. Authorized to assume tenant context via explicit audited act-as workflows.
2. **PLATFORM_ADMIN** (`Tenant Administrator`): Full administrative and configuration authority within the bounded tenant. Holds `platform.observe` and `platform.operate` for own tenant resources.
3. **CLOUD_ADMINISTRATOR** (`Cloud Infrastructure Administrator`): Ingestion, connector management, inventory discovery, and technical synchronization within assigned scopes.
4. **FINOPS_ADMINISTRATOR** (`FinOps Lead / Administrator`): Budget configuration, rate card management, governance override execution, and policy evaluation within tenant boundaries.
5. **FINANCE_USER** (`FinOps Analyst / Financial User`): Full financial analytics, unredacted unit rates, invoice drill-through, and export capabilities within assigned scopes.
6. **IT_OPERATIONS_USER** (`IT Operations / Engineering User`): Infrastructure monitoring, aggregated cost totals, and inventory view within assigned scopes. Financial rates and pricing margins are strictly redacted.
7. **APPLICATION_OWNER** (`Workload / Application Owner`): Inventory, budget consumption tracking, and threshold metrics scoped specifically to owned applications and projects.
8. **READ_ONLY_USER** (`Executive / Read-Only Viewer`): Read-only dashboards and high-level cost totals without mutation or export rights.
9. **AUDITOR** (`Security & Compliance Auditor`): Read-only compliance inspection, audit trail verification, governance policy inspection, and aggregated Control Tower observation (`platform.observe`) across all tenants. Strictly prohibited from operational mutations (`platform.operate` -> 403 Forbidden).

### 33.2 Permission Catalogue & Platform Capabilities (Table 33-2)
The permission catalogue is defined as authoritative master data (`masterdata/seeds/permission.json`), encompassing the 17 core BBP capabilities plus 3 platform-level capabilities:

| Capability Code | Description | Role Assignments |
|:---|:---|:---|
| `platform.observe` | Read-only Control Tower visibility across all tenants and aggregated fleet metrics. | `SUPER_ADMIN`, `PLATFORM_ADMIN`, `AUDITOR` |
| `platform.operate` | Control Tower administrative mutations, connector triggers, and governance actions. | `SUPER_ADMIN`, `PLATFORM_ADMIN` (Step-up MFA required) |
| `platform.act_as` | Assumption of scoped tenant identity with explicit justification (>= 20 chars). | `SUPER_ADMIN` only |
| `cost:totals:read` | Read high-level aggregated spend and budget totals. | All 9 Roles |
| `financial:detail:read` | Access unredacted unit rates, contracted pricing, and drill-through charge lines. | `SUPER_ADMIN`, `PLATFORM_ADMIN`, `FINOPS_ADMINISTRATOR`, `FINANCE_USER` |
| `billing:read` | Read billing facts, focus normalisations, and statements. | All except `AUDITOR` |
| `billing:export` | Export billing data sets and accounting packs. | `SUPER_ADMIN`, `PLATFORM_ADMIN`, `FINOPS_ADMINISTRATOR`, `FINANCE_USER` |
| `inventory:read` | Read discovered cloud resources and dependency topologies. | All 9 Roles |
| `inventory:write` | Mutate inventory metadata, tags, and lifecycle states. | `SUPER_ADMIN`, `PLATFORM_ADMIN`, `CLOUD_ADMINISTRATOR` |
| `budgets:read` | View budget allocations, consumption velocity, and forecasts. | All except `AUDITOR`, `IT_OPERATIONS_USER` |
| `budgets:write` | Create and adjust budget thresholds and allocation rules. | `SUPER_ADMIN`, `PLATFORM_ADMIN`, `FINOPS_ADMINISTRATOR` |
| `budgets:approve` | Approve formal budget plan submissions and adjustments. | `SUPER_ADMIN`, `PLATFORM_ADMIN`, `FINOPS_ADMINISTRATOR` |
| `overrides:apply` | Enforce governed operational overrides with mandatory 8 attributes. | `SUPER_ADMIN`, `PLATFORM_ADMIN`, `FINOPS_ADMINISTRATOR` |
| `audit:read` | Read immutable cryptographic audit logs and event registers. | `SUPER_ADMIN`, `PLATFORM_ADMIN`, `AUDITOR` |
| `audit:export` | Export audit trail records for regulatory compliance. | `SUPER_ADMIN`, `PLATFORM_ADMIN`, `AUDITOR` |
| `governance:read` | Inspect policies, anomaly rules, and compliance status. | `SUPER_ADMIN`, `PLATFORM_ADMIN`, `CLOUD_ADMINISTRATOR`, `FINOPS_ADMINISTRATOR`, `AUDITOR` |
| `governance:write` | Author and mutate governance policies and automated actions. | `SUPER_ADMIN`, `PLATFORM_ADMIN`, `FINOPS_ADMINISTRATOR` |
| `connectors:read` | View connector status, ingestion telemetry, and sync health. | `SUPER_ADMIN`, `PLATFORM_ADMIN`, `CLOUD_ADMINISTRATOR` |
| `connectors:write` | Register, update, and configure cloud provider connectors. | `SUPER_ADMIN`, `PLATFORM_ADMIN`, `CLOUD_ADMINISTRATOR` |
| `connectors:sync` | Trigger manual or on-demand connector ingestion syncs. | `SUPER_ADMIN`, `PLATFORM_ADMIN`, `CLOUD_ADMINISTRATOR` |

### 33.3 Eight-Dimensional Scoping Architecture & Precedence Rules
Scope evaluation enforces declarative grants across all 8 canonical dimensions:
1. **Cloud Provider**: `aws`, `azure`, `gcp`, `oci`, or wildcard `*`.
2. **Account / Billing Boundary**: AWS account ID, Azure subscription ID, GCP project, OCI compartment.
3. **Hierarchy Subtree**: Organizational hierarchy path with recursive cascading or leaf-only targeting.
4. **Project / Application**: Workload tags and application identifiers.
5. **Cost Centre & Business Unit**: Financial allocation dimensions.
6. **Financial Sensitivity**: `FULL_FINANCIAL_DETAIL`, `COST_TOTALS_ONLY`, `NON_FINANCIAL`.
7. **Administrative Boundary**: Explicit flag restricting administrative and configuration endpoints.
8. **Resource-Level Exceptions**: Granular inclusion / exclusion overrides.

*Precedence Rules*:
- **Strict Deny-Over-Allow**: Any matching `DENY` grant defeats all overlapping `ALLOW` grants.
- **Default Deny**: In the absence of an explicit matching grant or superuser status, access is denied.
- **Disclosure Rule on Aggregates**: When scope filtering suppresses out-of-scope resources, response headers and payloads report `is_filtered=True`, `hidden_count`, and disclosure notices. Silent filtering is strictly forbidden.
- **Unmapped IdP Protection**: Users authenticating via SSO/OIDC/SAML whose identity groups do not match any mapped role receive zero platform access, trigger an immediate security alert (`UNMAPPED_ROLE_ACCESS_DENIED`), and log an audit event. No default fallback role is ever assigned.

---

## 34. Non-Functional & Quality Standards

- **Availability**: 99.9% uptime with zero-downtime blue-green rolling upgrade path.
- **Mathematical Integrity**: 100% `Decimal` arithmetic with zero floating-point contamination. Cent-for-cent invoice reconciliation.
- **Security Posture**: Read-only cloud credentials (zero write permissions), OIDC token revocation, AES-256 encryption at rest, TLS 1.3 in transit.
- **Traceability**: All 458 requirements verified across 20 automated test levels and corporate mandates.

---

## 35. Enterprise Observability Stack & Telemetry Infrastructure (Prompt R-OBS)

### 35.1 Architecture & Components
The CloudLens observability infrastructure is completely open source, vendor-neutral, and containerized within `ops/docker-compose.yml`:
1. **Metrics Collection & Storage**: Prometheus (`v2.51.0`) scrapes API endpoints and dedicated infrastructure exporters every 15s.
2. **Exporters**: Dedicated exporters provide low-level operational signals:
   - `postgres-exporter` (`v0.15.0`) on port 9187: Database connections, deadlocks, transaction throughput, replication lag.
   - `redis-exporter` (`v1.58.0`) on port 9121: Cache memory utilization, evictions, connected clients, queue depth.
   - `celery-exporter` (`latest`) on port 9808: Worker task latency, runtime, concurrency saturation.
3. **Log Aggregation & Redaction**: Loki (`v2.9.4`) with Promtail (`v2.9.4`). Structured JSON logs carry `tenant`, `service`, `correlation_id`, and `level` labels. All log streams enforce pre-shipping regex and PII redaction (Prompt 03 engine) ensuring secrets (AWS keys, tokens, passwords) never hit Loki storage.
4. **Distributed Tracing**: OpenTelemetry auto-instrumentation for FastAPI, SQLAlchemy, Celery, and HTTPX exporting via OTLP (`v0.96.0` collector) to Grafana Tempo (`v2.4.1`). A single `cloudlens.correlation_id` binds the end-to-end trace from HTTP ingress down to DB queries and asynchronous Celery tasks.
5. **Visualization & SSO**: Grafana (`10.4.0`) pre-provisioned with 10 operational and governance dashboards. Authentication is secured via Keycloak OIDC SSO with zero local administrator passwords stored in files; RBAC roles map dynamically (`SUPER_ADMIN` / `PLATFORM_ADMIN` -> Admin/Editor, `AUDITOR` -> Viewer).
6. **Alerting & Dead-Man's Switch**: Alertmanager (`v0.27.0`) executes 14 versioned operational threshold rules, routing critical alerts to `admin@jyotirmoyb.com` via Mailpit SMTP relay. A persistent `Watchdog` alert acts as a dead-man's switch to guarantee monitoring pipeline liveness.

---

## 36. Enterprise Platform Improvements & Governance Additions (Prompt R-FEAT)

### 36.1 Authoritative Improvement Register & Master Data Anchors
In accordance with Prompt R-FEAT and Mandates M1/M2/M3, ten production platform enhancements have been integrated into the canonical architecture, governed by master data seed `masterdata/seeds/improvement_features.json` and synchronized via `SYSTEM_MASTER_REGISTRY`:

| Feature Code | Name | Architecture & Control Tower Integration | Verification Asset |
|:---|:---|:---|:---|
| **IMP-01** | Maintenance Mode | Tenant & global read-only flag. Blocks mutating REST operations with RFC 7807 503 Problem Details (`Platform Maintenance Mode`), pauses Celery Beat scheduling, displays global UI banner (`MaintenanceModeBanner.tsx`), audited via `MAINTENANCE_MODE_TOGGLED`. | `domain/maintenance/`, `api/cloudlens_api/conventions/middleware.py`, `tests/improvements/` |
| **IMP-02** | Session Management | User session inventory, granular single-session and global user session revocation (`revoke_user_sessions`), master-data driven idle (1800s) and absolute (43200s) timeouts. Control Tower action `revoke-user-sessions`. | `domain/identity/`, `api/cloudlens_api/routes/auth.py`, `tests/improvements/` |
| **IMP-03** | Audit Export & SIEM Forwarding | Signed daily audit log bundle export to MinIO, standard ArcSight Common Event Format (CEF 0) / syslog forwarding to corporate SIEM, cryptographic SHA-256 hash-chain verification tool. | `domain/audit/`, `scripts/verify_audit_chain.py`, `tests/improvements/` |
| **IMP-04** | Backup / Restore Self-Service | Control Tower `backups` panel displays last backup timestamp and last automated restore verification. Step-up action `run-restore-test` executes restore into isolated ephemeral schema and verifies 0.0 variance ratio. | `domain/control_tower/`, `tests/improvements/` |
| **IMP-05** | Synthetic Journey Monitor | Scheduled Celery task (`cloudlens.tasks.run_synthetic_journey_monitor`) executes 4-step user journey (`READ_ONLY` role on `tenant-synthetic`): auth, dashboard summary, cost query, report generation. Emits duration and outcome Prometheus metrics. | `domain/synthetic/`, `domain/observability/metrics.py`, `tests/improvements/` |
| **IMP-06** | In-App Release & Change Log | `/about` web screen and `/api/v1/about` REST endpoint exposing authoritative version, full Git commit SHA, Alembic migration head, environment, and release notes. Control Tower `release` panel reads unified service. | `domain/release/`, `web/src/pages/AboutPage.tsx`, `api/cloudlens_api/routes/about.py`, `tests/improvements/` |
| **IMP-07** | Rate-Limit & Abuse Dashboard | Centralized tracking of HTTP 429 rate limit breaches, top client IPs, caller identities, and authentication failure spikes. Enforces progressive IP/account lockout after 5 consecutive failures. Control Tower endpoint `/api/v1/control-tower/abuse`. | `domain/abuse/`, `api/cloudlens_api/routes/control_tower.py`, `tests/improvements/` |
| **IMP-08** | Data Freshness SLA Report | Weekly scheduled evaluation of ingestion freshness across all providers and capabilities against master data SLA targets. Formats compliance digest and dispatches notification to platform owner (`admin@jyotirmoyb.com`). | `domain/reports/freshness_sla.py`, `tests/improvements/` |
| **IMP-09** | Configuration Snapshot & Diff | Full export of master data catalogues and tenant configuration into versioned JSON bundles. Computes structural diffs between environments (DEV vs UAT vs PROD) and enables deterministic promotion without manual re-keying. | `domain/config/snapshot_engine.py`, `scripts/config_snapshot.py`, `tests/improvements/` |
| **IMP-10** | Licence & Commitment Calendar | Aggregated unified calendar across 5 lifecycle streams: cloud credential expiries, TLS certificate expiries, cloud commitments (RIs/Savings Plans), enterprise software licences, and financial budget period closes. Exposed at `/api/v1/commitments/calendar` and Control Tower `expiries` panel. | `domain/commitments/calendar.py`, `api/cloudlens_api/routes/calendar.py`, `tests/improvements/` |

### 36.2 Phase 2 Deferred Improvements (Safety Interlock)
The following items are defined in master data with `phase: 2` and `status: "PENDING_CONFIRMATION"`, and are strictly deferred until explicit confirmation is provided by the platform authority:
- **IMP-11**: Microsoft Teams & Slack Webhook Notification Pipelines with interactive remediation buttons.
- **IMP-12**: Advanced Statistical Cost Anomaly Detection (Holt-Winters double exponential smoothing with dynamic noise rejection).
