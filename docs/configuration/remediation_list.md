# Retrospective Zero Hard-Coding Remediation Register (Prompts 01–44 & 48)

This register records the retrospective static analysis and remediation performed across all modules built under Prompts 01–44, fulfilling **Mandate M2** and **Prompt 48 Item 40**.

---

## 1. Summary of Scan
- **Engine**: AST-based static analyzer (`scripts/check_no_hardcoded_constants.py`) and bidirectional enumeration bridge (`scripts/check_enum_bridge.py`).
- **Scanned Directories**: `api/`, `domain/`, `masterdata/`, `normalisation/`, `workers/`, `connectors/`.
- **Total Unresolved Violations**: **0** (Zero).
- **Compliance Status**: **100% Compliant**.

---

## 2. Remediated Items & Audit History

| Finding ID | Module / File | Category | Original Finding | Remediation Applied | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **REM-001** | `domain/models/enums.py` | Enumeration Parity | Missing `DEVELOPER_TOOLS` in `ServiceCategory` enum | Added `DEVELOPER_TOOLS` to align with `SERVICE_CATEGORY` master seed. | **RESOLVED** |
| **REM-002** | `masterdata/seeds/cloud_provider.json` | Master Parity | Master omitted internal `CANONICAL` boundary role | Seeded `CANONICAL` boundary in `cloud_provider.json` matching `ProviderType.CANONICAL`. | **RESOLVED** |
| **REM-003** | `domain/config/resolver.py` | Provenance Layering | Audit entry metadata not exposed via dedicated report | Built `ConfigurationAuditEngine` surfacing setting values, layer provenance, and change timestamps. | **RESOLVED** |
| **REM-004** | `domain/config/drift_detector.py` | Configuration Drift | No automated drift detection comparing running config to defaults | Built `ConfigurationDriftEngine` detecting modifications and percentage drift against factory baseline. | **RESOLVED** |
| **REM-005** | `masterdata/string_catalogue.py` | User-Facing Text | Static user-facing text and labels stored in code | Created `STRING_CATALOGUE` system master and `StringCatalogueService` (`t()`) for zero-deployment text changes. | **RESOLVED** |
| **REM-006** | `scripts/check_no_hardcoded_constants.py` | Static Analysis | Scanner checked only basic float thresholds | Upgraded AST scanner to detect statuses, severities, roles, colours, formats, and enforce allow-list reviewer validation. | **RESOLVED** |

---

## 3. Deliberately Allowed Exceptions
- Currently, **0** unannotated literals exist in application code.
- Any future exception must follow Rule 35:
  `# no-hardcode-allow: reason="<business-rationale>", reviewer="<lead-reviewer-id>"`
  and will be automatically published into `docs/configuration/exception_register.md`.
