# CloudLens Environment Configuration Matrix

This document defines the configuration, feature flags, secret handling, and runtime characteristics across the four supported deployment tiers: **Local**, **Test**, **Staging**, and **Production**. 

Per Enterprise Rule 1.1–5.3 and Architecture Rules (Prompt 02), differences between environments are **explicitly documented**, never implied or assumed.

---

## 1. Environment Comparison Matrix

| Area / Subsystem | Local (`local`) | Test / CI (`test`) | Staging (`staging`) | Production (`production`) |
| :--- | :--- | :--- | :--- | :--- |
| **Primary Purpose** | Local developer workstation inner loop & debugging | Hermetic automated unit, integration, and contract tests | Pre-production validation, load testing, integration sandboxes | Live multi-tenant enterprise governance & FinOps operations |
| **Database Engine** | PostgreSQL 16 (Local Docker Compose or SQLite memory) | Ephemeral PostgreSQL 16 container or in-memory DB | AWS RDS PostgreSQL 16 Multi-AZ (Sanitized snapshot) | AWS Aurora PostgreSQL 16 Multi-AZ with read replicas |
| **DB Connection Pool** | `pool_size = 5`, `max_overflow = 5`, `timeout = 10s` | `pool_size = 5`, `max_overflow = 0`, `timeout = 5s` | `pool_size = 20`, `max_overflow = 20`, `timeout = 30s` | `pool_size = 50`, `max_overflow = 50`, `timeout = 30s` |
| **Cache & Task Broker** | Redis 7 (Local Docker Compose or Mock cache) | In-memory Mock Redis / FakeRedis | ElastiCache Redis 7 (Single-node cluster) | ElastiCache Redis 7 Multi-AZ with Auto-Failover |
| **Object Storage** | MinIO S3 (`http://localhost:9000`) | Ephemeral MinIO or mock S3 filesystem store | AWS S3 Standard (Isolated staging bucket) | AWS S3 Multi-Region with KMS SSE & Object Lock |
| **Secret Management** | Local HashiCorp Vault (`http://localhost:8200`) or `.env` | Mock Secret Provider / Static Test Tokens | HashiCorp Vault (Dedicated Staging Cluster) | HashiCorp Vault Enterprise HA Cluster / AWS KMS |
| **Identity / Auth** | Mock JWT Header / Local Dev OIDC Issuer | Mock Auth Middleware (Test Tokens) | Okta / Entra ID Staging Tenant | Enterprise Okta / Microsoft Entra ID Production SSO |
| **Connectors Mode** | `stub` simulator + Optional local sandbox credentials | `stub` simulator (Strictly hermetic, zero outbound calls)| Live sandbox subscriptions / read-only test accounts | Live enterprise accounts (Azure, AWS, GCP, OCI) with least-privilege |
| **Log Level & Format** | `DEBUG` / Human-readable Console + JSON | `WARNING` / Structured JSON | `INFO` / Structured JSON with OTel Correlation IDs | `INFO` / Structured JSON with OTel Distributed Tracing |
| **Trace Sampling** | `1.0` (100% trace capture) | `0.0` (Disabled unless running trace test) | `0.5` (50% adaptive sampling) | `0.1` (10% adaptive sampling, 100% on errors) |
| **Ingress Rate Limits** | `10,000 req/min` (Relaxed for dev testing) | Disabled / Unlimited in test suite | `1,200 req/min` (Token bucket burst: 200) | `600 req/min` (Token bucket burst: 100) |
| **Export File Limit** | `10 MB` / `5,000` rows | `5 MB` / `1,000` rows | `50 MB` / `100,000` rows | `100 MB` / `500,000` rows (Async S3 staging) |
| **Diagnostic Dumps** | Secrets masked (`******`), internal diagnostics open | Masked (`******`), test assertions verified | Strict masking (`******`), PII redacted | Strict masking (`******`), PII redacted, audit logged |

---

## 2. Configuration Layering Order

Effective configuration values resolve dynamically according to the following strict hierarchy:

```
[Layer 1: Built-in Defaults (SystemConfig / TenantSettings)]
                     │
                     ▼ Overridden by
[Layer 2: Environment Variables (CLOUDLENS_<SECTION>__<KEY>)]
                     │
                     ▼ Overridden by
[Layer 3: Tenant Configuration (TenantSettings Store / Database)]
```

Every resolved value tracks its exact layer of origin. The **Configuration Inspector** exposes this provenance transparently at `/api/v1/config/inspector`.

---

## 3. Secret Masking & Diagnostic Protections

Per Security Architecture (`SEC-` rules) and Prompt 02 constraints:
- **No secrets in diagnostics**: Secrets (`password`, `token`, `secret`, `key`, `cert`) are automatically identified via field metadata and substring matching.
- When accessed through diagnostic endpoints, configuration inspectors, or error responses, secret values are replaced with `"******"`.
- Application error responses conform to Enterprise Rule 2.4 and **never** expose stack traces, database credentials, or server file paths.

---

## 4. Feature Flag Toggles by Environment

| Flag Key | `local` Default | `test` Default | `staging` Default | `production` Default |
| :--- | :--- | :--- | :--- | :--- |
| `enable_azure_connector` | `true` | `true` | `true` | `true` |
| `enable_aws_connector` | `true` | `true` | `true` | `true` |
| `enable_gcp_connector` | `true` | `true` | `true` | `true` |
| `enable_oci_connector` | `true` | `false` | `true` | `false` (Staged rollout) |
| `enable_multi_currency_forecasting`| `true` | `false` | `true` | `false` (Alpha preview) |
| `strict_budget_enforcement` | `false` | `true` | `false` | `false` (Opt-in per tenant) |
| `enable_anomaly_detection` | `true` | `true` | `true` | `true` |
| `enable_raw_metrics_export` | `true` | `false` | `true` | `false` (Beta preview) |
| `enable_amortised_cost_basis` | `true` | `true` | `true` | `true` |

---

## 5. Verification Checklist

Before deploying to any higher environment:
1. Validate layering rules: `pnpm check:layering`.
2. Validate zero hard-coded business constants: `python scripts/check_no_hardcoded_constants.py`.
3. Confirm zero secret leaks: run configuration inspector test suite.
4. Verify environment variable overrides are sourced from managed KMS or Vault secrets.
