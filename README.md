# CloudLens: Multi-Cloud Governance, Inventory & FinOps Platform

[![Stage 1 Passed](https://img.shields.io/badge/Stage-1%20Foundation-blue.svg)](#)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](#)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](#)
[![React 18](https://img.shields.io/badge/React-18.3-61DAFB.svg)](#)
[![License](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)

CloudLens delivers an enterprise-wide, multi-cloud governance, service inventory, cloud pricing, cost management, runtime/usage monitoring, dependency mapping, budgeting, alerting, and reporting application across **Microsoft Azure**, **Amazon Web Services (AWS)**, **Google Cloud Platform (GCP)**, and **Oracle Cloud Infrastructure (OCI)**.

---

## 1. What CloudLens Is and What It Is Not

### What CloudLens Is:
CloudLens gives an organisation a structured, common, single-pane view of cloud environments across multiple cloud providers. It answers:
- **Inventory & Deployment**: What services and resources exist, where they are deployed, and under which native provider hierarchy.
- **Ownership & Attribution**: Who owns them (technical and business owners), what application or cost centre they belong to, and what technical dependencies exist.
- **Pricing & Billing Dimensions**: What each service costs, how it is priced, and which billing dimensions apply.
- **Free-Tier Transparency**: Whether a resource is free, free-tier eligible, or conditionally free, and what consumption triggers charges.
- **Cost & Forecasting**: Expected cost, actual billed cost, and forecast cost tracking against hierarchical budgets.
- **Runtime Governance**: Operating hours verification (24x7 vs. schedule-based) and out-of-schedule waste detection.
- **Pre-Deployment Estimation**: Pre-deployment cost estimation ("What will this cost?") strictly keeping list price, estimated effective cost, actual billed cost, and forecast cost separate.

### What CloudLens Is NOT:
- **NOT an APM or Infrastructure Monitoring Replacement**: It is deliberately **not** a replacement for Datadog, Dynatrace, SolarWinds, Zabbix, CloudWatch, Azure Monitor, or Google Cloud Monitoring.
- **NO Autonomous Remediation in MVP**: It provides actionable recommendations and governance tasks; it does not execute destructive automated actions on live estates.
- **NO Artificially Flattened Hierarchies**: It models and preserves each provider's native organizational structure without loss of fidelity.
- **NEVER Invents Pricing Data**: Absolute rule: pricing data is never hallucinated or assumed. All rates derive from official APIs or verified documentation with timestamps and sources.

---

## 2. Where the Authoritative Requirements Live

All requirements for CloudLens are rigorously version-controlled, traceably linked, and published in:
- **Machine-Readable Register**: [`requirements-register.json`](requirements-register.json) (458 total requirements across all 13 prefixes: `BR`, `FR`, `PR`, `CST`, `USE`, `RUN`, `DEP`, `CON`, `API`, `SEC`, `NFR`, `DR`, `AC`).
- **Human-Readable Register & Audit Ledger**: [`docs/requirements-register.md`](docs/requirements-register.md).
- **Reconciled Pricing Dimensions**: [`docs/pricing-dimensions-reconciled.md`](docs/pricing-dimensions-reconciled.md) (All 29 dimensions and qualifiers, closing Defect `D-06`).
- **Orphan Analysis & Gap-or-Deferral Classification**: [`docs/orphan-requirements.md`](docs/orphan-requirements.md) (Zero unassigned orphan gaps).
- **Architecture Overview**: [`docs/architecture-overview.md`](docs/architecture-overview.md).
- **Module Map**: [`docs/module-map.md`](docs/module-map.md).

---

## 3. Architecture & Strict Layering Rule

CloudLens enforces strict inward dependency flow:

$$\text{Presentation (web)} \longrightarrow \text{Application (api, workers)} \longrightarrow \text{Domain} \longrightarrow \text{Normalisation} \longrightarrow \text{Ingestion} \longrightarrow \text{Connector} \longrightarrow \text{Provider}$$

- **The Rule**: Nothing above the connector layer may import a provider SDK (`boto3`, `azure.*`, `google.cloud.*`, `oci.*`) or reference a provider by name.
- **Automated Check**: `python scripts/check_layering.py` runs on every pre-commit and CI build.

---

## 4. Quickstart & Developer Bootstrap

### Prerequisites:
- Python 3.11+
- Node.js 20+ & pnpm 10+
- Docker Engine (optional for containerized PostgreSQL, Redis, MinIO, Vault)

### One-Command Developer Bootstrap:

```powershell
# Windows PowerShell
./bootstrap.ps1
```

```bash
# Linux / macOS
./bootstrap.sh
```

```bash
# Or directly via Python
python scripts/bootstrap.py
```

### Running Services Locally:

```bash
# Start FastAPI Server (Port 8000)
uvicorn api.cloudlens_api.main:app --reload --port 8000

# Start Web Shell (Port 3000)
cd web && pnpm dev
```

### Service URLs:
- **Web Interface**: `http://localhost:3000`
- **API Health Probe**: `http://localhost:8000/api/v1/health`
- **Interactive API Docs**: `http://localhost:8000/docs`
- **MinIO Object Store**: `http://localhost:9001`
- **Vault Secret Store**: `http://localhost:8200`

---

## 5. Verification & Quality Gates

Run all quality gates with zero warnings:

```bash
# Check layering rule enforcement
python scripts/check_layering.py

# Linting & Formatting
ruff check .
ruff format --check .

# Static Type Verification
mypy .

# Run Unit & Layering Tests
pytest
```
