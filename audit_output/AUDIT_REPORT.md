# CloudLens Audit Report v2.0

Generated **2026-10-06 05:55:01 UTC** | repo `CloudLens` | HEAD `e3b3f747fc30` | branch `main` | python `C:\Users\TEST\CloudLens\.venv\Scripts\python.exe`

> Every figure below was produced by a command or file scan in this run. Raw outputs: `audit_output/raw/`. Flags: `--run-tests` ON, `--coverage` ON, `--probe-startup` ON

## 0. Findings summary — RED 6 | AMBER 19

| # | Severity | Area | Finding |
|---|---|---|---|
| 1 | RED | Persistence | 87 non-test files hold state in Python dicts |
| 2 | RED | Security | health_check() returns constant True in: domain/credentials/store.py |
| 3 | RED | Security | Secret-like default values in code |
| 4 | RED | Evidence | fat/control_tower_screenshot.jpg carries AI-generation / content-credential markers ['c2pa', 'C2PA', 'jumb', 'trainedAlgorithmicMedia'] — not valid test evidence |
| 5 | RED | Evidence | Metric values (RTO/RPO/latency/cost/ROI) appear hard-coded in 6 script(s) that generate FAT evidence — they must be measured, not written |
| 6 | RED | Evidence | AC-040 (two closed billing periods reconciled) marked PASS — impossible without live billing periods |
| 7 | AMBER | Git | Very large or multi-prompt commit: 2027ff7|feat(platform): release authoritative enterprise governance platform (R-RUN, R-OBS (250 files, +21422) — hard to review; one prompt per commit expected |
| 8 | AMBER | Git | No commit message references R-SEC; no commit-level evidence it was executed |
| 9 | AMBER | Git | No commit message references R-QUAL; no commit-level evidence it was executed |
| 10 | AMBER | Git | No commit message references R-ROLES; no commit-level evidence it was executed |
| 11 | AMBER | Git | No commit message references R-PERSIST; no commit-level evidence it was executed |
| 12 | AMBER | Git | No commit message references R-DATA; no commit-level evidence it was executed |
| 13 | AMBER | Tests | tests/upgrade has only 1 tests — thin evidence for that test level |
| 14 | AMBER | Tests | tests/load has only 2 tests — thin evidence for that test level |
| 15 | AMBER | Tests | tests/rbac has only 3 tests — thin evidence for that test level |
| 16 | AMBER | Security | A break-glass provision route still referenced — only one break-glass path is allowed |
| 17 | AMBER | Security | cors wildcard: 1 file(s) |
| 18 | AMBER | Gates | Hard-coding gate passes with 84 allow-listed exceptions — review whether findings were exempted rather than fixed |
| 19 | AMBER | Mandate M2 | Thresholds compared against Decimal literals in 28 file(s) — should come from master data |
| 20 | AMBER | Evidence | Evidence/docs cite 'gitleaks' results but gitleaks is not installed here — results cannot have been produced on this machine |
| 21 | AMBER | Evidence | Evidence/docs cite 'trivy' results but trivy is not installed here — results cannot have been produced on this machine |
| 22 | AMBER | Evidence | Evidence/docs cite 'zap' results but zap is not installed here — results cannot have been produced on this machine |
| 23 | AMBER | Deployment | Dockerfiles without a non-root USER: ['ops/docker/Dockerfile.api', 'ops/docker/Dockerfile.web', 'ops/docker/Dockerfile.worker'] |
| 24 | AMBER | Security | 134 routes have no visible auth/tenant dependency in their signature — verify they are protected by middleware |
| 25 | AMBER | Docs | Duplicate documents: ['exception_register', 'identity_verification_report', 'pre_identity_verification_report', 'pricing_dimensions_reconciled', 'sbom'] |

## 1. Git
- Commits **78** | uncommitted **0** | unpushed **no upstream**
- Prompt IDs in commit messages: `15B, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 31B, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 43, 47B, 50, 51, 52, 53, 54, 55, 56, 58, 59, 60, 61, CT, DOC, FEAT, FINAL, OBS, OPS, PERF, RUN, UI`
- Recent commit sizes:
```
   1 files +919     e3b3f74|Add files via upload
   2 files +85      205761a|chore(audit): update exception register timestamps
   3 files +19      e3549ad|fix(migrations): widen alembic_version version_num to varchar(128) and update boot
  35 files +2847    2db198c|feat(r-final): complete re-audit, fat package assembly, baseline delta, and go-liv
  30 files +4071    51d29c2|docs(r-doc): rebuild documentation from evidence, on-prem lld, rtm generator, and 
  11 files +1206    ea1cc4f|feat(perf): real load, DR failover, zero-downtime upgrade, security scans, and 20-
 250 files +21422   2027ff7|feat(platform): release authoritative enterprise governance platform (R-RUN, R-OBS
   1 files +374     7831aa5|chore: add cloudlens_audit.py script
   1 files +1       d01098a|chore: add audit_output/ to .gitignore
   1 files +512     c4b90ce|docs: update README.md with comprehensive LLD, architecture diagrams, FAT matrix, 
  15 files +2901    3303556|feat(adoption): implement Prompt 61 adoption analytics, value ledger, and review p
  18 files +3870    6cb8436|feat(integrations): implement Prompt 60 integration hub, adapters, event replay, a
   8 files +487     d6c1024|feat(lifecycle): complete Prompt 59 resource lifecycle, decommissioning workflow, 
   5 files +499     9813329|feat(commitments): complete commitment renewal, workflow routing, and alerting (Pr
   2 files +143     25c68bc|docs: add provider capability register and open items register (Prompt 43)
```
Last 15 commits:
```
e3b3f74|2026-10-06|Add files via upload
205761a|2026-10-06|chore(audit): update exception register timestamps
e3549ad|2026-10-06|fix(migrations): widen alembic_version version_num to varchar(128) and update bootstrap identity verification
2db198c|2026-10-06|feat(r-final): complete re-audit, fat package assembly, baseline delta, and go-live readiness
51d29c2|2026-10-06|docs(r-doc): rebuild documentation from evidence, on-prem lld, rtm generator, and fat artifacts
ea1cc4f|2026-10-06|feat(perf): real load, DR failover, zero-downtime upgrade, security scans, and 20-level markers (Prompt R-PERF)
2027ff7|2026-10-06|feat(platform): release authoritative enterprise governance platform (R-RUN, R-OBS, R-CT, R-OPS, R-UI, R-FEAT)
7831aa5|2026-10-04|chore: add cloudlens_audit.py script
d01098a|2026-10-04|chore: add audit_output/ to .gitignore
c4b90ce|2026-10-04|docs: update README.md with comprehensive LLD, architecture diagrams, FAT matrix, and SRE runbook
3303556|2026-10-04|feat(adoption): implement Prompt 61 adoption analytics, value ledger, and review pack
6cb8436|2026-10-04|feat(integrations): implement Prompt 60 integration hub, adapters, event replay, and sandbox
d6c1024|2026-10-04|feat(lifecycle): complete Prompt 59 resource lifecycle, decommissioning workflow, and residue tasks
9813329|2026-10-04|feat(commitments): complete commitment renewal, workflow routing, and alerting (Prompt 58)
25c68bc|2026-10-04|docs: add provider capability register and open items register (Prompt 43)
```

## 2. Size
- Files **920** | non-blank lines **303425**

| Top-level | Files | LOC |
|---|---|---|
| domain | 327 | 86036 |
| docs | 44 | 85388 |
| tests | 119 | 40215 |
| web | 68 | 24503 |
| connectors | 83 | 15800 |
| (root) | 13 | 14287 |
| api | 61 | 13786 |
| masterdata | 67 | 8006 |
| scripts | 39 | 5585 |
| db | 23 | 2894 |
| ops | 46 | 2793 |
| fat | 11 | 2132 |
| workers | 6 | 1011 |
| artifacts | 4 | 411 |
| normalisation | 7 | 399 |
| .github | 2 | 179 |

| Language | Files | LOC |
|---|---|---|
| Python | 672 | 173111 |
| JSON | 84 | 97301 |
| TypeScript | 66 | 24454 |
| Markdown | 55 | 5133 |
| YAML | 38 | 3192 |
| TOML | 2 | 135 |
| Template | 1 | 67 |
| PowerShell | 1 | 22 |
| Shell | 1 | 10 |

Key directories:
- **api/**: cloudlens_api
- **domain/**: abuse, adoption, alerting, analytics, attribution, audit, bootstrap, budgets, bulk_import, catalogues, commitments, config, control_tower, cost, credentials, dashboards, demo, dependency, diagnostics, explanation, forecasting, hierarchy, identity, integrations, lifecycle, maintenance, models, notification, observability, overrides, planning, policy, pricing, provisioning, quotas, rbac, release, remediation, reports, resource_detail, rules, runtime, statements, sync, synthetic, tenant, thresholds, topology, usage, wizard, workflows
- **connectors/**: aws, azure, conformance, contract, diagnostics, fixtures, gcp, oci, simulator, stub, sync, wizard
- **normalisation/**: mappings, tags, units
- **masterdata/**: catalogues, registries, seeds
- **db/**: aggregates, lifecycle, migrations, partitioning, schema, seeds
- **web/**: public, src, tests
- **tests/**: acceptance, adoption, analytics, cloud_provider, commitments, connectors, contracts, control_tower, cost_reconciliation, data, data_validation, dr, e2e, failure_injection, improvements, integration, integrations, lifecycle, load, mandates, masterdata, perf, planning, rbac, regression, security, ui, unit, upgrade, workers, workflow
- **ops/**: alertmanager, cosign, dashboards, docker, grafana, helm, keycloak, loki, otel, prometheus, promtail, sbom, tempo
- **scripts/**: (files only)
- **docs/**: analytics, configuration, connectors, decisions, permissions, security
- **workers/**: cloudlens_workers
- **fat/**: (files only)

## 3. Tests
- Collected **1413** | collection errors **0** | collect exit 0
- EXECUTED: **1413** | passed **1409** | failed **0** | errors **0** | skipped **4** | 265.5s
- Random-order run: `{'exit': 0, 'tail': ['=========== 1409 passed, 4 skipped, 1 warning in 261.06s (0:04:21) ============']}`
- Skipped (reasons):
```
SKIPPED [1] tests\integration\test_database_real.py:74: Real PostgreSQL instance is not reachable at localhost:5432. Skipping real database integration test. (Strict constraint: Mock databases are str
SKIPPED [1] tests\integration\test_database_real.py:84: Real PostgreSQL instance is not reachable at localhost:5432. Skipping real database integration test. (Strict constraint: Mock databases are str
SKIPPED [1] tests\integration\test_database_real.py:145: Real PostgreSQL instance is not reachable at localhost:5432. Skipping real database integration test. (Strict constraint: Mock databases are st
SKIPPED [1] tests\integration\test_database_real.py:171: Real PostgreSQL instance is not reachable at localhost:5432. Skipping real database integration test. (Strict constraint: Mock databases are st
```

| Test directory | Tests |
|---|---|
| unit | 1026 |
| security | 95 |
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
| integration | 6 |
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

Slowest tests:
```
8.1s tests.workers.test_scheduled_work_suite::test_beat_leader_lock_prevents_duplicate_runs
8.1s tests.workers.test_scheduled_work_suite::test_task_concurrency_lock
6.5s tests.unit.test_bulk_import_framework.Test5000RowBulkImportAndProvenance::test_five_thousand_row_import_lifecycle
5.6s tests.unit.test_layering::test_layering_rule_passes_on_clean_codebase
4.3s tests.workers.test_scheduled_work_suite::test_database_beat_scheduler_zero_cron_literals
4.3s tests.workers.test_scheduled_work_suite::test_canonical_task_execution[send_daily_platform_summary]
4.3s tests.workers.test_scheduled_work_suite::test_canonical_task_execution[run_analytical_extract]
4.1s tests.workers.test_scheduled_work_suite::test_canonical_task_execution[verify_remediation]
4.1s tests.workers.test_scheduled_work_suite::test_canonical_task_execution[ingest_usage]
4.1s tests.workers.test_scheduled_work_suite::test_canonical_task_execution[heartbeat]
```

## 4. Coverage
- Total: **87%** over domain, api, connectors, normalisation, masterdata, workers

## 5. Quality gates
- **layering**: exit 0 — [PASS] Layering rule check passed. Zero forbidden provider SDK imports above connector layer.
- **no_hardcoded_constants**: exit 0 — [PASS] Zero hard-coding scan passed cleanly! (84 allow-listed exceptions in register)
- **ruff**: exit 1 — Found 1 error. / [*] 1 fixable with the `--fix` option.
- **ruff F-class findings**:
```
api\cloudlens_api\routes\__init__.py:1:54: F401 `api.cloudlens_api.routes.about.router` imported but unused; consider removing, adding to `__all__`, or using a redundant alias
api\cloudlens_api\routes\__init__.py:11:57: F401 `api.cloudlens_api.routes.calendar.router` imported but unused; consider removing, adding to `__all__`, or using a redundant alias
api\cloudlens_api\routes\control_tower.py:29:5: F401 [*] `domain.control_tower.models.BlastRadius` imported but unused
api\cloudlens_api\routes\control_tower.py:31:5: F401 [*] `domain.control_tower.models.ControlTowerActionResult` imported but unused
api\cloudlens_api\routes\inventory.py:32:33: F401 [*] `domain.models.enums.PricingStatus` imported but unused
api\cloudlens_api\routes\inventory.py:32:48: F401 [*] `domain.models.enums.ProviderType` imported but unused
api\cloudlens_api\routes\inventory.py:32:62: F401 [*] `domain.models.enums.ServiceCategory` imported but unused
domain\attribution\governance_resolver.py:10:20: F401 [*] `typing.Any` imported but unused
domain\control_tower\service.py:30:32: F401 [*] `datetime.timedelta` imported but unused
domain\control_tower\service.py:34:8: F401 [*] `httpx` imported but unused
domain\control_tower\service.py:46:38: F401 [*] `domain.credentials.store.get_secret_store` imported but unused
domain\control_tower\service.py:48:34: F401 [*] `domain.observability.metrics` imported but unused
domain\control_tower\service.py:52:5: F401 [*] `domain.sync.repository.get_connector_schedule_repository` imported but unused
domain\control_tower\service.py:396:9: F811 Redefinition of unused `metrics` from line 48: `metrics` redefined here
domain\synthetic\journey_monitor.py:20:33: F401 [*] `domain.models.enums.AlertSeverity` imported but unused
domain\synthetic\journey_monitor.py:20:48: F401 [*] `domain.models.enums.AlertStatus` imported but unused
domain\synthetic\journey_monitor.py:45:9: F841 Local variable `tc` is assigned to but never used
domain\synthetic\journey_monitor.py:68:13: F841 Local variable `cost_engine` is assigned to but never used
domain\synthetic\journey_monitor.py:105:17: F841 Local variable `alert_svc` is assigned to but never used
scripts\count_level_markers.py:6:8: F401 [*] `subprocess` imported but unused
scripts\count_level_markers.py:7:8: F401 [*] `sys` imported but unused
scripts\generate_fat_package.py:22:22: F401 [*] `datetime.datetime` imported but unused
scripts\generate_fat_package.py:22:32: F401 [*] `datetime.timezone` imported but unused
scripts\generate_fat_package.py:24:38: F401 [*] `xml.etree.ElementTree` imported but unused
scripts\generate_fat_package.py:140:9: F841 Local variable `content` is assigned to but never used
scripts\generate_rtm.py:21:8: F401 [*] `os` imported but unused
scripts\generate_rtm.py:23:8: F401 [*] `sys` imported but unused
scripts\run_proof_tasks.py:15:8: F401 [*] `time` imported but unused
scripts\run_proof_tasks.py:16:22: F401 [*] `datetime.UTC` imported but unused
scripts\run_proof_tasks.py:16:27: F401 [*] `datetime.datetime` imported but unused
```
- **web_typecheck**: exit 0 —  (TS errors 0)

## 6. Persistence and fail-closed startup
- `domain/**/repository.py` files: **26** | using SQL: **23**
- Non-test files holding state in Python dicts: **87** | files using a DB session: **6** | files with `class InMemory*`: **2** | files with `class Sql*Repository`: **0**
- Migrations: **10** | tables created: **49** | RLS statements: **10** | code that sets `app.current_tenant`: **2** file(s)
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
```
- repository.py files with NO SQL (in-memory):
```
domain/catalogues/repository.py
domain/pricing/repository.py
domain/provisioning/repository.py
```
- Startup probe with no Vault/DB reachable (expect REFUSED):
  - `production`: `REFUSED_TO_START exit 1`
  - `staging`: `REFUSED_TO_START exit 1`
- Environment guards found:
```
api/cloudlens_api/routes/provisioning.py:76: intended_environment: str = Field(..., description="Target environment (PROD, STAGING, DEV)")
api/cloudlens_api/routes/runtime.py:231: environment=request.environment or "production",
domain/analytics/models.py:132: ..., description="Descriptive environment classification: Production, Staging, etc."
domain/budgets/templates.py:165: display_name="Environment Sandbox/Production Spend Cap Template",
domain/budgets/templates.py:166: description="Environment isolation budget ceiling (e.g. dev sandbox cap or production baseline).",
domain/bulk_import/catalogue.py:366: description="Environment tiers (Production, Staging, Dev) with production flags.",
domain/bulk_import/catalogue.py:381: description="Environment code (e.g. ENV-PROD, ENV-STAGING)",
domain/hierarchy/service.py:106: {"key": "Environment", "value": "Production"},
domain/hierarchy/service.py:144: {"key": "Environment", "value": "Production"},
domain/hierarchy/service.py:181: {"key": "Environment", "value": "Production"},
```

## 7. Security checks
| Check | Files | Examples |
|---|---|---|
| superuser_literal_in_app_code | 0 |  |
| email_identity_comparison | 0 |  |
| secret_like_defaults | 1 | domain/identity/models.py:136: token_type: str = Field(default="Bearer", description="Token type descriptor") |
| inmemory_secret_fallback | 0 |  |
| break_glass_provision_route | 1 | api/cloudlens_api/routes/auth.py:6: - POST /api/v1/auth/break-glass/provision: Strictly limited emergency break-glass account setup (Item 65). |
| secret_returned_or_printed | 1 | domain/credentials/store.py:45: Returns an opaque reference URI (e.g. vault://secret/data/tenants/{tenant_id}/credentials/{profile_id}/v{version}).<br>domain/credentials/store.py:152: return copy.deepcopy(secret) |
| cors_wildcard | 1 | api/cloudlens_api/main.py:209: allow_origins=["*"], |
| debug_true | 0 |  |
| verify_false | 0 |  |
| sql_string_format | 0 |  |
| sample_people_in_app_code | 0 |  |
| email_literals_in_app_code | 14 | connectors/fixtures/aws_cur_sample.json:23: "resourceTags/user:Owner": "platform-team@company.internal",<br>connectors/fixtures/aws_cur_sample.json:47: "resourceTags/user:Owner": "data-engineering@company.internal",<br>connectors/fixtures/gcp_billing_export_sample.json:26: { "key": "owner", "value": "banking-eng@cloudlens.internal" }, |

- `health_check()` returning constant True: ['domain/credentials/store.py']

## 8. Hard-coding exception register
- File: `docs/configuration/exception_register.json` | entries: **84** | missing reason/reviewer: **0**
- By area: `{'?': 84}`
- Entries touching sensitive areas:
```
"file_path": "api/cloudlens_api/tenant_context.py",
"literal_value": "SUPER_ADMIN",
"file_path": "api/cloudlens_api/tenant_context.py",
"literal_value": "GLOBAL_ADMIN",
"file_path": "domain/cost/reconciliation/engine.py",
"reason": "Executive trust score tier thresholds (99.5% and 98.0%)",
"file_path": "domain/cost/reconciliation/engine.py",
"reason": "Executive trust score tier thresholds (99.5% and 98.0%)",
"file_path": "domain/cost/reconciliation/engine.py",
"file_path": "domain/cost/reconciliation/engine.py",
"reason": "Investigation severity variance threshold",
"reason": "Standard quarterly milestone thresholds (25%, 50%, 75%)",
"reason": "Standard quarterly milestone thresholds (25%, 50%, 75%)",
"reason": "Standard quarterly milestone thresholds (25%, 50%, 75%)",
"reason": "Cost trend spiking threshold ratio (30%)",
"reason": "Cost trend volatility coefficient of variation threshold (0.40)",
"reason": "Cost trend normalized slope drift threshold (5%)",
"reason": "Canonical threshold state string",
"reason": "Canonical threshold state string",
"file_path": "domain/identity/password_hasher.py",
"literal_value": "@",
"file_path": "domain/statements/acceptance.py",
"reason": "SLA escalation threshold days",
"file_path": "domain/statements/acceptance.py",
"reason": "SLA reminder threshold days",
"file_path": "domain/statements/acceptance.py",
"reason": "SLA overdue threshold days",
"file_path": "domain/statements/disputes.py",
"file_path": "domain/statements/generator.py",
"reason": "Budget variance tolerance threshold percentage (10%)",
```
- Comparisons against Decimal literals: **28** file(s)
```
domain/adoption/value_ledger.py:63: if dec_amount <= Decimal("0.00"):
domain/adoption/value_ledger.py:161: if platform_cost.total_platform_cost > Decimal("0.00"):
domain/attribution/aggregation.py:189: if other_amount > Decimal("0.00"):
domain/catalogues/unit_service.py:44: if val < Decimal("0"):
domain/catalogues/unit_service.py:102: if eff_duration <= Decimal("0"):
domain/commitments/service.py:140: coverage_ratio = (cov_dec / el_dec) if el_dec > Decimal("0.00") else Decimal("0.0000")
domain/commitments/service.py:143: utilization_ratio = (act_dec / cost_dec) if cost_dec > Decimal("0.00") else Decimal("0.0000")
domain/commitments/service.py:151: if coverage_ratio >= Decimal("0.8000") and utilization_ratio < Decimal("0.8500"):
```

## 9. Evidence integrity (fat/, README, docs)
- fat/ files:
```
fat/ACCEPTANCE.md (13248 B)
fat/BASELINE_VS_FINAL.md (5759 B)
fat/FAT_RESULTS.md (3587 B)
fat/acceptance_criteria_results.md (471 B)
fat/baseline_audit_7831aa5.json (84559 B)
fat/control_tower_screenshot.jpg (620032 B)
fat/cost_register.md (5708 B)
fat/coverage.xml (90359 B)
fat/decision_log_extract.md (17814 B)
fat/exception_register.md (10709 B)
fat/gate_constants.txt (182 B)
fat/gate_layering.txt (161 B)
fat/gate_ruff.txt (59 B)
fat/go_live_readiness.md (4272 B)
fat/junit.xml (205329 B)
fat/performance_benchmark.md (2803 B)
fat/test_summary.md (4568 B)
```
- Image `fat/control_tower_screenshot.jpg` (620032 B) markers: `['c2pa', 'C2PA', 'jumb', 'trainedAlgorithmicMedia']` | git: `2db198c 2026-10-06 feat(r-final): complete re-audit, fat package assembly, baseline delta, and go-live readiness`
- Tool claims vs tools installed here:

| Tool | Mentioned in fat/docs/README | Installed |
|---|---|---|
| helm | 2 file(s) | True |
| kubeconform | 2 file(s) | True |
| gitleaks | 3 file(s) | False |
| trivy | 1 file(s) | False |
| k6 | 0 file(s) | False |
| zap | 3 file(s) | False |
| cosign | 1 file(s) | True |
| kubectl | 4 file(s) | True |
- Metric values hard-coded in scripts: **6** file(s)
```
scripts/generate_fat_package.py:121: "| **DR-001** | CloudNativePG Primary Crash & Failover | **18.4s RTO / 0 byte loss** | RTO $\\le 4\\text{h}$, RPO $= 0$ | **PASS** |",
scripts/run_dr_exercise.py:67: print(f"{'DR-001':<10} | {'Full Restoration RTO':<36} | {'<= 4.0 hours':<16} | {f'{elapsed:.3f}s':<12} | {'PASS'}")
scripts/run_dr_exercise.py:68: print(f"{'DR-002':<10} | {'Configuration & Telemetry RPO':<36} | {'<= 1.0 hour':<16} | {'0.000s':<12} | {'PASS'}")
scripts/run_scale_load_test.py:88: """NFR-011: Bulk cost ingestion throughput must process >= 10,000 records/sec."""
scripts/run_scale_load_test.py:188: """NFR-016: Database read replica average query latency <= 50ms."""
scripts/run_scale_load_test.py:214: """NFR-018: Background worker queue latency <= 5.0 seconds under peak sync load."""
scripts/run_scale_load_test.py:224: status = "PASS" if p95 <= 5.0 else "FAIL"
scripts/verify_all_levels.py:135: "Automated restore, failover, verification within RTO <= 4h, RPO <= 1h",
scripts/verify_release_readiness.py:122: return True, "RTO <= 4h, RPO <= 1h, zero data loss, rolling upgrade verified"
scripts/verify_seventeen_levels.py:130: "Automated restore, failover, verification within RTO <= 4h, RPO <= 1h",
```
- fat/ACCEPTANCE.md status words: `{'PASS': 76, 'FAIL': 1, 'UNVERIFIED': 1, 'NOT TESTABLE': 3}`
  - AC-040: `| **AC-040** | Orphaned disk and residue asset detection | `domain/lifecycle/` | `test_orphan_and_residue_detection` | **PASS** |`
  - AC-101: `absent`
  - AC-103: `absent`
  - AC-104: `| **AC-104** | Independent third-party penetration testing | External Red-Team | Scheduled for dedicated production staging environment | **NOT TESTABLE IN FAT (External Staging Engagement Required; a`
- Numeric claims in fat/README/cost register (sample):
```
README.md:4: [![Automated Tests](https://img.shields.io/badge/Tests-350%20Passed%20(FAT)-success.svg)](fat/test_summary.md)
README.md:5: [![BBP v1.1](https://img.shields.io/badge/BBP-458%20Requirements%20Traceable-blue.svg)](docs/requirement_traceability_matrix.md)
README.md:6: [![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](pyproject.toml)
README.md:7: [![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](pyproject.toml)
README.md:9: [![FOCUS 1.0](https://img.shields.io/badge/FOCUS-1.0%20Compliant-orange.svg)](docs/data-dictionary.md)
README.md:235: E --> F{"Is Delta > $100.00<br/>OR Delta > 0.1%?"}
README.md:322: $$\text{Platform ROI Multiple} = \frac{\sum \text{Realised Savings}_{\text{Empirical}}}{\text{Total Platform Running Cost}}$$
README.md:343: ROI["Platform ROI Multiple"]
README.md:354: TotS & TotC --> Net & ROI
README.md:355: Net & ROI & DQ & Funnel --> Pack
README.md:375: - **Recovery Time Objective (RTO)**: [RTO $\le$ 4 hours (measured 3.2m in drill)](fat/performance_benchmark.md).
README.md:376: - **Recovery Point Objective (RPO)**: [RPO $\approx$ 0 (< 60s WAL lag, 0 bytes lost)](fat/performance_benchmark.md).
README.md:496: | **Disaster Recovery RTO/RPO** | [5 DR Scenarios](fat/test_summary.md) | **RTO 3.2m / RPO 0 bytes lost** | [`fat/performance_benchmark.md`](fat/performance_benchmark.md)
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
```

## 10. Deployment and runtime
- Helm charts: `['ops/helm/cloudlens']`
  - ops/helm/cloudlens templates (20): _helpers.tpl, api-deployment.yaml, api-hpa.yaml, api-pdb.yaml, api-service.yaml, backup-cnpg.yaml, backup-openbao-snapshot.yaml, backup-velero-schedule.yaml, beat-deployment.yaml, bootstrap-49a-job.yaml, configmap.yaml, ingress.yaml, migrate-job.yaml, networkpolicy.yaml, serviceaccount.yaml, servicemonitor.yaml, superuser-49b-job.yaml, web-deployment.yaml, web-service.yaml, worker-deployment.yaml
- helm lint: `{'exit': 0, 'tail': ['[INFO] Chart.yaml: icon is recommended', '', '1 chart(s) linted, 0 chart(s) failed']}`
- Possible secrets in values files: 0
- Dockerfiles: ['ops/docker/Dockerfile.api', 'ops/docker/Dockerfile.web', 'ops/docker/Dockerfile.web.dev', 'ops/docker/Dockerfile.worker'] | without non-root USER: ['ops/docker/Dockerfile.api', 'ops/docker/Dockerfile.web', 'ops/docker/Dockerfile.worker']
- Compose services: docker-compose.yml:postgres, docker-compose.yml:redis, docker-compose.yml:minio, docker-compose.yml:vault, docker-compose.yml:api, docker-compose.yml:worker, docker-compose.yml:web, docker-compose.yml:prometheus, docker-compose.yml:alertmanager, docker-compose.yml:grafana, docker-compose.yml:loki, docker-compose.yml:promtail, docker-compose.yml:tempo, docker-compose.yml:otel-collector, docker-compose.yml:postgres-exporter, docker-compose.yml:redis-exporter, docker-compose.yml:celery-exporter, docker-compose.yml:mailpit, docker-compose.yml:keycloak, docker-compose.yml:pgdata, docker-compose.yml:redisdata, docker-compose.yml:miniodata, docker-compose.yml:prometheusdata, docker-compose.yml:alertmanagerdata, docker-compose.yml:grafanadata, docker-compose.yml:lokidata, docker-compose.yml:tempodata
- Celery tasks registered (26): cloudlens.health, cloudlens.overrides.revert_expired, cloudlens.tasks.apply_retention_and_downsampling, cloudlens.tasks.auto_resolve_alerts, cloudlens.tasks.collect_quota, cloudlens.tasks.compute_forecasts, cloudlens.tasks.credential_expiry_check, cloudlens.tasks.discover_relationships, cloudlens.tasks.escalate_alerts, cloudlens.tasks.evaluate_policies, cloudlens.tasks.evaluate_thresholds, cloudlens.tasks.export_daily_audit_bundle, cloudlens.tasks.generate_freshness_sla_report, cloudlens.tasks.heartbeat, cloudlens.tasks.ingest_cost, cloudlens.tasks.ingest_inventory, cloudlens.tasks.ingest_usage, cloudlens.tasks.maintain_partitions, cloudlens.tasks.reconcile_closed_period, cloudlens.tasks.refresh_pricing, cloudlens.tasks.renewal_pipeline, cloudlens.tasks.revert_overrides, cloudlens.tasks.run_analytical_extract, cloudlens.tasks.run_synthetic_journey_monitor, cloudlens.tasks.send_daily_platform_summary, cloudlens.tasks.verify_remediation
- Beat schedule evidence:
```
workers/cloudlens_workers/celery_app.py:31: beat_scheduler="workers.cloudlens_workers.scheduler.DatabaseBeatScheduler",
```
- Tools on this machine:

| Tool | Version |
|---|---|
| docker | Docker version 29.8.1, build 4a63305 |
| helm | v4.3.0+gbec5b06 |
| kubectl | Client Version: v1.35.3-dispatcher |
| kubeconform | v0.8.0 |
| gitleaks | NOT INSTALLED |
| trivy | NOT INSTALLED |
| k6 | NOT INSTALLED |
| cosign | ______   ______        _______. __    _______ .__   __. |
| node | v24.11.1 |
| pnpm | NOT FOUND: [WinError 2] The system cannot find the file specified |

## 11. API and Web
- API routes: **279** | routes with no visible auth dependency: **134**
- Routes by prefix:
```
  29 /api/v1/masterdata
  19 /api/v1/control-tower
  18 /api/v1/alerts
  17 /api/v1/system
  16 /api/v1/imports
  14 /api/v1/connectors
  14 /api/v1/policies
  13 /api/v1/dependencies
  13 /api/v1/statements
  12 /api/v1/auth
  11 /api/v1/admin
   9 /api/v1/wizard
   8 /api/v1/analytics
   8 /api/v1/budgets
   8 /api/v1/sync
   7 /api/v1/topology
   6 /api/v1/cost
   6 /api/v1/pricing
   6 /api/v1/rbac
   5 /api/v1/attribution
   5 /api/v1/reports
   4 /api/v1/features
   4 /api/v1/dashboards
   4 /api/v1/users
   3 /api/v1/health
   3 /api/v1/hierarchy
   3 /api/v1/inventory
   3 /api/v1/thresholds
   2 /api/v1/resource-detail
   1 /
   1 /api/v1/about
   1 /api/v1/commitments
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
api/cloudlens_api/routes/auth.py: POST /step-up/initiate
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
api/cloudlens_api/routes/cost.py: GET /summary
api/cloudlens_api/routes/cost.py: GET /drill-through
api/cloudlens_api/routes/cost.py: GET /timeseries
```
- Web pages (36): AboutPage.tsx, AdminConsolePage.tsx, AuditLogPage.tsx, BudgetManagementPage.tsx, BudgetPlanningPage.tsx, CommitmentRenewalsPage.tsx, ConnectorManagementPage.tsx, ControlTowerPage.tsx, CostEstimatorPage.tsx, CostExplorerPage.tsx, DependencyGraphPage.tsx, DesignSystemShowcase.tsx, ExecutiveDashboard.tsx, ExplanationLayerView.tsx, ForbiddenPage.tsx, HierarchyExplorer.tsx, InvestigationViewPage.tsx, LandingPage.tsx, LoginPage.tsx, MasterDataConsole.tsx, NotFoundPage.tsx, OnboardingWizardPage.tsx, PolicyManagementPage.tsx, ProviderDashboard.tsx, ProvisioningRequestsPage.tsx, QuotaHeadroomPage.tsx, RemediationBoardPage.tsx, ReportsPage.tsx, ResourceDetailPage.tsx, RuntimeViewPage.tsx, ServiceDashboard.tsx, ServiceInventory.tsx, SettingsPage.tsx, ShowbackStatementsPage.tsx, UsageDetailPage.tsx, UsersRbacPage.tsx
- Web route definitions found: **67** | Playwright specs: 1
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
- Docs: 44 files | duplicates: ['exception_register', 'identity_verification_report', 'pre_identity_verification_report', 'pricing_dimensions_reconciled', 'sbom']
- rtm_distinct_ids: `458`
- rtm_ids_by_prefix: `{'AC': 78, 'API': 66, 'BR': 18, 'CON': 32, 'CST': 32, 'DEP': 18, 'DR': 7, 'FR': 89, 'NFR': 50, 'PR': 20, 'RUN': 10, 'SEC': 31, 'USE': 10}`
- rtm_status_words: `{'fail': 1, 'implemented': 1, 'pass': 432, 'implemented - unverified': 27, 'verified': 2, 'partial': 1}`
- rtm_rows_with_test_reference: `2`
- register_ac_count: `76`
- README statements containing figures/claims (each needs a source):
```
[![Automated Tests](https://img.shields.io/badge/Tests-350%20Passed%20(FAT)-success.svg)](fat/test_summary.md)
$$\text{Platform ROI Multiple} = \frac{\sum \text{Realised Savings}_{\text{Empirical}}}{\text{Total Platform Running Cost}}$$
ROI["Platform ROI Multiple"]
TotS & TotC --> Net & ROI
Net & ROI & DQ & Funnel --> Pack
- **Recovery Time Objective (RTO)**: [RTO $\le$ 4 hours (measured 3.2m in drill)](fat/performance_benchmark.md).
- **Recovery Point Objective (RPO)**: [RPO $\approx$ 0 (< 60s WAL lag, 0 bytes lost)](fat/performance_benchmark.md).
│   ├── upgrade/                   # Rolling Upgrade Zero-Downtime Tests
| **Total Test Suite Execution** | [354 Testcases](fat/test_summary.md) | **350 Passed / 4 Skipped / 0 Failed** | [`fat/junit.xml`](fat/junit.xml) |
| **BBP Acceptance Criteria** | [76 Acceptance Criteria](fat/acceptance_criteria_results.md) | **75 Passed / 1 FAT-Exempt / 0 Failed** | [`fat/acceptance_criter
| **Disaster Recovery RTO/RPO** | [5 DR Scenarios](fat/test_summary.md) | **RTO 3.2m / RPO 0 bytes lost** | [`fat/performance_benchmark.md`](fat/performance_ben
| **Rolling Upgrade Continuity**| [1 Upgrade Drill](fat/test_summary.md) | **Zero Downtime, Zero Data Loss** | [`fat/test_summary.md`](fat/test_summary.md) |
| **Factory Acceptance Test Summary** | [`fat/test_summary.md`](fat/test_summary.md) | Verified test execution evidence ([350 Passed / 4 Skipped](fat/test_summa
```

## 13. Specification pattern checks
| Check | Files | Distinct | Expect | Notes |
|---|---|---|---|---|
| ROLES_BBP_NINE | 1 | 9 | 9 | APPLICATION_OWNER, AUDITOR, CLOUD_ADMINISTRATOR, FINANCE_USER, FINOPS_ADMINISTRATOR, IT_OPERATIONS_USER, PLATFORM_ADMIN, READ_ONLY_USER |
| ROLES_NON_BBP | 0 | 0 | 0 |  |
| ALERT_IDS | 13 | 20 | 20 | missing: none |
| POLICY_IDS | 21 | 18 | 18 | missing: none |
| REQ_PREFIXES | 6 | 6 | 6 | missing: none |
| PLATFORM_OBSERVE | 6 | 1 | 1 | platform.observe |
| ACT_AS_TENANT | 7 | 5 | 1 | ACT_AS, Act-As, Act-as, act-as, act_as |
| CONTROL_TOWER | 12 | 5 | 1 | CONTROL_TOWER, Control-Tower, ControlTower, control-tower, control_tower |
| DEMO_MODE | 33 | 6 | 1 | DEMO MODE, DEMO_MODE, Demo Mode, DemoMode, demo mode, demo_mode |
| SIMULATOR | 2 | 2 | 1 | class ProviderSimulatorConnector, class SimulatorProfile |
| QUOTA | 46 | 3 | 1 | QUOTA, Quota, quota |
| PROVISIONING_GATE | 19 | 6 | 1 | GATE, Gate, REQUEST, Request, gate, request |
| SHOWBACK | 21 | 3 | 1 | SHOWBACK, Showback, showback |
| BULK_IMPORT_DRYRUN | 16 | 7 | 1 | DRY_RUN, Dry-Run, Dry-run, DryRun, dry-run, dry_run, dryrun |
| MASTER_REGISTRY | 7 | 2 | 1 | MasterRegistry, SYSTEM_MASTER_REGISTRY |
| MAINTENANCE_MODE | 7 | 6 | 1 | MAINTENANCE_MODE, Maintenance Mode, Maintenance mode, MaintenanceMode, maintenance mode, maintenance_mode |
| SESSION_REVOKE | 2 | 2 | 1 | /sessions, revoke_session |
| FIRST_SYNC | 8 | 5 | 1 | FIRST_SYNC, First sync, FirstSync, first sync, first_sync |
| ALERT_DELIVERY_TEST | 6 | 9 | 1 | Alert Delivery Test, Alert delivery test, AlertDeliveryTest, TEST_ALERT, Test alert, TestAlert, alert delivery test, test alert |
| PROVIDER_SDK_LEAK | 0 | 0 | 0 |  |
| TODO_FIXME | 0 | 0 | - |  |
| NOT_IMPLEMENTED_OUTSIDE_ABSTRACT | 2 | 1 | - | raise NotImplementedError |
| PASS_ONLY_FUNCTIONS | 0 | 0 | - |  |

---
End of report. Paste this whole file back for review. Attach `audit_output/audit_full.json` if asked.