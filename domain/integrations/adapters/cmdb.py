"""CMDB Integration Adapter with Declared Field Authority and Conflict Surfacing (Prompt 60 / BBP Section 13.5).

Enforces:
- Inherits from BaseIntegrationAdapter with declared capabilities:
  AUTHENTICATE, HEALTH_CHECK, IMPORT_ENTITIES, SURFACE_CONFLICTS.
- Integrates with Prompt 53 Bulk Import framework for applications, owners, services, and dependency edges.
- Declared Field Authority: The CMDB is declared as the sole authoritative source for nominated fields.
- Overwrite Protection: CloudLens strictly declines to overwrite any CMDB-authoritative field and
  surfaces the divergence as a CMDBConflictRecord for explicit human governance resolution.
  Conflicts are surfaced, never silently resolved.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from domain.integrations.contract import BaseIntegrationAdapter
from domain.integrations.exceptions import AuthoritativeFieldOverwriteBlockedException
from domain.integrations.models import (
    CMDBConflictRecord,
    IntegrationConfig,
)
from domain.models.enums import (
    FieldAuthority,
    IntegrationCapability,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)


class CMDBAdapter(BaseIntegrationAdapter):
    """Adapter for Enterprise Configuration Management Databases (ServiceNow CMDB, Atlassian Assets)."""

    def __init__(
        self,
        config: IntegrationConfig,
        declared_capabilities: set[IntegrationCapability] | None = None,
    ) -> None:
        super().__init__(config, declared_capabilities)
        # Nominated authoritative fields: e.g. ["owner_email", "criticality_tier", "business_service"]
        self._authoritative_fields = set(
            config.authoritative_fields
            or config.custom_attributes.get(
                "authoritative_fields",
                ["owner_email", "criticality_tier", "lifecycle_phase", "business_service"],
            )
        )
        # In-memory store of imported CMDB records: (entity_type, natural_key) -> attributes
        self._cmdb_records: dict[tuple[str, str], dict[str, Any]] = {}
        # Conflict registry: conflict_id -> CMDBConflictRecord
        self._conflicts: dict[str, CMDBConflictRecord] = {}

    @property
    def adapter_name(self) -> str:
        return f"{self.config.custom_attributes.get('system_type', 'servicenow').lower()}_cmdb"

    def default_capabilities(self) -> set[IntegrationCapability]:
        return {
            IntegrationCapability.AUTHENTICATE,
            IntegrationCapability.HEALTH_CHECK,
            IntegrationCapability.IMPORT_ENTITIES,
            IntegrationCapability.SURFACE_CONFLICTS,
        }

    @property
    def authoritative_fields(self) -> set[str]:
        """Returns the set of fields where CMDB is declared as authoritative."""
        return set(self._authoritative_fields)

    def is_authoritative(self, field_name: str) -> bool:
        """Checks if a field is nominated as CMDB-authoritative."""
        return field_name in self._authoritative_fields

    def import_cmdb_records(
        self,
        entity_type: str,
        records: list[dict[str, Any]],
        natural_key_field: str = "code",
        *,
        tenant_context: TenantContext,
    ) -> dict[str, Any]:
        """Imports entity records (applications, business services, edges) from external CMDB."""

        def _action() -> dict[str, Any]:
            created = 0
            updated = 0

            for rec in records:
                natural_key = str(rec.get(natural_key_field, "")).strip()
                if not natural_key:
                    continue

                key = (entity_type.upper(), natural_key)
                enriched = dict(rec)
                enriched["_imported_at"] = dt.datetime.now(dt.UTC).isoformat()
                enriched["_provenance_source"] = "CMDB_IMPORT"
                enriched["_declared_authority"] = FieldAuthority.CMDB.value
                enriched["_tenant_id"] = tenant_context.tenant_id

                if key in self._cmdb_records:
                    self._cmdb_records[key].update(enriched)
                    updated += 1
                else:
                    self._cmdb_records[key] = enriched
                    created += 1

            logger.info(
                "CMDB import for '%s' processed %d records (created=%d, updated=%d).",
                entity_type,
                len(records),
                created,
                updated,
            )
            return {
                "entity_type": entity_type,
                "total_records": len(records),
                "created": created,
                "updated": updated,
                "status": "SUCCESS",
            }

        return self.execute_with_resilience(
            IntegrationCapability.IMPORT_ENTITIES,
            "import_cmdb_records",
            _action,
        )

    def validate_or_block_overwrite(
        self,
        entity_type: str,
        natural_key: str,
        proposed_updates: dict[str, Any],
        *,
        tenant_context: TenantContext,
        raise_on_blocked: bool = True,
    ) -> list[CMDBConflictRecord]:
        """Validates proposed CloudLens updates against CMDB-authoritative fields.

        Acceptance requirement:
        - A CMDB-authoritative field is not overwritten by CloudLens.
        - The conflict is surfaced for resolution (never silently resolved).
        """
        conflicts: list[CMDBConflictRecord] = []
        key = (entity_type.upper(), natural_key)
        existing_cmdb_data = self._cmdb_records.get(key, {})

        for field_name, new_val in proposed_updates.items():
            if self.is_authoritative(field_name):
                cmdb_val = existing_cmdb_data.get(field_name)
                # If CMDB has a value and CloudLens proposes a different value, conflict!
                if cmdb_val is not None and cmdb_val != new_val:
                    conflict = CMDBConflictRecord(
                        tenant_id=tenant_context.tenant_id,
                        entity_type=entity_type.upper(),
                        natural_key=natural_key,
                        field_name=field_name,
                        cmdb_value=cmdb_val,
                        cloudlens_value=new_val,
                        declared_authority=FieldAuthority.CMDB,
                        surfaced=True,
                        resolved=False,
                    )
                    self._conflicts[conflict.conflict_id] = conflict
                    conflicts.append(conflict)

                    logger.warning(
                        "CMDB Authority Conflict: Proposed update to '%s.%s' rejected. "
                        "CMDB value='%s', CloudLens proposed='%s'. Conflict ID='%s'.",
                        entity_type,
                        field_name,
                        cmdb_val,
                        new_val,
                        conflict.conflict_id,
                    )

        if conflicts and raise_on_blocked:
            first = conflicts[0]
            raise AuthoritativeFieldOverwriteBlockedException(
                f"Field '{first.field_name}' on {first.entity_type} '{first.natural_key}' "
                f"is authoritative in CMDB ('{first.cmdb_value}') and cannot be overwritten by "
                f"CloudLens ('{first.cloudlens_value}'). Surfaced conflict '{first.conflict_id}'."
            )

        return conflicts

    def get_surfaced_conflicts(
        self, tenant_id: str | None = None, unresolved_only: bool = True
    ) -> list[CMDBConflictRecord]:
        """Returns all surfaced CMDB conflicts awaiting governance resolution."""
        results: list[CMDBConflictRecord] = []
        for c in self._conflicts.values():
            if tenant_id and c.tenant_id != tenant_id:
                continue
            if unresolved_only and c.resolved:
                continue
            results.append(c)
        return results

    def resolve_conflict(
        self,
        conflict_id: str,
        actor_id: str,
        resolution_strategy: str,
        note: str,
    ) -> CMDBConflictRecord:
        """Records resolution of a surfaced CMDB authority conflict."""
        conflict = self._conflicts.get(conflict_id)
        if not conflict:
            raise KeyError(f"Conflict '{conflict_id}' not found.")

        conflict.resolved = True
        conflict.resolved_by = actor_id
        conflict.resolution_note = f"[{resolution_strategy}] {note}"
        logger.info(
            "Conflict '%s' resolved by '%s' with strategy '%s'.",
            conflict_id,
            actor_id,
            resolution_strategy,
        )
        return conflict

    def get_cmdb_record(self, entity_type: str, natural_key: str) -> dict[str, Any] | None:
        """Retrieves an imported CMDB record by entity type and natural key."""
        return self._cmdb_records.get((entity_type.upper(), natural_key))
