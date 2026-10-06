# Production Go-Live Readiness Register (Enterprise Guide §11)

> Authoritative production sign-off matrix for CloudLens deployment on-premises.
> In accordance with Enterprise Mandate M-DOC: Unticked items stay unticked until verifiable evidence is provided.

| # | Gate Item | Requirement & Scope | Status | Evidence Artifact Link | Verification Detail |
|:---|:---|:---|:---:|:---|:---|
| **G-01** | Air-Gapped Helm Packaging | Helm templates lint clean, `kubeconform` passes on strict K8s 1.28+ schema | [x] | [`ops/helm/cloudlens/`](../ops/helm/cloudlens/) | `helm lint` and `kubeconform -strict` passed with 0 errors |
| **G-02** | Container Image Signing | Multi-arch Linux images signed via Cosign; Syft SBOM generated | [x] | [`ops/cosign/`](../ops/cosign/), [`ops/sbom/`](../ops/sbom/) | Cosign pubkey verified; SPDX JSON SBOMs committed |
| **G-03** | Secret Store Zero Plaintext | Zero credentials in Git history or Helm values; OpenBao HA + HSM unseal | [x] | [`fat/gate_constants.txt`](gate_constants.txt) | `gitleaks` clean over full git history; OpenBao K8s auth |
| **G-04** | CloudNativePG 16 HA Quorum | 3-instance PostgreSQL cluster with quorum failover and zero data loss | [x] | [`fat/FAT_RESULTS.md`](FAT_RESULTS.md#4-disaster-recovery-dr--rolling-upgrade-verification) | DR drill verified failover in 18.4s RTO, 0 byte lag |
| **G-05** | 35-Day PITR Backup | Continuous WAL streaming + daily base backup to MinIO object storage | [x] | [`docs/enterprise-datacenter-deployment-guide.md`](../docs/enterprise-datacenter-deployment-guide.md#4-disaster-recovery--backup-architecture-35-day-pitr) | Barman WAL archiver running; 3.2m test restore executed |
| **G-06** | OpenBao Raft Snapshot Schedule | Daily automated Raft snapshot CronJob targeting MinIO S3 bucket | [x] | [`ops/helm/cloudlens/templates/cronjob-raft-snapshot.yaml`](../ops/helm/cloudlens/templates/cronjob-raft-snapshot.yaml) | Restored in drill in 12.1s with 0 bytes lost |
| **G-07** | Valkey Sentinel Failover | 3-sentinel Valkey cluster with automatic leader election | [x] | [`docs/architecture-overview.md`](../docs/architecture-overview.md#32-high-availability-infrastructure-matrix) | Redis Sentinel protocol quorum verified |
| **G-08** | Inward Architectural Layering | Zero provider SDK imports (`boto3`, `azure`, `google`) outside `connectors/` | [x] | [`fat/gate_layering.txt`](gate_layering.txt) | AST layering scanner passed with exit code 0 |
| **G-09** | Zero Hardcoded Constants (M2) | 100% of financial tolerances, thresholds, and enum literals from master data | [x] | [`fat/gate_constants.txt`](gate_constants.txt) | Enforce mode exit 0; 84 allow-listed exceptions registered |
| **G-10** | Synthetic Demo Isolation (M3) | Complete demo mode separation with watermark and read-only interlocks | [x] | [`fat/acceptance_criteria_results.md`](acceptance_criteria_results.md) | All 11 demo scenarios load cleanly; zero live connector cross-talk |
| **G-11** | Full Automated Test Suite | Complete execution of unit, contract, E2E, DR, and performance test suites | [x] | [`fat/junit.xml`](junit.xml) | **1,409 passed / 0 failed / 4 skipped** |
| **G-12** | 27 Views + Control Tower | React Router v6 SPA with deep links, 4 null states, and RBAC guards | [x] | [`web/src/App.tsx`](../web/src/App.tsx) | 28 production routes verified with zero critical accessibility defects |
| **G-13** | Superuser Single Break-Glass | Dedicated superuser provisioned via master data with mandatory MFA | [x] | [`fat/acceptance_criteria_results.md`](acceptance_criteria_results.md) | Zero superuser literals in code; break-glass verified |
| **G-14** | SEC-024 Independent Pen Test | External third-party penetration testing engagement on staging environment | [ ] | **OPEN (Scheduled for Staging)** | Automated OWASP ZAP & gitleaks passed; human red-team engagement scheduled |
| **G-15** | Two Closed Periods Reconciled | Real invoice reconciliation against 2 full closed production billing periods | [ ] | **OPEN (Pending First Month-End Close)** | Mathematical engine verified on fixtures; awaits live calendar close |

---
**Overall Go-Live Posture**: **13 CLOSED / 2 OPEN** (SEC-024 Pen Test & 2 Closed Periods Reconciled remain open as expected at FAT).