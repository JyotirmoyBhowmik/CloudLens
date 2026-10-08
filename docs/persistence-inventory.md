# CloudLens Platform Persistence Inventory (Prompt P03)

## 1. Executive Summary & Inventory Breakdown

In accordance with CloudLens Enterprise Architecture Standards and **Prompt P03**, this document catalogs all **87 in-memory dictionary stores and singletons** across the platform codebase. Stateful in-memory dictionaries are classified into four architectural tiers with their designated target persistence infrastructure.

### Persistence Tier Summary

| Tier | Category | Target Infrastructure | RLS Enforced | Count |
| :--- | :--- | :--- | :--- | :---: |
| **Tier 1** | **REPOSITORY** | PostgreSQL 16 (SQLAlchemy 2.0 Async + asyncpg) | Yes | **68** |
| **Tier 2** | **CACHE** | Redis / Valkey (Key-Value + TTL + Cluster) | No (Key Prefixed) | **7** |
| **Tier 3** | **FIXTURE** | Isolated Test Fakes (`tests/fakes/`) & Object Storage (MinIO) | N/A | **4** |
| **Tier 4** | **CONFIG** | PostgreSQL Master Data Tables & OpenBao Transit/KV | System / Tenant | **8** |
| **TOTAL** | | | | **87** |

---

## 2. Tier 1: REPOSITORY (68 Dict Holders)

Domain repositories represent business-critical, persistent state. In staging and production, these stores must strictly execute via `Sql<Name>Repository` backed by PostgreSQL 16 using `SET LOCAL app.current_tenant_id` within transactions and PostgreSQL Row-Level Security (`FORCE ROW LEVEL SECURITY`).

| # | File Path | Class / Component | Attribute / Field | Target Persistence Table / Schema |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `domain/config/tenant_settings.py` | `TenantSettingsStore` | `_tenants` | `tenant_settings` (Reference Impl - P03) |
| 2 | `domain/alerting/repository.py` | `AlertRepository` | `_alerts` | `alerts` |
| 3 | `domain/alerting/repository.py` | `AlertRepository` | `_subscriptions` | `alert_subscriptions` |
| 4 | `domain/alerting/repository.py` | `AlertRepository` | `_delivery_logs` | `alert_delivery_logs` |
| 5 | `domain/alerting/contextual.py` | `ContextualAlertEngine` | `_alerts` | `contextual_alerts` |
| 6 | `domain/alerting/channels/in_app.py` | `InAppChannelAdapter` | `_inboxes` | `in_app_notifications` |
| 7 | `domain/analytics/repository.py` | `AnalyticsRepository` | `_jobs` | `analytics_jobs` |
| 8 | `domain/analytics/repository.py` | `AnalyticsRepository` | `_snapshots` | `analytics_snapshots` |
| 9 | `domain/analytics/watermark.py` | `WatermarkTracker` | `_watermarks` | `partition_watermarks` |
| 10 | `domain/commitments/repository.py` | `CommitmentRepository` | `_commitments` | `commitments` |
| 11 | `domain/commitments/repository.py` | `CommitmentRepository` | `_recommendations` | `commitment_recommendations` |
| 12 | `domain/commitments/repository.py` | `CommitmentRepository` | `_utilization_history` | `commitment_utilization_history` |
| 13 | `domain/commitments/repository.py` | `CommitmentRepository` | `_coverage_snapshots` | `commitment_coverage_snapshots` |
| 14 | `domain/commitments/repository.py` | `CommitmentRepository` | `_exchanges` | `commitment_exchanges` |
| 15 | `domain/commitments/ledger.py` | `AmortizationLedger` | `_entries` | `amortization_ledger_entries` |
| 16 | `connectors/contract/checkpoint_store.py` | `CheckpointStore` | `_checkpoints` | `connector_checkpoints` |
| 17 | `connectors/contract/raw_landing.py` | `RawLandingStore` | `_landings` | `raw_landing_records` |
| 18 | `connectors/contract/lifecycle.py` | `ConnectorLifecycleTracker` | `_states` | `connector_lifecycle_states` |
| 19 | `connectors/contract/lifecycle.py` | `ConnectorLifecycleTracker` | `_capability_health` | `connector_capability_health` |
| 20 | `domain/corrections/repository.py` | `CorrectionRepository` | `_records` | `cost_corrections` |
| 21 | `domain/corrections/repository.py` | `CorrectionRepository` | `_reversals` | `cost_correction_reversals` |
| 22 | `domain/overrides/repository.py` | `OverrideRepository` | `_records` | `rate_overrides` |
| 23 | `domain/cost/repository.py` | `CostRepository` | `_actuals` | `cost_actuals` |
| 24 | `domain/cost/repository.py` | `CostRepository` | `_allocations` | `cost_allocations` |
| 25 | `domain/hierarchy/service.py` | `HierarchyService` | `_resources` | `resources` |
| 26 | `domain/hierarchy/service.py` | `HierarchyService` | `_budgets` | `budgets` |
| 27 | `domain/hierarchy/service.py` | `HierarchyService` | `_saved_views` | `hierarchy_saved_views` |
| 28 | `domain/dependency/repository.py` | `DependencyRepository` | `_dependencies` | `service_dependencies` |
| 29 | `domain/dependency/repository.py` | `DependencyRepository` | `_conflicts` | `dependency_conflicts` |
| 30 | `domain/dependency/repository.py` | `DependencyRepository` | `_history` | `dependency_history` |
| 31 | `domain/forecasting/repository.py` | `ForecastRepository` | `_forecasts` | `forecasts` |
| 32 | `domain/forecasting/repository.py` | `ForecastRepository` | `_milestones` | `forecast_milestones` |
| 33 | `domain/planning/service.py` | `PlanningService` | `_cycles` | `budget_cycles` |
| 34 | `domain/planning/service.py` | `PlanningService` | `_submissions` | `budget_submissions` |
| 35 | `domain/planning/service.py` | `PlanningService` | `_submission_history` | `budget_submission_history` |
| 36 | `domain/planning/service.py` | `PlanningService` | `_targets` | `budget_targets` |
| 37 | `domain/planning/service.py` | `PlanningService` | `_scenarios` | `planning_scenarios` |
| 38 | `domain/identity/service.py` | `IdentityService` | `_users` | `identity_users` |
| 39 | `domain/identity/service.py` | `IdentityService` | `_break_glass_accounts` | `break_glass_accounts` |
| 40 | `domain/identity/service.py` | `IdentityService` | `_machine_clients` | `machine_clients` |
| 41 | `domain/rbac/catalogue.py` | `PermissionCatalogue` | `_custom_roles` | `custom_roles` |
| 42 | `domain/rbac/service.py` | `RBACService` | `_grants` | `role_grants` |
| 43 | `domain/integrations/adapters/chat.py` | `ChatAdapter` | `_cards` | `chat_notification_cards` |
| 44 | `domain/integrations/adapters/cmdb.py` | `CMDBAdapter` | `_cmdb_records` | `cmdb_records` |
| 45 | `domain/integrations/adapters/directory.py` | `IdentityDirectoryAdapter` | `_directory_users` | `directory_users` |
| 46 | `domain/integrations/adapters/finance.py` | `FinanceERPAdapter` | `_accrual_extracts` | `erp_accruals` |
| 47 | `domain/integrations/adapters/itsm.py` | `ITSMAdapter` | `_tickets` | `itsm_tickets` |
| 48 | `domain/integrations/events.py` | `OutboundEventDispatcher` | `_journal` | `outbound_events` |
| 49 | `domain/lifecycle/service.py` | `LifecycleService` | `_resources` | `lifecycle_resources` |
| 50 | `domain/lifecycle/service.py` | `LifecycleService` | `_requests` | `lifecycle_requests` |
| 51 | `domain/lifecycle/service.py` | `LifecycleService` | `_programmes` | `lifecycle_programmes` |
| 52 | `domain/notification/repository.py` | `NotificationLogRepository` | `_logs` | `notification_logs` |
| 53 | `domain/policy/repository.py` | `PolicyRepository` | `_policies` | `policies` |
| 54 | `domain/policy/repository.py` | `PolicyRepository` | `_policy_history` | `policy_history` |
| 55 | `domain/policy/repository.py` | `PolicyRepository` | `_findings` | `policy_findings` |
| 56 | `domain/policy/repository.py` | `PolicyRepository` | `_exemptions` | `policy_exemptions` |
| 57 | `domain/pricing/repository.py` | `PricingRepository` | `_records` | `pricing_catalogues` |
| 58 | `domain/pricing/repository.py` | `PricingRepository` | `_changes` | `pricing_changes` |
| 59 | `domain/provisioning/repository.py` | `ProvisioningRepository` | `_estimates` | `provisioning_estimates` |
| 60 | `domain/provisioning/repository.py` | `ProvisioningRepository` | `_requests` | `provisioning_requests` |
| 61 | `domain/quotas/repository.py` | `QuotaRepository` | `_quotas` | `quotas` |
| 62 | `domain/quotas/repository.py` | `QuotaRepository` | `_increase_requests` | `quota_increase_requests` |
| 63 | `domain/remediation/repository.py` | `RemediationRepository` | `_tasks` | `remediation_tasks` |
| 64 | `domain/reports/repository.py` | `ReportRepository` | `_jobs` | `report_jobs` |
| 65 | `domain/reports/repository.py` | `ReportRepository` | `_schedules` | `report_schedules` |
| 66 | `domain/runtime/repository.py` | `RuntimeRepository` | `_results` | `runtime_results` |
| 67 | `domain/runtime/repository.py` | `RuntimeRepository` | `_schedules` | `runtime_schedules` |
| 68 | `domain/statements/repository.py` | `StatementRepository` | `_statements` | `showback_statements` |

---

## 3. Tier 2: CACHE (7 Dict Holders)

Caches represent ephemeral data with defined TTLs designed for low-latency lookups, rate limiting, and security blacklists. These must be migrated to Redis/Valkey with atomic operations and bounded expiration.

| # | File Path | Class / Component | Attribute / Field | Target Persistence Infrastructure |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `api/cloudlens_api/conventions/rate_limit.py` | `RateLimiter` | `_buckets` | Redis Token Bucket (`ratelimit:{tenant}:{key}`) |
| 2 | `api/cloudlens_api/conventions/idempotency.py` | `IdempotencyStore` | `_records` | Redis String with TTL (`idempotency:{key}`) |
| 3 | `domain/abuse/tracker.py` | `AbuseTracker` | `_auth_failures` | Redis Sorted Set with sliding window TTL |
| 4 | `domain/abuse/tracker.py` | `AbuseTracker` | `_locked_principals` | Redis Key with lockout expiration TTL |
| 5 | `domain/identity/service.py` | `IdentityService` | `_sessions` | Redis Hash (`session:{session_id}`) with 8h TTL |
| 6 | `domain/identity/service.py` | `IdentityService` | `_step_up_challenges` | Redis Key (`stepup:{challenge_id}`) with 10m TTL |
| 7 | `domain/identity/token_engine.py` | `TokenRevocationRegistry` | `_revoked_jtis` | Redis Set (`revoked_tokens`) with JTI TTL |

---

## 4. Tier 3: FIXTURE (4 Dict Holders)

Fixtures are test harnesses or synthetic demo data generators. These remain strictly isolated in test directories (`tests/fakes/`) or synthetic tenants of type `DEMO` and are never loaded in production runtime.

| # | File Path | Class / Component | Attribute / Field | Target Handling Strategy |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `domain/synthetic/demo_tenant.py` | `DemoTenantLoaderService` | `_estates` | Isolated to `tenant_type = DEMO`; MinIO/JSON seeds |
| 2 | `domain/synthetic/demo_tenant.py` | `DemoTenantLoaderService` | `_seed_reports` | Isolated to `tenant_type = DEMO`; MinIO/JSON seeds |
| 3 | `domain/synthetic/journey_monitor.py` | `SyntheticJourneyMonitor` | `_last_result` | Synthetic probe execution results (test harness only) |
| 4 | `domain/tenant/object_store.py` | `InMemoryTenantObjectStorage` | `_store` | Replaced by `MinioTenantObjectStorage` in prod |

---

## 5. Tier 4: CONFIG (8 Dict Holders)

Configuration stores represent immutable or slow-moving platform configuration, role catalogues, and cryptographic keys.

| # | File Path | Class / Component | Attribute / Field | Target Persistence Infrastructure |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `domain/rbac/catalogue.py` | `PermissionCatalogue` | `_permissions` | PostgreSQL `permissions` master table |
| 2 | `domain/rbac/catalogue.py` | `PermissionCatalogue` | `_roles` | PostgreSQL `system_roles` master table |
| 3 | `domain/identity/token_engine.py` | `TokenKeyManager` | `_keys` | OpenBao Transit Engine / Key rotation config |
| 4 | `domain/maintenance/service.py` | `MaintenanceModeService` | `_tenant_maintenance` | PostgreSQL `platform_maintenance_states` |
| 5 | `domain/statements/templates.py` | `StatementTemplateEngine` | `_templates` | PostgreSQL `statement_templates` / Static assets |
| 6 | `domain/workflows/appliers.py` | `WorkflowApplierRegistry` | `_appliers` | Dependency Injection Registry (immutable code) |
| 7 | `masterdata/service.py` | `MasterDataService` | `_records` | PostgreSQL `master_data_catalogues` |
| 8 | `domain/observability/health.py` | `DependencyHealthProbe` | `_overrides` | Redis runtime health probe flag overrides |

---

## 6. Migration Roadmap

Per CloudLens architectural guidelines:
- **P03**: Foundation established. Protocol + `SqlTenantSettingsRepository` reference implementation, startup guard, RLS verification, and pattern documentation.
- **Subsequent Prompts**: Repositories are systematically converted domain-by-domain following `docs/persistence-pattern.md` without modifying unrelated domains ahead of time (Scope Freeze).
