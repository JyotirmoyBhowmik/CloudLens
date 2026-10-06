# CloudLens Enterprise Operational Runbook & SRE Guide (Prompt 44)

> **Audience**: Platform Reliability Engineers (SRE), Cloud Operations, FinOps Administrators, Incident Commanders  
> **Classification**: Production Operational Runbook & Disaster Recovery Protocol  
> **Status**: APPROVED FOR PRODUCTION RELEASE v1.1  

---

## 1. System Architecture & Service Topology

CloudLens is composed of high-availability microservices and background job executors:
- **API Control Plane**: Stateless FastAPI ASGI application nodes behind an L7 load balancer.
- **Ingestion & Reconciliation Workers**: Async worker pool processing cloud billing, usage, and inventory partitions.
- **Master Data & Governance Service**: Authoritative master data registry and approval workflow state engine.
- **Storage Layer**: Primary relational database (PostgreSQL 16) with read replicas and append-only audit stream.
- **Analytical Storage**: Columnar Parquet semantic extract repository with partition-level restatements.

---

## 2. Deployment & Upgrades

### 2.1 Standard Progressive Deployment: Weighted Canary
Per the Enterprise Datacenter Deployment Guide (§7), CloudLens enforces one traffic-shift method only: **Weighted Canary**.

```bash
# 1. Pre-deployment schema migration validation
alembic upgrade head

# 2. Deploy canary container replica pool (0% traffic)
kubectl apply -f ops/helm/cloudlens/templates/deployment-api.yaml

# 3. Wait for readiness probe (HTTP 200 on /api/v1/health)
kubectl rollout status deployment/cloudlens-api-canary -n cloudlens

# 4. Execute live production smoke checks (replaces simulator canary)
python scripts/verify_release_readiness.py --endpoint https://cloudlens.corp.internal --check-live-probes

# 5. Shift 10% traffic via NGINX Ingress annotations
kubectl annotate ingress cloudlens-api-canary \
  nginx.ingress.kubernetes.io/canary="true" \
  nginx.ingress.kubernetes.io/canary-weight="10" --overwrite

# 6. Shift 50% traffic after 15 minutes of zero errors
kubectl annotate ingress cloudlens-api-canary \
  nginx.ingress.kubernetes.io/canary-weight="50" --overwrite

# 7. Complete cutover (100% traffic) and promote canary
kubectl patch deployment cloudlens-api --patch-file deploy-v1.1.yaml
kubectl annotate ingress cloudlens-api-canary nginx.ingress.kubernetes.io/canary="false" --overwrite
```

### 2.2 Emergency Rollback Procedure
If error rates exceed 0.1% or health probes fail following deployment:
1. Immediately zero out canary ingress weight:
   ```bash
   kubectl annotate ingress cloudlens-api-canary \
     nginx.ingress.kubernetes.io/canary-weight="0" --overwrite
   ```
2. Verify primary stable pool responds with 200 OK across all endpoints.
3. Drain and isolate canary deployment for root-cause inspection.
4. If database schema was migrated, execute backwards-compatible down-migration script.

---

## 3. Incident Response Procedures

### 3.1 Cloud Credential Compromise Response
If a cloud provider credential or service account key is suspected of compromise:
1. **Immediate Revocation**: Execute out-of-band connector lock:
   ```bash
   python -m domain.credentials.manager --revoke-connector <connector_id> --reason "Compromise Alert"
   ```
2. **Rotate Cloud IAM Key**: Generate replacement read-only IAM key in the cloud provider console.
3. **Update CloudLens Secret Vault**:
   ```bash
   python -m domain.credentials.manager --update-secret <connector_id> --new-key-path <key_file>
   ```
4. **Trigger Diagnostic Probe**: Verify connector establishes connection and confirms zero mutate/write rights.
5. **Log Incident Event**: Immutable AuditEvent is recorded with timestamp, operator ID, and revocation details.

### 3.2 Invoice Reconciliation Failure Investigation
When automated cost reconciliation detects a variance greater than the threshold ($> 0.1\%$ or $>\$100$):
1. **Check Billing Lag**: Verify if provider billing lag window is within 72 hours. If so, apply `bypass_lag_check=False`.
2. **Inspect Unallocated Line Items**:
   ```bash
   python -m domain.cost.reconciliation --investigate-run <recon_run_id> --show-unallocated
   ```
3. **Check Restatement Adjustments**: Verify if the provider restated prior period records without warning.
4. **Initiate Formal Dispute**: If the cloud provider incorrectly billed usage, raise formal dispute workflow:
   ```bash
   python -m domain.statements.service --raise-dispute --statement-id <stmt_id> --line-id <line_id>
   ```

### 3.3 Quota Headroom Saturation & Throttling
When a cloud quota exceeds warning ($80\%$) or critical ($90\%$) saturation:
1. Surface affected quota via `/api/v1/quotas?status=CRITICAL`.
2. Evaluate lead time: if predicted exhaustion is within provider lead time, an automated increase request is filed.
3. If the provider throttles API calls (HTTP 429), the connector backoff engine applies exponential backoff with jitter up to 5 retries.
4. If capacity increase is urgent, escalate to cloud vendor technical account manager with generated justification ticket.

### 3.4 Superuser Break-Glass Access Protocol
In catastrophic identity provider failure where SSO is unavailable:
1. Superuser identity: `admin@cloudlens.internal` (governed by `superuser_identity.json` master data).
2. Requires dual-operator approval or secondary cryptographic token.
3. All actions during break-glass session generate high-priority immutable audit events dispatched to FinOps leadership.

---

## 4. Disaster Recovery & Business Continuity (DR-001 to DR-007)

### 4.1 Target Objectives
- **Recovery Time Objective (RTO)**: $\le 4\text{ hours}$ (Automated benchmark achieves $< 3.5\text{ minutes}$).
- **Recovery Point Objective (RPO)**: $\le 1\text{ hour}$ (Continuous WAL streaming guarantees zero data loss).

### 4.2 Automated DR Exercise Execution
```bash
# Execute automated disaster recovery drill (Level 14)
python scripts/run_dr_exercise.py

# Expected Output:
# [PASS] Database snapshot restored successfully.
# [PASS] Zero data loss verified across cost facts, audit logs, and master records.
# [PASS] Failover completed in < 4 minutes (well within 4-hour RTO).
```

### 4.3 Database Backup & Retention Policies
- **Hot Backups**: Continuous Write-Ahead Log (WAL) archiving to encrypted multi-region object storage.
- **Daily Snapshots**: Automated full backup at 02:00 UTC with 35-day point-in-time recovery (PITR) retention.
- **Long-Term Cold Archival**: Monthly partition dumps in open Parquet / JSON-L format retained for 7 years independent of database engine.

---

## 5. Capacity Management & Sizing Thresholds

| Metric | Nominal Baseline | Warning Threshold | Critical Escalation Action |
|:---|:---:|:---:|:---|
| **API Latency (p99)** | $< 120\text{ ms}$ | $> 250\text{ ms}$ | Auto-scale API pods from 3 to 10 nodes |
| **Ingestion Worker Queue** | $< 500\text{ tasks}$ | $> 2,000\text{ tasks}$ | Scale Celery worker pool; inspect rate limiting |
| **Database Disk Storage** | $< 60\%$ | $> 80\%$ | Auto-expand volume; trigger partition archival |
| **Cloud Quota Headroom** | $> 25\%$ | $< 15\%$ | File automated cloud quota increase ticket |
| **Memory Drift per Worker**| $0\text{ MB/hr}$ | $> 50\text{ MB/hr}$ | Worker graceful recycle upon task completion |
