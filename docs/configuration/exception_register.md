# CloudLens Configuration Exception Register

Enforces **Mandate M2** and **Prompt 48 Item 35**.
Every allow-listed literal in application code must be approved with a named reason and reviewer.

**Last Updated:** 2026-10-06 03:05:23Z | **Total Exceptions:** 84

| File Path | Line | Literal | Business Rationale | Approving Reviewer |
| :--- | :--- | :--- | :--- | :--- |
| `api/cloudlens_api/tenant_context.py` | 170 | `SUPER_ADMIN` | Legacy role string fallback check | **Prompt-48-Audit** |
| `api/cloudlens_api/tenant_context.py` | 170 | `GLOBAL_ADMIN` | Legacy role string fallback check | **Prompt-48-Audit** |
| `domain/alerting/engine.py` | 78 | `engine:` | Internal background engine identity check | **Prompt-48-Audit** |
| `domain/alerting/engine.py` | 78 | `system` | Internal background engine identity check | **Prompt-48-Audit** |
| `domain/attribution/governance_resolver.py` | 26 | `BUSINESS_OWNER` | Master data OWNER_TEAM role attribute matching | **Prompt-48-Audit** |
| `domain/bootstrap/superuser.py` | 57 | `2555` | Statutory 7-year audit retention requirement (365 * 7) | **Prompt-48-Audit** |
| `domain/cost/reconciliation/engine.py` | 323 | `Decimal('99.50')` | Executive trust score tier thresholds (99.5% and 98.0%) | **Prompt-48-Audit** |
| `domain/cost/reconciliation/engine.py` | 325 | `Decimal('98.00')` | Executive trust score tier thresholds (99.5% and 98.0%) | **Prompt-48-Audit** |
| `domain/cost/reconciliation/engine.py` | 494 | `2` | Minimum sample size for half-split trend comparison | **Prompt-48-Audit** |
| `domain/cost/reconciliation/engine.py` | 701 | `Decimal('5.00')` | Investigation severity variance threshold | **Prompt-48-Audit** |
| `domain/forecasting/accuracy.py` | 40 | `0.75` | Standard quarterly milestone thresholds (25%, 50%, 75%) | **Prompt-48-Audit** |
| `domain/forecasting/accuracy.py` | 42 | `0.5` | Standard quarterly milestone thresholds (25%, 50%, 75%) | **Prompt-48-Audit** |
| `domain/forecasting/accuracy.py` | 44 | `0.25` | Standard quarterly milestone thresholds (25%, 50%, 75%) | **Prompt-48-Audit** |
| `domain/forecasting/engine.py` | 211 | `0.9` | Empirical statistical confidence score for historical baseline | **Prompt-48-Audit** |
| `domain/forecasting/engine.py` | 322 | `0.9` | Empirical statistical confidence score for seasonal pattern | **Prompt-48-Audit** |
| `domain/forecasting/engine.py` | 506 | `0.3` | Cost trend spiking threshold ratio (30%) | **Prompt-48-Audit** |
| `domain/forecasting/engine.py` | 514 | `0.4` | Cost trend volatility coefficient of variation threshold (0.40) | **Prompt-48-Audit** |
| `domain/forecasting/engine.py` | 530 | `0.05` | Cost trend normalized slope drift threshold (5%) | **Prompt-48-Audit** |
| `domain/hierarchy/service.py` | 750 | `CRITICAL` | Canonical threshold state string | **Prompt-48-Audit** |
| `domain/hierarchy/service.py` | 752 | `WARNING` | Canonical threshold state string | **Prompt-48-Audit** |
| `domain/hierarchy/service.py` | 2128 | `0.9` | Search ranking score weight | **Prompt-48-Audit** |
| `domain/identity/password_hasher.py` | 22 | `30` | RFC 6238 TOTP standard interval of 30 seconds | **security-arch** |
| `domain/observability/health.py` | 65 | `0.9` | Simulated probe latency metric | **Prompt-48-Audit** |
| `domain/pricing/repository.py` | 103 | `1e-09` | Floating point pricing comparison epsilon | **Prompt-48-Audit** |
| `domain/provisioning/service.py` | 135 | `@` | Check if user identifier contains email domain delimiter | **Prompt-48-Audit** |
| `domain/resource_detail/service.py` | 1355 | `0.9` | Derivation multiplier for estimated cost | **Prompt-48-Audit** |
| `domain/resource_detail/service.py` | 1771 | `RESTRICTED_VIEWER` | Restricted viewer role permission boundary check | **Prompt-48-Audit** |
| `domain/resource_detail/service.py` | 2007 | `STOPPED` | Runtime stopped state check | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 69 | `#10b981` | Canonical UI runtime state hex colour code | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 71 | `#64748b` | Canonical UI runtime state hex colour code | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 73 | `#f59e0b` | Canonical UI runtime state hex colour code | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 75 | `#94a3b8` | Canonical UI runtime state hex colour code | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 78 | `#94a3b8` | Canonical UI runtime state hex colour code | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 81 | `#94a3b8` | Canonical UI runtime state hex colour code | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 82 | `#94a3b8` | Canonical UI runtime state hex colour code | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 145 | `#10b981` | Canonical UI adherence badge hex colour code | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 147 | `#3b82f6` | Canonical UI adherence badge hex colour code | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 149 | `#f59e0b` | Canonical UI adherence badge hex colour code | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 151 | `#ef4444` | Canonical UI adherence badge hex colour code | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 154 | `#94a3b8` | Canonical UI adherence badge hex colour code | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 157 | `#94a3b8` | Canonical UI adherence badge hex colour code | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 159 | `#94a3b8` | Canonical UI adherence badge hex colour code | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 160 | `#94a3b8` | Canonical UI adherence badge hex colour code | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 412 | `#10b981` | Disallowed green shade hex values for runtime compliance validation | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 412 | `#22c55e` | Disallowed green shade hex values for runtime compliance validation | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 412 | `#16a34a` | Disallowed green shade hex values for runtime compliance validation | **Prompt-48-Audit** |
| `domain/runtime/models.py` | 412 | `#15803d` | Disallowed green shade hex values for runtime compliance validation | **Prompt-48-Audit** |
| `domain/statements/acceptance.py` | 94 | `7` | SLA escalation threshold days | **Prompt-48-Audit** |
| `domain/statements/acceptance.py` | 96 | `3` | SLA reminder threshold days | **Prompt-48-Audit** |
| `domain/statements/acceptance.py` | 124 | `5` | SLA overdue threshold days | **Prompt-48-Audit** |
| `domain/statements/disputes.py` | 66 | `5` | Minimum dispute justification text length | **Prompt-48-Audit** |
| `domain/statements/generator.py` | 183 | `Decimal('10.0')` | Budget variance tolerance threshold percentage (10%) | **Prompt-48-Audit** |
| `domain/statements/generator.py` | 205 | `Decimal('50.00')` | Period cost movement significance threshold | **Prompt-48-Audit** |
| `domain/statements/generator.py` | 207 | `Decimal('-50.00')` | Period cost movement significance threshold | **Prompt-48-Audit** |
| `domain/thresholds/models.py` | 49 | `#10b981` | Canonical UI threshold state hex colour code | **Prompt-48-Audit** |
| `domain/thresholds/models.py` | 51 | `#f59e0b` | Canonical UI threshold state hex colour code | **Prompt-48-Audit** |
| `domain/thresholds/models.py` | 53 | `#f97316` | Canonical UI threshold state hex colour code | **Prompt-48-Audit** |
| `domain/thresholds/models.py` | 55 | `#ef4444` | Canonical UI threshold state hex colour code | **Prompt-48-Audit** |
| `domain/thresholds/models.py` | 57 | `#3b82f6` | Canonical UI threshold state hex colour code | **Prompt-48-Audit** |
| `domain/thresholds/models.py` | 59 | `#94a3b8` | Canonical UI threshold state hex colour code | **Prompt-48-Audit** |
| `domain/thresholds/models.py` | 60 | `#94a3b8` | Canonical UI threshold state hex colour code | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 159 | `#e2f0d9` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 160 | `#203764` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 162 | `#f2f2f2` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 163 | `#7f7f7f` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 165 | `#f8d7da` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 166 | `#721c24` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 168 | `#fff3cd` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 169 | `#856404` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 263 | `#ffffff` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 264 | `#cbd5e1` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 265 | `#10b981` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 268 | `#f1f5f9` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 269 | `#94a3b8` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 270 | `#64748b` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 273 | `#ef4444` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 274 | `#ef4444` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 276 | `#f59e0b` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/topology/exporter.py` | 277 | `#f59e0b` | Graphviz and DrawIO export styling colours | **Prompt-48-Audit** |
| `domain/workflows/service.py` | 325 | `GLOBAL_ADMIN` | Role authorization fallback check | **Prompt-48-Audit** |
| `domain/workflows/service.py` | 326 | `TENANT_ADMIN` | Role authorization fallback check | **Prompt-48-Audit** |
| `domain/workflows/service.py` | 720 | `TENANT_ADMIN` | Role authorization fallback check | **Prompt-48-Audit** |
| `workers/cloudlens_workers/scheduler.py` | 66 | `30.0` | Schedule refresh polling interval seconds | **Prompt-48-Audit** |
| `connectors/diagnostics/service.py` | 219 | `6` | Standard 6-hour reconciliation window slice for backfill planning | **enterprise-arch** |
