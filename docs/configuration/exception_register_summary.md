# CloudLens Configuration Exception Register

Enforces **Mandate M2**, **Prompt 48 Item 35**, and **Prompt 18**.
Every allow-listed literal in application code must be approved with a named reason and reviewer.

**Last Updated:** 2026-10-11 05:11:21Z | **Total Exceptions:** 25

| File Path | Line | Literal | Business Rationale | Approving Reviewer |
| :--- | :--- | :--- | :--- | :--- |
| `domain/bootstrap/superuser.py` | 57 | `2555` | Statutory 7-year audit retention requirement (365 * 7) | **Prompt-48-Audit** |
| `domain/cost/reconciliation/engine.py` | 368 | `Decimal('99.50')` | Executive trust score tier thresholds (99.5% and 98.0%) | **Prompt-48-Audit** |
| `domain/cost/reconciliation/engine.py` | 370 | `Decimal('98.00')` | Executive trust score tier thresholds (99.5% and 98.0%) | **Prompt-48-Audit** |
| `domain/cost/reconciliation/engine.py` | 539 | `2` | Minimum sample size for half-split trend comparison | **Prompt-48-Audit** |
| `domain/forecasting/accuracy.py` | 40 | `0.75` | Standard quarterly milestone thresholds (25%, 50%, 75%) | **Prompt-48-Audit** |
| `domain/forecasting/accuracy.py` | 42 | `0.5` | Standard quarterly milestone thresholds (25%, 50%, 75%) | **Prompt-48-Audit** |
| `domain/forecasting/accuracy.py` | 44 | `0.25` | Standard quarterly milestone thresholds (25%, 50%, 75%) | **Prompt-48-Audit** |
| `domain/forecasting/engine.py` | 211 | `0.9` | Empirical statistical confidence score for historical baseline | **Prompt-48-Audit** |
| `domain/forecasting/engine.py` | 322 | `0.9` | Empirical statistical confidence score for seasonal pattern | **Prompt-48-Audit** |
| `domain/forecasting/engine.py` | 506 | `0.3` | Cost trend spiking threshold ratio (30%) | **Prompt-48-Audit** |
| `domain/forecasting/engine.py` | 514 | `0.4` | Cost trend volatility coefficient of variation threshold (0.40) | **Prompt-48-Audit** |
| `domain/forecasting/engine.py` | 530 | `0.05` | Cost trend normalized slope drift threshold (5%) | **Prompt-48-Audit** |
| `domain/hierarchy/service.py` | 1383 | `0.9` | Search ranking score weight | **Prompt-48-Audit** |
| `domain/identity/password_hasher.py` | 22 | `30` | RFC 6238 TOTP standard interval of 30 seconds | **security-arch** |
| `domain/observability/health.py` | 65 | `0.9` | Simulated probe latency metric | **Prompt-48-Audit** |
| `domain/resource_detail/service.py` | 1355 | `0.9` | Derivation multiplier for estimated cost | **Prompt-48-Audit** |
| `domain/statements/acceptance.py` | 94 | `7` | SLA escalation threshold days | **Prompt-48-Audit** |
| `domain/statements/acceptance.py` | 96 | `3` | SLA reminder threshold days | **Prompt-48-Audit** |
| `domain/statements/acceptance.py` | 124 | `5` | SLA overdue threshold days | **Prompt-48-Audit** |
| `domain/statements/disputes.py` | 66 | `5` | Minimum dispute justification text length | **Prompt-48-Audit** |
| `domain/statements/generator.py` | 183 | `Decimal('10.0')` | Budget variance tolerance threshold percentage (10%) | **Prompt-48-Audit** |
| `domain/statements/generator.py` | 205 | `Decimal('50.00')` | Period cost movement significance threshold | **Prompt-48-Audit** |
| `domain/statements/generator.py` | 207 | `Decimal('-50.00')` | Period cost movement significance threshold | **Prompt-48-Audit** |
| `workers/cloudlens_workers/scheduler.py` | 66 | `30.0` | Schedule refresh polling interval seconds | **Prompt-48-Audit** |
| `connectors/diagnostics/service.py` | 219 | `6` | Standard 6-hour reconciliation window slice for backfill planning | **enterprise-arch** |
