# Fake Data Inventory & Zero-Embedded-Data Architecture

## 1. Executive Summary

As part of Prompt P09 ("Blank Application — Remove All Embedded Data"), CloudLens has completed the transition from embedded sample datasets to a pure repository-backed, zero-embedded-data architecture. 

In production, CloudLens operates under the strict invariant: **An empty database produces empty views.**
- No hardcoded fallback dictionaries, sample mock lists, or simulated dollar amounts exist in `api/` or `domain/`.
- Services never branch on tenant identity (`if tenant == "demo"`) to return canned responses.
- Demo estates are populated solely by the synthetic generator (`domain/synthetic/demo_tenant.py`) inserting persisted relational rows into PostgreSQL for the `T-DEMO` tenant.
- New production tenants without ingested telemetry or connector runs return pristine empty collections (`[]`), zero/null monetary values (`Decimal("0.00")`), and explicit sentinel statuses (`NO_DATA`, `NOT_SUPPORTED`, `NOT_APPLICABLE`, `NO_COST`, `Never synced`).

---

## 2. Inventory of Historical Literal Records and Replacement Strategy

| Location | Historical Literal Figure / Record | Replacement Architecture | Blank State Behavior |
| :--- | :--- | :--- | :--- |
| `domain/dashboards/service.py:221` | Hardcoded Total Cloud Spend `Decimal("342850.40")` | Dynamic aggregation across `HierarchyRepository.list_resources` and `CostRepository` | Returns `Decimal("0.00")` with 0 delta |
| `domain/dashboards/service.py:323` | Hardcoded Actual Spend `Decimal("112000.00")` | Aggregated sum of resource `monthly_cost` / actual billing facts | Returns `Decimal("0.00")` and `0.00%` utilisation |
| `domain/dashboards/service.py:813` | Hardcoded Resource Count `res_count = 14500` | Dynamic count: `len(provider_resources)` from `HierarchyRepository` | Returns `0` resources |
| `domain/dashboards/service.py:815` | Hardcoded Actual Cost `actual_amt = Decimal("112000.00")` | Sum of provider resources: `sum(r.monthly_cost for r in provider_resources)` | Returns `Decimal("0.00")` |
| `domain/dashboards/service.py:824` | Hardcoded Scope Label `"Enterprise Tenant Root"` | Dynamic root scope lookup via `HierarchyRepository.get_scopes_by_tenant` | Returns `None` / empty root node |
| `domain/dashboards/service.py:834` | Hardcoded Native Scope Node `"Core Production MG"` | Hierarchy tree projection generated from persisted `Scope` records | Returns empty children array `[]` |
| `domain/hierarchy/service.py` | ~850 lines of static `_resources` dictionary fixtures | Excised completely. All queries route through `HierarchyRepository` (`SqlHierarchyRepository` in production, `InMemoryHierarchyRepository` in test suites) | Returns `[]` resources and scopes |
| `domain/resource_detail/*` | Hardcoded narratives, telemetry figures, and owner contacts | Replaced with dynamic database queries against telemetry and cost fact tables | Missing telemetry yields `NO_DATA`; missing cost yields `NO_COST`; unmapped features yield `NOT_SUPPORTED` / `NOT_APPLICABLE` |
| Multiple domain fixtures | Canned employee identities (`alice@example.com`, `bob@example.com`, etc.) | Removed from production domain models. Synthetic people are isolated strictly within `domain/synthetic/demo_tenant.py` for demo DB seeding | Contacts and owners are populated only from real identity providers or connector metadata; empty tenant yields `null` |

---

## 3. Freshness & Sync Derivation Discipline

CloudLens forbids static freshness strings (such as hardcoded `"FRESH - synced 5m ago"`).
- Data freshness is calculated dynamically from the connector execution audit records: `ConnectorSyncJob.last_success_timestamp`.
- When a tenant has never configured a connector or never completed a sync:
  - Connector status is evaluated as `Never synced`.
  - Freshness status returns `Never synced` with `age_seconds = 0` and `is_stale = False`.
  - Stale provider alerts are only triggered when an active connector exists whose `last_success_timestamp` exceeds the provider lag SLA (> 24 hours).

---

## 4. Demo Estate Isolation Principle

To support sales demonstrations and UI previews without compromising production integrity:
1. **One-Way Seeding**: The synthetic generator (`domain/synthetic/demo_tenant.py`) creates rich multi-cloud scopes, resources, cost facts, and budgets by issuing standard SQL `INSERT` statements into PostgreSQL.
2. **Tenant Scoping**: All seeded records belong strictly to tenant `T-DEMO`.
3. **No Service-Level Branching**: `DashboardService`, `HierarchyService`, `ResourceDetailService`, and all REST routers have zero awareness of demo mode. They execute identical SQL queries against `SqlHierarchyRepository` and `SqlCostRepository` regardless of tenant ID.
4. **Production Purity**: Production tenants (`prod-*`) have no seeded rows and therefore cleanly evaluate to empty collections.

---

## 5. Verification & Continuous Enforcement

### 5.1 Automated Blank Tenant Contract Test (`scripts/verify_blank_tenant.py`)
A dedicated verification script introspects the OpenAPI schema (`/openapi.json`), spins up an ephemeral production tenant (`prod-blank-verification`), and tests every GET endpoint:
- Verifies that collections return HTTP 200 with `[]`.
- Verifies that financial aggregates return `Decimal("0.00")` or `null`.
- Verifies that freshness returns `Never synced` or `NO_DATA`.
- Asserts zero HTTP 500 internal server errors.

### 5.2 AST & Literal Scanning Gates
Continuous CI/CD gates guarantee that no developer accidentally re-introduces mock literals:
- **Regex Gate**: 
  ```bash
  git grep -n -E "342850|112000\.00|14500|Enterprise Tenant Root|Core Production MG|@example\.com" -- api/ domain/ ':!domain/synthetic'
  ```
  Must always return exit code 1 (zero matches).
- **AST Constant Scanner**:
  ```bash
  python scripts/check_no_hardcoded_constants.py
  ```
  Scans all AST nodes in `api/` and `domain/` to prohibit inline currency literals and mock collections exceeding 3 items, except where explicitly registered in `docs/configuration/exception_register.json`.
