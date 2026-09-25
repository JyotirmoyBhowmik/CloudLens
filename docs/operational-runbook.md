# CloudLens Operational Runbook

> **Audience**: Platform Administrators & Site Reliability Engineers  
> **Status**: Template Baseline (Stage 1)

---

## 1. Routine Operations

### Starting the Local Development Stack
```bash
# Using PowerShell on Windows
./bootstrap.ps1

# Using Bash on Linux/macOS
./bootstrap.sh

# Or directly using Python
python scripts/bootstrap.py
```

### Running Test Gates & Quality Audits
```bash
# Verify layering rule
python scripts/check_layering.py

# Run test suites
pytest
```

---

## 2. Emergency Procedures

### Superuser Break-Glass Access
- Superuser: `admin@jyotirmoyb.com`
- Authentication mechanism: Local break-glass with mandatory MFA assertion (SEC-005, SEC-027).
- Exactly one break-glass path is evidenced (Defect D-01 / D-05).

### Connector Failure Recovery
- When a connector state degrades to `Failed`, inspect error diagnostics in Admin Console (`/api/v1/connectors/{id}`).
- Rotate credentials in secret store without connector downtime (`SEC-014`).
- Trigger manual resumable sync (`/api/v1/connectors/{id}/sync`).
