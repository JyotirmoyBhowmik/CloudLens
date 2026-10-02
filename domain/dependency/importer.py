"""Bulk Import Engine for CMDB and External File Synchronisation (Prompt 32).

Enforces BBP Section 24:
1. Bulk import of relationships from CMDB (e.g. ServiceNow) or structured files.
2. Provenance recorded as IMPORTED with import_source and import_job_id.
3. Honors merge rules: imported edges do not silently overwrite manual edges.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid

from domain.dependency.merger import EdgeMergeEngine
from domain.dependency.models import (
    BulkImportRequest,
    BulkImportResult,
    DependencyEdge,
    EdgeProvenance,
    TypedEntityRef,
)
from domain.dependency.repository import DependencyRepository
from domain.models.enums import (
    EdgeProvenanceType,
    EdgeStatus,
)
from domain.tenant.context import TenantContext, require_tenant_context

logger = logging.getLogger(__name__)


class BulkDependencyImporter:
    """Imports batch relationships from external CMDBs, CSV, or JSON sources."""

    def __init__(self, repository: DependencyRepository, merge_engine: EdgeMergeEngine) -> None:
        self.repository = repository
        self.merge_engine = merge_engine

    def import_relationships(
        self, request: BulkImportRequest, *, tenant_context: TenantContext
    ) -> BulkImportResult:
        """Executes a bulk relationship import batch with merge validation."""
        tc = require_tenant_context(tenant_context)
        now = dt.datetime.now(dt.UTC)

        created_count = 0
        updated_count = 0
        conflicts_count = 0
        errors: list[str] = []

        for idx, item in enumerate(request.items):
            try:
                # Basic validation
                if not item.source_id or not item.target_id:
                    errors.append(f"Row {idx}: Missing source_id or target_id.")
                    continue

                if item.source_id == item.target_id:
                    errors.append(f"Row {idx}: Self-referential edge forbidden.")
                    continue

                edge_id = f"dep-imp-{tc.tenant_id[:6]}-{uuid.uuid4().hex[:8]}"
                edge = DependencyEdge(
                    id=edge_id,
                    tenant_id=tc.tenant_id,
                    source_ref=TypedEntityRef(
                        entity_type=item.source_type,
                        entity_id=item.source_id,
                    ),
                    target_ref=TypedEntityRef(
                        entity_type=item.target_type,
                        entity_id=item.target_id,
                    ),
                    relationship_type=item.relationship_type,
                    direction=item.direction,
                    provenance=EdgeProvenance(
                        provenance_type=EdgeProvenanceType.IMPORTED,
                        import_source=request.import_source,
                        import_job_id=request.import_job_id,
                        created_at=now,
                    ),
                    confidence=item.confidence,
                    criticality=item.criticality,
                    status=EdgeStatus.ACTIVE,
                    notes=item.notes or f"Imported from {request.import_source}",
                    first_seen=now,
                    last_seen=now,
                    effective_from=now,
                    billing_attributes=item.billing_attributes,
                )

                # Route through merge engine to enforce conflict surfacing against manual edges
                saved, conflict = self.merge_engine.merge_candidate_edge(edge, tenant_context=tc)
                if conflict is not None:
                    conflicts_count += 1
                elif saved.id == edge.id:
                    created_count += 1
                else:
                    updated_count += 1

            except Exception as e:
                msg = f"Row {idx} import error: {str(e)}"
                logger.error(msg)
                errors.append(msg)

        logger.info(
            f"Bulk import '{request.import_job_id}' completed: {created_count} created, "
            f"{updated_count} updated, {conflicts_count} conflicts, {len(errors)} errors."
        )

        return BulkImportResult(
            import_job_id=request.import_job_id,
            import_source=request.import_source,
            total_received=len(request.items),
            edges_created=created_count,
            edges_updated=updated_count,
            conflicts_surfaced=conflicts_count,
            errors=errors,
        )
