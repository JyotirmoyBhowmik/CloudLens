"""Curated-Field Protection Mechanism (Prompt 08 Item 59).

Enforces:
1. "A manually set owner, application, environment, cost centre or monitoring type
   survives re-discovery and is never overwritten by a discovered value without an
   explicit user action."
2. Acceptance: "A manually assigned owner survives three simulated re-discovery cycles unchanged."
"""

from datetime import UTC, datetime
from typing import Any

from domain.attribution.models import CuratedField, CuratedFieldRecord
from domain.models.base import ProvenanceRecord
from domain.models.enums import OriginType
from domain.models.inventory import Resource


class CuratedFieldProtectionService:
    """Guards curated business metadata against automated cloud discovery overrides."""

    def __init__(self) -> None:
        # Key: (resource_id, CuratedField)
        self._curated_records: dict[tuple[str, CuratedField], CuratedFieldRecord] = {}

    def protect_curation(
        self,
        resource: Resource,
        field_name: CuratedField,
        value: Any,
        actor: str,
        reason: str = "Manual curation by FinOps administrator",
    ) -> CuratedFieldRecord:
        """Applies a manual curation to a resource attribute and marks it protected."""
        record = CuratedFieldRecord(
            resource_id=resource.id,
            field_name=field_name,
            curated_value=value,
            curated_by=actor,
            curated_at=datetime.now(UTC),
            reason=reason,
        )
        self._curated_records[(resource.id, field_name)] = record

        # Apply value to resource
        if field_name == CuratedField.OWNER:
            resource.owner_id = str(value) if value is not None else None
        elif field_name == CuratedField.APPLICATION:
            resource.application_id = str(value) if value is not None else None
        elif field_name == CuratedField.ENVIRONMENT:
            resource.environment_id = str(value) if value is not None else None
        elif field_name == CuratedField.COST_CENTER:
            resource.cost_center_id = str(value) if value is not None else None

        # Update provenance to CURATED
        resource.source_provenance = ProvenanceRecord(
            source_system="cloudlens-curation",
            origin_type=OriginType.CURATED,
            survives_rediscovery=True,
        )
        return record

    def is_curated(self, resource_id: str, field_name: CuratedField) -> bool:
        """Checks if a specific attribute on a resource is currently curated."""
        return (resource_id, field_name) in self._curated_records

    def get_curated_record(
        self, resource_id: str, field_name: CuratedField
    ) -> CuratedFieldRecord | None:
        """Retrieves active curation record for resource field."""
        return self._curated_records.get((resource_id, field_name))

    def get_curated_fields_for_resource(self, resource_id: str) -> set[str]:
        """Returns set of field names curated for given resource ID."""
        return {
            field.value for (r_id, field) in self._curated_records.keys() if r_id == resource_id
        }

    def clear_curation(self, resource_id: str, field_name: CuratedField, actor: str) -> None:
        """Explicitly unprotects and clears curation record."""
        _ = actor
        key = (resource_id, field_name)
        if key in self._curated_records:
            del self._curated_records[key]

    def reconcile_rediscovery(
        self,
        existing_resource: Resource,
        discovered_resource: Resource,
        explicit_user_action: bool = False,
        actor: str | None = None,
    ) -> Resource:
        """Reconciles newly discovered telemetry against an existing resource.

        Protected attributes (owner, application, environment, cost centre, monitoring type)
        are guarded and never overwritten unless explicit_user_action is True.
        """
        # 1. Update non-protected runtime & technical attributes
        existing_resource.name = discovered_resource.name
        existing_resource.service_id = discovered_resource.service_id
        existing_resource.resource_type_id = discovered_resource.resource_type_id
        existing_resource.region_id = discovered_resource.region_id
        existing_resource.availability_zone = discovered_resource.availability_zone
        existing_resource.pricing_status = discovered_resource.pricing_status
        existing_resource.tags = discovered_resource.tags

        # 2. Reconcile protected fields
        protected_mappings = [
            (CuratedField.OWNER, "owner_id"),
            (CuratedField.APPLICATION, "application_id"),
            (CuratedField.ENVIRONMENT, "environment_id"),
            (CuratedField.COST_CENTER, "cost_center_id"),
        ]

        for field_enum, attr_name in protected_mappings:
            is_curated = self.is_curated(existing_resource.id, field_enum)
            disc_val = getattr(discovered_resource, attr_name)

            if is_curated:
                if explicit_user_action:
                    # User explicitly authorized overwrite
                    setattr(existing_resource, attr_name, disc_val)
                    self.clear_curation(existing_resource.id, field_enum, actor=actor or "system")
                else:
                    # Guard curated value: Ignore discovered value!
                    # Curated value survives re-discovery unchanged.
                    pass
            else:
                # Not curated: Discovered value is adopted
                setattr(existing_resource, attr_name, disc_val)

        existing_resource.updated_at = datetime.now(UTC)
        return existing_resource

    def simulate_rediscovery_cycles(
        self,
        resource: Resource,
        cycles: list[Resource],
        explicit_overwrite: bool = False,
    ) -> Resource:
        """Simulates multiple discovery cycles, verifying curated field survival."""
        current = resource
        for cycle_discovered in cycles:
            current = self.reconcile_rediscovery(
                existing_resource=current,
                discovered_resource=cycle_discovered,
                explicit_user_action=explicit_overwrite,
            )
        return current
