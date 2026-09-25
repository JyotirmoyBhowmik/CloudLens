# CloudLens Master Module Map (Prompts 00 to 62)

> **Execution Sequence Authority**: Authoritative sequence per Addendum C Section 4 & Master Workbook.  
> **Total Prompts**: 69 (Prompts 00, 00R, 01–48, 49A, 49B, 50–61, 15B, 31B, 42B, 47B, 62).

---

## Stage & Module Matrix

| Stage | Track | Prompt ID | Module Name | Primary Responsibility |
|:---:|:---|:---:|:---|:---|
| **0** | Setup | `00` | Master Context Prompt | Establishes role, concepts, non-negotiables |
| **0** | Setup | `00R` | Requirement Register Re-issue | Closes D-05, D-06; issues 13 ranges & reconciles 29 dimensions |
| **1** | Foundation | `01` | Repository & Conventions | Monorepo skeleton, layering check, developer bootstrap |
| **1** | Foundation | `02` | Configuration & Feature Flags | Dynamic tenant-scoped configuration & feature flags |
| **1** | Foundation | `03` | Observability Skeleton | Structured logging, OpenTelemetry tracing, Prometheus |
| **1** | Foundation | `04` | CI & Quality Gates | Automated gates, zero hard-coding scan, pre-commit |
| **2** | Domain | `05` | Canonical Domain Model | Provider-agnostic canonical entities & scopes |
| **2** | Domain | `06` | Schema, Partitioning, Migrations | PostgreSQL partitioned fact tables & Alembic migrations |
| **2** | Domain | `07` | Catalogues | 29 pricing dimensions, service categories, units |
| **3** | Master Data | `45` | Master Data Management | MDM console, registry metadata, no-redeploy edits |
| **3** | Master Data | `46` | Business Master Data | Organization hierarchy, cost centres, approval authorities |
| **3** | Master Data | `48` | Zero Hard-Coding Enforcement | Automated AST scanner enforcing Mandate M2 |
| **3** | Master Data | `49A` | Bootstrap - Pre-Identity | System bootstrapping prior to identity provider integration |
| **4** | Attribution | `08` | Tags, Ownership, Allocation | 6-level ownership precedence, tag normalization |
| **4** | Attribution | `09` | Reference Seeding & Estate | Versioned deterministic synthetic multi-cloud estate |
| **4** | Attribution | `47` | Mock Data, Demo Mode, Simulator | Complete offline demonstrable demo mode (Mandate M3) |
| **5** | Security | `10` | Authentication & Sessions | OIDC SSO, MFA enforcement, session tokens |
| **5** | Security | `11` | RBAC & Scope Grants | 9 built-in roles, permission evaluation engine |
| **5** | Security | `49B` | Superuser Provisioning | Single break-glass admin@jyotirmoyb.com provisioning |
| **5** | Security | `12` | Secret & Credential Lifecycle | Secret store integration, zero-downtime rotation |
| **5** | Security | `13` | Tenant Isolation & Audit | Row-level tenant security, immutable audit logs |
| **6** | Connector | `14` | Connector Contract | BaseCloudConnector interface & capability probes |
| **6** | Connector | `15` | Sync Orchestration & Onboarding | Connector sync engine & guided onboarding wizard |
| **6** | Connector | `15B`| Onboarding Step Restoration | Restores 5 onboarding steps & channel alert test |
| **7** | Providers | `16` | Azure Connector | Azure Resource Graph, Cost Management API |
| **7** | Providers | `17` | AWS Connector | AWS Organizations, Resource Explorer, CUR, Pricing |
| **7** | Providers | `18` | GCP Connector | Cloud Asset Inventory, Cloud Billing BigQuery export |
| **7** | Providers | `19` | OCI Connector | OCI Resource Search, Cost Analysis & Usage APIs |
| **8** | Cost | `20` | Pricing Catalogue | Effective-dated rate cards & SKU mappings |
| **8** | Cost | `21` | Pricing Status & Traceability | 7 pricing statuses & explanation layer |
| **8** | Cost | `22` | Cost Ingestion & FOCUS | FOCUS-aligned cost facts, restatement look-back |
| **8** | Cost | `23` | Calculation Engine & Estimator | Pre-deployment cost estimation ('What will this cost?') |
| **8** | Cost | `24` | Cost Reconciliation | Closed-period variance reporting against invoices |
| **9** | Usage | `25` | Monitoring Types & Usage | 15 monitoring types & usage telemetry ingestion |
| **9** | Usage | `26` | Runtime & Schedule Adherence | State machine, schedule tracking, out-of-schedule excess |
| **9** | Usage | `27` | Threshold Engine | Multi-band thresholds, hysteresis, anti-flapping |
| **9** | Usage | `54` | Quota & Headroom Tracking | Provider limits & predicted exhaustion alerting |
| **10**| Governance | `28` | Budget Model | Hierarchical budgets, overlap detection, approvals |
| **10**| Governance | `29` | Forecasting Engine | Run rate, trend regression, breach date predictions |
| **10**| Governance | `30` | Policy Engine | Declarative policies (POL-01 to POL-18) |
| **10**| Governance | `31` | Alerting & Notification | 20 alert types (AL-01 to AL-20) & channel routing |
| **10**| Governance | `31B`| Alert & Policy Extension | Adds AL-17..AL-20 and POL-17..POL-18 |
| **11**| Workflow | `50` | Workflow & Approval Engine | Multi-level approval routing & task assignment |
| **11**| Workflow | `51` | Remediation & Accountability | Governance exception tasks & realized savings tracking |
| **12**| Topology | `32` | Dependency Model | Directional graph, multi-provenance, manual edges |
| **12**| Topology | `33` | Cost-Aware Topology | Cost propagation along dependency chains |
| **13**| API | `34` | Public API Surface | OpenAPI 3.1 endpoints (API-001 to API-048) |
| **13**| API | `35` | Reporting & Export | 16 standard reports (RPT-01 to RPT-16) |
| **13**| API | `56` | Analytics Export & Semantic Layer | Star-schema conformed semantic layer for BI tools |
| **14**| Control | `52` | Showback Statements | Business unit statements with shared apportionment |
| **14**| Control | `55` | Cost-Aware Provisioning Gate | Pre-deployment budget & quota gating |
| **14**| Control | `47B`| Governance Mock Data Extension | Mock data for all 27 screens (Mandate M3) |
| **15**| Import | `53` | Bulk Import Framework | 5,000-row dry run, validation, reversible imports |
| **16**| Frontend | `36` | Design System | WCAG 2.1 AA tokens, components, light/dark themes |
| **16**| Frontend | `37` | Dashboards | Executive & FinOps dashboards with freshness |
| **16**| Frontend | `38` | Explorer, Inventory, Search | Global search, multi-faceted filtering, grid views |
| **16**| Frontend | `39` | Detail Views | 35-field resource inspector, cost breakdown |
| **16**| Frontend | `40` | Explanation Layer & Icons | Information icon (17 fields), contextual alerts |
| **16**| Frontend | `41` | Graph, Budget, Admin Console | Screens S-21 to S-27, dependency graph, admin tools |
| **17**| Quality | `42` | Test Suites | Levels 1 to 17 testing suites |
| **17**| Quality | `42B`| Test Strategy Extension | Levels 18 to 20 & Mandate validation suite |
| **17**| Quality | `43` | Traceability Matrix | Bidirectional traceability across all 458 requirements |
| **17**| Quality | `44` | Release Readiness | Exit checklist across AC-001 to AC-127 |
| **17**| Quality | `62` | BBP v1.1 Issuance | Harmonized BBP v1.1 publication & consistency test |
| **P2**| Phase 2 | `57` | Budget Planning & Scenarios | Multi-year scenario modeling & what-if forecasts |
| **P2**| Phase 2 | `58` | Commitment Renewal | Reservation & savings plan renewal pipeline |
| **P2**| Phase 2 | `59` | Resource Lifecycle | Automated resource decommissioning workflows |
| **P2**| Phase 2 | `60` | Integration Hub | Webhook broadcasts & scheduled outbound exports |
| **P2**| Phase 2 | `61` | Adoption & Value Measurement | FinOps maturity index & ROI tracking |
