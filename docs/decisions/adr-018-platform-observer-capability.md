# Architecture Decision Record: Platform Observer Capability & RBAC Matrix

- **Status**: ACCEPTED & IMPLEMENTED
- **Date**: 2026-10-05
- **Deciders**: Enterprise Architecture Board, Security Architecture Team
- **Prompt Reference**: Prompt R-ROLES

## 1. Context & Problem Statement
In multi-tenant FinOps environments, operations, security, and administrative personas require distinct levels of platform-wide visibility and administrative authority. Previously, coarse-grained administrative roles combined read and mutation capabilities, posing privilege escalation risks. Furthermore, compliance auditors required cross-tenant observability into Control Tower telemetry without possessing rights to mutate connectors, budgets, or operational overrides.

## 2. Decision Drivers
- Strict alignment with BBP Nine Canonical Roles: `SUPER_ADMIN`, `PLATFORM_ADMIN`, `CLOUD_ADMINISTRATOR`, `FINOPS_ADMINISTRATOR`, `FINANCE_USER`, `IT_OPERATIONS_USER`, `APPLICATION_OWNER`, `READ_ONLY_USER`, `AUDITOR`.
- Introduction of explicit platform-level capabilities: `platform.observe`, `platform.operate`, and `platform.act_as`.
- Mandatory enforcement of least-privilege: `AUDITOR` may observe cross-tenant status (`platform.observe`) but must receive `403 Forbidden` on every operational mutation (`platform.operate`, `platform.act_as`, `overrides:apply`).
- Complete RBAC Matrix test coverage across all OpenAPI routes ($9 \times 446 = 4,014$ cells).
- Zero-access enforcement and security alerts for unmapped IdP groups.

## 3. Considered Options
1. **Status Quo**: Overloaded `GLOBAL_ADMIN` and `TENANT_ADMIN` roles with heuristic string matching and implicit bypasses. *(Rejected)*
2. **Coarse Role Extension**: Adding boolean flags on role models without permission catalogue alignment. *(Rejected)*
3. **Master-Data-Driven RBAC Matrix & Enumeration Bridging**: Defining all nine roles and 48 capabilities in authoritative master data seeds (`masterdata/seeds/role.json`, `masterdata/seeds/permission.json`), bridged bidirectionally via `EnumerationBridge`, with fine-grained declarative scope grants across all eight dimensions. *(Accepted)*

## 4. Decision
We adopted Option 3:
1. **BBP Nine Roles**: Registered `SUPER_ADMIN`, `PLATFORM_ADMIN`, `CLOUD_ADMINISTRATOR`, `FINOPS_ADMINISTRATOR`, `FINANCE_USER`, `IT_OPERATIONS_USER`, `APPLICATION_OWNER`, `READ_ONLY_USER`, and `AUDITOR` in master data and `SystemRole` enum with full backward-compatibility meta-access.
2. **Platform Capabilities**:
   - `platform.observe`: Granted to `SUPER_ADMIN`, `PLATFORM_ADMIN`, and `AUDITOR`. Enables aggregated read-only Control Tower visibility across all tenants.
   - `platform.operate`: Granted to `SUPER_ADMIN` and `PLATFORM_ADMIN` (step-up authentication required). `AUDITOR` has zero access.
   - `platform.act_as`: Granted to `SUPER_ADMIN` only. Requires step-up authentication, $\ge 20$-character business justification, short-lived token, and generates mandatory audit event and alert.
3. **Scope Grants & Precedence**: Evaluated across 8 canonical dimensions (provider, account, hierarchy, project, cost centre, financial sensitivity, administrative, resource exceptions) with strict Deny-Over-Allow precedence.
4. **IdP Safeguard**: Any authenticating user whose IdP groups cannot be mapped to platform roles is denied entry, issued zero permissions, and generates an `UNMAPPED_ROLE_ACCESS_DENIED` security alert.

## 5. Consequences
- **Positive**:
  - Full compliance with BBP v1.1 Section 33.
  - Zero privilege escalation paths for compliance auditors.
  - Complete matrix verification ($4,014$ cells evaluated with zero mismatches).
- **Negative / Operational Considerations**:
  - Requires explicit `platform.operate` step-up when executing Control Tower administrative actions.
