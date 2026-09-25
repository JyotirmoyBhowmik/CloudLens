# CloudLens Orphan Requirement Analysis & Gap-or-Deferral Classification

> **Stage 0 Integrity Verification** — Verifies that every requirement in the 13 ranges resolves to an implementing module in Prompts 00–62, or carries an explicit, documented deferral reason.

## 1. Orphan Analysis Summary

- **Total Requirements Analyzed**: 458
- **MVP Active Requirements (Prompts 00–44, 47B, 49A, 49B, 50–56, 62)**: 450
- **Deliberately Deferred Requirements (Phase 2 / Phase 3)**: 8
- **Unassigned Orphan Requirements (Genuine Gaps)**: **0**

## 2. Deliberately Deferred Requirements (Phase 2 & Phase 3)

| ID | Requirement Statement | Priority | Target Phase | Owning Module / Prompt | Recorded Deferral Justification |
|:---|:---|:---:|:---:|:---|:---|
| **FR-506** | Dashboard widget layout and customization must be user-configurable in Phase 2. | Could | Phase 2 | Prompt 57 / P2 | Deliberately scheduled for Phase 2 under Prompt 57 / P2 |
| **FR-605** | Scheduled recurring report delivery via email and webhook must be available in Phase 2. | Could | Phase 2 | Prompt 60 / P2 | Deliberately scheduled for Phase 2 under Prompt 60 / P2 |
| **PR-007** | Commitment coverage and utilisation analysis for reservations and savings plans must be supported in Phase 2. | Could | Phase 2 | Prompt 58 / P2 | Deliberately scheduled for Phase 2 under Prompt 58 / P2 |
| **CST-032** | Multi-year budget planning, what-if scenario modeling, and commitment capacity planning must be supported in Phase 2. | Could | Phase 2 | Prompt 57 / P2 | Deliberately scheduled for Phase 2 under Prompt 57 / P2 |
| **RUN-010** | Automated resource lifecycle governance (provisioning, active lifecycle, scheduled decommissioning) must be supported in Phase 2. | Could | Phase 2 | Prompt 59 / P2 | Deliberately scheduled for Phase 2 under Prompt 59 / P2 |
| **API-054** | GET/POST /api/v1/plans - Multi-period budget plans and scenario models. | Must | Phase 2 | Prompt 57 | Deliberately scheduled for Phase 2 under Prompt 57 |
| **API-055** | GET /api/v1/commitments/renewals - Commitment tracking, utilization, and renewal pipeline. | Must | Phase 2 | Prompt 58 | Deliberately scheduled for Phase 2 under Prompt 58 |
| **API-056** | GET/POST /api/v1/decommissioning-requests - Resource decommissioning and retirement requests. | Must | Phase 2 | Prompt 59 | Deliberately scheduled for Phase 2 under Prompt 59 |

## 3. Stage 0 Acceptance Sign-Off

- [x] **Requirement 1**: Every one of the thirteen prefixes named in Prompt 00 resolves to a populated range in the register.
- [x] **Requirement 2**: No requirement carries two primary identifiers; all re-classified items retain original ID as metadata.
- [x] **Requirement 3**: Pricing dimension count is exactly 29 across the register, BBP Section 18.2, and Prompt 07.
- [x] **Requirement 4**: Every register entry names the module that will implement it; zero unassigned orphan requirements exist.
