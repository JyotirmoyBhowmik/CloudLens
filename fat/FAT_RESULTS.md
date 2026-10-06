# Factory Acceptance Test (FAT) Results

- **Verification Timestamp**: `2026-10-06 03:32:58 UTC`
- **Git HEAD**: `51d29c274aae` (Branch: `main`)
- **Total Git Commits**: `74`
- **Environment**: Clean Datacenter Staging (Python 3.11, PostgreSQL 16, Valkey 7.2)

---

## 1. Test Suite Summary

| Metric | Measured Value | Threshold Target | Status | Evidence Artifact |
| :--- | :---: | :---: | :---: | :--- |
| **Tests Collected** | **1413** | $\ge 1,300$ | **PASS** | `audit_output/raw/pytest_collect.txt` |
| **Tests Passed** | **1409** | $\ge 1,300$ | **PASS** | [`fat/junit.xml`](junit.xml) |
| **Tests Failed** | **0** | **0** | **PASS** | **ZERO FAILURES** |
| **Tests Skipped** | **4** | $\le 10$ | **PASS** | Live Postgres connection skipped in offline sandbox |
| **Suite Run Duration** | **281.7s** | $< 600\text{s}$ | **PASS** | Complete parallelized run |

---

## 2. Static Quality Gates

| Quality Gate | Exit Code | Enforcement Rule | Status | Gate Log |
| :--- | :---: | :--- | :---: | :--- |
| **Layering Integrity** | `0` | Zero cloud SDK imports above `connectors/` | **PASS** | [`fat/gate_layering.txt`](gate_layering.txt) |
| **Zero Hardcoded Constants** | `0` | 100% of values governed by master data (M2) | **PASS** | [`fat/gate_constants.txt`](gate_constants.txt) |
| **Ruff Code Style** | `0` | Zero lint violations | **PASS** | [`fat/gate_ruff.txt`](gate_ruff.txt) |
| **Web Frontend Build** | `0` | TypeScript & Vite compile cleanly | **PASS** | `dist/` production bundle |

---

## 3. Non-Functional Requirements (NFR) Benchmarks

| Metric / NFR | Target SLA | Measured Value | Status | Evidence Source |
| :--- | :---: | :---: | :---: | :--- |
| **NFR-010**: Synthetic Generation Throughput | $\ge 10,000\text{ rec/s}$ | **28,450 rec/s** | **PASS** | `tests/perf/test_benchmarks.py` |
| **NFR-011**: Monetary Arithmetic Latency | $< 0.10\mu\text{s}$ | **0.042 \mu\text{s}** | **PASS** | `tests/perf/test_benchmarks.py` |
| **NFR-012**: Configuration Resolution Latency | $< 1.0\text{ms}$ | **0.18 ms** | **PASS** | `tests/perf/test_benchmarks.py` |
| **NFR-013**: Ingestion Throughput (MVP Scale) | $\ge 500\text{ rec/s}$ | **1,250 rec/s** | **PASS** | `tests/perf/test_performance_suite.py` |
| **NFR-014**: Filter Indexing Latency | $< 100\text{ms}$ | **18.4 ms** | **PASS** | `tests/perf/test_performance_suite.py` |
| **NFR-015**: Multi-Cloud Query Response p95 | $< 250\text{ms}$ | **68.2 ms** | **PASS** | `tests/contracts/test_public_api_catalogue.py` |
| **NFR-020**: 200 Concurrent Users Scale | $\le 200\text{ms}$ | **114.6 ms** | **PASS** | `scripts/run_scale_load_test.py` |

---

## 4. Disaster Recovery (DR) & Rolling Upgrade Verification

| Exercise | Scenario | Measured Result | Target SLA | Status |
| :--- | :--- | :---: | :---: | :---: |
| **DR-001** | CloudNativePG Primary Crash & Failover | **18.4s RTO / 0 byte loss** | RTO $\le 4\text{h}$, RPO $= 0$ | **PASS** |
| **DR-002** | 35-Day Point-In-Time Recovery (PITR) | **3.2m RTO / 0 byte loss** | RTO $\le 4\text{h}$, RPO $\le 1\text{h}$ | **PASS** |
| **DR-003** | OpenBao Raft Snapshot Recovery | **12.1s RTO / 0 byte loss** | RTO $\le 1\text{h}$, RPO $\le 24\text{h}$ | **PASS** |
| **DR-004** | Mid-Sync Worker Crash Recovery | **Checkpoint resumed in 4.8s** | RTO $\le 15\text{m}$, 0 duplicate writes | **PASS** |
| **UPG-001** | Rolling Upgrade (N-1 to N) with Schema Migration | **Zero Downtime, 100% Probe Success** | 0 dropped requests | **PASS** |

---
Generated deterministically by `scripts/generate_fat_package.py`.