# CloudLens Audit Report v2.0

Generated **2026-10-11 19:57:59 UTC** | repo `CloudLens` | HEAD `6bda3885ba3c` | branch `main` | python `C:\Users\TEST\CloudLens\.venv\Scripts\python.exe`

> Every figure below was produced by a command or file scan in this run. Raw outputs: `audit_output/raw/`. Flags: `--run-tests` OFF, `--coverage` OFF, `--probe-startup` OFF

## 0. Findings summary — RED 0 | AMBER 14

| # | Severity | Area | Finding |
|---|---|---|---|
| 1 | AMBER | Git | Very large or multi-prompt commit: 6bda388|P19: Production Test Suite and CI (294 files, +9976) — hard to review; one prompt per commit expected |
| 2 | AMBER | Git | 13 uncommitted files — audit does not reflect a committed state |
| 3 | AMBER | Git | No commit message references R-SEC; no commit-level evidence it was executed |
| 4 | AMBER | Git | No commit message references R-QUAL; no commit-level evidence it was executed |
| 5 | AMBER | Git | No commit message references R-ROLES; no commit-level evidence it was executed |
| 6 | AMBER | Git | No commit message references R-PERSIST; no commit-level evidence it was executed |
| 7 | AMBER | Git | No commit message references R-DATA; no commit-level evidence it was executed |
| 8 | AMBER | Tests | tests/upgrade has only 1 tests — thin evidence for that test level |
| 9 | AMBER | Tests | tests/load has only 2 tests — thin evidence for that test level |
| 10 | AMBER | Tests | tests/rbac has only 3 tests — thin evidence for that test level |
| 11 | AMBER | Persistence | 52 non-test files hold in-memory cache/registry dicts |
| 12 | AMBER | Mandate M2 | Thresholds compared against Decimal literals in 28 file(s) — should come from master data |
| 13 | AMBER | Evidence | Evidence/docs cite 'zap' results but zap is not installed here — results cannot have been produced on this machine |
| 14 | AMBER | Security | 128 routes have no visible auth/tenant dependency in their signature — verify they are protected by middleware |

## 1. Git
- Commits **102** | uncommitted **13** | unpushed **no upstream**
- Prompt IDs in commit messages: `15B, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 31B, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 43, 47B, 50, 51, 52, 53, 54, 55, 56, 58, 59, 60, 61, CT, DOC, FEAT, FINAL, OBS, OPS, PERF, RUN, UI`
- Recent commit sizes:
```
 294 files +9976    6bda388|P19: Production Test Suite and CI
  59 files +1294    b2f24d3|P18: Evidence and Documentation Cleanup
  11 files +322     9ab3c2a|P17: Operational Hardening
   5 files +775     c6cdab2|P16: Control Tower With Measured Values Only
  13 files +3716    15249a0|P15: Configuration Panel and Editable Business Objects
   8 files +570     928016f|P14: Ingestion Pipeline on Schedule
  17 files +2332    8b6e032|P13: Cloud Connections UI — Real Read-Only Integration
  25 files +1999    9b80f8a|P13A: Real Cloud Connectors (Replace Fixtures with Provider APIs)
  20 files +3905    76daa55|P12: Tenant Administration and First-Run Setup
  39 files +1281    9c6b162|P11: Left Sidebar and Clean Labels
  31 files +58604   9206beb|P10: Wire Every Web Page to the API
  47 files +2589    18fc177|P09: Blank Application — Remove All Embedded Data
  69 files +4665    3ffbbb5|P08: Persistence Tier 5 — Remaining Modules and In-Memory Removal
  34 files +8512    117ebe7|P07: Persistence Tier 4 — Governance and Estate
  35 files +6101    ca1063e|P06: Persistence Tier 3 — Cost, Pricing, Budgets, Thresholds, Forecast, Reconcilia
```
Last 15 commits:
```
6bda388|2026-10-12|P19: Production Test Suite and CI
b2f24d3|2026-10-11|P18: Evidence and Documentation Cleanup
9ab3c2a|2026-10-11|P17: Operational Hardening
c6cdab2|2026-10-10|P16: Control Tower With Measured Values Only
15249a0|2026-10-10|P15: Configuration Panel and Editable Business Objects
928016f|2026-10-10|P14: Ingestion Pipeline on Schedule
8b6e032|2026-10-10|P13: Cloud Connections UI — Real Read-Only Integration
9b80f8a|2026-10-10|P13A: Real Cloud Connectors (Replace Fixtures with Provider APIs)
76daa55|2026-10-10|P12: Tenant Administration and First-Run Setup
9c6b162|2026-10-10|P11: Left Sidebar and Clean Labels
9206beb|2026-10-10|P10: Wire Every Web Page to the API
18fc177|2026-10-10|P09: Blank Application — Remove All Embedded Data
3ffbbb5|2026-10-09|P08: Persistence Tier 5 — Remaining Modules and In-Memory Removal
117ebe7|2026-10-09|P07: Persistence Tier 4 — Governance and Estate
ca1063e|2026-10-09|P06: Persistence Tier 3 — Cost, Pricing, Budgets, Thresholds, Forecast, Reconciliation
```
Uncommitted:
```
 M docs/configuration/exception_register.json
 M docs/configuration/exception_register_summary.md
 M docs/configuration/identity_verification_report.json
 M docs/configuration/identity_verification_summary.md
 M domain/identity/models.py
 M scripts/check_no_hardcoded_constants.py
 M tests/dr/test_disaster_recovery.py
?? docs/go_live_checklist.md
?? docs/uat_sign_off.md
?? ops/helm/cloudlens/values-uat.yaml
?? scripts/activate_superuser_uat.py
?? scripts/run_business_user_uat.py
?? scripts/run_uat_drills.py
```

## 2. Size
- Files **1079** | non-blank lines **398896**

| Top-level | Files | LOC |
|---|---|---|
| domain | 338 | 97620 |
| docs | 51 | 88849 |
| web | 84 | 80825 |
| tests | 177 | 51786 |
| (root) | 14 | 17065 |
| connectors | 86 | 16626 |
| api | 63 | 16070 |
| masterdata | 69 | 8583 |
| scripts | 51 | 8553 |
| db | 30 | 4818 |
| ops | 48 | 3256 |
| fat | 11 | 2112 |
| workers | 6 | 1624 |
| artifacts | 4 | 411 |
| normalisation | 7 | 406 |
| .github | 2 | 254 |
| data | 38 | 38 |

| Language | Files | LOC |
|---|---|---|
| Python | 764 | 205548 |
| JSON | 125 | 102976 |
| TypeScript | 82 | 80775 |
| Markdown | 62 | 5699 |
| YAML | 39 | 3513 |
| TOML | 2 | 151 |
| PowerShell | 2 | 133 |
| Template | 1 | 67 |
| JavaScript | 1 | 24 |
| Shell | 1 | 10 |

Key directories:
- **api/**: cloudlens_api
- **domain/**: abuse, adoption, alerting, analytics, attribution, audit, bootstrap, budgets, bulk_import, catalogues, commitments, config, connectors, control_tower, cost, credentials, dashboards, demo, dependency, diagnostics, explanation, forecasting, hierarchy, identity, integrations, lifecycle, maintenance, models, notification, observability, overrides, planning, policy, pricing, provisioning, quotas, rbac, release, remediation, reports, resource_detail, rules, runtime, statements, sync, synthetic, tenant, thresholds, topology, usage, wizard, workflows
- **connectors/**: aws, azure, conformance, contract, diagnostics, fixtures, gcp, oci, simulator, stub, sync, wizard
- **normalisation/**: mappings, tags, units
- **masterdata/**: catalogues, registries, seeds
- **db/**: aggregates, lifecycle, migrations, partitioning, schema, seeds
- **web/**: public, screenshots, src, tests
- **tests/**: acceptance, adoption, analytics, cloud_provider, commitments, connectors, contracts, control_tower, cost_reconciliation, data, data_validation, dr, e2e, failure_injection, fakes, fixtures, improvements, integration, integrations, lifecycle, load, mandates, masterdata, perf, planning, playwright, rbac, regression, security, ui, unit, upgrade, workers, workflow
- **ops/**: alertmanager, cosign, dashboards, docker, grafana, helm, keycloak, loki, otel, prometheus, promtail, sbom, tempo
- **scripts/**: (files only)
- **docs/**: analytics, configuration, connectors, decisions, permissions, security
- **workers/**: cloudlens_workers
- **fat/**: (files only)

## 3. Tests
- Collected **1522** | collection errors **0** | collect exit 0
- Tests not executed in this run (use `--run-tests`).

| Test directory | Tests |
|---|---|
| unit | 1034 |
| security | 136 |
| integration | 66 |
| contracts | 30 |
| e2e | 26 |
| workers | 26 |
| acceptance | 25 |
| integrations | 17 |
| adoption | 16 |
| lifecycle | 14 |
| improvements | 13 |
| cloud_provider | 9 |
| commitments | 9 |
| control_tower | 9 |
| cost_reconciliation | 8 |
| mandates | 8 |
| analytics | 7 |
| connectors | 7 |
| failure_injection | 7 |
| perf | 7 |
| planning | 7 |
| masterdata | 6 |
| ui | 6 |
| data_validation | 5 |
| dr | 5 |
| workflow | 5 |
| data | 4 |
| regression | 4 |
| rbac | 3 |
| load | 2 |
| upgrade | 1 |

## 4. Coverage
- {'status': 'not run (use --coverage)'}

## 5. Quality gates
- **layering**: exit 0 — [PASS] Layering rule check passed. Zero forbidden provider SDK imports above connector layer.
- **no_hardcoded_constants**: exit 0 — Allow-listed exceptions recorded: 48 / [GATE RESULT: REPORT MODE] Exiting with status 0 (Reporting mode for CI).
- **ruff**: exit 0 — 
- **ruff F-class findings**:
```
api\cloudlens_api\routes\__init__.py:1:54: F401 `api.cloudlens_api.routes.about.router` imported but unused; consider removing, adding to `__all__`, or using a redundant alias
api\cloudlens_api\routes\__init__.py:12:57: F401 `api.cloudlens_api.routes.calendar.router` imported but unused; consider removing, adding to `__all__`, or using a redundant alias
api\cloudlens_api\routes\auth.py:25:24: F401 [*] `sqlalchemy.select` imported but unused
api\cloudlens_api\routes\auth.py:28:30: F401 [*] `db.schema.tables.TenantModel` imported but unused
api\cloudlens_api\routes\auth.py:29:24: F401 [*] `db.session.get_tenant_session` imported but unused
api\cloudlens_api\routes\auth.py:33:36: F401 [*] `domain.identity.models.AuthContext` imported but unused
api\cloudlens_api\routes\auth.py:40:5: F401 [*] `domain.models.exceptions.NoMappedRoleException` imported but unused
api\cloudlens_api\routes\auth.py:47:5: F401 [*] `domain.models.exceptions.UserNotProvisionedException` imported but unused
api\cloudlens_api\routes\business_objects.py:23:22: F401 [*] `datetime.UTC` imported but unused
api\cloudlens_api\routes\connectors.py:24:38: F401 [*] `connectors.contract.base.BaseCloudConnector` imported but unused
api\cloudlens_api\routes\control_tower.py:29:5: F401 [*] `domain.control_tower.models.BlastRadius` imported but unused
api\cloudlens_api\routes\control_tower.py:31:5: F401 [*] `domain.control_tower.models.ControlTowerActionResult` imported but unused
api\cloudlens_api\routes\credentials.py:23:41: F401 [*] `fastapi.Header` imported but unused
api\cloudlens_api\routes\inventory.py:32:33: F401 [*] `domain.models.enums.PricingStatus` imported but unused
api\cloudlens_api\routes\inventory.py:32:48: F401 [*] `domain.models.enums.ProviderType` imported but unused
api\cloudlens_api\routes\inventory.py:32:62: F401 [*] `domain.models.enums.ServiceCategory` imported but unused
api\cloudlens_api\routes\rbac.py:23:81: F401 [*] `domain.models.enums.SystemRole` imported but unused
api\cloudlens_api\routes\tenants.py:23:42: F401 [*] `domain.tenant.models.TenantStatus` imported but unused
connectors\contract\checkpoint_store.py:16:8: F401 [*] `os` imported but unused
connectors\contract\checkpoint_store.py:17:8: F401 [*] `sys` imported but unused
connectors\contract\checkpoint_store.py:41:13: F841 Local variable `loop` is assigned to but never used
connectors\contract\raw_landing.py:14:8: F401 [*] `asyncio` imported but unused
connectors\contract\raw_landing.py:15:8: F401 [*] `concurrent.futures` imported but unused
connectors\contract\raw_landing.py:19:8: F401 [*] `os` imported but unused
connectors\contract\raw_landing.py:20:8: F401 [*] `sys` imported but unused
connectors\factory.py:22:33: F401 [*] `domain.models.enums.ProviderType` imported but unused
connectors\gcp\cost.py:16:8: F401 [*] `json` imported but unused
connectors\oci\cost.py:15:8: F401 [*] `csv` imported but unused
connectors\oci\cost.py:16:8: F401 [*] `io` imported but unused
connectors\oci\cost.py:17:8: F401 [*] `json` imported but unused
```
- **web_typecheck**: exit 0 —  (TS errors 0)

## 6. Persistence and fail-closed startup
- `domain/**/repository.py` files: **33** | using SQL: **33**
- Non-test files holding state in Python dicts: **52** | files using a DB session: **37** | files with `class InMemory*`: **0** | files with `class Sql*Repository`: **34**
- Migrations: **17** | tables created: **133** | RLS statements: **22** | code that sets `app.current_tenant`: **11** file(s)
- Migration files:
```
db/migrations/versions/001_initial_schema.py
db/migrations/versions/002_partitioned_facts.py
db/migrations/versions/003_materialized_aggregates.py
db/migrations/versions/004_expand_migrate_contract.py
db/migrations/versions/005_catalogues_and_gap_registry.py
db/migrations/versions/006_master_data_framework.py
db/migrations/versions/007_tenant_isolation_and_overrides.py
db/migrations/versions/008_connector_contract_and_capabilities.py
db/migrations/versions/009_sync_orchestration_and_wizard.py
db/migrations/versions/010_onboarding_step_restoration_and_alert_test.py
db/migrations/versions/011_persistence_foundation_and_rls.py
db/migrations/versions/012_persistence_tier1_identity_audit_config.py
db/migrations/versions/013_persistence_tier2_unique_idempotency.py
db/migrations/versions/014_persistence_tier3_cost_budgets_pricing.py
db/migrations/versions/015_persistence_tier4_governance_and_estate.py
db/migrations/versions/016_persistence_tier5_remaining_modules.py
db/migrations/versions/017_tenant_administration_fields.py
```
- Environment guards found:
```
api/cloudlens_api/routes/provisioning.py:76: intended_environment: str = Field(..., description="Target environment (PROD, STAGING, DEV)")
api/cloudlens_api/routes/runtime.py:231: environment=request.environment or "production",
domain/analytics/models.py:132: ..., description="Descriptive environment classification: Production, Staging, etc."
domain/budgets/templates.py:165: display_name="Environment Sandbox/Production Spend Cap Template",
domain/budgets/templates.py:166: description="Environment isolation budget ceiling (e.g. dev sandbox cap or production baseline).",
domain/bulk_import/catalogue.py:366: description="Environment tiers (Production, Staging, Dev) with production flags.",
domain/bulk_import/catalogue.py:381: description="Environment code (e.g. ENV-PROD, ENV-STAGING)",
domain/models/inventory.py:121: name: str = Field(..., description="Environment name (e.g. Production, Staging, QA)")
domain/policy/models.py:118: description="Target deployment environments (PROD, DEV, STAGING, etc.)",
domain/provisioning/models.py:142: default="*", description="Deployment environment (PROD, STAGING, DEV, or '*')"
```

## 7. Security checks
| Check | Files | Examples |
|---|---|---|
| superuser_literal_in_app_code | 0 |  |
| email_identity_comparison | 0 |  |
| secret_like_defaults | 0 |  |
| inmemory_secret_fallback | 0 |  |
| break_glass_provision_route | 0 |  |
| secret_returned_or_printed | 1 | domain/credentials/store.py:45: Returns an opaque reference URI (e.g. vault://secret/data/tenants/{tenant_id}/credentials/{profile_id}/v{version}). |
| cors_wildcard | 0 |  |
| debug_true | 0 |  |
| verify_false | 0 |  |
| sql_string_format | 0 |  |
| sample_people_in_app_code | 0 |  |
| email_literals_in_app_code | 17 | connectors/fixtures/aws_cur_sample.json:23: "resourceTags/user:Owner": "platform-team@company.internal",<br>connectors/fixtures/aws_cur_sample.json:47: "resourceTags/user:Owner": "data-engineering@company.internal",<br>connectors/fixtures/gcp_billing_export_sample.json:26: { "key": "owner", "value": "banking-eng@cloudlens.internal" }, |

- `health_check()` returning constant True: none

## 8. Hard-coding exception register
- File: `docs/configuration/exception_register.json` | entries: **7** | missing reason/reviewer: **0**
- By area: `{'?': 7}`
- Entries touching sensitive areas:
```
"file_path": "domain/identity/password_hasher.py",
"reason": "Standard 6-hour reconciliation window slice for backfill planning",
```
- Comparisons against Decimal literals: **28** file(s)
```
domain/adoption/value_ledger.py:63: if dec_amount <= Decimal("0.00"):
domain/adoption/value_ledger.py:163: if platform_cost.total_platform_cost > Decimal("0.00"):
domain/attribution/aggregation.py:189: if other_amount > Decimal("0.00"):
domain/catalogues/unit_service.py:44: if val < Decimal("0"):
domain/catalogues/unit_service.py:102: if eff_duration <= Decimal("0"):
domain/commitments/service.py:146: coverage_ratio = (cov_dec / el_dec) if el_dec > Decimal("0.00") else Decimal("0.0000")
domain/commitments/service.py:150: (act_dec / cost_dec) if cost_dec > Decimal("0.00") else Decimal("0.0000")
domain/commitments/service.py:159: if coverage_ratio >= Decimal("0.8000") and utilization_ratio < Decimal("0.8500"):
```

## 9. Evidence integrity (fat/, README, docs)
- fat/ files:
```
fat/ACCEPTANCE.md (13269 B)
fat/BASELINE_VS_FINAL.md (5759 B)
fat/FAT_RESULTS.md (3513 B)
fat/acceptance_criteria_results.md (471 B)
fat/baseline_audit_7831aa5.json (84559 B)
fat/cost_register.md (5708 B)
fat/coverage.xml (90359 B)
fat/decision_log_extract.md (24774 B)
fat/exception_register.md (3555 B)
fat/gate_constants.txt (182 B)
fat/gate_layering.txt (387 B)
fat/gate_ruff.txt (91 B)
fat/go_live_readiness.md (4269 B)
fat/junit.xml (205329 B)
fat/performance_benchmark.md (2803 B)
fat/test_summary.md (4568 B)
```
- Tool claims vs tools installed here:

| Tool | Mentioned in fat/docs/README | Installed |
|---|---|---|
| helm | 3 file(s) | True |
| kubeconform | 2 file(s) | True |
| gitleaks | 2 file(s) | True |
| trivy | 0 file(s) | False |
| k6 | 0 file(s) | False |
| zap | 2 file(s) | False |
| cosign | 1 file(s) | True |
| kubectl | 5 file(s) | True |
- Metric values hard-coded in scripts: **0** file(s)
```

```
- fat/ACCEPTANCE.md status words: `{'PASS': 75, 'FAIL': 1, 'UNVERIFIED': 1, 'NOT TESTABLE': 1}`
  - AC-040: `| **AC-040** | Closed-period report shows platform total, provider total, and variance within agreed tolerance | `domain/cost/reconciliation/` | `test_reconciliation_pass_within_absolute_tolerance` | `
  - AC-101: `absent`
  - AC-103: `absent`
  - AC-104: `| **AC-104** | Independent third-party penetration testing | External Red-Team | Scheduled for dedicated production staging environment | **OPEN** |`
- Numeric claims in fat/README/cost register (sample):
```
README.md:5: [![BBP v1.1](https://img.shields.io/badge/BBP-458%20Requirements%20Traceable-blue.svg)](docs/requirement_traceability_matrix.md)
README.md:6: [![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](pyproject.toml)
README.md:7: [![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](pyproject.toml)
README.md:9: [![FOCUS 1.0](https://img.shields.io/badge/FOCUS-1.0%20Compliant-orange.svg)](docs/data-dictionary.md)
README.md:235: E --> F{"Is Delta > $100.00<br/>OR Delta > 0.1%?"}
README.md:322: $$\text{Platform ROI Multiple} = \frac{\sum \text{Realised Savings}_{\text{Empirical}}}{\text{Total Platform Running Cost}}$$
README.md:343: ROI["Platform ROI Multiple"]
README.md:354: TotS & TotC --> Net & ROI
README.md:355: Net & ROI & DQ & Funnel --> Pack
README.md:375: - **Recovery Time Objective (RTO)**: Target SLA $\le$ 4 hours. See [Disaster Recovery Verification](fat/FAT_RESULTS.md).
README.md:376: - **Recovery Point Objective (RPO)**: Target SLA $\le$ 1 hour with continuous WAL archiving. See [Disaster Recovery Architecture](docs/enterprise-datacenter-deployment-gu
docs/cost-register.md:18: | **Daily Collection Cost (Total)** | **$\le$ \$25.00 / day** | **\$14.20 / day** | **-43.2% (Nominal / Healthy)** |
docs/cost-register.md:19: | **Monthly Collection Cost (Total)** | **$\le$ \$750.00 / month** | **\$426.00 / month** | **-43.2% (Under Budget)** |
docs/cost-register.md:20: | **Collection Cost as % of Managed Spend** | **$\le$ 0.05%** | **0.0096%** | **Optimal FinOps ROI** |
docs/cost-register.md:21: | **Emergency Kill-Switch Threshold** | **\$100.00 / day** | N/A | Circuit Breaker Armed |
docs/cost-register.md:22: | **Runaway Query Circuit Breaker** | **\$10.00 / query** | **Max \$0.42 / query** | Pass |
docs/cost-register.md:29: - **Daily Cost**: **\$4.80 / day**
docs/cost-register.md:31: - AWS Cost and Usage Report (CUR 2.0) delivered to S3 bucket: \$0.15 / day (S3 standard storage + GET requests).
docs/cost-register.md:32: - AWS Organizations & Resource Explorer queries: \$0.00 / day (included in AWS free tier).
docs/cost-register.md:33: - AWS CloudWatch Metrics queries (GetMetricData API): \$3.85 / day (approx. 77,000 metric requests/month @ \$0.01 per 1,000 metrics requested).
docs/cost-register.md:34: - Cross-region data egress: \$0.80 / day (approx. 9 GB/day at standard inter-region transfer rates).
docs/cost-register.md:40: - **Daily Cost**: **\$3.90 / day**
docs/cost-register.md:42: - Azure Cost Management Scheduled Exports to Blob Storage: \$0.20 / day (storage + read transactions).
docs/cost-register.md:43: - Azure Resource Graph (ARG) queries: \$0.00 / day (free tier within throttled quota limits).
docs/cost-register.md:44: - Azure Monitor Metrics REST API (batch queries): \$3.10 / day (approx. 155,000 API calls/month).
```

## 10. Deployment and runtime
- Helm charts: `['ops/helm/cloudlens']`
  - ops/helm/cloudlens templates (20): _helpers.tpl, api-deployment.yaml, api-hpa.yaml, api-pdb.yaml, api-service.yaml, backup-cnpg.yaml, backup-openbao-snapshot.yaml, backup-velero-schedule.yaml, beat-deployment.yaml, bootstrap-49a-job.yaml, configmap.yaml, ingress.yaml, migrate-job.yaml, networkpolicy.yaml, serviceaccount.yaml, servicemonitor.yaml, superuser-49b-job.yaml, web-deployment.yaml, web-service.yaml, worker-deployment.yaml
- helm lint: `{'exit': 0, 'tail': ['[INFO] Chart.yaml: icon is recommended', '', '1 chart(s) linted, 0 chart(s) failed']}`
- Possible secrets in values files: 0
- Dockerfiles: ['ops/docker/Dockerfile.api', 'ops/docker/Dockerfile.web', 'ops/docker/Dockerfile.web.dev', 'ops/docker/Dockerfile.worker'] | without non-root USER: none
- Compose services: docker-compose.yml:postgres, docker-compose.yml:redis, docker-compose.yml:minio, docker-compose.yml:openbao, docker-compose.yml:mailpit, docker-compose.yml:keycloak, docker-compose.yml:api, docker-compose.yml:worker, docker-compose.yml:web, docker-compose.yml:prometheus, docker-compose.yml:alertmanager, docker-compose.yml:grafana, docker-compose.yml:loki, docker-compose.yml:promtail, docker-compose.yml:tempo, docker-compose.yml:otel-collector, docker-compose.yml:postgres-exporter, docker-compose.yml:redis-exporter, docker-compose.yml:celery-exporter, docker-compose.yml:pgdata, docker-compose.yml:redisdata, docker-compose.yml:miniodata, docker-compose.yml:prometheusdata, docker-compose.yml:alertmanagerdata, docker-compose.yml:grafanadata, docker-compose.yml:lokidata, docker-compose.yml:tempodata
- Celery tasks registered (26): cloudlens.health, cloudlens.overrides.revert_expired, cloudlens.tasks.apply_retention_and_downsampling, cloudlens.tasks.auto_resolve_alerts, cloudlens.tasks.collect_quota, cloudlens.tasks.compute_forecasts, cloudlens.tasks.credential_expiry_check, cloudlens.tasks.discover_relationships, cloudlens.tasks.escalate_alerts, cloudlens.tasks.evaluate_policies, cloudlens.tasks.evaluate_thresholds, cloudlens.tasks.export_daily_audit_bundle, cloudlens.tasks.generate_freshness_sla_report, cloudlens.tasks.heartbeat, cloudlens.tasks.ingest_cost, cloudlens.tasks.ingest_inventory, cloudlens.tasks.ingest_usage, cloudlens.tasks.maintain_partitions, cloudlens.tasks.reconcile_closed_period, cloudlens.tasks.refresh_pricing, cloudlens.tasks.renewal_pipeline, cloudlens.tasks.revert_overrides, cloudlens.tasks.run_analytical_extract, cloudlens.tasks.run_synthetic_journey_monitor, cloudlens.tasks.send_daily_platform_summary, cloudlens.tasks.verify_remediation
- Beat schedule evidence:
```
workers/cloudlens_workers/celery_app.py:34: beat_scheduler="workers.cloudlens_workers.scheduler.DatabaseBeatScheduler",
```
- Tools on this machine:

| Tool | Version |
|---|---|
| docker | Docker version 29.8.1, build 4a63305 |
| helm | v4.3.0+gbec5b06 |
| kubectl | Client Version: v1.35.3-dispatcher |
| kubeconform | v0.8.0 |
| gitleaks | 8.30.1 |
| trivy | NOT INSTALLED |
| k6 | NOT INSTALLED |
| cosign | ______   ______        _______. __    _______ .__   __. |
| node | v24.11.1 |
| pnpm | NOT FOUND: [WinError 2] The system cannot find the file specified |

## 11. API and Web
- API routes: **303** | routes with no visible auth dependency: **128**
- Routes by prefix:
```
  29 /api/v1/masterdata
  18 /api/v1/alerts
  18 /api/v1/connectors
  18 /api/v1/control-tower
  17 /api/v1/system
  16 /api/v1/imports
  14 /api/v1/auth
  14 /api/v1/policies
  13 /api/v1/dependencies
  13 /api/v1/statements
  11 /api/v1/admin
  11 /api/v1/tenants
   9 /api/v1/budgets
   9 /api/v1/wizard
   8 /api/v1/analytics
   8 /api/v1/sync
   7 /api/v1/topology
   6 /api/v1/cost
   6 /api/v1/pricing
   6 /api/v1/rbac
   5 /api/v1/attribution
   5 /api/v1/business-objects
   5 /api/v1/reports
   4 /api/v1/features
   4 /api/v1/dashboards
   4 /api/v1/users
   3 /api/v1/health
   3 /api/v1/hierarchy
   3 /api/v1/inventory
   3 /api/v1/thresholds
   2 /api/v1/commitments
   2 /api/v1/resource-detail
   1 /
   1 /api/v1/about
   1 /api/v1/config
   1 /ready
   1 /metrics
   1 /api/v1/roles
   1 /api/v1/runtime
   1 /api/v1/scopes
   1 /api/v1/usage
```
- No visible auth dependency (verify middleware):
```
api/cloudlens_api/routes/admin.py: GET /rbac/access-review/export
api/cloudlens_api/routes/admin.py: GET /overrides
api/cloudlens_api/routes/alerts.py: GET /catalogue
api/cloudlens_api/routes/alerts.py: GET 
api/cloudlens_api/routes/alerts.py: GET /contextual
api/cloudlens_api/routes/alerts.py: GET /delivery-logs
api/cloudlens_api/routes/analytics.py: POST /extracts
api/cloudlens_api/routes/analytics.py: GET /extracts
api/cloudlens_api/routes/analytics.py: GET /reference/cost-pack
api/cloudlens_api/routes/attribution.py: POST /tags/normalise
api/cloudlens_api/routes/attribution.py: POST /ownership/resolve
api/cloudlens_api/routes/attribution.py: GET /allocation/rules
api/cloudlens_api/routes/attribution.py: POST /allocation/evaluate
api/cloudlens_api/routes/attribution.py: POST /allocation/aggregate
api/cloudlens_api/routes/auth.py: GET /oidc/authorize
api/cloudlens_api/routes/auth.py: GET /oidc/callback
api/cloudlens_api/routes/auth.py: POST /step-up/verify
api/cloudlens_api/routes/bootstrap.py: POST /pre-identity
api/cloudlens_api/routes/bootstrap.py: GET /pre-identity/status
api/cloudlens_api/routes/budgets.py: GET 
api/cloudlens_api/routes/bulk_import.py: GET /entities
api/cloudlens_api/routes/bulk_import.py: GET /entities/{entity_type}
api/cloudlens_api/routes/bulk_import.py: GET /templates/{entity_type}
api/cloudlens_api/routes/bulk_import.py: GET /export/{entity_type}
api/cloudlens_api/routes/bulk_import.py: GET /profiles
api/cloudlens_api/routes/bulk_import.py: GET /dry-run/{dry_run_id}/result
api/cloudlens_api/routes/bulk_import.py: POST /{dry_run_id}/apply
api/cloudlens_api/routes/bulk_import.py: GET /history
api/cloudlens_api/routes/business_objects.py: GET /{entity_type}
api/cloudlens_api/routes/business_objects.py: PUT /{entity_type}/{object_id}
api/cloudlens_api/routes/calendar.py: GET /calendar
api/cloudlens_api/routes/config.py: GET /features
api/cloudlens_api/routes/config.py: GET /features/{flag_key}/evaluate
api/cloudlens_api/routes/config.py: POST /features/{flag_key}/toggle
api/cloudlens_api/routes/config.py: GET /features/audit-log
api/cloudlens_api/routes/connectors.py: GET /{connector_id}/landings
api/cloudlens_api/routes/connectors.py: PATCH /{connector_id}
api/cloudlens_api/routes/connectors.py: GET /{connector_id}/jobs
api/cloudlens_api/routes/control_tower.py: GET /audit/tail
api/cloudlens_api/routes/control_tower.py: POST /actions/{action_name}
```
- Web pages (38): AboutPage.tsx, AdminConsolePage.tsx, AuditLogPage.tsx, BudgetManagementPage.tsx, BudgetPlanningPage.tsx, CommitmentRenewalsPage.tsx, ConnectorManagementPage.tsx, ControlTowerPage.tsx, CostEstimatorPage.tsx, CostExplorerPage.tsx, DependencyGraphPage.tsx, DesignSystemShowcase.tsx, ExecutiveDashboard.tsx, ExplanationLayerView.tsx, ForbiddenPage.tsx, HierarchyExplorer.tsx, InvestigationViewPage.tsx, LandingPage.tsx, LoginPage.tsx, MasterDataConsole.tsx, NotFoundPage.tsx, OnboardingWizardPage.tsx, PolicyManagementPage.tsx, ProviderDashboard.tsx, ProvisioningRequestsPage.tsx, QuotaHeadroomPage.tsx, RemediationBoardPage.tsx, ReportsPage.tsx, ResourceDetailPage.tsx, RuntimeViewPage.tsx, ServiceDashboard.tsx, ServiceInventory.tsx, SettingsPage.tsx, SetupWizardPage.tsx, ShowbackStatementsPage.tsx, TenantsPage.tsx, UsageDetailPage.tsx, UsersRbacPage.tsx
- Web route definitions found: **70** | Playwright specs: 8
- Screen presence:

| Screen | Page file |
|---|---|
| S-01 Login | yes |
| S-02 Landing | yes |
| S-03 Executive | yes |
| S-04 Provider | yes |
| S-05 Hierarchy | yes |
| S-06 Inventory | yes |
| S-07 Resource | yes |
| S-08 Cost | yes |
| S-09 Usage | yes |
| S-10 Runtime | yes |
| S-11 Dependency | yes |
| S-12 Budget | yes |
| S-13 Policy | yes |
| S-14 Onboarding | yes |
| S-15 Connectors | yes |
| S-16 Admin | yes |
| S-17 RBAC | yes |
| S-18 Audit | yes |
| S-19 Reports | yes |
| S-20 Settings | yes |
| S-21 Estimator | yes |
| S-22 Quota | yes |
| S-23 Provisioning | yes |
| S-24 Tasks | yes |
| S-25 Statements | yes |
| S-26 Planning | yes |
| S-27 Commitments | yes |
| Control Tower | yes |

## 12. Docs and traceability
- Docs: 51 files | duplicates: none
- rtm_distinct_ids: `458`
- rtm_ids_by_prefix: `{'AC': 78, 'API': 66, 'BR': 18, 'CON': 32, 'CST': 32, 'DEP': 18, 'DR': 7, 'FR': 89, 'NFR': 50, 'PR': 20, 'RUN': 10, 'SEC': 31, 'USE': 10}`
- rtm_status_words: `{'partial': 1, 'pass': 421, 'implemented - unverified': 36, 'verified': 2, 'implemented': 1, 'fail': 1}`
- rtm_rows_with_test_reference: `2`
- register_ac_count: `76`
- README statements containing figures/claims (each needs a source):
```
$$\text{Platform ROI Multiple} = \frac{\sum \text{Realised Savings}_{\text{Empirical}}}{\text{Total Platform Running Cost}}$$
ROI["Platform ROI Multiple"]
TotS & TotC --> Net & ROI
Net & ROI & DQ & Funnel --> Pack
- **Recovery Time Objective (RTO)**: Target SLA $\le$ 4 hours. See [Disaster Recovery Verification](fat/FAT_RESULTS.md).
- **Recovery Point Objective (RPO)**: Target SLA $\le$ 1 hour with continuous WAL archiving. See [Disaster Recovery Architecture](docs/enterprise-datacenter-dep
│   ├── upgrade/                   # Rolling Upgrade Zero-Downtime Tests
| **Factory Acceptance Test Summary** | [`fat/test_summary.md`](fat/test_summary.md) | Verified test execution evidence ([350 Passed / 4 Skipped](fat/test_summa
```

## 13. Specification pattern checks
| Check | Files | Distinct | Expect | Notes |
|---|---|---|---|---|
| ROLES_BBP_NINE | 1 | 9 | 9 | APPLICATION_OWNER, AUDITOR, CLOUD_ADMINISTRATOR, FINANCE_USER, FINOPS_ADMINISTRATOR, IT_OPERATIONS_USER, PLATFORM_ADMIN, READ_ONLY_USER |
| ROLES_NON_BBP | 0 | 0 | 0 |  |
| ALERT_IDS | 15 | 20 | 20 | missing: none |
| POLICY_IDS | 23 | 18 | 18 | missing: none |
| REQ_PREFIXES | 6 | 6 | 6 | missing: none |
| PLATFORM_OBSERVE | 7 | 1 | 1 | platform.observe |
| ACT_AS_TENANT | 11 | 5 | 1 | ACT_AS, Act-As, Act-as, act-as, act_as |
| CONTROL_TOWER | 15 | 5 | 1 | CONTROL_TOWER, Control-Tower, ControlTower, control-tower, control_tower |
| DEMO_MODE | 36 | 6 | 1 | DEMO MODE, DEMO_MODE, Demo Mode, DemoMode, demo mode, demo_mode |
| SIMULATOR | 2 | 2 | 1 | class ProviderSimulatorConnector, class SimulatorProfile |
| QUOTA | 47 | 3 | 1 | QUOTA, Quota, quota |
| PROVISIONING_GATE | 20 | 6 | 1 | GATE, Gate, REQUEST, Request, gate, request |
| SHOWBACK | 21 | 3 | 1 | SHOWBACK, Showback, showback |
| BULK_IMPORT_DRYRUN | 16 | 7 | 1 | DRY_RUN, Dry-Run, Dry-run, DryRun, dry-run, dry_run, dryrun |
| MASTER_REGISTRY | 8 | 2 | 1 | MasterRegistry, SYSTEM_MASTER_REGISTRY |
| MAINTENANCE_MODE | 9 | 6 | 1 | MAINTENANCE_MODE, Maintenance Mode, Maintenance mode, MaintenanceMode, maintenance mode, maintenance_mode |
| SESSION_REVOKE | 2 | 2 | 1 | /sessions, revoke_session |
| FIRST_SYNC | 8 | 5 | 1 | FIRST_SYNC, First sync, FirstSync, first sync, first_sync |
| ALERT_DELIVERY_TEST | 6 | 9 | 1 | Alert Delivery Test, Alert delivery test, AlertDeliveryTest, TEST_ALERT, Test alert, TestAlert, alert delivery test, test alert |
| PROVIDER_SDK_LEAK | 0 | 0 | 0 |  |
| TODO_FIXME | 0 | 0 | - |  |
| NOT_IMPLEMENTED_OUTSIDE_ABSTRACT | 2 | 1 | - | raise NotImplementedError |
| PASS_ONLY_FUNCTIONS | 0 | 0 | - |  |

---
End of report. Paste this whole file back for review. Attach `audit_output/audit_full.json` if asked.