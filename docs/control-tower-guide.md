# CloudLens Platform Control Tower Operations Guide

## Executive Overview
The **CloudLens Platform Control Tower** (`/control-tower`) is the authoritative operational cockpit and emergency control plane for the Platform Super Administrator (`admin@jyotirmoyb.com`). 

It provides real-time operational observability across **14 distinct technical monitoring panels**, Server-Sent Events (SSE) streaming updates, cryptographic audit logs, and audited administrative actions guarded by step-up multi-factor authentication (MFA).

---

## 1. Authentication & Access Governance

### 1.1 Superuser Sign-In & SSO Integration
1. **OIDC Single Sign-On**: Operators authenticate via Keycloak (`http://localhost:8081` in dev) with their enterprise identity (`admin@jyotirmoyb.com`).
2. **Capability Assignment**:
   - `SUPER_ADMIN`: Holds `platform.observe`, `platform.operate`, and `platform.act_as`.
   - `PLATFORM_ADMIN`: Holds `platform.observe` and `platform.operate` (scoped to assigned tenants).
   - `AUDITOR`: Holds `platform.observe` only (read-only visibility; every operational action strictly returns `403 Forbidden`).
3. **Step-Up Authentication Proof**:
   - All mutate and emergency actions under `/api/v1/control-tower/actions` require a short-lived step-up token provided via the `X-Step-Up-Token` header or `step_up_token` in the JSON request body.
4. **Routine-Use Exemption (Prompt R-CT Item 5)**:
   - Read-only Control Tower queries (`GET /api/v1/control-tower/*`) by `admin@jyotirmoyb.com` are exempt from the 3-day consecutive routine-use detector.
   - Any operational action or non-Control-Tower business logic usage counts towards the routine-use threshold and raises security alerts per governance policy.

---

## 2. The 14 Operational Monitoring Panels

Each panel displays an accessible status indicator (never color alone: `[HEALTHY / GREEN]`, `[DEGRADED / AMBER]`, `[CRITICAL / RED]`, `[UNKNOWN / GREY]`), empirical explanation, metrics snapshot, and deep-links to Grafana dashboards.

| Panel ID | Name | Monitored Subsystems | Green Criteria | Amber Criteria | Red Criteria |
|:---|:---|:---|:---|:---|:---|
| `health` | System & Dependency Health | PostgreSQL, Redis, HashiCorp Vault, Prometheus exporters | All dependencies healthy, latency < 100ms | Non-critical latency > 100ms | DB, Redis, or Vault unreachable |
| `release` | Platform Release & Build Info | Build commit, semantic version, CLOUDLENS_ENV | Valid git SHA, release tag active | Commit age > 90 days | Untracked dirty build or mismatch |
| `tenants` | Tenant Partitioning & Isolation | Multi-tenant boundary integrity, quarantines | 0 quarantined tenants, RLS active | Quarantined entities < 5% | Cross-tenant breach attempt or isolation fault |
| `connectors` | Cloud Connectors & Ingestion Lag | AWS, Azure, GCP, OCI connectors | Freshness lag < 6h (21,600s) | Lag between 6h and 24h | Connector error streak $\ge 3$ or lag > 24h |
| `jobs` | Background Jobs & Sync Engine | Celery tasks, scheduled beat runs | Task success rate $\ge 98\%$ | Failure rate 2%–5% | Failure rate > 5% or task failure streak $\ge 3$ |
| `queues` | Task Queues & Worker Saturation | Redis broker queues, Celery worker concurrency | Queue backlog < 50 items, saturation < 70% | Queue 50–200 items, saturation 70%–90% | Queue > 200 items or workers offline |
| `pipeline` | Ingestion Pipeline Throughput | FOCUS normalization, tag mapping, drops | Zero drop ratio, pipeline EPS nominal | Drop ratio 0.01%–1% | Ingestion pipeline halted or drop ratio > 1% |
| `security` | Security Governance & Access Isolation | Superuser signins, cross-tenant attempts, unmapped IdP | 0 isolation violations, MFA active | Elevated sign-in frequency | Unauthorized cross-tenant attempt detected |
| `alerts_pipeline` | Alertmanager & Notification Pipeline | Mailpit relay, email delivery, Watchdog heartbeat | Watchdog firing, 0 failed deliveries | Undelivered alerts 1–3 | Watchdog stops firing (pipeline dead) |
| `collection_cost` | Collection Cost & Telemetry Overhead | Connector API cost, BigQuery cost vs estimates | Cost $\le$ estimate envelope ($14.20/day) | Cost 100%–125% of estimate | Cost > 125% of estimate or runaway query |
| `capacity` | Infrastructure Capacity & Resource Headroom | Database disk space, memory, cloud provider quotas | Disk usage < 70%, quota headroom > 30% | Disk 70%–85%, quota headroom 15%–30% | Disk > 85% or quota exhaustion risk |
| `backups` | Database Backups & RPO Replication | Automated snapshots, PostgreSQL WAL lag | Last backup < 26h ago, WAL lag < 60s | WAL lag 60s–3600s | Backup missed (> 26h) or WAL lag > 3600s |
| `expiries` | Certificates & Credential Expiries | TLS certificates, IAM credentials, tokens | Expiry > 30 days | Expiry 7–30 days | Expiry < 7 days or credential expired |
| `value` | Value Ledger & Realized FinOps Savings | Cumulative realized savings vs platform run cost | Net positive benefit, ROI multiple > 3.0x | ROI 1.0x–3.0x | Run cost exceeds realized savings |

---

## 3. Administrative Actions & Blast Radius Controls

Operators holding `platform.operate` can trigger emergency interventions. Every action enforces:
1. **Pre-Execution Blast Radius Assessment** (`confirm: false`): Shows affected tenants, cloud connectors, and task queues.
2. **Step-Up MFA Proof**: Requires valid `X-Step-Up-Token`.
3. **Operational Justification**: Mandatory reason text with at least 20 characters.
4. **Cryptographic Audit Event**: Emits `AuditEventType.CT_ACTION` logged in the append-only ledger.

### Action Catalog:
- `retry-job`: Re-queues a failed sync job for automatic processing.
  - *Parameters*: `job_id`, `tenant_id`
  - *Blast Radius*: Single tenant, target connector, ingestion queue.
- `pause-connector`: Freezes cloud provider ingestion syncs to mitigate upstream throttling or maintenance.
  - *Parameters*: `connector_id`
  - *Blast Radius*: All tenants utilizing the specified connector.
- `resume-connector`: Resumes automated scheduling for a paused connector.
  - *Parameters*: `connector_id`
  - *Blast Radius*: Target connector.
- `force-sync`: Dispatches an immediate, out-of-schedule cost or inventory synchronization.
  - *Parameters*: `connector_id`, `tenant_id`
  - *Blast Radius*: Target tenant and connector sync worker.
- `drain-queue`: Purges stalled or backlogged job queues during incident recovery.
  - *Parameters*: `queue_name`
  - *Blast Radius*: All pending tasks in the target queue.
- `requeue-quarantine`: Releases quarantined records after policy review or schema correction.
  - *Parameters*: `tenant_id`
  - *Blast Radius*: Quarantined entity backlog for target tenant.
- `maintenance-mode`: Toggles global platform maintenance mode on or off.
  - *Parameters*: `enabled` (boolean)
  - *Blast Radius*: Platform-wide; pauses all non-administrative tenant traffic.
- `revoke-user-sessions`: Revokes active JWT authentication tokens and sessions.
  - *Parameters*: `user_id`
  - *Blast Radius*: Target user identity and active sessions.
- `trigger-backup`: Initiates an on-demand database snapshot and WAL checkpoint.
  - *Parameters*: None
  - *Blast Radius*: Relational database persistence storage layer.
- `trigger-reconciliation`: Forces an immediate cent-for-cent statement reconciliation run.
  - *Parameters*: `tenant_id`, `billing_period`
  - *Blast Radius*: Financial ledger for target tenant and billing period.

---

## 4. Standard Operating Procedures (SOP) & Incident Response

### SOP-01: Response to `connectors` Tile Turning RED
1. Open drill-down modal on the `Cloud Connectors` tile to identify the failing provider connector.
2. Click **Open in Grafana** to inspect API error codes (e.g., HTTP 429 Throttling, HTTP 403 Invalid Credentials).
3. If provider is throttling: Execute `pause-connector` with reason: `"Pausing AWS connector due to provider rate limit exhaustion"`.
4. Once upstream provider stabilizes: Execute `resume-connector` followed by `force-sync`.

### SOP-02: Response to `queues` Tile Turning RED
1. Inspect worker saturation and queue depth metrics.
2. If workers are offline: Check Docker container logs (`docker compose logs worker`).
3. If queue depth is runaway (> 1,000 backlog): Execute `drain-queue` for non-critical telemetry queues with reason: `"Draining backlogged ingestion queue during worker recovery"`.

### SOP-03: Response to `health` (Vault / Secret Store) Turning RED
1. Confirm Vault container liveness (`docker compose ps vault` or secret store process).
2. Check network connectivity between API and Vault (`http://vault:8200/v1/sys/health`).
3. If unsealed or rotated: Update root token via secure environment variable and restart API container.

---

## 5. Daily Platform Summary Email & Watchdog Monitoring

1. **Daily Platform Summary (Task `send_daily_platform_summary`)**:
   - Dispatched daily to `admin@jyotirmoyb.com` via Mailpit SMTP relay (`mailpit:1025`).
   - Summarizes 8 key platform indicators: overall status, 24h failure count, security events, superuser logins, connector lag, reconciliation status, collection cost vs estimate, and backup freshness.
2. **Dead-Man's Switch (Watchdog Alert)**:
   - Alertmanager continuously receives a firing `Watchdog` alert from Prometheus.
   - If the platform owner stops receiving alerts or the dead-man's heartbeat fails, the external monitor alerts `admin@jyotirmoyb.com` that the monitoring pipeline is impaired.
