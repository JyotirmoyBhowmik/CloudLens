# CloudLens Production Go-Live Readiness Checklist

> **Scope**: Pre-Production to Production Operational Gate Matrix  
> **Environment**: Option A (k3s / RKE2 on UAT VM, JyotirmoyB Datacenter)  
> **UAT Reference**: [`docs/uat_sign_off.md`](uat_sign_off.md)  
> **Operational Drills Reference**: [`scripts/run_uat_drills.py`](../scripts/run_uat_drills.py)  
> **Audit Status**: `audit_output/AUDIT_REPORT.md` (RED 0)  
> **Policy**: In accordance with Enterprise Mandate M-DOC, unticked items strictly remain OPEN `[ ]` until live external evidence is verified in subsequent phases.

---

## 1. Production Readiness Gate Status

| # | Gate Item | Requirement & Scope | Status | Authoritative Evidence Link | Verification Detail |
|:---|:---|:---|:---:|:---|:---|
| **G-01** | Air-Gapped Helm Packaging | Helm templates lint clean, Option A values configured for k3s/RKE2 | [x] | [`ops/helm/cloudlens/values-uat.yaml`](../ops/helm/cloudlens/values-uat.yaml) | `helm lint` passed with 0 errors across all deployment templates |
| **G-02** | Container Image Signing | Multi-arch Linux images signed via Cosign; Syft SBOM generated | [x] | [`ops/cosign/`](../ops/cosign/), [`ops/sbom/`](../ops/sbom/) | Cosign pubkey verified; SPDX JSON SBOMs committed |
| **G-03** | Secret Store Zero Plaintext | Zero credentials in Git history or Helm values; OpenBao HA + HSM unseal | [x] | [`ops/helm/cloudlens/values-uat.yaml`](../ops/helm/cloudlens/values-uat.yaml) | Zero plaintext secrets; OpenBao `vault://` secret store references only |
| **G-04** | CloudNativePG 16 HA Quorum | 3-instance PostgreSQL cluster with quorum failover and zero data loss | [x] | [`scripts/run_uat_drills.py`](../scripts/run_uat_drills.py) | Standby promoted in < 1.0s RTO with 0 data loss verified |
| **G-05** | 35-Day PITR Backup | Continuous WAL streaming + daily base backup to MinIO object storage | [x] | [`scripts/run_uat_drills.py`](../scripts/run_uat_drills.py) | Continuous WAL replay restored 10 pre-corruption transactions |
| **G-06** | OpenBao Raft Snapshot Schedule | Daily automated Raft snapshot CronJob targeting MinIO S3 bucket | [x] | [`ops/helm/cloudlens/templates/cronjob-raft-snapshot.yaml`](../ops/helm/cloudlens/templates/cronjob-raft-snapshot.yaml) | Raft snapshot wipe & restore verified with 100% hash parity |
| **G-07** | Valkey Sentinel Failover | 3-sentinel Valkey cluster with automatic leader election | [x] | [`docs/architecture-overview.md`](architecture-overview.md#32-high-availability-infrastructure-matrix) | Redis Sentinel protocol quorum verified |
| **G-08** | Inward Architectural Layering | Zero provider SDK imports (`boto3`, `azure`, `google`) outside `connectors/` | [x] | [`scripts/check_layering.py`](../scripts/check_layering.py) | AST layering scanner passed with exit code 0 |
| **G-09** | Zero Hardcoded Constants (M2) | 100% of financial tolerances, thresholds, and enum literals from master data | [x] | [`scripts/check_no_hardcoded_constants.py`](../scripts/check_no_hardcoded_constants.py) | Constants scanner executed clean in enforce mode |
| **G-10** | Synthetic Demo Isolation (M3) | Complete demo mode separation with watermark and read-only interlocks | [x] | [`domain/tenant/models.py`](../domain/tenant/models.py) | `TenantType.DEMO` isolation; simulator barred from production tenants |
| **G-11** | Full Automated Test Suite | Complete execution of unit, contract, E2E, DR, and performance test suites | [x] | [`tests/dr/test_disaster_recovery.py`](../tests/dr/test_disaster_recovery.py) | 5/5 DR scenarios and production test suite passed |
| **G-12** | 27 Views + Control Tower | React Router v6 SPA with deep links, 4 null states, and RBAC guards | [x] | [`web/src/App.tsx`](../web/src/App.tsx) | 28 production routes verified with zero critical accessibility defects |
| **G-13** | Superuser Single Break-Glass | Dedicated superuser provisioned via master data with mandatory MFA | [x] | [`scripts/activate_superuser_uat.py`](../scripts/activate_superuser_uat.py) | `admin@jyotirmoyb.com` activated via RFC 6238 TOTP (AM-05 compliant) |
| **G-14** | SEC-024 Independent Pen Test | External third-party penetration testing engagement on staging environment | [ ] | **OPEN (Scheduled for P22 Staging)** | Automated OWASP ZAP & gitleaks passed; human red-team engagement scheduled for P22 |
| **G-15** | Two Closed Periods Reconciled | Real invoice reconciliation against 2 full closed production billing periods | [ ] | **OPEN (Pending P23 Month-End Closes)** | Mathematical engine verified on test fixtures; awaits live calendar closes in P23 |

---

## 2. Gate Verification Summary

- **Total Gates**: 15
- **Gates Closed (Verified)**: 13
- **Gates Remaining Open**: 2 (G-14 and G-15 remain strictly `[ ]` **OPEN** until Prompt P22 and P23 completion)
- **Production Account Connection Interlock**: Production cloud accounts remain disconnected until final sign-off is complete.
