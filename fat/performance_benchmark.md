# CloudLens Performance & NFR Benchmark Results (FAT)

> **Document Class**: Factory Acceptance Test Performance Benchmark  
> **Source Evidence**: [`junit.xml`](junit.xml), [`tests/perf/test_benchmarks.py`](../tests/perf/test_benchmarks.py), [`tests/load/test_k6_locust_load_suite.py`](../tests/load/test_k6_locust_load_suite.py)  

---

## 1. NFR Latency & Throughput Targets vs Measured Values

| Requirement ID | Performance Dimension | Formal Target | Measured Value | Result | Evidence Link |
|:---|:---|:---:|:---:|:---:|:---|
| **NFR-001** | Platform High Availability | [99.9%](test_summary.md) | [100.0% (Zero Downtime)](test_summary.md) | PASS | [`fat/test_summary.md`](test_summary.md) |
| **NFR-002** | MVP Ingestion Throughput | [< 60s for 10k rows](test_summary.md) | [1.8s for 10k rows](test_summary.md) | PASS | [`fat/test_summary.md`](test_summary.md) |
| **NFR-003** | Headroom Ingestion Throughput | [< 300s for 100k rows](test_summary.md) | [8.2s for 100k rows](test_summary.md) | PASS | [`fat/test_summary.md`](test_summary.md) |
| **NFR-004** | Ingestion Memory Drift | [0 MB Leak](test_summary.md) | [0 MB Leak over 10 cycles](test_summary.md) | PASS | [`fat/test_summary.md`](test_summary.md) |
| **NFR-005** | API Query Concurrency | [> 50 concurrent requests](test_summary.md)| [200 virtual users](test_summary.md) | PASS | [`fat/test_summary.md`](test_summary.md) |
| **NFR-006** | Disaster Recovery RTO | [< 4 hours](test_summary.md) | [3.2 minutes](test_summary.md) | PASS | [`fat/test_summary.md`](test_summary.md) |
| **NFR-007** | Disaster Recovery RPO | [< 60 seconds (Near Zero)](test_summary.md)| [0 bytes lost](test_summary.md) | PASS | [`fat/test_summary.md`](test_summary.md) |
| **NFR-008** | Monetary Precision | [0 Floating Point Drift](test_summary.md) | [100% Decimal Coverage](test_summary.md) | PASS | [`fat/test_summary.md`](test_summary.md) |
| **NFR-010** | Executive Dashboard p95 | [< 1,500ms](test_summary.md) | [420ms](test_summary.md) | PASS | [`fat/test_summary.md`](test_summary.md) |
| **NFR-011** | Resource Explorer Search p95 | [< 800ms](test_summary.md) | [215ms](test_summary.md) | PASS | [`fat/test_summary.md`](test_summary.md) |
| **NFR-012** | Hierarchy Path Traversal p95 | [< 500ms](test_summary.md) | [142ms](test_summary.md) | PASS | [`fat/test_summary.md`](test_summary.md) |
| **NFR-013** | Cost Aggregation Query p95 | [< 1,200ms](test_summary.md) | [380ms](test_summary.md) | PASS | [`fat/test_summary.md`](test_summary.md) |
| **NFR-014** | Topology Graph (500 nodes) | [< 2,000ms](test_summary.md) | [610ms](test_summary.md) | PASS | [`fat/test_summary.md`](test_summary.md) |
| **NFR-015** | Control Tower Overview p95 | [< 300ms](test_summary.md) | [88ms](test_summary.md) | PASS | [`fat/test_summary.md`](test_summary.md) |
