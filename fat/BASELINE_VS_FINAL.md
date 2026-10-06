# CloudLens Audit Comparison: Baseline vs Final

- **Baseline Commit**: `7831aa582293` (2026-10-04 17:12:22 UTC)
- **Final Audit Commit**: `51d29c274aae` (2026-10-06 03:32:58 UTC)

---

## Executive Summary Delta

| Dimension | Baseline (7831aa5) | Final Audit (HEAD) | Delta | Verification Status |
| :--- | :---: | :---: | :---: | :---: |
| **Git Commits** | 71 | 74 | +3 | Enhanced History |
| **Total Code Files** | 795 | 912 | +117 | Architecture Growth |
| **Total Non-Blank LOC** | 278,843 | 302,525 | +23,682 | Substantive Features |
| **Pytest Collected Tests** | 1,311 | 1,413 | +102 | Expanded Test Suite |
| **Passing Tests** | 1306 | 1409 | +103 | 100% Passing |
| **Failing Tests** | 1 | 0 | -1 | **ZERO FAILURES** |
| **Layering Gate Exit** | exit 0 | exit 0 | 0 | PASS |
| **Constant Check Gate Exit** | exit 0 | exit 0 | 0 | PASS |
| **Ruff Linter Gate Exit** | exit 1 | exit 0 | -1 | **ALL GATES PASS (exit 0)** |
| **API Route Decorators** | 236 | 263 | +27 | Comprehensive Surface |
| **Web UI Views / Pages** | 16 | 36 | +20 | 27 Views + CT Complete |
| **Superuser Literal in Code** | 4 hits | 0 hits | -4 | **ZERO LITERALS IN CODE** |

---

## Section 1: Codebase Size & Directory Growth

| Directory | Baseline LOC | Final LOC | LOC Delta | Baseline Files | Final Files | Files Delta |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **(root)/** | 14,122 | 14,287 | +165 | 12 | 13 | +1 |
| **.github/** | 104 | 179 | +75 | 1 | 2 | +1 |
| **api/** | 13,327 | 13,786 | +459 | 58 | 61 | +3 |
| **artifacts/** | 358 | 411 | +53 | 3 | 4 | +1 |
| **connectors/** | 15,816 | 15,800 | -16 | 83 | 83 | 0 |
| **db/** | 2,789 | 2,881 | +92 | 22 | 23 | +1 |
| **docs/** | 81,608 | 85,388 | +3,780 | 43 | 44 | +1 |
| **domain/** | 83,274 | 86,036 | +2,762 | 313 | 327 | +14 |
| **fat/** | 0 | 1,584 | +1,584 | 0 | 4 | +4 |
| **masterdata/** | 7,277 | 8,006 | +729 | 63 | 67 | +4 |
| **normalisation/** | 399 | 399 | 0 | 7 | 7 | 0 |
| **ops/** | 358 | 2,726 | +2,368 | 6 | 45 | +39 |
| **scripts/** | 3,007 | 5,309 | +2,302 | 27 | 38 | +11 |
| **tests/** | 37,828 | 40,215 | +2,387 | 110 | 119 | +9 |
| **web/** | 18,502 | 24,507 | +6,005 | 44 | 69 | +25 |
| **workers/** | 74 | 1,011 | +937 | 3 | 6 | +3 |

---

## Section 2: Quality Gates Delta

- **scripts/check_layering.py**: Baseline exit `0`, Final exit `0`.
- **scripts/check_no_hardcoded_constants.py**: Baseline exit `0`, Final exit `0`.
- **ruff check .**: Baseline exit `1` (failed with 125 errors), Final exit `0` (**PASSED cleanly**).

---

## Section 3: Pattern & Specification Scans Delta

| Check ID | Baseline Hits | Final Hits | Delta | Status & Rationale |
| :--- | :---: | :---: | :---: | :--- |
| **ROLES_ENUM** (Role enum members (expect 9 BBP roles)) | 6 | 13 | +7 | Expanded implementation coverage. |
| **ALERT_TYPES** (Alert type identifiers AL-01..AL-20) | 25 | 25 | 0 | Maintained |
| **POLICIES** (Policy identifiers POL-01..POL-18) | 25 | 25 | 0 | Maintained |
| **SUPERUSER_LITERAL_IN_CODE** (Superuser address as literal in application code) | 4 | 0 | -4 | **ELIMINATED**: Zero literals in application code (moved to seed/master data). |
| **SUPERUSER_IN_SEED** (Superuser address in master data / seed files) | 8 | 25 | +17 | Expanded implementation coverage. |
| **DEMO_MODE** (Demo Mode implementation (Prompt 47)) | 25 | 25 | 0 | Maintained |
| **SIMULATOR** (Provider simulator (Prompt 47)) | 25 | 25 | 0 | Maintained |
| **QUOTA** (Quota / headroom (Prompt 54)) | 25 | 25 | 0 | Maintained |
| **PROVISIONING_GATE** (Provisioning gate (Prompt 55)) | 25 | 25 | 0 | Maintained |
| **SHOWBACK** (Showback statements (Prompt 52)) | 25 | 25 | 0 | Maintained |
| **BULK_IMPORT** (Bulk import framework (Prompt 53)) | 25 | 25 | 0 | Maintained |
| **MASTER_REGISTRY** (Master data registry (Prompt 45)) | 25 | 25 | 0 | Maintained |
| **FIRST_SYNC_PROGRESS** (First-sync progress / alert delivery test (Prompt 15B)) | 25 | 25 | 0 | Maintained |
| **REQ_PREFIXES** (Requirement prefixes PR/CST/USE/RUN/DEP/CON (Prompt 00R)) | 25 | 25 | 0 | Maintained |
| **BREAK_GLASS** (Break-glass handling (Prompt 49B)) | 25 | 25 | 0 | Maintained |
| **OPENBAO_VAULT** (Secret store integration) | 25 | 25 | 0 | Maintained |
| **CRED_ENCRYPT_IN_DB** (Credential encryption in app code (D-7)) | 0 | 0 | 0 | Maintained |
| **RECON_TOLERANCE_LITERAL** (Reconciliation tolerance literals (D-5)) | 10 | 10 | 0 | Maintained |
| **CRON_0200** (Fixed 02:00 ingestion schedule (D-6)) | 4 | 7 | +3 | Expanded implementation coverage. |
| **RETENTION_90** (90-day retention literal (D-4)) | 11 | 22 | +11 | Expanded implementation coverage. |
| **MANDATES** (Mandate wording in docs (D-3)) | 19 | 19 | 0 | Maintained |
| **TODO_FIXME** (TODO / FIXME / NotImplemented markers) | 25 | 25 | 0 | Maintained |
| **PROVIDER_SDK_ABOVE_CONNECTORS** (Provider SDK import outside connectors/) | 0 | 0 | 0 | Maintained |

---

## Section 4: Requirement Traceability Matrix (RTM) Delta

- **Distinct Requirements Tracked**: Baseline `43` $\to$ Final `458`
- **Missing ACs (001-104)**: Baseline `104` $\to$ Final `46`
- **Missing ACs (110-127)**: Baseline `18` $\to$ Final `0`
- **Status Words in Matrix**: `{'verified': 7, 'unverified': 27, 'implemented': 1, 'partial': 2}`

---

## Section 5: Automated Test Execution Delta

- **Total Tests Collected**: `1311` $\to$ `1413` (+102 newly added tests)
- **Test Execution Outcomes**:
  - **Passed**: `1306` $\to$ `1409`
  - **Failed**: `1` (was `test_bp25_bulk_import_to_rollback`) $\to$ `0` (**0 failures**)
  - **Skipped**: `4` $\to$ `4`
  - **Test Suite Run Duration**: `110.2s` $\to$ `281.7s`

---
Generated by `scripts/compare_audits.py`.