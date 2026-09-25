# CloudLens Master Requirements Register (v1.0)

> **Stage 0 Master Register** — Produced by **Prompt 00R** to close Defect **D-05** (issuing 6 missing requirement ranges) and Defect **D-06** (reconciling pricing dimensions). Single authoritative source of truth for Prompt 43 Traceability Matrix.

## 1. Executive Summary & Prefix Breakdown

| Prefix | Meaning / Range | Count | Primary BBP Sections & Origin | Owning Stage(s) |
|:---|:---|:---:|:---|:---:|
| **BR** | Business Requirements | 18 | BBP Section 10 | Stages 0–17 |
| **FR** | Functional Requirements (Core) | 89 | BBP Sections 14–16, 21, 30, 32–37, 39 | Stages 1–16 |
| **PR** | Pricing Requirements *(Newly Issued)* | 20 | BBP Section 18 + Master Brief 00.3–00.8 | Stages 2, 8, 16 |
| **CST** | Cost Requirements *(Newly Issued)* | 32 | BBP Sections 17, 22, 23, 24 | Stages 8, 10, 14 |
| **USE** | Usage Requirements *(Newly Issued)* | 10 | BBP Section 19 + Quota Addenda | Stage 9 |
| **RUN** | Runtime Requirements *(Newly Issued)* | 10 | BBP Section 20 + Schedules | Stage 9 |
| **DEP** | Dependency Requirements *(Newly Issued)* | 18 | BBP Sections 24, 25 | Stage 12 |
| **CON** | Connector Requirements *(Newly Issued)* | 32 | BBP Sections 26–29 | Stages 6, 7 |
| **API** | API Interface Requirements | 66 | BBP Section 38 + Addendum B | Stages 5, 13, 14, 15 |
| **SEC** | Security Requirements | 30 | BBP Sections 27, 40 | Stages 1, 3, 5, 17 |
| **NFR** | Non-Functional Requirements | 50 | BBP Sections 31, 43, 44, 46 | Stages 1, 16, 17 |
| **DR** | Disaster Recovery Requirements | 7 | BBP Section 45 | Stages 2, 17 |
| **AC** | Acceptance Criteria | 76 | BBP Section 48 + Addenda A & B | Stages 1–17 |
| **TOTAL** | **All Thirteen Ranges Populated** | **458** | **Full Scope Traceable** | **Stages 0–17** |

## BR — BR Range (18 Requirements)

| ID | Original ID | Requirement Statement | Priority | Phase | Owning Prompt(s) | Verification |
|:---|:---|:---|:---:|:---:|:---|:---:|
| **BR-001** | — | The organisation must have an accurate, complete, automated inventory of all cloud resources across all four providers. | Must | MVP | Prompt 05, 08 | Integration Test |
| **BR-002** | — | Every cloud resource must have a determinable owner (technical and business) and attribution to an application and cost centre. | Must | MVP | Prompt 08, 46 | Automated Test |
| **BR-003** | — | The organisation must understand its total cloud cost, cost trends, and cost distribution across business units and applications. | Must | MVP | Prompt 22, 37 | Automated Test |
| **BR-004** | — | Teams must understand how their services are priced and which billing dimensions drive their costs. | Must | MVP | Prompt 20, 21, 40 | Demonstration |
| **BR-005** | — | The organisation must maximise its use of provider free tiers and avoid unintended transitions from free to paid usage. | Must | MVP | Prompt 21, 27 | Automated Test |
| **BR-006** | — | Costs must be controllable through budgets with timely alerting before overspend occurs, not after. | Must | MVP | Prompt 28, 31 | Automated Test |
| **BR-007** | — | Non-production workloads must not run 24x7 without business justification; runtime must be monitored against expected schedules. | Must | MVP | Prompt 26, 30 | Automated Test |
| **BR-008** | — | Cost increases, usage spikes, and abnormal patterns must trigger contextual alerts with explanatory detail. | Must | MVP | Prompt 27, 31, 31B | Integration Test |
| **BR-009** | — | The organisation must understand service dependencies so that cost changes can be traced to upstream causes. | Must | MVP | Prompt 32, 33 | Integration Test |
| **BR-010** | — | The organisation must be able to compare costs across cloud providers using a canonical framework. | Must | MVP | Prompt 05, 07, 23 | Automated Test |
| **BR-011** | — | CloudLens cost data must reconcile with provider invoices so that management reports are trusted by Finance. | Must | MVP | Prompt 24 | Automated Test |
| **BR-012** | — | Teams must be able to estimate the cost of new workloads before deployment using verified provider pricing. | Must | MVP | Prompt 23 | Automated Test |
| **BR-013** | — | All governance actions, overrides, and administrative changes must be fully auditable. | Must | MVP | Prompt 13, 41 | Audit |
| **BR-014** | — | The platform must operate with least privilege and must never possess write or modify permissions in cloud environments. | Must | MVP | Prompt 10, 11, 12, 14 | Inspection |
| **BR-015** | — | Data must be exportable for corporate reporting, BI integration, and compliance auditing. | Must | MVP | Prompt 35, 56 | Integration Test |
| **BR-016** | — | Senior leadership must have a single-pane-of-glass executive dashboard showing cross-cloud KPIs and trends. | Must | MVP | Prompt 37 | Demonstration |
| **BR-017** | — | Governance policies must be enforceable across all providers through a unified policy and compliance framework. | Must | MVP | Prompt 30, 31B | Automated Test |
| **BR-018** | — | The platform must be deployable on open-source technologies without vendor lock-in to any commercial software. | Must | MVP | Prompt 01, 04 | Inspection |

## FR — FR Range (89 Requirements)

| ID | Original ID | Requirement Statement | Priority | Phase | Owning Prompt(s) | Verification |
|:---|:---|:---|:---:|:---:|:---|:---:|
| **FR-001** | — | The system must discover and represent Microsoft Azure native hierarchy: Tenant -> Management Group -> Subscription -> Resource Group -> Resource. | Must | MVP | Prompt 05, 16 | Integration Test |
| **FR-002** | — | The system must discover and represent AWS native hierarchy: Organization -> OU -> Account -> Region -> Resource. | Must | MVP | Prompt 05, 17 | Integration Test |
| **FR-003** | — | The system must discover and represent GCP native hierarchy: Organization -> Folder -> Project -> Region/Zone -> Resource. | Must | MVP | Prompt 05, 18 | Integration Test |
| **FR-004** | — | The system must discover and represent OCI native hierarchy: Tenancy -> Compartment -> Sub-compartment -> Region/AD -> Resource. | Must | MVP | Prompt 05, 19 | Integration Test |
| **FR-005** | — | The system must preserve native hierarchy depth and allow navigation at any level of each provider hierarchy. | Must | MVP | Prompt 05, 38 | Demonstration |
| **FR-006** | — | The system must map native hierarchy nodes to a canonical scope abstraction for cross-provider aggregation. | Must | MVP | Prompt 05 | Automated Test |
| **FR-007** | — | The system must support resources belonging to multiple logical groupings simultaneously. | Must | MVP | Prompt 05, 08 | Automated Test |
| **FR-020** | — | The canonical data model must define a provider-agnostic representation for all cloud entities while retaining native attributes in extension fields. | Must | MVP | Prompt 05 | Inspection |
| **FR-021** | — | The system must maintain a unified Resource entity with standard attributes across all four providers. | Must | MVP | Prompt 05 | Automated Test |
| **FR-022** | — | Every canonical entity must carry a global unique identifier, provider-native identifier, and tenant isolation key. | Must | MVP | Prompt 05, 06 | Automated Test |
| **FR-023** | — | The model must support bi-temporal data tracking (valid time and transaction time) for historical analysis. | Must | MVP | Prompt 05, 06 | Automated Test |
| **FR-024** | — | The system must map provider-native service names to canonical service categories aligned to FOCUS taxonomy. | Must | MVP | Prompt 05, 07 | Automated Test |
| **FR-025** | — | The model must support flexible tag/label key-value pairs with provider-specific normalisation. | Must | MVP | Prompt 05, 08 | Automated Test |
| **FR-026** | — | Schema migrations must be version-controlled, backward-compatible, and executed without data loss. | Must | MVP | Prompt 06 | Automated Test |
| **FR-100** | — | The system must maintain an inventory of all discovered cloud services and resources with a 35-field inventory schema. | Must | MVP | Prompt 05, 08 | Integration Test |
| **FR-101** | — | The inventory must detect and record newly created resources within the configured freshness SLA. | Must | MVP | Prompt 08, 15 | Automated Test |
| **FR-102** | — | Deleted resources must be marked as Deleted after two consecutive sync cycles and retain historical cost attribution. | Must | MVP | Prompt 05, 08 | Automated Test |
| **FR-103** | — | Manual ownership assignments must survive subsequent discovery synchronisations unchanged. | Must | MVP | Prompt 08 | Automated Test |
| **FR-104** | — | The inventory must display the specific ownership resolution rule that produced the current assigned owner. | Must | MVP | Prompt 08, 39 | Demonstration |
| **FR-105** | — | Resources of unmapped provider types must appear as 'Unclassified' with their native type visible and in gap reports. | Must | MVP | Prompt 07, 08 | Automated Test |
| **FR-106** | — | The system must support bulk tag editing and manual ownership assignment through the UI. | Must | MVP | Prompt 08, 38 | Demonstration |
| **FR-107** | — | Inventory search must support filtering across provider, account, region, type, status, tag, and owner. | Must | MVP | Prompt 38 | Demonstration |
| **FR-108** | — | The system must calculate and display inventory drift and changes between any two sync snapshots. | Must | MVP | Prompt 08, 38 | Automated Test |
| **FR-109** | — | Inventory export must respect user scope grants and disclose that data filtering occurred. | Must | MVP | Prompt 11, 35 | Automated Test |
| **FR-110** | — | The system must identify orphaned resources (unattached disks, unassociated IPs, idle gateways). | Must | MVP | Prompt 08, 30 | Automated Test |
| **FR-260** | — | The system must support threshold evaluation across all eleven threshold bases. | Must | MVP | Prompt 27, AM-09 | Automated Test |
| **FR-261** | — | Threshold templates must be definable globally, per tenant, or per scope with inheritance. | Must | MVP | Prompt 07, 27 | Automated Test |
| **FR-262** | — | Threshold detail must disclose whether the applied rule is local, inherited, or overridden, and from where. | Must | MVP | Prompt 27, 40 | Demonstration |
| **FR-263** | — | Threshold evaluation must support multiple severity bands (Normal, Warning/Amber, Critical/Red). | Must | MVP | Prompt 27 | Automated Test |
| **FR-264** | — | The system must implement hysteresis and cool-down periods to prevent alert flapping on boundary oscillation. | Must | MVP | Prompt 27 | Automated Test |
| **FR-265** | — | Threshold modifications must be audited and immediately reflect in the next evaluation cycle. | Must | MVP | Prompt 13, 27 | Audit |
| **FR-266** | — | Threshold evaluation on unchanged data must produce identical deterministic results. | Must | MVP | Prompt 27 | Automated Test |
| **FR-267** | — | The threshold engine must support evaluation triggered both on schedule and on data ingestion arrival. | Must | MVP | Prompt 27 | Integration Test |
| **FR-500** | — | The executive dashboard must render within interactive performance targets using pre-aggregated rollups. | Must | MVP | Prompt 37 | Automated Test |
| **FR-501** | — | Every dashboard widget must explicitly display the data freshness timestamp of the underlying data. | Must | MVP | Prompt 37, 40 | Demonstration |
| **FR-502** | — | Every widget must be filtered by the requesting user's RBAC scope grants; restricted data masked, not silently omitted. | Must | MVP | Prompt 11, 37 | Automated Test |
| **FR-503** | — | Users must be able to set a default landing dashboard per role. | Should | MVP | Prompt 37 | Demonstration |
| **FR-504** | — | Dashboards must support dynamic period selection including calendar months, quarters, years, and custom dates. | Must | MVP | Prompt 37 | Demonstration |
| **FR-505** | — | Widgets must support exporting underlying data in CSV and JSON formats. | Should | MVP | Prompt 35, 37 | Demonstration |
| **FR-506** | — | Dashboard widget layout and customization must be user-configurable in Phase 2. | Could | Phase 2 | Prompt 57 / P2 | Demonstration |
| **FR-700** | — | The administrative console must be a distinct, secured area requiring administrative role privilege. | Must | MVP | Prompt 41 | Automated Test |
| **FR-701** | — | All twenty-nine administrative functions (A-01 to A-29) must be accessible in the Admin Console. | Must | MVP | Prompt 41, AM-06 | Demonstration |
| **FR-702** | — | Every manual override must record actor, timestamp, justification, old value, new value, expiry, and approval. | Must | MVP | Prompt 41 | Audit |
| **FR-703** | — | Manual overrides must support time-boxed expiration with automatic reversion and audited state change. | Must | MVP | Prompt 41 | Automated Test |
| **FR-704** | — | Administrators must be able to simulate policy and threshold changes prior to committing them. | Should | MVP | Prompt 27, 30, 41 | Demonstration |
| **FR-705** | — | Catalogue changes must be versioned so historical classifications remain interpretable. | Must | MVP | Prompt 07, 41 | Automated Test |
| **FR-706** | — | No role, including Super Admin, may edit or delete audit records; immutable at database level. | Must | MVP | Prompt 06, 13 | Automated Test |
| **FR-707** | — | Feature flags must be configurable and evaluable per tenant with complete audit logging. | Must | MVP | Prompt 02, 41 | Automated Test |
| **FR-720** | — | The system must implement nine built-in roles and support custom roles defined as permission matrices. | Must | MVP | Prompt 11 | Automated Test |
| **FR-721** | — | Authorization must be evaluated on every request against both functional role and organizational scope grant. | Must | MVP | Prompt 11 | Automated Test |
| **FR-722** | — | Deny permissions must take precedence over allow permissions where both apply. | Must | MVP | Prompt 11 | Automated Test |
| **FR-723** | — | Aggregates must exclude data the user cannot access and must disclose when data filtering has occurred. | Must | MVP | Prompt 11, 34 | Automated Test |
| **FR-724** | — | Financial rate details (unit rates, charge lines) must be separately permissioned from aggregate costs. | Must | MVP | Prompt 11 | Automated Test |
| **FR-725** | — | The system must provide an automated access review export listing every user, role, scope grant, and last login. | Must | MVP | Prompt 11, 35 | Audit |
| **FR-726** | — | All role and scope grant changes must be audited with previous and new values. | Must | MVP | Prompt 11, 13 | Audit |
| **FR-727** | — | A user with no mapped role must receive zero access rather than a default role. | Must | MVP | Prompt 11 | Automated Test |
| **FR-740** | — | Governance policies must be declarative, versioned, and definable without code modification or deployment. | Must | MVP | Prompt 30 | Automated Test |
| **FR-741** | — | Policies must support simulate and enforce modes, with simulation producing findings without alerting. | Must | MVP | Prompt 30 | Demonstration |
| **FR-742** | — | A policy condition that cannot be evaluated for an entity must produce 'Not Evaluable', never False. | Must | MVP | Prompt 30 | Automated Test |
| **FR-743** | — | Policy exemptions must be time-boxed, justified, approved, and reported while active. | Must | MVP | Prompt 30, 50 | Audit |
| **FR-744** | — | Policy violation findings must be deduplicated against open findings for the same entity and condition. | Must | MVP | Prompt 30 | Automated Test |
| **FR-745** | — | Governance exception counts and resolution times must be trended over time and reportable. | Must | MVP | Prompt 30, 35, 51 | Automated Test |
| **FR-746** | — | The system must ship with eighteen default policies (POL-01 to POL-18), disabled by default except connector health. | Must | MVP | Prompt 07, 30, 31B | Automated Test |
| **FR-560** | — | The system must support all twenty alert types (AL-01 to AL-20) defined in the alert catalogue. | Must | MVP | Prompt 31, 31B | Automated Test |
| **FR-561** | — | Every generated alert must link directly to the empirical evidence and contributing data that triggered it. | Must | MVP | Prompt 31 | Demonstration |
| **FR-562** | — | Alerts must support deduplication, grouping by scope, and automatic resolution when conditions clear. | Must | MVP | Prompt 31 | Automated Test |
| **FR-563** | — | Notification routing must resolve recipients from technical owner, business owner, scope owner, and subscription lists. | Must | MVP | Prompt 31 | Integration Test |
| **FR-564** | — | Notification delivery attempts and outcomes must be logged and visible per channel (Email, Webhook, Slack, Teams). | Must | MVP | Prompt 31 | Integration Test |
| **FR-565** | — | Where no recipient can be resolved, alerts must route to the scope default administrator and flag the missing assignment. | Must | MVP | Prompt 31 | Automated Test |
| **FR-566** | — | Escalation rules must be configurable per alert category and severity when alerts remain unacknowledged. | Should | MVP | Prompt 31 | Automated Test |
| **FR-600** | — | All sixteen MVP reports (RPT-01 to RPT-16) must be available in PDF, CSV, Excel, and JSON formats. | Must | MVP | Prompt 35 | Integration Test |
| **FR-601** | — | Reports must respect the requesting user's scope grants and explicitly state if filtering was applied. | Must | MVP | Prompt 11, 35 | Automated Test |
| **FR-602** | — | Every report must state data freshness timestamps, cost basis (billed/amortised), and currency exchange rates. | Must | MVP | Prompt 35 | Demonstration |
| **FR-603** | — | Large report generations must execute asynchronously in the background with user notification upon completion. | Must | MVP | Prompt 35 | Integration Test |
| **FR-604** | — | Report generation, download, and parameter choices must be recorded in the audit trail. | Must | MVP | Prompt 13, 35 | Audit |
| **FR-605** | — | Scheduled recurring report delivery via email and webhook must be available in Phase 2. | Could | Phase 2 | Prompt 60 / P2 | Integration Test |
| **FR-580** | — | Global search must index resources, services, accounts, applications, tags, and budgets while respecting scope grants. | Must | MVP | Prompt 38 | Integration Test |
| **FR-581** | — | Filters must support boolean logic: AND semantics across filter attributes and OR semantics within multi-selects. | Must | MVP | Prompt 38 | Automated Test |
| **FR-582** | — | Filter state must be bi-directionally synchronized with URL query parameters for bookmarking and sharing. | Must | MVP | Prompt 38 | Demonstration |
| **FR-583** | — | Users must be able to save, name, and share custom filter configurations as reusable views. | Should | MVP | Prompt 38 | Demonstration |
| **FR-584** | — | Filter result counts must be displayed reactively before full result set pagination loads. | Should | MVP | Prompt 38 | Demonstration |
| **FR-585** | — | Search queries must never disclose the existence or names of entities outside the user's scope grants. | Must | MVP | Prompt 11, 38 | Automated Test |
| **FR-800** | — | Every database table must carry tenant_id and all data access queries must enforce strict tenant isolation. | Must | MVP | Prompt 06, 13 | Automated Test |
| **FR-801** | — | High-volume fact tables must be range-partitioned by period with partition creation automated in advance. | Must | MVP | Prompt 06 | Automated Test |
| **FR-802** | — | Period re-ingestion must execute atomic partition replacement to prevent dirty reads or data duplication. | Must | MVP | Prompt 06, 22 | Automated Test |
| **FR-803** | — | Materialized aggregate tables must be refreshed deterministically following successful sync cycles. | Must | MVP | Prompt 06, 22 | Automated Test |
| **FR-804** | — | Audit log tables must be strictly append-only with database-level constraints preventing update or delete. | Must | MVP | Prompt 06, 13 | Automated Test |
| **FR-805** | — | Data retention and downsampling policies must be configurable per data class within corporate governance limits. | Must | MVP | Prompt 06 | Automated Test |
| **FR-806** | — | Archived historical partitions must be restorable into an active queryable state within defined recovery SLAs. | Should | MVP | Prompt 06, 44 | Integration Test |

## PR — PR Range (20 Requirements)

| ID | Original ID | Requirement Statement | Priority | Phase | Owning Prompt(s) | Verification |
|:---|:---|:---|:---:|:---:|:---|:---:|
| **PR-001** | FR-220 | Pricing dimensions, units and conversions must be configurable catalogue data, not hard-coded in logic. | Must | MVP | Prompt 07, 20 | Automated Test |
| **PR-002** | FR-221 | The system must store pricing as effective-dated records so historical estimates and rates can be accurately reproduced. | Must | MVP | Prompt 20 | Automated Test |
| **PR-003** | FR-222 | Where negotiated enterprise rates are available, the system must use them and never present public list rates as the organisation's contracted rate. | Must | MVP | Prompt 20 | Automated Test |
| **PR-004** | FR-223 | The system must separate upfront and recurring reservation/savings plan purchase charges from runtime usage charges in all trend views. | Must | MVP | Prompt 22, 37 | Automated Test |
| **PR-005** | FR-224 | The system must support both billed and amortised presentation with the active accounting basis prominently and unmistakably labelled. | Must | MVP | Prompt 22, 37, 39 | Demonstration |
| **PR-006** | FR-225 | Unmapped SKUs and dimensions must be ingested and reported as Unclassified rather than discarded or zero-rated. | Must | MVP | Prompt 07, 20 | Automated Test |
| **PR-007** | FR-226 | Commitment coverage and utilisation analysis for reservations and savings plans must be supported in Phase 2. | Could | Phase 2 | Prompt 58 / P2 | Automated Test |
| **PR-008** | — | ABSOLUTE RULE: The application must NEVER invent or hallucinate pricing information. All rates must derive from verified sources following strict precedence: 1. Pricing/Catalog API, 2. Billing API, 3. Usage API, 4. Official pricing documentation, 5. Official service documentation. | Must | MVP | Prompt 20, 21 | Inspection |
| **PR-009** | — | Where a provider does not expose a pricing value via an API, CloudLens must display the verified provider documentation source, link, and effective date, and never present it as API-derived. | Must | MVP | Prompt 21, 40 | Demonstration |
| **PR-010** | — | Every discovered service, resource, and cost field must be classified into one of seven non-conflated pricing statuses: FREE, FREE TIER, CONDITIONAL FREE, PAID, ESTIMATED, UNKNOWN, NOT APPLICABLE. | Must | MVP | Prompt 21 | Automated Test |
| **PR-011** | — | The UI must never display a bare 'Free'; it must state the exact conditions, allowances, post-allowance rates, thresholds, source reference, and effective date. | Must | MVP | Prompt 21, 40 | Demonstration |
| **PR-012** | — | Every service, resource, and cost field must support an information icon revealing seventeen pricing metadata attributes and a direct link to official provider documentation. | Must | MVP | Prompt 40 | Demonstration |
| **PR-013** | — | The platform must provide six contextual alerts: Cost Information, Free Tier, Budget, Forecast, Pricing Change, and Pricing Unavailable. | Must | MVP | Prompt 31, 40 | Integration Test |
| **PR-014** | — | The platform must support pre-deployment cost estimation ('What will this cost?') providing hourly, daily, monthly, and annualised projections from stated configurations across all four providers. | Must | MVP | Prompt 23, AM-08 | Automated Test |
| **PR-015** | — | The system must keep four cost values strictly separate and never treat them as interchangeable: provider list price, estimated effective cost, actual billed cost, and forecast cost. | Must | MVP | Prompt 21, 23 | Automated Test |
| **PR-016** | — | The system must implement the full twenty-nine reconciled pricing dimensions and models across consumption units, structural models, and pricing qualifiers. | Must | MVP | Prompt 07, 20, AM-14 | Automated Test |
| **PR-017** | — | The system must model Microsoft Azure-specific pricing models: Enterprise Agreement (EA), MCA, Azure Hybrid Benefit, Dev/Test pricing, and Reservations. | Must | MVP | Prompt 16, 20 | Integration Test |
| **PR-018** | — | The system must model AWS-specific pricing models: On-Demand, Savings Plans (Compute/EC2), Standard/Convertible Reserved Instances, and CUR line item types. | Must | MVP | Prompt 17, 20 | Integration Test |
| **PR-019** | — | The system must model Google Cloud-specific pricing models: Sustained Use Discounts (SUD), Committed Use Discounts (CUD), and BigQuery pricing. | Must | MVP | Prompt 18, 20 | Integration Test |
| **PR-020** | — | The system must model OCI-specific pricing models: Universal Credits, Annual Commitments, OCPU/memory decoupled pricing, and storage performance tiers. | Must | MVP | Prompt 19, 20 | Integration Test |

## CST — CST Range (32 Requirements)

| ID | Original ID | Requirement Statement | Priority | Phase | Owning Prompt(s) | Verification |
|:---|:---|:---|:---:|:---:|:---|:---:|
| **CST-001** | FR-200 | All cost figures must be stored in the canonical cost fact schema strictly aligned to the FinOps Open Cost & Usage Specification (FOCUS). | Must | MVP | Prompt 22 | Automated Test |
| **CST-002** | FR-201 | The system must store both billed cost and effective cost for every charge line where the provider distinguishes them. | Must | MVP | Prompt 22 | Automated Test |
| **CST-003** | FR-202 | Cost data must be converted to the tenant reporting currency using effective-dated currency exchange rates. | Must | MVP | Prompt 22 | Automated Test |
| **CST-004** | FR-203 | The system must record provider cost restatements with effective date and maintain complete version history of restated periods. | Must | MVP | Prompt 22, 24 | Automated Test |
| **CST-005** | FR-204 | Cost aggregation must be supported across any combination of provider, account, service, application, cost centre, business unit, environment, region, and tag. | Must | MVP | Prompt 22, 37 | Automated Test |
| **CST-006** | FR-205 | Shared service costs and unallocated costs must be identifiable and reportable at every aggregation level. | Must | MVP | Prompt 08, 22 | Automated Test |
| **CST-007** | FR-206 | Unallocated cost must be displayed explicitly at every hierarchy level and never silently absorbed into general overhead. | Must | MVP | Prompt 22, 37 | Demonstration |
| **CST-008** | FR-207 | Users must be able to drill from any aggregate cost figure down to contributing line items in no more than four interactions. | Must | MVP | Prompt 37, 39 | Demonstration |
| **CST-009** | FR-208 | The system must reconcile platform cost totals against authoritative provider billing totals per period and report variance. | Must | MVP | Prompt 24 | Automated Test |
| **CST-010** | FR-209 | Cost data ingestion must be idempotent and support period-level atomic partition replacement. | Must | MVP | Prompt 06, 22 | Automated Test |
| **CST-011** | FR-210 | Each provider cost figure must display its own independent data freshness timestamp. | Must | MVP | Prompt 22, 37, 40 | Demonstration |
| **CST-012** | FR-211 | Negative charges (credits, refunds, corrections) must be preserved as distinct charge categories and not netted invisibly into usage cost. | Must | MVP | Prompt 22 | Automated Test |
| **CST-013** | FR-300 | Budgets must be definable at any canonical scope (tenant, provider, account, application, cost centre, business unit, environment, service, resource). | Must | MVP | Prompt 28 | Automated Test |
| **CST-014** | FR-301 | The system must support monthly, quarterly, annual, and custom budget periods aligned to the tenant's fiscal calendar. | Must | MVP | Prompt 28 | Automated Test |
| **CST-015** | FR-302 | Budgets must support multiple warning and alert thresholds (e.g. 50%, 75%, 90%, 100%, 120%) with configurable routing. | Must | MVP | Prompt 28, 31 | Automated Test |
| **CST-016** | FR-303 | The system must detect and warn on overlapping budgets for the same scope and period to prevent double-counting. | Must | MVP | Prompt 28 | Automated Test |
| **CST-017** | FR-304 | Budget creation and amendment above configured approval limits must require formal workflow approval. | Must | MVP | Prompt 28, 50 | Automated Test |
| **CST-018** | FR-305 | The system must maintain an immutable audit trail of budget amendments (previous amount, new amount, requester, approver, reason). | Must | MVP | Prompt 13, 28 | Audit |
| **CST-019** | FR-306 | Budgets must track actual spend, committed spend, and forecast spend against the assigned budget allocation. | Must | MVP | Prompt 28, 29 | Automated Test |
| **CST-020** | FR-307 | The system must support budget hierarchy inheritance and rollup from child scopes to parent organizational scopes. | Must | MVP | Prompt 28 | Automated Test |
| **CST-021** | FR-308 | Budget status must be evaluated automatically upon arrival of newly ingested cost data and on a scheduled timer. | Must | MVP | Prompt 28 | Integration Test |
| **CST-022** | FR-320 | The system must generate end-of-period cost forecasts using historical run rate, linear regression trend, and seasonal modeling. | Must | MVP | Prompt 29 | Automated Test |
| **CST-023** | FR-321 | Forecast calculations must require a minimum data history and flag low-confidence projections when history is insufficient. | Must | MVP | Prompt 29 | Automated Test |
| **CST-024** | FR-322 | Every displayed forecast must clearly indicate its forecasting method, evaluation window, and confidence rating label. | Must | MVP | Prompt 29, 37, 40 | Demonstration |
| **CST-025** | FR-323 | When period data contains fewer than three days, the system must generate a simple run-rate forecast explicitly labelled 'Low Confidence'. | Must | MVP | Prompt 29 | Automated Test |
| **CST-026** | FR-324 | Forecast calculations must incorporate known future events (scheduled shutdowns, reserved capacity expirations, planned deployments). | Must | MVP | Prompt 29 | Automated Test |
| **CST-027** | FR-325 | The system must predict budget breach dates based on current run rate and raise alerts before the breach occurs. | Must | MVP | Prompt 29, 31 | Automated Test |
| **CST-028** | FR-326 | Forecast accuracy must be tracked retroactively by comparing predicted period spend against actual closed reconciled spend. | Must | MVP | Prompt 29 | Automated Test |
| **CST-029** | — | For each closed billing period, the reconciliation engine must verify platform totals against provider authoritative invoices within configured tolerances. | Must | MVP | Prompt 24 | Automated Test |
| **CST-030** | — | Business unit owners must receive monthly showback statements with budget variance, shared-service apportionment, and unallocated cost details. | Must | MVP | Prompt 52 | Demonstration |
| **CST-031** | — | Pre-deployment provisioning gate must evaluate proposed architecture costs against remaining scope budget and quota headroom. | Must | MVP | Prompt 55 | Integration Test |
| **CST-032** | — | Multi-year budget planning, what-if scenario modeling, and commitment capacity planning must be supported in Phase 2. | Could | Phase 2 | Prompt 57 / P2 | Automated Test |

## USE — USE Range (10 Requirements)

| ID | Original ID | Requirement Statement | Priority | Phase | Owning Prompt(s) | Verification |
|:---|:---|:---|:---:|:---:|:---|:---:|
| **USE-001** | FR-240 | The system must support all fifteen monitoring types (MT-01 to MT-15), including Quota headroom as the 15th type. | Must | MVP | Prompt 25, 54, AM-09 | Automated Test |
| **USE-002** | FR-241 | Resource-to-monitoring-type mapping must be determined by canonical resource type with support for manual overrides. | Must | MVP | Prompt 25 | Automated Test |
| **USE-003** | FR-242 | The system must ingest usage metrics at configurable aggregation intervals (hourly, daily, monthly) per resource. | Must | MVP | Prompt 25 | Integration Test |
| **USE-004** | FR-243 | Usage data gaps in provider telemetry must be recorded and rendered explicitly as 'No Data' rather than assumed zero consumption. | Must | MVP | Prompt 25, 39 | Demonstration |
| **USE-005** | FR-244 | The system must execute metric unit conversions through the declarative, versioned unit catalogue. | Must | MVP | Prompt 07, 25 | Automated Test |
| **USE-006** | FR-245 | Usage metrics must be retained with configurable downsampling policies (raw samples, hourly rollups, daily rollups). | Must | MVP | Prompt 06, 25 | Automated Test |
| **USE-007** | FR-246 | Usage spikes and abnormal consumption patterns must be detected using baseline statistical standard deviations. | Must | MVP | Prompt 25, 27 | Automated Test |
| **USE-008** | — | Quota headroom and service limits must be tracked continuously across providers and alerted at predicted exhaustion minus lead time. | Must | MVP | Prompt 54, AM-07 | Automated Test |
| **USE-009** | — | The system must correlate granular usage metrics with billing dimensions to explain the technical drivers behind cost increases. | Must | MVP | Prompt 25, 39 | Demonstration |
| **USE-010** | — | Usage monitoring must support volume-based and transaction-based services across all four cloud providers. | Must | MVP | Prompt 25 | Integration Test |

## RUN — RUN Range (10 Requirements)

| ID | Original ID | Requirement Statement | Priority | Phase | Owning Prompt(s) | Verification |
|:---|:---|:---|:---:|:---:|:---|:---:|
| **RUN-001** | FR-250 | The system must determine runtime state (Running, Stopped, Suspended, Terminated, Unknown) for all discoverable resources. | Must | MVP | Prompt 26 | Automated Test |
| **RUN-002** | FR-251 | Runtime schedules (business hours, batch windows, weekend shutdown) must be attachable to resources, applications, or environments. | Must | MVP | Prompt 26 | Automated Test |
| **RUN-003** | FR-252 | Out-of-schedule execution must be detected within one evaluation cycle, and excess runtime hours and estimated excess cost must be calculated. | Must | MVP | Prompt 26 | Automated Test |
| **RUN-004** | FR-253 | A resource whose runtime signal cannot be verified or is missing must be displayed as 'Unknown', never assumed 'Stopped' or 'Green'. | Must | MVP | Prompt 26, 39 | Demonstration |
| **RUN-005** | FR-254 | Temporary runtime exemptions must be time-boxed, require recorded justification, be fully audited, and expire automatically. | Must | MVP | Prompt 26, 41 | Audit |
| **RUN-006** | FR-255 | The system must track cumulative operating hours per resource across billing periods to identify underutilised or idle capacity. | Must | MVP | Prompt 26 | Automated Test |
| **RUN-007** | FR-256 | Runtime evaluation must be idempotent and re-evaluable deterministically across any historical evaluation window. | Must | MVP | Prompt 26 | Automated Test |
| **RUN-008** | — | The system must generate schedule adherence reports by application, cost centre, and environment showing compliance percentages. | Must | MVP | Prompt 26, 35 | Automated Test |
| **RUN-009** | — | Runtime monitoring must distinguish between 24x7 continuous workloads, schedule-based workloads, and volume-triggered burst workloads. | Must | MVP | Prompt 26 | Automated Test |
| **RUN-010** | — | Automated resource lifecycle governance (provisioning, active lifecycle, scheduled decommissioning) must be supported in Phase 2. | Could | Phase 2 | Prompt 59 / P2 | Automated Test |

## DEP — DEP Range (18 Requirements)

| ID | Original ID | Requirement Statement | Priority | Phase | Owning Prompt(s) | Verification |
|:---|:---|:---|:---:|:---:|:---|:---:|
| **DEP-001** | FR-400 | The system must model directional dependencies between resources, services, and applications (Upstream and Downstream relationships). | Must | MVP | Prompt 32 | Automated Test |
| **DEP-002** | FR-401 | Dependencies must support multiple discovery provenances: provider-discovered, configuration-inferred, and manually curated. | Must | MVP | Prompt 32 | Automated Test |
| **DEP-003** | FR-402 | Manually created dependency edges must persist across discovery cycles and be visibly labelled as 'Manual'. | Must | MVP | Prompt 32 | Automated Test |
| **DEP-004** | FR-403 | Each dependency edge must carry metadata: edge type, direction, discovery method, confidence level, and last verified timestamp. | Must | MVP | Prompt 32 | Automated Test |
| **DEP-005** | FR-404 | The system must calculate the cumulative cost of dependency chains (total upstream cost supporting a specific business service). | Must | MVP | Prompt 33 | Automated Test |
| **DEP-006** | FR-405 | Impact analysis must identify all downstream dependents when a resource, service, or configuration change is simulated. | Must | MVP | Prompt 32, 55 | Automated Test |
| **DEP-007** | FR-406 | The dependency model must support cyclic dependency detection and versioned topology snapshots. | Must | MVP | Prompt 32 | Automated Test |
| **DEP-008** | FR-410 | The platform must provide an interactive node-link graph visualization supporting zoom, pan, search, and layout selection. | Must | MVP | Prompt 41 | Demonstration |
| **DEP-009** | FR-411 | The graph engine must support expanding/collapsing nodes and filtering by application, environment, provider, and tier. | Must | MVP | Prompt 41 | Demonstration |
| **DEP-010** | FR-412 | The graph visualization must render topologies of at least 500 nodes within interactive performance target (<2.0s). | Must | MVP | Prompt 41 | Automated Test |
| **DEP-011** | FR-413 | The graph must support a Cost Overlay mode where node dimensions and visual encoding reflect selected period spend. | Must | MVP | Prompt 33, 41 | Demonstration |
| **DEP-012** | FR-414 | The graph must display health, threshold status, and active alert badges directly on affected nodes. | Must | MVP | Prompt 41 | Demonstration |
| **DEP-013** | FR-415 | Users must be able to export dependency graphs in standard formats (SVG, PNG, JSON). | Must | MVP | Prompt 41 | Demonstration |
| **DEP-014** | FR-416 | Graph views must respect user RBAC scope grants; nodes outside scope must render as 'Restricted' with names masked, never silently omitted. | Must | MVP | Prompt 41 | Automated Test |
| **DEP-015** | FR-417 | The graph must support time-travel inspection of historical topology states based on versioned snapshots. | Must | MVP | Prompt 32, 41 | Demonstration |
| **DEP-016** | — | The system must infer network relationships from provider VPC peering, transit gateways, route tables, and private endpoints. | Must | MVP | Prompt 32 | Integration Test |
| **DEP-017** | — | Shared infrastructure nodes (clusters, databases) must accurately apportion costs across multiple dependent applications. | Must | MVP | Prompt 33, 52 | Automated Test |
| **DEP-018** | — | The topology engine must calculate upstream dependency cost propagation using configurable attribution weighting. | Must | MVP | Prompt 33 | Automated Test |

## CON — CON Range (32 Requirements)

| ID | Original ID | Requirement Statement | Priority | Phase | Owning Prompt(s) | Verification |
|:---|:---|:---|:---:|:---:|:---|:---:|
| **CON-001** | FR-030 | All connectors must implement a common interface contract (discovery, inventory, pricing, usage, cost, health). | Must | MVP | Prompt 14 | Automated Test |
| **CON-002** | FR-031 | Connectors must operate strictly read-only in MVP; write and autonomous remediation access is strictly forbidden. | Must | MVP | Prompt 14 | Inspection |
| **CON-003** | FR-032 | Connectors must support pre-flight permission validation to report available capabilities based on granted credentials. | Must | MVP | Prompt 14, 15 | Automated Test |
| **CON-004** | FR-033 | Connectors must implement exponential backoff with jitter and retry handling for provider API rate limits. | Must | MVP | Prompt 14 | Automated Test |
| **CON-005** | FR-034 | Connector sync jobs must be resumable from checkpoints in the event of worker interruption or process termination. | Must | MVP | Prompt 14, 15 | Automated Test |
| **CON-006** | FR-035 | Connector health and connection status must be monitored continuously with diagnostic logging and failure alerting. | Must | MVP | Prompt 14, 15 | Integration Test |
| **CON-007** | FR-036 | Connectors must support pluggable credential providers (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, environment/file). | Must | MVP | Prompt 12, 14 | Integration Test |
| **CON-008** | FR-037 | Missing permissions must gracefully degrade specific capabilities rather than aborting overall connector sync. | Must | MVP | Prompt 14, 15 | Automated Test |
| **CON-009** | FR-038 | A provider-agnostic stub and simulator connector must be provided for testing, conformance checking, and offline demo mode. | Must | MVP | Prompt 14, 47, 47B, AM-19 | Automated Test |
| **CON-010** | FR-010 | Onboarding of cloud accounts must be guided through a self-service, step-by-step wizard. | Must | MVP | Prompt 15, 15B | Demonstration |
| **CON-011** | FR-011 | The wizard must perform inline credential syntax and connectivity validation before persistence. | Must | MVP | Prompt 15, 15B | Automated Test |
| **CON-012** | FR-012 | The wizard must execute permission pre-flight checks and display capability status (supported, degraded, blocked). | Must | MVP | Prompt 15, 15B | Automated Test |
| **CON-013** | FR-013 | The onboarding flow must support pausing and resuming without loss of entered configuration. | Must | MVP | Prompt 15, 15B | Demonstration |
| **CON-014** | FR-014 | Discovery scope selection must allow including or excluding specific management groups, accounts, projects, or regions. | Must | MVP | Prompt 15, 15B | Demonstration |
| **CON-015** | FR-015 | The wizard must conduct an alert and notification delivery test to verify recipient channels before completing setup. | Must | MVP | Prompt 15B, D-07 | Integration Test |
| **CON-016** | FR-016 | The wizard must estimate resource count, initial sync duration, and estimated API call volume prior to triggering full sync. | Should | MVP | Prompt 15, 15B | Demonstration |
| **CON-017** | FR-017 | Wizard completion must queue initial discovery immediately and display real-time progress and expected time to first view. | Must | MVP | Prompt 15, 15B | Demonstration |
| **CON-018** | FR-018 | All onboarding actions, configuration changes, and credential validations must be audited without exposing secrets. | Must | MVP | Prompt 13, 15 | Audit |
| **CON-019** | FR-050 | Synchronisation must support scheduled full sync, incremental sync, event-driven sync, and manual on-demand sync. | Must | MVP | Prompt 15 | Integration Test |
| **CON-020** | FR-051 | Sync schedules and intervals must be independently configurable per connector and per capability group. | Must | MVP | Prompt 15 | Automated Test |
| **CON-021** | FR-052 | All data ingestion pipelines must be strictly idempotent and safe to re-run without duplicate records. | Must | MVP | Prompt 06, 15 | Automated Test |
| **CON-022** | FR-053 | Sync failures must be tracked per scope; partial failure in one account or region must not fail overall connector sync. | Must | MVP | Prompt 15 | Automated Test |
| **CON-023** | FR-054 | Sync lag, last successful run timestamp, and sync health status must be maintained and displayed per connector. | Must | MVP | Prompt 15, 37 | Demonstration |
| **CON-024** | FR-055 | Every displayed figure and record must be traceable to the specific sync job execution ID that ingested it. | Must | MVP | Prompt 15, 21 | Automated Test |
| **CON-025** | FR-056 | Ingestion pipelines must quarantine unprocessable or schema-violating records with failure reasons rather than dropping them. | Must | MVP | Prompt 15 | Automated Test |
| **CON-026** | FR-057 | Cost synchronization must support a configurable historical look-back window to capture provider billing restatements. | Must | MVP | Prompt 15, 22 | Automated Test |
| **CON-027** | FR-058 | Manual on-demand sync triggers must be rate-limited per connector to protect provider API quotas. | Must | MVP | Prompt 15 | Automated Test |
| **CON-028** | FR-059 | Sync history, execution logs, and row-level statistics must be retained for at least 90 days and be exportable. | Should | MVP | Prompt 15, 35 | Audit |
| **CON-029** | — | The system must provide a production-ready Microsoft Azure connector using Azure Resource Graph and Cost Management APIs. | Must | MVP | Prompt 16 | Integration Test |
| **CON-030** | — | The system must provide a production-ready Amazon Web Services connector using Resource Explorer, Cost Explorer, and CUR. | Must | MVP | Prompt 17 | Integration Test |
| **CON-031** | — | The system must provide a production-ready Google Cloud Platform connector using Cloud Asset Inventory and BigQuery Export. | Must | MVP | Prompt 18 | Integration Test |
| **CON-032** | — | The system must provide a production-ready Oracle Cloud Infrastructure connector using Resource Search and Cost Analysis APIs. | Must | MVP | Prompt 19 | Integration Test |

## API — API Range (66 Requirements)

| ID | Original ID | Requirement Statement | Priority | Phase | Owning Prompt(s) | Verification |
|:---|:---|:---|:---:|:---:|:---|:---:|
| **API-001** | — | GET /api/v1/health - System and connector liveness/readiness probe. | Must | MVP | Prompt 03, 34 | Automated Test |
| **API-002** | — | GET /api/v1/auth/session - Current authenticated session state and user identity. | Must | MVP | Prompt 10, 34 | Automated Test |
| **API-003** | — | POST /api/v1/auth/login - Local superuser break-glass authentication. | Must | MVP | Prompt 10, 34 | Automated Test |
| **API-004** | — | POST /api/v1/auth/logout - Terminate current session and invalidate tokens. | Must | MVP | Prompt 10, 34 | Automated Test |
| **API-005** | — | GET /api/v1/users - List users with role assignments and scope grants. | Must | MVP | Prompt 11, 34 | Automated Test |
| **API-006** | — | POST /api/v1/users - Invite or provision a new user. | Must | MVP | Prompt 11, 34 | Automated Test |
| **API-007** | — | GET /api/v1/users/{id} - Get detailed user profile and permissions. | Must | MVP | Prompt 11, 34 | Automated Test |
| **API-008** | — | PATCH /api/v1/users/{id} - Update user role, scope grants, or active status. | Must | MVP | Prompt 11, 34 | Automated Test |
| **API-009** | — | GET /api/v1/roles - List available roles and permission definitions. | Must | MVP | Prompt 11, 34 | Automated Test |
| **API-010** | — | GET /api/v1/scopes - Canonical hierarchy scopes tree. | Must | MVP | Prompt 05, 34 | Automated Test |
| **API-011** | — | GET /api/v1/connectors - List configured cloud provider connectors. | Must | MVP | Prompt 14, 34 | Automated Test |
| **API-012** | — | POST /api/v1/connectors - Create a new cloud provider connector. | Must | MVP | Prompt 15, 34 | Automated Test |
| **API-013** | — | GET /api/v1/connectors/{id} - Get connector configuration, health, and capability status. | Must | MVP | Prompt 14, 34 | Automated Test |
| **API-014** | — | PATCH /api/v1/connectors/{id} - Update connector configuration or credential reference. | Must | MVP | Prompt 15, 34 | Automated Test |
| **API-015** | — | POST /api/v1/connectors/{id}/sync - Trigger an on-demand connector synchronization. | Must | MVP | Prompt 15, 34 | Automated Test |
| **API-016** | — | GET /api/v1/connectors/{id}/jobs - List synchronization execution history. | Must | MVP | Prompt 15, 34 | Automated Test |
| **API-017** | — | POST /api/v1/connectors/validate - Pre-flight permission validation on candidate credentials. | Must | MVP | Prompt 14, 34 | Automated Test |
| **API-018** | — | GET /api/v1/inventory/resources - Query discovered resources with multi-attribute filtering. | Must | MVP | Prompt 08, 34 | Automated Test |
| **API-019** | — | GET /api/v1/inventory/resources/{id} - Detailed 35-field resource record. | Must | MVP | Prompt 08, 34 | Automated Test |
| **API-020** | — | PATCH /api/v1/inventory/resources/{id} - Manually update resource owner or custom tags. | Must | MVP | Prompt 08, 34 | Automated Test |
| **API-021** | — | GET /api/v1/inventory/services - Aggregated service inventory list. | Must | MVP | Prompt 05, 34 | Automated Test |
| **API-022** | — | GET /api/v1/inventory/drift - Inventory changes and deltas between snapshots. | Must | MVP | Prompt 08, 34 | Automated Test |
| **API-023** | — | GET /api/v1/cost/summary - Executive cost summary and KPI aggregations. | Must | MVP | Prompt 22, 34 | Automated Test |
| **API-024** | — | GET /api/v1/cost/timeseries - Daily/monthly cost time series by scope and dimension. | Must | MVP | Prompt 22, 34 | Automated Test |
| **API-025** | — | GET /api/v1/cost/breakdown - Cost distribution by provider, service, application, or owner. | Must | MVP | Prompt 22, 34 | Automated Test |
| **API-026** | — | GET /api/v1/cost/line-items - Paginated underlying FOCUS cost charge lines. | Must | MVP | Prompt 22, 34 | Automated Test |
| **API-027** | — | GET /api/v1/cost/reconciliation - Reconciled closed-period variance reports. | Must | MVP | Prompt 24, 34 | Automated Test |
| **API-028** | — | GET /api/v1/pricing/catalog - Effective-dated provider rate card entries. | Must | MVP | Prompt 20, 34 | Automated Test |
| **API-029** | — | GET /api/v1/pricing/status - Pricing status classification for services and resources. | Must | MVP | Prompt 21, 34 | Automated Test |
| **API-030** | — | POST /api/v1/pricing/estimate - Calculate workload cost estimate from configuration. | Must | MVP | Prompt 23, 34 | Automated Test |
| **API-031** | — | GET /api/v1/usage/metrics - Query ingested usage metric time series. | Must | MVP | Prompt 25, 34 | Automated Test |
| **API-032** | — | GET /api/v1/runtime/states - Resource running/stopped/unknown runtime status. | Must | MVP | Prompt 26, 34 | Automated Test |
| **API-033** | — | GET /api/v1/runtime/schedules - Configured operational schedules and exemptions. | Must | MVP | Prompt 26, 34 | Automated Test |
| **API-034** | — | POST /api/v1/runtime/exemptions - Create a time-boxed runtime schedule exemption. | Must | MVP | Prompt 26, 34 | Automated Test |
| **API-035** | — | GET /api/v1/thresholds - Configured threshold templates and active rules. | Must | MVP | Prompt 27, 34 | Automated Test |
| **API-036** | — | POST /api/v1/thresholds - Create or update a threshold configuration. | Must | MVP | Prompt 27, 34 | Automated Test |
| **API-037** | — | GET /api/v1/budgets - List budgets with current spend and utilisation. | Must | MVP | Prompt 28, 34 | Automated Test |
| **API-038** | — | POST /api/v1/budgets - Create a new budget record. | Must | MVP | Prompt 28, 34 | Automated Test |
| **API-039** | — | PATCH /api/v1/budgets/{id} - Amend an existing budget allocation. | Must | MVP | Prompt 28, 34 | Automated Test |
| **API-040** | — | GET /api/v1/forecasts - Forecasted period-end spend and predicted breach dates. | Must | MVP | Prompt 29, 34 | Automated Test |
| **API-041** | — | GET /api/v1/policies - Active policy rules and compliance findings. | Must | MVP | Prompt 30, 34 | Automated Test |
| **API-042** | — | POST /api/v1/policies/simulate - Simulate policy evaluation against current estate. | Must | MVP | Prompt 30, 34 | Automated Test |
| **API-043** | — | GET /api/v1/alerts - Active and historical alerts with evidence references. | Must | MVP | Prompt 31, 34 | Automated Test |
| **API-044** | — | POST /api/v1/alerts/{id}/ack - Acknowledge or annotate an open alert. | Must | MVP | Prompt 31, 34 | Automated Test |
| **API-045** | — | GET /api/v1/topology/graph - Directed dependency graph node-link dataset. | Must | MVP | Prompt 32, 34 | Automated Test |
| **API-046** | — | POST /api/v1/topology/edges - Manually create or verify a dependency edge. | Must | MVP | Prompt 32, 34 | Automated Test |
| **API-047** | — | GET /api/v1/reports - List generated reports and available report templates. | Must | MVP | Prompt 35, 34 | Automated Test |
| **API-048** | — | POST /api/v1/reports/export - Trigger asynchronous report export generation. | Must | MVP | Prompt 35, 34 | Automated Test |
| **API-049** | — | GET/POST /api/v1/estimates - Saved cost estimates and pre-deployment bills of materials. | Must | MVP | Prompt 23 | Automated Test |
| **API-050** | — | GET /api/v1/quotas - Quota consumption, limits, and headroom tracking across providers. | Must | MVP | Prompt 54 | Automated Test |
| **API-051** | — | GET/POST /api/v1/provisioning-requests - Pre-deployment cost-aware provisioning gate requests. | Must | MVP | Prompt 55 | Automated Test |
| **API-052** | — | GET/PATCH /api/v1/tasks - Assigned remediation tasks and tracking. | Must | MVP | Prompt 51 | Automated Test |
| **API-053** | — | GET /api/v1/statements - Showback statements and variance analysis. | Must | MVP | Prompt 52 | Automated Test |
| **API-054** | — | GET/POST /api/v1/plans - Multi-period budget plans and scenario models. | Must | Phase 2 | Prompt 57 | Automated Test |
| **API-055** | — | GET /api/v1/commitments/renewals - Commitment tracking, utilization, and renewal pipeline. | Must | Phase 2 | Prompt 58 | Automated Test |
| **API-056** | — | GET/POST /api/v1/decommissioning-requests - Resource decommissioning and retirement requests. | Must | Phase 2 | Prompt 59 | Automated Test |
| **API-057** | — | GET /api/v1/master-data/{type} - Master data registry lookups and administration. | Must | MVP | Prompt 45 | Automated Test |
| **API-058** | — | POST /api/v1/imports - Bulk data import execution and dry-run validation. | Must | MVP | Prompt 53 | Automated Test |
| **API-100** | — | All endpoints must adhere to OpenAPI 3.1 specification with contract-first development. | Must | MVP | Prompt 34 | Automated Test |
| **API-101** | — | All API requests must be authenticated via Bearer token with RBAC and scope evaluation. | Must | MVP | Prompt 10, 11, 34 | Automated Test |
| **API-102** | — | API responses must follow standardized JSON structure with correlation_id, timestamp, status, and data. | Must | MVP | Prompt 03, 34 | Automated Test |
| **API-103** | — | All error responses must be sanitized; never expose internal stack traces or database schema. | Must | MVP | Prompt 03, 34 | Automated Test |
| **API-104** | — | All list endpoints must enforce strict cursor or limit/offset pagination with default limit of 50. | Must | MVP | Prompt 34 | Automated Test |
| **API-105** | — | State-mutating endpoints must support idempotency keys to prevent duplicate execution on retry. | Must | MVP | Prompt 34 | Automated Test |
| **API-106** | — | All endpoints must enforce rate limiting per client token and client IP address. | Must | MVP | Prompt 34 | Automated Test |
| **API-107** | — | Public API must never return secret material, raw certificates, or plaintext credentials. | Must | MVP | Prompt 12, 34 | Automated Test |

## SEC — SEC Range (30 Requirements)

| ID | Original ID | Requirement Statement | Priority | Phase | Owning Prompt(s) | Verification |
|:---|:---|:---|:---:|:---:|:---|:---:|
| **SEC-010** | — | Provider credentials must be written directly to the secure secret store; the application database holds only an opaque reference. | Must | MVP | Prompt 12 | Inspection |
| **SEC-011** | — | Credentials must never be logged, never returned by any API endpoint, and never rendered in the UI after creation. | Must | MVP | Prompt 03, 12, 34 | Automated Test |
| **SEC-012** | — | Only read-only provider permissions may be requested or stored in MVP; any write permission is rejected. | Must | MVP | Prompt 12, 14 | Inspection |
| **SEC-013** | — | Credential expiry must be tracked continuously and alerted at 30, 14, and 3 days prior to expiration. | Must | MVP | Prompt 12, 31 | Automated Test |
| **SEC-014** | — | Credential rotation must be supported with zero downtime: new credential is validated before the old one is revoked. | Must | MVP | Prompt 12 | Automated Test |
| **SEC-015** | — | Password-based provider authentication is strictly forbidden; only IAM roles, certificates, and API keys are permitted. | Must | MVP | Prompt 12, 14 | Inspection |
| **SEC-016** | — | Credential profiles may be shared across connectors within a tenant but never across tenant boundaries. | Must | MVP | Prompt 12, 13 | Automated Test |
| **SEC-017** | — | Every credential usage must be traceable to a specific connector, sync job ID, and execution timestamp. | Must | MVP | Prompt 12, 13 | Audit |
| **SEC-001** | — | All web traffic and inter-service communications must enforce TLS 1.3 in transit. | Must | MVP | Prompt 01, 44 | Automated Test |
| **SEC-002** | — | All persistent data at rest (database, backups, cache) must be encrypted using AES-256. | Must | MVP | Prompt 06, 12 | Automated Test |
| **SEC-003** | — | The platform must integrate with enterprise OIDC / SAML 2.0 Identity Providers for single sign-on. | Must | MVP | Prompt 10 | Integration Test |
| **SEC-004** | — | Multi-Factor Authentication (MFA) must be enforced for all administrative and privileged roles. | Must | MVP | Prompt 10, 49B | Automated Test |
| **SEC-005** | — | Local user authentication is permitted only for the initial superuser break-glass account. | Must | MVP | Prompt 10, 49B, AM-05 | Inspection |
| **SEC-006** | — | Disabling a user must immediately terminate all active sessions and revoke all issued API tokens. | Must | MVP | Prompt 10, 11 | Automated Test |
| **SEC-007** | — | Session tokens must be short-lived JWTs with absolute lifetime and configurable idle timeout. | Must | MVP | Prompt 10 | Automated Test |
| **SEC-008** | — | Strict tenant data isolation must be enforced at the database level using Row-Level Security (RLS) or tenant schemas. | Must | MVP | Prompt 06, 13 | Automated Test |
| **SEC-009** | — | Cross-tenant data access must be impossible; verified by an automated multi-tenant penetration test suite. | Must | MVP | Prompt 13, 42 | Automated Test |
| **SEC-018** | — | All user inputs must be strictly validated and sanitized to prevent SQLi, XSS, and command injection. | Must | MVP | Prompt 01, 34 | Automated Test |
| **SEC-019** | — | API responses must include standard security headers: Content-Security-Policy, HSTS, X-Content-Type-Options. | Must | MVP | Prompt 01, 34 | Automated Test |
| **SEC-020** | — | Application dependencies must be scanned continuously for known CVEs; zero critical/high vulnerabilities allowed. | Must | MVP | Prompt 04, 44 | Automated Test |
| **SEC-021** | — | Container base images must be minimal, unprivileged, distroless or Alpine-based, and cryptographically signed. | Must | MVP | Prompt 01, 44 | Inspection |
| **SEC-022** | — | Audit log records must be cryptographically chained or signed to prevent undetectable tampering. | Must | MVP | Prompt 13 | Automated Test |
| **SEC-023** | — | Sensitive configuration items and encryption keys must be managed through dedicated KMS. | Must | MVP | Prompt 12 | Inspection |
| **SEC-024** | — | Independent third-party penetration testing must be conducted prior to production release with zero high findings. | Must | MVP | Prompt 44 | Audit |
| **SEC-025** | — | Secrets must never be stored in source code, commit history, Docker images, or build artifacts. | Must | MVP | Prompt 04, 48 | Automated Test |
| **SEC-026** | — | Zero Hard-Coding Mandate M2: monetary values, enums, states, and rules must not be hard-coded. | Must | MVP | Prompt 48, AM-02 | Automated Test |
| **SEC-027** | — | Superuser bootstrap must provision admin@jyotirmoyb.com with mandatory MFA and zero plaintext passwords. | Must | MVP | Prompt 49B, AC-116 | Automated Test |
| **SEC-028** | — | All API access from external automated systems must use scoped, expiring Service Account API keys. | Must | MVP | Prompt 10, 34 | Automated Test |
| **SEC-029** | — | Step-up authentication must be required for destructive operations, credential updates, and budget approvals. | Should | MVP | Prompt 10, 28, 50 | Automated Test |
| **SEC-030** | — | Network ingress must be restricted to authenticated load balancers with DDoS mitigation. | Must | MVP | Prompt 01, 44 | Inspection |

## NFR — NFR Range (50 Requirements)

| ID | Original ID | Requirement Statement | Priority | Phase | Owning Prompt(s) | Verification |
|:---|:---|:---|:---:|:---:|:---|:---:|
| **NFR-001** | — | Executive Dashboard initial page load must render in under 1.5 seconds at p95. | Must | MVP | Prompt 37 | Automated Test |
| **NFR-002** | — | Inventory table search and filter response time must be under 800ms at p95 for up to 100,000 resources. | Must | MVP | Prompt 38 | Automated Test |
| **NFR-003** | — | Resource detail view and explanation panel must load in under 500ms at p95. | Must | MVP | Prompt 39, 40 | Automated Test |
| **NFR-004** | — | Dependency graph rendering (500 nodes) must complete in under 2.0 seconds at p95. | Must | MVP | Prompt 41 | Automated Test |
| **NFR-005** | — | Standard report generation must complete in under 5.0 seconds for synchronous requests. | Must | MVP | Prompt 35 | Automated Test |
| **NFR-010** | — | Interactive API endpoints must respond with p95 latency under 200ms under nominal load. | Must | MVP | Prompt 34 | Automated Test |
| **NFR-011** | — | Bulk cost ingestion throughput must process at least 10,000 charge line records per second. | Must | MVP | Prompt 22 | Automated Test |
| **NFR-012** | — | Nightly batch synchronization for a 50,000-resource estate must complete within 2 hours. | Must | MVP | Prompt 15 | Automated Test |
| **NFR-013** | — | Threshold evaluation pipeline must process 100,000 metric data points per minute. | Must | MVP | Prompt 27 | Automated Test |
| **NFR-014** | — | Full-text global search must return relevant results within 300ms at p95. | Must | MVP | Prompt 38 | Automated Test |
| **NFR-015** | — | UI state changes and client-side interactions must respond in under 100ms. | Must | MVP | Prompt 36 | Automated Test |
| **NFR-016** | — | Database read replica queries must not exceed 50ms average query latency. | Must | MVP | Prompt 06 | Automated Test |
| **NFR-017** | — | Export generation for 1,000,000 rows must complete within 60 seconds asynchronously. | Must | MVP | Prompt 35 | Automated Test |
| **NFR-018** | — | Background worker queue latency must not exceed 5 seconds under peak sync load. | Must | MVP | Prompt 03, 15 | Automated Test |
| **NFR-019** | — | Pre-deployment cost calculation must return estimates in under 1.0 second. | Must | MVP | Prompt 23 | Automated Test |
| **NFR-020** | — | Authentication and token verification overhead must add less than 10ms to API requests. | Must | MVP | Prompt 10 | Automated Test |
| **NFR-030** | — | The system must scale to support estates of at least 500,000 concurrent cloud resources per tenant. | Must | MVP | Prompt 06 | Automated Test |
| **NFR-031** | — | The cost fact storage must support ingesting and querying at least 50,000,000 cost fact rows per month. | Must | MVP | Prompt 06, 22 | Automated Test |
| **NFR-032** | — | The platform must support at least 100 concurrent active web users per tenant without performance degradation. | Must | MVP | Prompt 42, 44 | Automated Test |
| **NFR-033** | — | The system must support multi-tenant isolation for at least 1,000 distinct tenants on shared infrastructure. | Must | MVP | Prompt 13 | Automated Test |
| **NFR-034** | — | The system must support horizontal scaling of background sync workers via Celery / Kubernetes HPA. | Must | MVP | Prompt 01, 15 | Automated Test |
| **NFR-035** | — | The database must support partitioned data retention spanning at least 36 rolling months of historical data. | Must | MVP | Prompt 06 | Automated Test |
| **NFR-036** | — | The connector framework must support managing up to 250 cloud accounts per tenant. | Must | MVP | Prompt 15 | Automated Test |
| **NFR-037** | — | The alert engine must handle bursts of up to 1,000 alerts per minute with automated deduplication. | Must | MVP | Prompt 31 | Automated Test |
| **NFR-040** | — | The web application and API must achieve 99.9% uptime availability excluding planned maintenance. | Must | MVP | Prompt 01, 44 | Automated Test |
| **NFR-041** | — | Zero data loss during planned rolling zero-downtime application upgrades. | Must | MVP | Prompt 44 | Integration Test |
| **NFR-042** | — | The platform must implement circuit breakers on all external provider API connections. | Must | MVP | Prompt 14 | Automated Test |
| **NFR-043** | — | Worker process failure or termination mid-sync must not corrupt the database or duplicate ingested records. | Must | MVP | Prompt 14, 15 | Automated Test |
| **NFR-044** | — | Inventory discovery data freshness target: newly created resources visible within 4 hours. | Must | MVP | Prompt 15 | Automated Test |
| **NFR-045** | — | Cost ingestion data freshness target: reconciled with provider billing exports within 24 hours of availability. | Must | MVP | Prompt 22 | Automated Test |
| **NFR-046** | — | Alert delivery must guarantee at-least-once delivery semantics to downstream webhook destinations. | Must | MVP | Prompt 31 | Automated Test |
| **NFR-047** | — | Database failover to secondary replica must complete automatically in under 60 seconds. | Must | MVP | Prompt 44, 45 | Integration Test |
| **NFR-048** | — | Audit event logging must be guaranteed; failed audit write must abort the state-mutating transaction. | Must | MVP | Prompt 13 | Automated Test |
| **NFR-049** | — | The platform must operate gracefully during partial cloud provider outages, degrading only affected connectors. | Must | MVP | Prompt 14, 15 | Automated Test |
| **NFR-050** | — | The system must operate without loss of configuration in air-gapped / offline demo environments using mock providers. | Must | MVP | Prompt 47 | Demonstration |
| **NFR-051** | — | Rolling upgrade from previous release must complete with no data loss and backward-compatible database schema. | Must | MVP | Prompt 06, 44 | Automated Test |
| **NFR-052** | — | All database transactions must use READ COMMITTED isolation or higher to eliminate dirty reads. | Must | MVP | Prompt 06 | Automated Test |
| **NFR-060** | — | UI must comply with WCAG 2.1 Level AA accessibility standards across all 27 screens. | Must | MVP | Prompt 36 | Automated Test |
| **NFR-061** | — | The UI must be responsive and fully functional across desktop and tablet viewport widths (1024px to 3840px). | Must | MVP | Prompt 36 | Demonstration |
| **NFR-062** | — | The design system must support consistent Light and Dark visual themes with semantic token mapping. | Should | MVP | Prompt 36 | Demonstration |
| **NFR-063** | — | Information density must be optimized for enterprise FinOps analysts with collapsible panels and table column customization. | Must | MVP | Prompt 36, 38 | Demonstration |
| **NFR-064** | — | The four null states (No Data, Restricted, Not Applicable, Unknown) must be visually distinct across all screens. | Must | MVP | Prompt 36, 40 | Demonstration |
| **NFR-065** | — | All data tables must support sortable columns, multi-column filtering, column reordering, and sticky headers. | Must | MVP | Prompt 36, 38 | Demonstration |
| **NFR-066** | — | The UI must implement keyboard navigation shortcuts for core exploration and search workflows. | Should | MVP | Prompt 36 | Demonstration |
| **NFR-080** | — | All service logs must be structured JSON format with correlation_id, tenant_id, service_name, and severity. | Must | MVP | Prompt 03 | Automated Test |
| **NFR-081** | — | Distributed tracing must be implemented using OpenTelemetry standards across all API, worker, and database calls. | Must | MVP | Prompt 03 | Automated Test |
| **NFR-082** | — | Application and connector metrics must be exposed via Prometheus-compatible /metrics endpoint. | Must | MVP | Prompt 03 | Automated Test |
| **NFR-083** | — | Sensitive data (passwords, tokens, cloud credentials, PII) must be automatically masked before writing to log streams. | Must | MVP | Prompt 03 | Automated Test |
| **NFR-084** | — | Pre-configured Grafana dashboards must provide real-time visibility into system health, API latency, and sync queues. | Must | MVP | Prompt 03 | Demonstration |
| **NFR-085** | — | Error tracking and unexpected exception alerting must be integrated into centralized observability channels. | Must | MVP | Prompt 03 | Integration Test |

## DR — DR Range (7 Requirements)

| ID | Original ID | Requirement Statement | Priority | Phase | Owning Prompt(s) | Verification |
|:---|:---|:---|:---:|:---:|:---|:---:|
| **DR-001** | — | Recovery Time Objective (RTO) must not exceed 4 hours for full system restoration from cold backup. | Must | MVP | Prompt 44 | Automated Test |
| **DR-002** | — | Recovery Point Objective (RPO) must not exceed 1 hour of configuration data and 24 hours of cost telemetry. | Must | MVP | Prompt 44 | Automated Test |
| **DR-003** | — | Automated daily full database backups and continuous WAL archiving must be encrypted and stored in secondary geographic regions. | Must | MVP | Prompt 06, 44 | Automated Test |
| **DR-004** | — | The platform must provide automated disaster recovery scripts capable of rebuilding infrastructure on a secondary cluster. | Must | MVP | Prompt 44 | Integration Test |
| **DR-005** | — | Quarterly disaster recovery restoration drills must be executed and evidenced with zero unrecoverable records. | Must | MVP | Prompt 44 | Audit |
| **DR-006** | — | Database point-in-time recovery (PITR) must be supported for any timestamp within the last 14 days. | Must | MVP | Prompt 06, 44 | Automated Test |
| **DR-007** | — | Configuration and master data exports must be retained in independent version-controlled repositories. | Must | MVP | Prompt 45, 46 | Inspection |

## AC — AC Range (76 Requirements)

| ID | Original ID | Requirement Statement | Priority | Phase | Owning Prompt(s) | Verification |
|:---|:---|:---|:---:|:---:|:---|:---:|
| **AC-001** | — | Onboarding completes without developer assistance using the self-service wizard. | Must | MVP | Prompt 15, 15B | Automated Test |
| **AC-002** | — | Invalid credentials are never persisted to database or secret store. | Must | MVP | Prompt 12, 15 | Automated Test |
| **AC-003** | — | Permission pre-flight checks validate each required capability individually. | Must | MVP | Prompt 14, 15 | Automated Test |
| **AC-004** | — | Partial permissions yield a reduced capability profile rather than aborting connection. | Must | MVP | Prompt 14, 15 | Automated Test |
| **AC-005** | — | Credentials are completely unreachable from client-side network inspectors. | Must | MVP | Prompt 10, 12, 34 | Automated Test |
| **AC-006** | — | Onboarding wizard state is resumable after browser reload. | Must | MVP | Prompt 15, 15B | Automated Test |
| **AC-007** | — | Connector diagnostics display exact failing provider error codes. | Must | MVP | Prompt 14, 15 | Automated Test |
| **AC-008** | — | Credential revocation degrades only affected connector capabilities. | Must | MVP | Prompt 14, 15 | Automated Test |
| **AC-010** | — | Discovered resources appear with correct provider hierarchy placement. | Must | MVP | Prompt 05, 08 | Automated Test |
| **AC-011** | — | New resources appear in inventory within the configured freshness SLA (<4 hours). | Must | MVP | Prompt 08, 15 | Automated Test |
| **AC-012** | — | Deleted resources are marked Deleted after two sync cycles with cost history intact. | Must | MVP | Prompt 05, 08 | Automated Test |
| **AC-013** | — | Manually assigned owner survives three subsequent discovery cycles unchanged. | Must | MVP | Prompt 08 | Automated Test |
| **AC-014** | — | Ownership resolution detail displays which rule produced the winning assignment. | Must | MVP | Prompt 08, 39 | Automated Test |
| **AC-015** | — | Unmapped provider resource types appear as 'Unclassified' and in gap report. | Must | MVP | Prompt 07, 08 | Automated Test |
| **AC-016** | — | Inventory export contains only resources within user's scope grants and discloses filtering. | Must | MVP | Prompt 11, 35 | Automated Test |
| **AC-020** | — | Executive dashboard renders within 1.5s with all 15 widgets populated or marked No Data. | Must | MVP | Prompt 37 | Automated Test |
| **AC-021** | — | Total cost equals sum of provider costs with independent freshness markers. | Must | MVP | Prompt 22, 37 | Automated Test |
| **AC-022** | — | Aggregate cost figures can be drilled to charge lines in four or fewer interactions. | Must | MVP | Prompt 37, 39 | Automated Test |
| **AC-023** | — | Re-running cost ingestion for the same period produces identical totals with no duplication. | Must | MVP | Prompt 06, 22 | Automated Test |
| **AC-024** | — | Provider billing restatement is flagged with both original and restated values visible. | Must | MVP | Prompt 22, 24 | Automated Test |
| **AC-025** | — | Unallocated cost is visible explicitly at every hierarchy level and never absorbed. | Must | MVP | Prompt 22, 37 | Automated Test |
| **AC-026** | — | Switching between billed and amortised basis updates figures and updates the basis label. | Must | MVP | Prompt 22, 37 | Automated Test |
| **AC-030** | — | Budgets can be created at each canonical scope type and show real-time utilisation. | Must | MVP | Prompt 28 | Automated Test |
| **AC-031** | — | Creating an overlapping budget generates a warning identifying the duplicate scope. | Must | MVP | Prompt 28 | Automated Test |
| **AC-032** | — | Budgets above approval limit cannot become active without recorded approval. | Must | MVP | Prompt 28, 50 | Automated Test |
| **AC-033** | — | Budget amendment history shows previous amount, new amount, actor, approver, reason. | Must | MVP | Prompt 13, 28 | Automated Test |
| **AC-034** | — | Crossing a budget threshold changes displayed band colour and raises exactly one alert. | Must | MVP | Prompt 28, 31 | Automated Test |
| **AC-035** | — | Forecast displays its forecasting method, evaluation window, and confidence label. | Must | MVP | Prompt 29, 37 | Automated Test |
| **AC-036** | — | With fewer than three days of data, system generates run-rate forecast labelled Low confidence. | Must | MVP | Prompt 29 | Automated Test |
| **AC-040** | — | Closed-period report shows platform total, provider total, and variance within agreed tolerance. | Must | MVP | Prompt 24 | Automated Test |
| **AC-050** | — | Largest Increases panel shows daily series, contributing resources, and inventory deltas. | Must | MVP | Prompt 22, 37 | Automated Test |
| **AC-051** | — | Storage resource with 5 TB expectation shows Amber above 80% and Red above 100%. | Must | MVP | Prompt 25, 27 | Automated Test |
| **AC-052** | — | API service with 10M call expectation shows Amber above 8M and Red above 10M. | Must | MVP | Prompt 25, 27 | Automated Test |
| **AC-053** | — | Metric telemetry gap is displayed explicitly as 'No Data' and never as zero usage. | Must | MVP | Prompt 25, 39 | Automated Test |
| **AC-054** | — | Changing a threshold updates state on next evaluation cycle and logs the actor. | Must | MVP | Prompt 13, 27 | Automated Test |
| **AC-060** | — | VM running outside schedule is detected in one cycle with excess cost calculated. | Must | MVP | Prompt 26 | Automated Test |
| **AC-061** | — | Resource with unavailable runtime signal displays 'Unknown', never 'Green'. | Must | MVP | Prompt 26, 39 | Automated Test |
| **AC-062** | — | Temporary runtime exemption suppresses alert, appears in active reports, and expires. | Must | MVP | Prompt 26, 41 | Automated Test |
| **AC-063** | — | Value oscillating around threshold produces at most one alert in cool-down period. | Must | MVP | Prompt 27 | Automated Test |
| **AC-064** | — | Threshold detail displays whether rule is local, inherited, or overridden, and origin. | Must | MVP | Prompt 27, 40 | Automated Test |
| **AC-065** | — | Re-running threshold evaluation on unchanged data produces identical results. | Must | MVP | Prompt 27 | Automated Test |
| **AC-066** | — | More than ten alerts within one scope in a single cycle collapse into one grouped alert. | Must | MVP | Prompt 31 | Automated Test |
| **AC-070** | — | Manually created dependency edge persists through discovery and is labelled 'Manual'. | Must | MVP | Prompt 32 | Automated Test |
| **AC-071** | — | Dependency graph of 500 nodes renders within 2.0s and supports expand/collapse/depth. | Must | MVP | Prompt 41 | Automated Test |
| **AC-072** | — | Cost overlay changes graph node size and colour according to selected period cost. | Must | MVP | Prompt 33, 41 | Automated Test |
| **AC-073** | — | Nodes outside user scope render as 'Restricted' with labels masked, not omitted. | Must | MVP | Prompt 41 | Automated Test |
| **AC-080** | — | Nine built-in roles access exactly their defined permissions in the RBAC matrix. | Must | MVP | Prompt 11 | Automated Test |
| **AC-081** | — | User with no mapped role receives zero access and an administrator alert is raised. | Must | MVP | Prompt 11 | Automated Test |
| **AC-082** | — | Disabling a user terminates active sessions and revokes API tokens immediately. | Must | MVP | Prompt 10, 11 | Automated Test |
| **AC-083** | — | Access review export lists all users, roles, scope grants, and last login dates. | Must | MVP | Prompt 11, 35 | Automated Test |
| **AC-090** | — | Every manual override records mandatory 8 attributes; incomplete overrides are rejected. | Must | MVP | Prompt 41 | Automated Test |
| **AC-091** | — | No role, including Super Admin, can modify or delete audit rows at database level. | Must | MVP | Prompt 06, 13 | Automated Test |
| **AC-092** | — | Catalogue modifications are versioned and historical classifications remain interpretable. | Must | MVP | Prompt 07, 41 | Automated Test |
| **AC-100** | — | Rolling upgrade from previous release completes with zero downtime and zero data loss. | Must | MVP | Prompt 44 | Automated Test |
| **AC-101** | — | Disaster recovery exercise demonstrates restoration within RTO (<4h) and RPO (<1h). | Must | MVP | Prompt 44, 45 | Automated Test |
| **AC-102** | — | Killing sync worker mid-job results in graceful checkpoint resumption without duplicates. | Must | MVP | Prompt 14, 15 | Automated Test |
| **AC-103** | — | Under stated concurrent user load (100 users), all p95 latency targets are met. | Must | MVP | Prompt 42, 44 | Automated Test |
| **AC-104** | — | Zero penetration test findings of critical or high severity unresolved at go-live. | Must | MVP | Prompt 44 | Automated Test |
| **AC-110** | — | Every list, category, state, label, threshold default, rate and mapping resolves from registered master data. | Must | MVP | Prompt 45 | Automated Test |
| **AC-111** | — | Business user can update master values through Master Data Console without redeployment or restart. | Must | MVP | Prompt 45 | Automated Test |
| **AC-112** | — | Hard-coding scan passes with zero unannotated findings across entire repository. | Must | MVP | Prompt 04, 48 | Automated Test |
| **AC-113** | — | Complete product (every screen S-01 to S-27) is demonstrable in Demo Mode without cloud accounts. | Must | MVP | Prompt 47, 47B | Automated Test |
| **AC-114** | — | Two runs of mock data generator with same seed produce identical deterministic outputs. | Must | MVP | Prompt 09, 47 | Automated Test |
| **AC-115** | — | Demo Mode is visibly watermarked on every screen and cannot coexist with live connectors. | Must | MVP | Prompt 41, 47 | Automated Test |
| **AC-116** | — | Clean deployment bootstraps to superuser admin@jyotirmoyb.com with mandatory MFA and zero plaintext passwords. | Must | MVP | Prompt 49B | Automated Test |
| **AC-117** | — | Every approval routes through single workflow engine; adding new approval needs only definition row. | Must | MVP | Prompt 50 | Automated Test |
| **AC-118** | — | Detected governance exception produces assigned, dated remediation task verified before closing. | Must | MVP | Prompt 51 | Automated Test |
| **AC-119** | — | Business unit owner receives showback statement with budget variance, apportionment, and unallocated cost. | Must | MVP | Prompt 52 | Automated Test |
| **AC-120** | — | 5,000-row bulk import completes with dry run, validation against masters, provenance, and reversal. | Must | MVP | Prompt 53 | Automated Test |
| **AC-121** | — | Quota headroom is tracked across all exposed provider quotas and alerts at exhaustion minus lead time. | Must | MVP | Prompt 54 | Automated Test |
| **AC-122** | — | Proposed deployment is priced, assessed against budget and quota headroom, and gated for approval. | Must | MVP | Prompt 55 | Automated Test |
| **AC-123** | — | Resource deployed in gated scope without approved request raises exception and assigned task. | Must | MVP | Prompt 55 | Automated Test |
| **AC-124** | — | Approved estimates are reconciled against actual cost for three periods with accuracy reportable. | Must | MVP | Prompt 23, 24 | Automated Test |
| **AC-125** | — | BI tool connects to semantic layer with zero transformation; four null states remain distinguishable. | Must | MVP | Prompt 56 | Automated Test |
| **AC-126** | — | Every analytical extract carries schema version and requesting user scope grants in metadata. | Must | MVP | Prompt 56 | Automated Test |
| **AC-127** | — | Approval authority for every approval type resolves from approval-authority master, not code. | Must | MVP | Prompt 46, 50 | Automated Test |

