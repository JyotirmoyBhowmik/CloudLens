# CloudLens Configuration Exception Register

Enforces **Mandate M2** and **Prompt 48 Item 35**.
Every allow-listed literal in application code must be approved with a named reason and reviewer.

**Last Updated:** 2026-09-27 04:14:13Z | **Total Exceptions:** 1

| File Path | Line | Literal | Business Rationale | Approving Reviewer |
| :--- | :--- | :--- | :--- | :--- |
| `connectors/simulator/connector.py` | 116 | `0.001` | Minimum sleep threshold for OS thread scheduling granularity | **enterprise-arch** |
