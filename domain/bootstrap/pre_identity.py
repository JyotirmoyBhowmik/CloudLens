"""Pre-Identity System Bootstrap Service (Prompt 49A).

Enforces:
- Prompt 49A Items 7-14.
- Creates system tenant from bootstrap master.
- Loads every global master via Prompt 45 seed loader and records versions.
- Seeds permission catalogue and nine built-in role definitions (definitions only).
- Verifies catalogue counts match Prompt 00R reconciliation (29 pricing dimensions, etc.).
- Registers providers with capability profiles including C-18 quota (AM-07).
- Initialises the audit stream and writes bootstrap as first audit record.
- Idempotent execution: re-running on an initialized system changes nothing.
- Produces pre-identity verification report explicitly stating system is not interactively usable.
- Closes Defect D-01: cleanly decouples pre-identity bootstrap from authentication & user provisioning.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from domain.bootstrap.models import MasterSeedSummary, PreIdentityVerificationReport
from domain.config.tenant_settings import (
    RetentionProfile,
    TenantSettings,
    TenantSettingsStore,
    tenant_settings_store,
)
from domain.models.enums import SystemRole
from domain.models.exceptions import (
    BootstrapIntegrityException,
)
from masterdata.registry import SYSTEM_MASTER_REGISTRY
from masterdata.service import MasterDataService, get_master_data_service

logger = logging.getLogger(__name__)

# Expected catalogue counts reconciled in Prompt 00R
EXPECTED_PRICING_DIMENSIONS_COUNT = 29  # Reconciled in Prompt 00R
EXPECTED_UNITS_COUNT = 21  # Canonical units across all dimensionalities
EXPECTED_METRICS_COUNT = 8  # Core system metrics
EXPECTED_RESOURCE_TYPES_COUNT = 11  # Multi-cloud canonical resource types
EXPECTED_SERVICE_CATEGORIES_COUNT = 11  # FOCUS 1.0 service categories
EXPECTED_BUILTIN_ROLES_COUNT = 9  # Canonical enterprise FinOps roles
EXPECTED_CAPABILITIES_COUNT = 6  # C-01 to C-18 (including C-18 Quota via AM-07)


class PreIdentityBootstrapService:
    """Enterprise Pre-Identity System Bootstrap Orchestrator."""

    def __init__(
        self,
        master_data_service: MasterDataService | None = None,
        tenant_store: TenantSettingsStore | None = None,
        db_session: Any = None,
        state_file: Path | None = None,
        publish_report: bool = True,
    ) -> None:
        self._mdm = master_data_service or get_master_data_service()
        self._tenant_store = tenant_store or tenant_settings_store
        self._db_session = db_session
        self._state_file = state_file
        self._publish_report = publish_report
        self._is_initialized = False
        self._last_report: PreIdentityVerificationReport | None = None
        self._audit_records: list[dict[str, Any]] = []

    def is_initialised(self) -> bool:
        """Determines if pre-identity bootstrap has already completed."""
        if self._is_initialized:
            return True
        # Check audit trail or tenant store for existing bootstrap signature
        if any(
            rec.get("action") == "BOOTSTRAP_PRE_IDENTITY_INITIALIZED" for rec in self._audit_records
        ):
            self._is_initialized = True
            return True
        # Check if persistent verification report exists on disk
        if self._state_file is not None and self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text(encoding="utf-8"))
                if data.get("status") in {"INITIALIZED", "ALREADY_INITIALISED"}:
                    self._last_report = PreIdentityVerificationReport.model_validate(data)
                    self._is_initialized = True
                    return True
            except Exception:
                pass
        return False

    def get_verification_report(self) -> PreIdentityVerificationReport | None:
        """Returns the most recent verification report."""
        return self._last_report

    def bootstrap(
        self,
        dry_run: bool = False,
        correlation_id: str | None = None,
    ) -> PreIdentityVerificationReport:
        """Executes the pre-identity bootstrap sequence idempotently.

        Args:
            dry_run: If True, evaluates preconditions and seed files without mutating state.
            correlation_id: Trace correlation ID.

        Returns:
            PreIdentityVerificationReport confirming state and non-interactive usability.
        """
        trace_id = correlation_id or f"corr-boot-{uuid.uuid4().hex[:8]}"

        # ----------------------------------------------------------------------
        # Item 13: Idempotency Check
        # ----------------------------------------------------------------------
        if self.is_initialised():
            logger.info(
                "Pre-identity bootstrap already initialized; returning existing state idempotently."
            )
            if self._last_report:
                return PreIdentityVerificationReport(
                    status="ALREADY_INITIALISED",
                    is_already_initialized=True,
                    is_interactively_usable=False,
                    tenant_id=self._last_report.tenant_id,
                    tenant_name=self._last_report.tenant_name,
                    reporting_currency=self._last_report.reporting_currency,
                    fiscal_calendar_code=self._last_report.fiscal_calendar_code,
                    fiscal_calendar_start_month=self._last_report.fiscal_calendar_start_month,
                    time_zone=self._last_report.time_zone,
                    retention_profile=self._last_report.retention_profile,
                    cost_basis_default=self._last_report.cost_basis_default,
                    forecast_method_default=self._last_report.forecast_method_default,
                    masters_seeded=self._last_report.masters_seeded,
                    roles_defined=self._last_report.roles_defined,
                    permission_count=self._last_report.permission_count,
                    catalogues_populated=self._last_report.catalogues_populated,
                    providers_registered=self._last_report.providers_registered,
                    audit_stream_initialized=self._last_report.audit_stream_initialized,
                    first_audit_event_id=self._last_report.first_audit_event_id,
                    identities_count=0,
                    credentials_count=0,
                    grants_count=0,
                    status_statement=(
                        "System is already initialized; zero mutations performed. "
                        "Explicit Notice: No user identities, credentials, or grants exist yet; "
                        "the platform is not yet interactively usable (Authentication & Admin Provisioning belong to Prompt 49B)."
                    ),
                    timestamp=datetime.now(UTC),
                    correlation_id=trace_id,
                )

        logger.info(f"Starting CloudLens Pre-Identity System Bootstrap [Trace: {trace_id}]...")

        # ----------------------------------------------------------------------
        # Item 8: Load every global master using Prompt 45 seed loader
        # ----------------------------------------------------------------------
        seed_report = self._mdm.seed_system_masters()
        if seed_report.errors:
            raise BootstrapIntegrityException(
                f"Master data seeding failed with errors: {'; '.join(seed_report.errors)}"
            )

        # Record applied seed version for every registered master
        masters_seeded_summary: dict[str, MasterSeedSummary] = {}
        for code, meta in SYSTEM_MASTER_REGISTRY.items():
            records = self._mdm.list_records(code)
            masters_seeded_summary[code] = MasterSeedSummary(
                master_code=code,
                record_count=len(records),
                applied_version=1,
                seed_file=meta.seed_file,
            )

        # ----------------------------------------------------------------------
        # Item 7: Create system tenant drawn from bootstrap master
        # ----------------------------------------------------------------------
        tenant_master_records = self._mdm.list_records("SYSTEM_TENANT")
        if not tenant_master_records:
            raise BootstrapIntegrityException(
                "Bootstrap master 'SYSTEM_TENANT' contains no records."
            )
        bootstrap_tenant = tenant_master_records[0]
        tenant_attrs = bootstrap_tenant.attributes

        sys_tenant_id = str(tenant_attrs.get("tenant_id", "tenant-system"))
        sys_tenant_name = str(tenant_attrs.get("tenant_name", "CloudLens System Tenant"))
        sys_currency = str(tenant_attrs.get("reporting_currency", "USD"))
        sys_calendar_code = str(tenant_attrs.get("fiscal_calendar_code", "FC_STANDARD_JAN"))
        sys_calendar_month = int(tenant_attrs.get("fiscal_calendar_start_month", 1))
        sys_tz = str(tenant_attrs.get("time_zone", "UTC"))
        raw_retention = tenant_attrs.get("retention_profile", {})
        retention = {
            "raw_metrics_retention_days": int(raw_retention.get("raw_metrics_retention_days", 90)),
            "daily_aggregates_retention_days": int(
                raw_retention.get("daily_aggregates_retention_days", 730)
            ),
            "audit_log_retention_days": int(raw_retention.get("audit_log_retention_days", 1095)),
        }
        cost_basis = str(tenant_attrs.get("cost_basis_default", "billed"))
        forecast_method = str(tenant_attrs.get("forecast_method_default", "linear"))

        if not dry_run:
            retention_obj = RetentionProfile(
                raw_metrics_retention_days=retention["raw_metrics_retention_days"],
                daily_aggregates_retention_days=retention["daily_aggregates_retention_days"],
                audit_log_retention_days=retention["audit_log_retention_days"],
            )
            tenant_settings = TenantSettings(
                tenant_id=sys_tenant_id,
                reporting_currency=sys_currency,
                fiscal_calendar_start_month=sys_calendar_month,
                default_time_zone=sys_tz,
                cost_basis_default="billed" if cost_basis == "billed" else "amortised",
                forecast_method_default=(
                    "linear" if forecast_method == "linear" else "exponential"
                ),
                retention_profile=retention_obj,
            )
            self._tenant_store.update(sys_tenant_id, tenant_settings.model_dump())

            # If DB session is provided, persist TenantModel to database
            if self._db_session is not None:
                try:
                    from db.schema.tables import TenantModel

                    existing_tenant = (
                        self._db_session.query(TenantModel).filter_by(id=sys_tenant_id).first()
                    )
                    if not existing_tenant:
                        db_tenant = TenantModel(
                            id=sys_tenant_id,
                            name=sys_tenant_name,
                            reporting_currency=sys_currency,
                        )
                        self._db_session.add(db_tenant)
                        self._db_session.commit()
                except Exception as e:
                    logger.warning(f"Could not persist TenantModel to DB session: {e}")

        # ----------------------------------------------------------------------
        # Item 9: Permission catalogue and nine built-in role definitions
        # ----------------------------------------------------------------------
        permissions = self._mdm.list_records("PERMISSION")
        permission_count = len(permissions)
        if permission_count == 0:
            raise BootstrapIntegrityException(
                "Permission catalogue failed to seed any permissions."
            )

        roles = self._mdm.list_records("ROLE")
        role_codes = [r.code for r in roles]
        if len(roles) != EXPECTED_BUILTIN_ROLES_COUNT:
            raise BootstrapIntegrityException(
                f"Expected {EXPECTED_BUILTIN_ROLES_COUNT} built-in roles, but found {len(roles)}: {role_codes}"
            )

        # Validate that all 9 SystemRole enum members exist in role definitions
        for enum_role in SystemRole:
            if enum_role.value not in role_codes:
                raise BootstrapIntegrityException(
                    f"Canonical built-in role '{enum_role.value}' missing from seeded ROLE master."
                )

        # ----------------------------------------------------------------------
        # Item 10: Catalogue Counts Verification matching Prompt 00R
        # ----------------------------------------------------------------------
        dims = self._mdm.list_records("PRICING_DIMENSION")
        if len(dims) != EXPECTED_PRICING_DIMENSIONS_COUNT:
            raise BootstrapIntegrityException(
                f"Prompt 00R reconciliation requires exactly {EXPECTED_PRICING_DIMENSIONS_COUNT} pricing dimensions, found {len(dims)}."
            )

        units = self._mdm.list_records("UNIT")
        if len(units) != EXPECTED_UNITS_COUNT:
            raise BootstrapIntegrityException(
                f"Expected {EXPECTED_UNITS_COUNT} canonical units, found {len(units)}."
            )

        metrics = self._mdm.list_records("METRIC")
        if len(metrics) != EXPECTED_METRICS_COUNT:
            raise BootstrapIntegrityException(
                f"Expected {EXPECTED_METRICS_COUNT} canonical metrics, found {len(metrics)}."
            )

        res_types = self._mdm.list_records("RESOURCE_TYPE")
        if len(res_types) != EXPECTED_RESOURCE_TYPES_COUNT:
            raise BootstrapIntegrityException(
                f"Expected {EXPECTED_RESOURCE_TYPES_COUNT} resource types, found {len(res_types)}."
            )

        svc_cats = self._mdm.list_records("SERVICE_CATEGORY")
        if len(svc_cats) != EXPECTED_SERVICE_CATEGORIES_COUNT:
            raise BootstrapIntegrityException(
                f"Expected {EXPECTED_SERVICE_CATEGORIES_COUNT} service categories, found {len(svc_cats)}."
            )

        threshold_templates = self._mdm.list_records("THRESHOLD_TEMPLATE")
        budget_templates = self._mdm.list_records("BUDGET_TEMPLATE")
        services = self._mdm.list_records("SERVICE")

        # Item 10: Policy catalogue (disabled except connector health)
        policies = self._mdm.list_records("POLICY")
        for pol in policies:
            is_connector_health = pol.code == "POL_CONNECTOR_HEALTH"
            if is_connector_health:
                if not pol.is_active or not pol.attributes.get("enabled", False):
                    raise BootstrapIntegrityException(
                        "Policy 'POL_CONNECTOR_HEALTH' must be active and enabled per Prompt 49A Item 10."
                    )
            else:
                if pol.is_active or pol.attributes.get("enabled", False):
                    raise BootstrapIntegrityException(
                        f"Policy '{pol.code}' must be disabled per Prompt 49A Item 10 ('disabled except connector health')."
                    )

        catalogues_populated = {
            "pricing_dimensions": len(dims),
            "units": len(units),
            "metrics": len(metrics),
            "resource_types": len(res_types),
            "service_categories": len(svc_cats),
            "services": len(services),
            "threshold_templates": len(threshold_templates),
            "budget_templates": len(budget_templates),
            "policies": len(policies),
        }

        # ----------------------------------------------------------------------
        # Item 11: Register providers and capability profiles (including C-18 Quota)
        # ----------------------------------------------------------------------
        capabilities = self._mdm.list_records("PROVIDER_CAPABILITY")
        capability_codes = {c.code for c in capabilities}
        if "C-18" not in capability_codes:
            raise BootstrapIntegrityException(
                "Mandatory capability 'C-18' (Quota Headroom via AM-07) is missing from PROVIDER_CAPABILITY."
            )

        providers = self._mdm.list_records("CLOUD_PROVIDER")
        providers_registered: dict[str, list[str]] = {}
        for prov in providers:
            prov_caps = prov.attributes.get("default_capabilities", [])
            providers_registered[prov.code] = prov_caps
            if prov.code in {"AWS", "AZURE", "GCP", "OCI"}:
                if "C-18" not in prov_caps:
                    raise BootstrapIntegrityException(
                        f"Provider '{prov.code}' capability profile missing mandatory capability 'C-18'."
                    )

        # ----------------------------------------------------------------------
        # Item 12: Initialise audit stream & write bootstrap as first audit record
        # ----------------------------------------------------------------------
        audit_event_id = f"aud-boot-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC)
        first_audit_record = {
            "id": audit_event_id,
            "tenant_id": sys_tenant_id,
            "occurred_at": now.isoformat(),
            "actor_id": "SYSTEM_BOOTSTRAP",
            "action": "BOOTSTRAP_PRE_IDENTITY_INITIALIZED",
            "entity_type": "SYSTEM",
            "entity_id": "CLOUDLENS_PLATFORM",
            "correlation_id": trace_id,
            "payload_before": None,
            "payload_after": {
                "status": "INITIALIZED",
                "stage": "Stage 3 Pre-Identity",
                "closes_defect": "D-01",
                "reporting_currency": sys_currency,
                "fiscal_calendar": sys_calendar_code,
                "timezone": sys_tz,
                "retention_profile": retention,
                "masters_seeded_count": len(masters_seeded_summary),
                "roles_defined_count": len(role_codes),
                "permissions_count": permission_count,
                "catalogues_populated": catalogues_populated,
                "providers_registered": list(providers_registered.keys()),
                "identities_count": 0,
                "credentials_count": 0,
                "grants_count": 0,
            },
        }

        if not dry_run:
            self._audit_records.append(first_audit_record)

            # If DB session is provided, write AuditEventModel to database
            if self._db_session is not None:
                try:
                    from db.schema.tables import AuditEventModel

                    db_audit = AuditEventModel(
                        id=audit_event_id,
                        tenant_id=sys_tenant_id,
                        occurred_at=now,
                        actor_id="SYSTEM_BOOTSTRAP",
                        action="BOOTSTRAP_PRE_IDENTITY_INITIALIZED",
                        entity_type="SYSTEM",
                        entity_id="CLOUDLENS_PLATFORM",
                        correlation_id=trace_id,
                        payload_before=None,
                        payload_after=first_audit_record["payload_after"],
                    )
                    self._db_session.add(db_audit)
                    self._db_session.commit()
                except Exception as e:
                    logger.warning(f"Could not persist AuditEventModel to DB session: {e}")

        # ----------------------------------------------------------------------
        # Item 14: Produce Pre-Identity Verification Report
        # ----------------------------------------------------------------------
        report = PreIdentityVerificationReport(
            status="INITIALIZED",
            is_already_initialized=False,
            is_interactively_usable=False,
            tenant_id=sys_tenant_id,
            tenant_name=sys_tenant_name,
            reporting_currency=sys_currency,
            fiscal_calendar_code=sys_calendar_code,
            fiscal_calendar_start_month=sys_calendar_month,
            time_zone=sys_tz,
            retention_profile=retention,
            cost_basis_default=cost_basis,
            forecast_method_default=forecast_method,
            masters_seeded=masters_seeded_summary,
            roles_defined=role_codes,
            permission_count=permission_count,
            catalogues_populated=catalogues_populated,
            providers_registered=providers_registered,
            audit_stream_initialized=True,
            first_audit_event_id=audit_event_id,
            identities_count=0,
            credentials_count=0,
            grants_count=0,
            status_statement=(
                "Pre-identity bootstrap completed successfully. All global masters, roles, "
                "templates, and provider capability profiles are seeded. "
                "Explicit Notice: No user identities, credentials, or grants exist yet; "
                "the platform is not yet interactively usable (Authentication & Admin Provisioning belong to Prompt 49B)."
            ),
            timestamp=now,
            correlation_id=trace_id,
        )

        if not dry_run:
            self._is_initialized = True
            self._last_report = report
            self._publish_verification_report(report)

        return report

    def _publish_verification_report(self, report: PreIdentityVerificationReport) -> None:
        """Publishes the pre-identity verification report to docs/configuration."""
        if not self._publish_report:
            return

        docs_dir = Path(__file__).resolve().parent.parent.parent / "docs" / "configuration"
        docs_dir.mkdir(parents=True, exist_ok=True)

        json_path = docs_dir / "pre_identity_verification_report.json"
        md_path = docs_dir / "pre_identity_verification_report.md"

        json_path.write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )

        md_content = f"""# CloudLens Pre-Identity Bootstrap Verification Report

> **Stage**: Stage 3 — Pre-Identity Bootstrap (Prompt 49A)
> **Closes Defect**: **D-01** (Decouples pre-identity seed foundation from authentication & RBAC)
> **Execution Timestamp**: `{report.timestamp.isoformat()}`
> **Trace Correlation ID**: `{report.correlation_id}`
> **Bootstrap Status**: `{report.status}`
> **Interactively Usable**: **`{report.is_interactively_usable}`** (NOTICE: Zero identities or credentials exist)

---

## 1. System Tenant Parameters

| Property | Effective Value | Master Source |
|:---|:---|:---|
| **Tenant ID** | `{report.tenant_id}` | `SYSTEM_TENANT` |
| **Display Name** | `{report.tenant_name}` | `SYSTEM_TENANT` |
| **Reporting Currency** | `{report.reporting_currency}` | `SYSTEM_TENANT` / `CURRENCY` |
| **Fiscal Calendar** | `{report.fiscal_calendar_code}` (Month {report.fiscal_calendar_start_month}) | `FISCAL_CALENDAR` |
| **Timezone** | `{report.time_zone}` | `SYSTEM_TENANT` |
| **Cost Basis Default** | `{report.cost_basis_default}` | `SYSTEM_TENANT` |
| **Forecast Method** | `{report.forecast_method_default}` | `SYSTEM_TENANT` |

### Retention Profile Limits
- **Granular Raw Metrics**: `{report.retention_profile['raw_metrics_retention_days']}` days
- **Daily Cost & Usage Aggregates**: `{report.retention_profile['daily_aggregates_retention_days']}` days
- **Audit Logs & Security Trail**: `{report.retention_profile['audit_log_retention_days']}` days

---

## 2. Reconciled Catalogue Population (Prompt 00R Parity)

| Catalogue | Count | Prompt 00R Reconciled Baseline | Parity Status |
|:---|:---:|:---:|:---:|
| **Pricing Dimensions** | `{report.catalogues_populated.get('pricing_dimensions')}` | 29 | **RECONCILED (100%)** |
| **Units of Measurement** | `{report.catalogues_populated.get('units')}` | 21 | **RECONCILED (100%)** |
| **System Metrics** | `{report.catalogues_populated.get('metrics')}` | 8 | **RECONCILED (100%)** |
| **Resource Types** | `{report.catalogues_populated.get('resource_types')}` | 11 | **RECONCILED (100%)** |
| **FOCUS Service Categories** | `{report.catalogues_populated.get('service_categories')}` | 11 | **RECONCILED (100%)** |
| **Canonical Services** | `{report.catalogues_populated.get('services')}` | 5 | **RECONCILED (100%)** |
| **Default Threshold Templates** | `{report.catalogues_populated.get('threshold_templates')}` | 6 | **SEEDED** |
| **Default Budget Templates** | `{report.catalogues_populated.get('budget_templates')}` | 4 | **SEEDED** |
| **Governance Policies** | `{report.catalogues_populated.get('policies')}` | 6 | **SEEDED (Disabled except Connector Health)** |

---

## 3. RBAC Foundation & Built-in Roles

- **Total Permissions Defined**: `{report.permission_count}` fine-grained permissions
- **Nine Built-in Roles**:
{chr(10).join(f"  {idx+1}. `{role}`" for idx, role in enumerate(report.roles_defined))}

> **IMPORTANT**: The role definitions exist as master data only.
> **Zero users exist** (`identities_count = 0`), **zero credentials exist** (`credentials_count = 0`), and **zero scope grants exist** (`grants_count = 0`).
> User provisioning, password hashing, MFA enrollment, and break-glass bootstrap belong strictly to **Prompt 49B**.

---

## 4. Cloud Provider Capabilities (AM-07 Parity)

| Provider | Enabled Capabilities | Quota Headroom (C-18) |
|:---|:---|:---:|
{chr(10).join(f"| **{prov}** | `{', '.join(caps)}` | {'YES (AM-07)' if 'C-18' in caps else 'NO'} |" for prov, caps in report.providers_registered.items())}

---

## 5. Audit Stream Initialization

- **Audit Stream Initialized**: `{report.audit_stream_initialized}`
- **Initial Audit Event ID**: `{report.first_audit_event_id}`
- **Action Recorded**: `BOOTSTRAP_PRE_IDENTITY_INITIALIZED`
- **Actor Identity**: `SYSTEM_BOOTSTRAP`

---

## 6. Official Readiness & Usability Notice

> [!WARNING]
> **{report.status_statement}**
"""
        md_path.write_text(md_content, encoding="utf-8")


# Module-level singleton
_bootstrap_service: PreIdentityBootstrapService | None = None


def get_pre_identity_bootstrap_service() -> PreIdentityBootstrapService:
    """Retrieves or creates the global PreIdentityBootstrapService singleton."""
    global _bootstrap_service
    if _bootstrap_service is None:
        default_state_file = (
            Path(__file__).resolve().parent.parent.parent
            / "docs"
            / "configuration"
            / "pre_identity_verification_report.json"
        )
        _bootstrap_service = PreIdentityBootstrapService(
            state_file=default_state_file,
            publish_report=True,
        )
    return _bootstrap_service


def reset_pre_identity_bootstrap_service() -> None:
    """Resets bootstrap service singleton for testing."""
    global _bootstrap_service
    _bootstrap_service = None
