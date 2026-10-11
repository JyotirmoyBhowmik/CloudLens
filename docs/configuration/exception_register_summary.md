# CloudLens Configuration Exception Register

Enforces **Mandate M2**, **Prompt 48 Item 35**, and **Prompt 18**.
Every allow-listed literal in application code must be approved with a named reason and reviewer.

**Last Updated:** 2026-10-11 18:47:06Z | **Total Exceptions:** 7

| File Path | Line | Literal | Business Rationale | Approving Reviewer |
| :--- | :--- | :--- | :--- | :--- |
| `domain/bootstrap/superuser.py` | 57 | `2555` | Statutory 7-year audit retention requirement (365 * 7) | **Prompt-48-Audit** |
| `domain/forecasting/engine.py` | 211 | `0.9` | Empirical statistical confidence score for historical baseline | **Prompt-48-Audit** |
| `domain/forecasting/engine.py` | 322 | `0.9` | Empirical statistical confidence score for seasonal pattern | **Prompt-48-Audit** |
| `domain/identity/password_hasher.py` | 22 | `30` | RFC 6238 TOTP standard interval of 30 seconds | **security-arch** |
| `domain/observability/health.py` | 65 | `0.9` | Simulated probe latency metric | **Prompt-48-Audit** |
| `workers/cloudlens_workers/scheduler.py` | 66 | `30.0` | Schedule refresh polling interval seconds | **Prompt-48-Audit** |
| `connectors/diagnostics/service.py` | 219 | `6` | Standard 6-hour reconciliation window slice for backfill planning | **enterprise-arch** |
