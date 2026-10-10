# CloudLens Production Restore Runbook & Disaster Recovery Protocol (Prompt P17)

> **Classification**: Authoritative Engineering Operations Runbook & SRE Recovery Protocol  
> **Recovery Targets**: Recovery Time Objective (RTO) $\le 4\text{ hours}$ | Recovery Point Objective (RPO) $\le 1\text{ hour}$  
> **Retention Policy**: 35-Day Point-In-Time Recovery (PITR) via Barman Object Store & MinIO S3

---

## 1. CloudNativePG (PostgreSQL) 35-Day Point-In-Time Recovery (PITR)

### 1.1 Architecture & Backup Invariants
- **WAL Archiving**: Continuous WAL streaming to MinIO bucket `cloudlens-backups/postgres/`.
- **Scheduled Backups**: Daily physical base backups executed at `00:00 UTC` by CloudNativePG `ScheduledBackup`.
- **Retention**: Barman object store retention policy enforces a rolling 35-day recovery window (`35d`).

### 1.2 Step-by-Step Recovery Procedure

#### Step 1: Identify Target Timestamp
Select the recovery target timestamp (ISO 8601 UTC) before the incident occurred:
```bash
export RECOVERY_TARGET_TIME="2026-10-10 18:00:00.000000+00"
```

#### Step 2: Create Recovery Cluster Definition (`restore-cluster.yaml`)
Deploy a restored PostgreSQL cluster pointing to the object store backup source:
```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: cloudlens-pg-cluster-restored
  namespace: cloudlens
spec:
  instances: 3
  primaryUpdateStrategy: unsupervised

  storage:
    size: 50Gi

  bootstrap:
    recovery:
      source: cloudlens-backup-source
      targetTime: "2026-10-10 18:00:00.000000+00"

  externalClusters:
    - name: cloudlens-backup-source
      barmanObjectStore:
        destinationPath: "s3://cloudlens-backups/postgres/"
        endpointURL: "https://minio.storage.svc.cluster.local:9000"
        s3Credentials:
          inheritFromAzureAD: false
        wal:
          maxParallel: 8
```

#### Step 3: Apply the Recovery Manifest
```bash
kubectl apply -f restore-cluster.yaml -n cloudlens
```

#### Step 4: Monitor Pod Rollout & WAL Replay
```bash
kubectl get cluster.postgresql.cnpg.io cloudlens-pg-cluster-restored -n cloudlens -w
kubectl logs -n cloudlens -l cnpg.io/cluster=cloudlens-pg-cluster-restored -c postgres -f
```

#### Step 5: Verify Database Consistency & Point-In-Time Accuracy
Execute validation checks against the restored instance:
```bash
kubectl exec -n cloudlens cloudlens-pg-cluster-restored-1 -c postgres -- \
  psql -U cloudlens -d cloudlens -c "
    SELECT 
      (SELECT COUNT(*) FROM tenants) AS total_tenants,
      (SELECT COUNT(*) FROM connectors) AS total_connectors,
      (SELECT COUNT(*) FROM sync_jobs) AS total_sync_jobs,
      (SELECT pg_last_xact_replay_timestamp()) AS last_replay_time;
  "
```

#### Step 6: Promote Restored Cluster & Switch Traffic
Update Helm values to point to `cloudlens-pg-cluster-restored-rw`:
```bash
helm upgrade cloudlens ops/helm/cloudlens \
  --namespace cloudlens \
  --set external.postgres.host="cloudlens-pg-cluster-restored-rw.cloudlens.svc.cluster.local" \
  --reuse-values
```

---

## 2. OpenBao / HashiCorp Vault Raft Snapshot Restore

### 2.1 Backup Verification
OpenBao snapshots are captured daily at `02:00 UTC` and stored encrypted in `cloudlens-backups/openbao/openbao-raft-YYYYMMDDHHMMSS.snap`.

### 2.2 Restore Execution Procedure

#### Step 1: Download Target Snapshot from S3
```bash
mc cp minio/cloudlens-backups/openbao/openbao-raft-latest.snap /tmp/restore.snap
```

#### Step 2: Acquire Superuser Token & Step-Up MFA
Log in to OpenBao using root or disaster-recovery operator token:
```bash
export VAULT_ADDR="https://openbao.security.svc.cluster.local:8200"
export VAULT_TOKEN="$(kubectl get secret openbao-recovery-token -n security -o jsonpath='{.data.token}' | base64 -d)"
```

#### Step 3: Restore Raft Cluster State
```bash
# Force restore of Raft storage backend
vault operator raft snapshot restore -force /tmp/restore.snap
```

#### Step 4: Verify Secret Paths
Verify critical secret mount paths are present and accessible:
```bash
vault kv get secret/data/cloudlens/database
vault kv get secret/data/cloudlens/redis
vault kv get secret/data/cloudlens/idp
```

---

## 3. End-to-End Post-Restore Smoke Test & Sign-Off

1. **Verify Health Probes**:
   ```bash
   kubectl exec -n cloudlens deploy/cloudlens-api -- \
     curl -sf http://localhost:8000/api/v1/health/readiness
   ```
2. **Execute Control Tower Overview**:
   ```bash
   python -c "
   from domain.control_tower.service import get_control_tower_service
   svc = get_control_tower_service()
   overview = svc.get_overview()
   print('Control Tower Status:', overview.overall_status.value)
   assert overview.overall_status.value in ('green', 'amber')
   "
   ```
3. **Audit Event Recording**:
   A high-severity `DR_RESTORE_COMPLETED` audit event is logged with operator identity and target restore timestamp.
