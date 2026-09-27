# Oracle Cloud Infrastructure (OCI) Connector Research Note

> **Author**: Antigravity Enterprise Integration Team  
> **Status**: Verified & Authoritative  
> **Date**: 2026-09-27  
> **Governing Standards**: SEC-012, SEC-016, BBP Sections 14.5 & 15.4

---

## 1. Authentication & Security Baselines

| Document Title | API Endpoint / Resource | API Version | Verified Authentication Pattern |
|:---|:---|:---:|:---|
| *OCI Documentation - SDK and CLI Configuration / Managing User Credentials* | `POST /20160918/instancePrincipals/` | `20160918` | **Instance / Resource Principals** for inside-OCI workloads; **IAM User + RSA API Signing Key** (2048/4096-bit PEM) with key fingerprint tracking and mandatory 90-day rotation notice. |
| *Identity and Access Management Service API* | `GET /20160918/users/{userId}/apiKeys` | `20160918` | API key fingerprint and lifecycle state verification. |

### Security Invariants
- Console passwords and interactive web credentials are **strictly prohibited** (`FORBIDDEN_USER_CREDENTIALS`).
- API signing keys require explicit key fingerprint tracking (`key_fingerprint`) and a mandatory 90-day key rotation policy.

---

## 2. Hierarchy Discovery & Compartment Trees

| Document Title | API Endpoint / Resource | API Version | Hierarchy Mapping Details |
|:---|:---|:---:|:---|
| *Identity and Access Management Service API - ListCompartments* | `GET /20160918/compartments` | `20160918` | Enumerates compartment tree within tenancy (`compartmentIdInSubtree=true`). |

### Compartment Preservation Principles
- **No Flattening**: OCI allows compartments up to 6 levels deep. The tree must preserve exact nesting depth.
- **Canonical Scope Roles**:
  - Tenancy root: `ROOT_GROUP`
  - Depth 1 compartments: `GROUP`
  - Depth > 1 sub-compartments: `SUB_GROUP`
- **Compartment as Ownership Model**: In OCI, compartments frequently double as the business ownership boundary. A dedicated compartment-to-owner mapping mechanism is provided to attribute un-tagged resources directly by compartment scope.
- **Compartment Depth Parameter**: Cost queries accept a `compartmentDepth` parameter to control roll-up aggregation.

---

## 3. Resource Inventory & Search

| Document Title | API Endpoint / Resource | API Version | Discovery Details |
|:---|:---|:---:|:---|
| *Search Service API - SearchResources* | `POST /20180409/resources` | `20180409` | Structured search query (`query all resources where lifeCycleState = 'AVAILABLE'`) across the tenancy as primary discovery path. |
| *Core Services API - Compute & Storage* | `GET /20160918/instances`<br>`GET /20160918/volumes` | `20160918` | Per-service enrichment for shapes, memory, and volume performance tiers. |

---

## 4. Cost & Usage Ingestion

| Document Title | API Endpoint / Resource | API Version | Ingestion Characteristics |
|:---|:---|:---:|:---|
| *Usage API - RequestSummarizedUsages* | `POST /20200107/usage` | `20200107` | Interactive query engine backing OCI Console **Cost Analysis**. Supports `groupBy` (`compartmentId`, `service`, `tag:namespace.key`), `compartmentDepth`, and negative cost adjustments. |
| *Object Storage Service API - Usage Reports* | `GET /20160918/b/{bucket}/o/{object}` | `20160918` | Ingestion of delivered CSV usage and cost reports from the tenancy's reporting bucket (`reports/usage-csv/` and `reports/cost-csv/`). |

---

## 5. Distinctive Tag Model & Attribution Timing (CRITICAL)

| Document Title | API Endpoint / Resource | API Version | Tag Architecture |
|:---|:---|:---:|:---|
| *Tagging Service API - Tags and Namespaces* | `GET /20160918/tagNamespaces`<br>`GET /20160918/tags` | `20160918` | Distinct separation between **Free-form Tags** and **Namespaced Defined Tags**. |
| *Managing Cost-Tracking Tags* | `POST /20160918/tags` (`isCostTracking=true`) | `20160918` | Dedicated flag for cost-tracking tags (maximum 10 per tenancy). |

### Non-Retroactive Tag Attribution Caveat
- **Timing Invariant**: OCI attaches tag values to cost records at generation time. Associating a tag to an OCI resource **applies strictly from the time of association onward**.
- **Permanent Consequence**: Tag-based cost allocation is **never retroactive**. A tag added today cannot allocate last month's costs.
- **UI & Analytics Mandate**: Whenever tag-based cost allocation is displayed for historical periods prior to tag association, the UI and API must explicitly surface the non-retroactive attribution notice explaining why untagged costs remain unallocated.

---

## 6. Budgets & Alert Rules

| Document Title | API Endpoint / Resource | API Version | Threshold & Alert Mapping |
|:---|:---|:---:|:---|
| *Budgets API - ListBudgets / ListAlertRules* | `GET /20190111/budgets`<br>`GET /20190111/budgets/{id}/alertRules` | `20190111` | Ingests budgets targeted by `COMPARTMENT` or `TAG`. |

### Threshold Basis Mapping
- Alert types: `ACTUAL` (historical spend) and `FORECAST` (projected spend).
- Threshold types: `ABSOLUTE` (currency amount) and `PERCENTAGE` (% of budget limit).
- Comparison-only semantics: `is_authoritative = False` (CloudLens master budgets remain authoritative).

---

## 7. Pricing Verification & Limitations

| Document Title | Verified Interface | Verification Finding & Limitations |
|:---|:---|:---:|
| *Oracle Cloud Infrastructure Pricing* | Static Rate Card / Universal Credits (UCC) Contract | **VERIFIED LIMITATION**: Unlike AWS, Azure, and GCP, OCI does **not** provide a comprehensive public unauthenticated dynamic SKU rate-card query API. OCI pricing is published via static web pricing sheets and authenticated Universal Credits contract agreements. The connector implements static public rate card lookup and custom negotiated Universal Credits rate cards, declaring no dynamic public API parity. |

---

## 8. Structural Relationships

| Document Title | API Endpoint / Resource | API Version | Relationship Scope |
|:---|:---|:---:|:---|
| *Core Services API - Virtual Network & Attachments* | `GET /20160918/vnicAttachments`<br>`GET /20160918/volumeAttachments` | `20160918` | Derives structural edges (Instance $\to$ VNIC $\to$ Subnet $\to$ VCN, Instance $\to$ Block Volume). Declared as **MINIMAL / PARTIAL** as OCI does not expose application dependency graphs. |
