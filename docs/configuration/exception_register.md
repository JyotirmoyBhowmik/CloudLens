# CloudLens Configuration Exception Register

Enforces **Mandate M2** and **Prompt 48 Item 35**.
Every allow-listed literal in application code must be approved with a named reason and reviewer.

**Last Updated:** 2026-10-02 18:22:27Z | **Total Exceptions:** 2

| File Path | Line | Literal | Business Rationale | Approving Reviewer |
| :--- | :--- | :--- | :--- | :--- |
| `connectors/diagnostics/service.py` | 219 | `6` | Standard 6-hour reconciliation window slice for backfill planning | **enterprise-arch** |
| `connectors/simulator/connector.py` | 127 | `0.001` | Minimum sleep threshold for OS thread scheduling granularity | **enterprise-arch** |
