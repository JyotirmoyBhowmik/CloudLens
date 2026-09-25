# CloudLens Enterprise Data Dictionary

> **Status**: Template Baseline (Stage 1)  
> **Standards Alignment**: FinOps Open Cost & Usage Specification (FOCUS) v1.0

---

## 1. Canonical Entity Dictionary

| Table / Entity | Field Name | Data Type | Nullable | Primary / Foreign Key | Description |
|:---|:---|:---|:---:|:---:|:---|
| `tenants` | `id` | UUID | No | PK | Globally unique tenant identifier |
| `tenants` | `name` | VARCHAR(100) | No | — | Organization tenant name |
| `tenants` | `reporting_currency` | VARCHAR(3) | No | — | ISO-4217 currency code (e.g. USD, EUR, INR) |
| `scopes` | `id` | UUID | No | PK | Canonical hierarchy scope identifier |
| `scopes` | `provider_type` | VARCHAR(20) | No | — | Provider type (`azure`, `aws`, `gcp`, `oci`) |
| `scopes` | `native_type` | VARCHAR(50) | No | — | Native type (`management_group`, `ou`, `folder`, `compartment`) |
| `scopes` | `materialized_path` | VARCHAR(500) | No | — | Hierarchical lineage path |
| `resources` | `id` | UUID | No | PK | Canonical resource identifier |
| `resources` | `native_id` | VARCHAR(500) | No | — | Provider resource ID / ARN |
| `resources` | `pricing_status` | VARCHAR(20) | No | — | Classification (`FREE`, `FREE TIER`, `CONDITIONAL FREE`, `PAID`, `ESTIMATED`, `UNKNOWN`, `NOT APPLICABLE`) |
| `cost_facts` | `id` | UUID | No | PK | Fact charge line identifier (partitioned by period) |
| `cost_facts` | `billed_cost` | NUMERIC(18,6) | No | — | Actual invoice charge |
| `cost_facts` | `effective_cost` | NUMERIC(18,6) | No | — | Amortised cost including commitment allocations |
