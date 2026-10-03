"""Generic Bulk Import and Data Onboarding Engine (Prompt 53).

Implements:
1. Complete dry-run validation reporting created, updated, skipped, rejected, and deactivated rows.
2. Four explicit import modes: INSERT_ONLY, UPDATE_ONLY, UPSERT, DEACTIVATE_MISSING.
3. Master-data configured atomicity policies: ALL_OR_NOTHING vs PARTIAL_SUCCESS.
4. Row-level provenance stamped on every imported record.
5. Time-boxed rollback path with dependent change guard and audit logging.
6. Export symmetry and round-trip support (export-edit-reimport).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import logging
import uuid
from typing import Any

from domain.audit.service import AuditService
from domain.bulk_import.catalogue import (
    ImportableEntityCatalogue,
    get_import_catalogue,
)
from domain.bulk_import.file_parser import (
    compute_content_hash,
    parse_file_content,
)
from domain.bulk_import.models import (
    AtomicityPolicy,
    DryRunRowResult,
    DryRunSummary,
    ImportMode,
    ImportProvenance,
    ImportRunRecord,
    ImportStatus,
    MappingProfile,
    RowOutcome,
)
from domain.bulk_import.repository import (
    BulkImportRepository,
    get_bulk_import_repository,
)
from domain.bulk_import.validator import BulkImportValidator
from domain.models.enums import AuditEventType
from domain.models.exceptions import (
    BulkImportException,
    DryRunRequiredException,
    ImportRunNotFoundException,
    ImportValidationException,
    RollbackBlockedException,
    RollbackWindowExpiredException,
)
from domain.tenant.context import TenantContext, require_tenant_context
from masterdata.service import MasterDataService, get_master_data_service

logger = logging.getLogger(__name__)


class BulkImportEngine:
    """Core processing engine for enterprise bulk imports, dry runs, and rollbacks."""

    def __init__(
        self,
        repository: BulkImportRepository | None = None,
        catalogue: ImportableEntityCatalogue | None = None,
        master_service: MasterDataService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self.repository = repository or get_bulk_import_repository()
        self.catalogue = catalogue or get_import_catalogue()
        self.master_service = master_service or get_master_data_service()
        self.audit_service = audit_service or AuditService()
        self.validator = BulkImportValidator(self.catalogue)

        # In-memory store for non-masterdata entity sets: (tenant_id, entity_type, natural_key) -> record_dict
        self._entity_stores: dict[tuple[str, str, str], dict[str, Any]] = {}
        # Track modification timestamps for rollback dependency conflict detection
        self._record_modified_at: dict[tuple[str, str, str], dt.datetime] = {}
        # Track downstream dependents for rollback blocking
        self._record_dependents: dict[tuple[str, str, str], set[str]] = {}

    # ==========================================================================
    # 1. Mandatory Dry Run Validation
    # ==========================================================================

    def execute_dry_run(
        self,
        *,
        content_bytes: bytes,
        filename: str,
        entity_type: str,
        mode: ImportMode,
        atomicity_policy: AtomicityPolicy | None = None,
        mapping_profile_id: str | None = None,
        tenant_context: TenantContext,
        actor_id: str = "SYSTEM",
    ) -> DryRunSummary:
        """Executes mandatory, complete dry run before any mutation occurs.

        Enforces: "Make the dry run genuinely complete: it reports what would be created,
        what would be updated, what would be skipped and why, what would be rejected and why,
        per-row and in summary, with a downloadable result file — before anything is written."
        """
        tc = require_tenant_context(tenant_context)
        et = entity_type.strip().upper()
        logger.debug(f"Dry run initiated by actor '{actor_id}' for entity '{et}'.")

        metadata = self.catalogue.get_metadata(et)
        if not metadata:
            raise BulkImportException(f"Entity type '{et}' is not registered as importable.")

        if mode not in metadata.allowed_modes:
            raise BulkImportException(
                f"Mode '{mode.value}' is not permitted for entity type '{et}'. "
                f"Allowed modes: {[m.value for m in metadata.allowed_modes]}"
            )

        applied_atomicity = atomicity_policy or metadata.default_atomicity_policy
        file_hash = compute_content_hash(content_bytes)

        # Retrieve optional mapping profile
        profile: MappingProfile | None = None
        if mapping_profile_id:
            profile = self.repository.get_mapping_profile(mapping_profile_id, tenant_context=tc)
            if not profile:
                raise BulkImportException(f"Mapping profile '{mapping_profile_id}' not found.")

        # Parse content
        _, _, raw_rows = parse_file_content(content_bytes, filename)

        # Load existing state for diffing and match resolution
        existing_records = self._get_existing_records(et, tc)

        row_results: list[DryRunRowResult] = []
        created_count = 0
        updated_count = 0
        skipped_count = 0
        rejected_count = 0
        seen_keys_in_file: set[str] = set()

        for row_num, raw_dict in raw_rows:
            # 1. Validate row schema & master references
            val_res = self.validator.validate_row(
                row_number=row_num,
                raw_row=raw_dict,
                metadata=metadata,
                mapping_profile=profile,
                tenant_id=tc.tenant_id,
            )

            if not val_res.is_valid:
                # Row is rejected
                rejected_count += 1
                row_results.append(
                    DryRunRowResult(
                        row_number=row_num,
                        outcome=RowOutcome.REJECTED,
                        natural_key=val_res.natural_key,
                        entity_data=val_res.mapped_data,
                        changes_diff={},
                        errors=val_res.errors,
                        failed_master=val_res.failed_master,
                        reasons=[f"Validation failed: {'; '.join(val_res.errors)}"],
                    )
                )
                continue

            nat_key = val_res.natural_key
            seen_keys_in_file.add(nat_key)
            existing = existing_records.get(nat_key)

            # 2. Evaluate outcome based on explicitly chosen mode
            if existing is not None:
                # Record exists in system
                if mode == ImportMode.INSERT_ONLY:
                    skipped_count += 1
                    row_results.append(
                        DryRunRowResult(
                            row_number=row_num,
                            outcome=RowOutcome.SKIPPED,
                            natural_key=nat_key,
                            entity_data=val_res.mapped_data,
                            changes_diff={},
                            errors=[],
                            reasons=[
                                "Record already exists in system; skipped in INSERT_ONLY mode."
                            ],
                        )
                    )
                elif mode in {
                    ImportMode.UPDATE_ONLY,
                    ImportMode.UPSERT,
                    ImportMode.DEACTIVATE_MISSING,
                }:
                    # Calculate diff
                    diff = self._calculate_diff(existing, val_res.mapped_data)
                    if not diff:
                        skipped_count += 1
                        row_results.append(
                            DryRunRowResult(
                                row_number=row_num,
                                outcome=RowOutcome.SKIPPED,
                                natural_key=nat_key,
                                entity_data=val_res.mapped_data,
                                changes_diff={},
                                errors=[],
                                reasons=[
                                    "Record attributes are identical to existing state; no update required."
                                ],
                            )
                        )
                    else:
                        updated_count += 1
                        row_results.append(
                            DryRunRowResult(
                                row_number=row_num,
                                outcome=RowOutcome.UPDATED,
                                natural_key=nat_key,
                                entity_data=val_res.mapped_data,
                                changes_diff=diff,
                                errors=[],
                                reasons=[f"Updated {len(diff)} fields: {', '.join(diff.keys())}."],
                            )
                        )
            else:
                # Record does NOT exist in system
                if mode == ImportMode.UPDATE_ONLY:
                    skipped_count += 1
                    row_results.append(
                        DryRunRowResult(
                            row_number=row_num,
                            outcome=RowOutcome.SKIPPED,
                            natural_key=nat_key,
                            entity_data=val_res.mapped_data,
                            changes_diff={},
                            errors=[],
                            reasons=["Record not found in system; skipped in UPDATE_ONLY mode."],
                        )
                    )
                elif mode in {
                    ImportMode.INSERT_ONLY,
                    ImportMode.UPSERT,
                    ImportMode.DEACTIVATE_MISSING,
                }:
                    created_count += 1
                    row_results.append(
                        DryRunRowResult(
                            row_number=row_num,
                            outcome=RowOutcome.CREATED,
                            natural_key=nat_key,
                            entity_data=val_res.mapped_data,
                            changes_diff={},
                            errors=[],
                            reasons=["New record to be created in platform."],
                        )
                    )

        # 3. Deactivate-Missing Mode evaluation for full refresh
        deactivated_count = 0
        if mode == ImportMode.DEACTIVATE_MISSING:
            for ex_key, ex_record in existing_records.items():
                if ex_key not in seen_keys_in_file and ex_record.get("is_active", True):
                    deactivated_count += 1
                    row_results.append(
                        DryRunRowResult(
                            row_number=len(row_results) + 1,
                            outcome=RowOutcome.DEACTIVATED,
                            natural_key=ex_key,
                            entity_data=ex_record,
                            changes_diff={"is_active": {"prior": True, "new": False}},
                            errors=[],
                            reasons=[
                                "Record omitted from full-refresh import file; will be deactivated."
                            ],
                        )
                    )

        # Determine validity according to atomicity policy
        if applied_atomicity == AtomicityPolicy.ALL_OR_NOTHING:
            is_valid = rejected_count == 0
        else:  # PARTIAL_SUCCESS
            # Valid if at least one actionable row or file was clean
            is_valid = rejected_count == 0 or (
                created_count + updated_count + deactivated_count > 0
            )

        dry_run_id = f"dry-{uuid.uuid4().hex[:12]}"
        summary = DryRunSummary(
            dry_run_id=dry_run_id,
            tenant_id=tc.tenant_id,
            entity_type=et,
            mode=mode,
            atomicity_policy=applied_atomicity,
            source_filename=filename,
            source_file_hash=file_hash,
            total_rows=len(raw_rows),
            created_count=created_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            rejected_count=rejected_count,
            deactivated_count=deactivated_count,
            is_valid=is_valid,
            executed_at=dt.datetime.now(dt.UTC),
            row_results=row_results,
        )

        self.repository.save_dry_run(summary, tenant_context=tc)
        return summary

    # ==========================================================================
    # 2. Applying Import (Requires Prior Dry Run)
    # ==========================================================================

    def apply_import(
        self,
        *,
        dry_run_id: str,
        tenant_context: TenantContext,
        actor_id: str,
    ) -> ImportRunRecord:
        """Applies validated import records to domain storage with full provenance.

        Enforces:
        - "Do not apply an import without a dry run."
        - Atomicity policy compliance.
        - Row-level provenance attached to every record.
        - Audit trail recording.
        """
        tc = require_tenant_context(tenant_context)
        dry_run = self.repository.get_dry_run(dry_run_id, tenant_context=tc)
        if not dry_run:
            raise DryRunRequiredException(
                f"No dry-run validation found for token '{dry_run_id}'. "
                "Do not apply an import without a dry run."
            )

        if not dry_run.is_valid:
            raise ImportValidationException(
                f"Cannot apply import: dry run failed with {dry_run.rejected_count} rejected rows "
                f"under {dry_run.atomicity_policy.value} atomicity policy.",
                rejected_count=dry_run.rejected_count,
            )

        start_time = dt.datetime.now(dt.UTC)
        import_run_id = f"imp-{uuid.uuid4().hex[:12]}"
        metadata = self.catalogue.get_metadata(dry_run.entity_type)
        window_hours = metadata.rollback_window_hours if metadata else 24

        # Take snapshot of prior state for rollback capability
        snapshot_before: list[dict[str, Any]] = []
        applied_created = 0
        applied_updated = 0
        applied_deactivated = 0

        # Apply mutations per row outcome
        for row in dry_run.row_results:
            if row.outcome == RowOutcome.REJECTED:
                # Under PARTIAL_SUCCESS, rejected rows are skipped during apply
                continue

            # Provenance stamp (Prompt 53)
            provenance = ImportProvenance(
                imported=True,
                source_filename=dry_run.source_filename,
                source_file_hash=dry_run.source_file_hash,
                import_run_id=import_run_id,
                imported_by=actor_id,
                imported_at=start_time,
                source_row_number=row.row_number,
            )

            store_key = (tc.tenant_id, dry_run.entity_type, row.natural_key)
            existing = self._get_record(dry_run.entity_type, row.natural_key, tc)

            if row.outcome == RowOutcome.CREATED:
                record_to_save = dict(row.entity_data)
                record_to_save["_provenance"] = provenance.model_dump(mode="json")
                record_to_save["is_active"] = True
                self._persist_record(dry_run.entity_type, row.natural_key, record_to_save, tc)
                self._record_modified_at[store_key] = start_time
                snapshot_before.append({"action": "CREATED", "natural_key": row.natural_key})
                applied_created += 1

            elif row.outcome == RowOutcome.UPDATED:
                if existing:
                    snapshot_before.append(
                        {
                            "action": "UPDATED",
                            "natural_key": row.natural_key,
                            "prior_data": dict(existing),
                        }
                    )
                record_to_save = dict(existing or {})
                record_to_save.update(row.entity_data)
                record_to_save["_provenance"] = provenance.model_dump(mode="json")
                self._persist_record(dry_run.entity_type, row.natural_key, record_to_save, tc)
                self._record_modified_at[store_key] = start_time
                applied_updated += 1

            elif row.outcome == RowOutcome.DEACTIVATED:
                if existing:
                    snapshot_before.append(
                        {
                            "action": "DEACTIVATED",
                            "natural_key": row.natural_key,
                            "prior_data": dict(existing),
                        }
                    )
                    record_to_save = dict(existing)
                    record_to_save["is_active"] = False
                    self._persist_record(dry_run.entity_type, row.natural_key, record_to_save, tc)
                    self._record_modified_at[store_key] = start_time
                    applied_deactivated += 1

        end_time = dt.datetime.now(dt.UTC)
        duration = (end_time - start_time).total_seconds()

        run_record = ImportRunRecord(
            id=import_run_id,
            tenant_id=tc.tenant_id,
            entity_type=dry_run.entity_type,
            mode=dry_run.mode,
            atomicity_policy=dry_run.atomicity_policy,
            source_filename=dry_run.source_filename,
            source_file_hash=dry_run.source_file_hash,
            actor_id=actor_id,
            status=ImportStatus.APPLIED,
            total_rows=dry_run.total_rows,
            created_count=applied_created,
            updated_count=applied_updated,
            skipped_count=dry_run.skipped_count,
            rejected_count=dry_run.rejected_count,
            deactivated_count=applied_deactivated,
            started_at=start_time,
            completed_at=end_time,
            duration_seconds=duration,
            dry_run_id=dry_run_id,
            rollback_window_hours=window_hours,
            can_rollback=True,
            row_results=dry_run.row_results,
            snapshot_before=snapshot_before,
        )

        self.repository.save_import_run(run_record, tenant_context=tc)

        # Record immutable audit event
        self.audit_service.record_event(
            tenant_context=tc,
            event_type=AuditEventType.CONFIG_CHANGED,
            actor=actor_id,
            action="BULK_IMPORT_APPLIED",
            resource_type=f"IMPORT_{dry_run.entity_type}",
            resource_id=import_run_id,
            payload={
                "import_run_id": import_run_id,
                "entity_type": dry_run.entity_type,
                "mode": dry_run.mode.value,
                "source_filename": dry_run.source_filename,
                "source_file_hash": dry_run.source_file_hash,
                "created_count": applied_created,
                "updated_count": applied_updated,
                "rejected_count": dry_run.rejected_count,
                "deactivated_count": applied_deactivated,
            },
        )

        logger.info(
            f"Bulk import '{import_run_id}' applied successfully for tenant '{tc.tenant_id}' "
            f"[{dry_run.entity_type}]: {applied_created} created, {applied_updated} updated, "
            f"{dry_run.rejected_count} rejected in {duration:.2f}s."
        )
        return run_record

    # ==========================================================================
    # 3. Rollback Path with Dependency Guard
    # ==========================================================================

    def rollback_import(
        self,
        *,
        import_run_id: str,
        tenant_context: TenantContext,
        actor_id: str,
        reason: str = "Rollback requested by user",
    ) -> ImportRunRecord:
        """Reverses an applied import run within the configured window.

        Enforces:
        - Time-boxed window enforcement.
        - Dependent change blocking: "Reversal is blocked where dependent changes
          have since occurred, with a clear explanation."
        - Audit trail recording.
        """
        tc = require_tenant_context(tenant_context)
        run = self.repository.get_import_run(import_run_id, tenant_context=tc)
        if not run:
            raise ImportRunNotFoundException(import_run_id)

        if run.status == ImportStatus.REVERSED:
            raise BulkImportException(f"Import run '{import_run_id}' has already been reversed.")

        now = dt.datetime.now(dt.UTC)
        elapsed_hours = (now - run.started_at).total_seconds() / 3600.0
        if elapsed_hours > run.rollback_window_hours:
            raise RollbackWindowExpiredException(
                import_run_id, elapsed_hours, run.rollback_window_hours
            )

        # Dependency conflict check
        for item in run.snapshot_before:
            nat_key = item["natural_key"]
            store_key = (tc.tenant_id, run.entity_type, nat_key)

            # Check if record was modified subsequent to import execution
            last_mod = self._record_modified_at.get(store_key)
            if last_mod and last_mod > (run.completed_at or run.started_at):
                raise RollbackBlockedException(
                    import_run_id,
                    f"Record '{nat_key}' was modified at {last_mod.isoformat()} "
                    "after import completion. Subsequent changes block rollback.",
                )

            # Check if record has registered dependent entities
            deps = self._record_dependents.get(store_key, set())
            if deps:
                raise RollbackBlockedException(
                    import_run_id,
                    f"Record '{nat_key}' is actively referenced by dependent records ({list(deps)[:3]}). "
                    "Downstream dependencies block rollback.",
                )

        # Execute reversal
        for item in reversed(run.snapshot_before):
            action = item["action"]
            nat_key = item["natural_key"]
            store_key = (tc.tenant_id, run.entity_type, nat_key)

            if action == "CREATED":
                # Remove created record
                self._delete_record(run.entity_type, nat_key, tc)
                self._record_modified_at.pop(store_key, None)

            elif action in {"UPDATED", "DEACTIVATED"}:
                # Restore prior snapshot
                prior = item.get("prior_data", {})
                self._persist_record(run.entity_type, nat_key, prior, tc)
                self._record_modified_at[store_key] = now

        run.status = ImportStatus.REVERSED
        run.can_rollback = False
        run.reversal_record = {
            "reversed_by": actor_id,
            "reversed_at": now.isoformat(),
            "reason": reason,
        }

        self.repository.save_import_run(run, tenant_context=tc)

        # Record audit event
        self.audit_service.record_event(
            tenant_context=tc,
            event_type=AuditEventType.CONFIG_CHANGED,
            actor=actor_id,
            action="BULK_IMPORT_REVERSED",
            resource_type=f"IMPORT_{run.entity_type}",
            resource_id=import_run_id,
            payload={
                "import_run_id": import_run_id,
                "entity_type": run.entity_type,
                "reason": reason,
                "reversed_records_count": len(run.snapshot_before),
            },
        )

        logger.info(
            f"Import run '{import_run_id}' reversed successfully by '{actor_id}' "
            f"({len(run.snapshot_before)} records restored)."
        )
        return run

    # ==========================================================================
    # 4. Template Generation & Export Symmetry (Round Trip)
    # ==========================================================================

    def generate_template(self, entity_type: str, export_format: str = "csv") -> str:
        """Generates template file with column headers, descriptions, and sample values."""
        et = entity_type.strip().upper()
        meta = self.catalogue.get_metadata(et)
        if not meta:
            raise BulkImportException(f"Entity type '{et}' is not registered.")

        fmt = export_format.strip().lower()
        if fmt == "csv":
            output = io.StringIO()
            # Commented header block explaining valid master references and requirements
            output.write(f"# Template for {meta.display_name} ({meta.entity_type})\n")
            output.write(f"# Purpose: {meta.description}\n")
            output.write(f"# Default Atomicity: {meta.default_atomicity_policy.value}\n")
            for col in meta.columns:
                ref_info = f" [Master: {col.master_reference}]" if col.master_reference else ""
                req_info = " [Required]" if col.required else " [Optional]"
                output.write(f"# - {col.name}: {col.description}{req_info}{ref_info}\n")

            writer = csv.writer(output)
            headers = [col.name for col in meta.columns]
            writer.writerow(headers)
            sample_row = [
                json.dumps(col.sample_value)
                if isinstance(col.sample_value, (dict, list))
                else (col.sample_value if col.sample_value is not None else "")
                for col in meta.columns
            ]
            writer.writerow(sample_row)
            return output.getvalue()

        elif fmt == "json":
            sample_dict = {col.name: col.sample_value for col in meta.columns}
            return json.dumps([sample_dict], indent=2)

        raise BulkImportException(f"Unsupported template format '{export_format}'.")

    def export_entity(
        self,
        entity_type: str,
        tenant_context: TenantContext,
        export_format: str = "csv",
    ) -> str:
        """Exports entity data in identical format to import (export symmetry / round-trip)."""
        tc = require_tenant_context(tenant_context)
        et = entity_type.strip().upper()
        meta = self.catalogue.get_metadata(et)
        if not meta:
            raise BulkImportException(f"Entity type '{et}' is not registered.")

        records = self._get_existing_records(et, tc)
        headers = [col.name for col in meta.columns]
        rows = list(records.values())

        fmt = export_format.strip().lower()
        if fmt == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(headers)
            for r in rows:
                row_vals = []
                for h in headers:
                    val = r.get(h)
                    if isinstance(val, (dict, list)):
                        row_vals.append(json.dumps(val))
                    else:
                        row_vals.append(str(val) if val is not None else "")
                writer.writerow(row_vals)
            return output.getvalue()

        elif fmt == "json":
            clean_records = []
            for r in rows:
                clean_r = {h: r.get(h) for h in headers}
                clean_records.append(clean_r)
            return json.dumps(clean_records, indent=2)

        raise BulkImportException(f"Unsupported export format '{export_format}'.")

    def generate_dry_run_download_result(
        self, dry_run: DryRunSummary, export_format: str = "csv"
    ) -> str:
        """Generates downloadable validation result report file (Prompt 53)."""
        fmt = export_format.strip().lower()
        if fmt == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(
                [
                    "row_number",
                    "outcome",
                    "natural_key",
                    "errors",
                    "failed_master",
                    "reasons",
                    "changes_diff",
                ]
            )
            for r in dry_run.row_results:
                writer.writerow(
                    [
                        r.row_number,
                        r.outcome.value,
                        r.natural_key,
                        " | ".join(r.errors),
                        r.failed_master or "",
                        " | ".join(r.reasons),
                        json.dumps(r.changes_diff) if r.changes_diff else "",
                    ]
                )
            return output.getvalue()
        elif fmt == "json":
            return json.dumps(dry_run.model_dump(mode="json"), indent=2)

        raise BulkImportException(f"Unsupported download format '{export_format}'.")

    # ==========================================================================
    # Helper Storage Methods
    # ==========================================================================

    def _get_existing_records(
        self, entity_type: str, tenant_context: TenantContext
    ) -> dict[str, dict[str, Any]]:
        """Retrieves active records for matching and diffing."""
        tc = require_tenant_context(tenant_context)
        et = entity_type.strip().upper()
        results: dict[str, dict[str, Any]] = {}

        # 1. Check local entity store
        for (tid, t_et, nat_key), data in self._entity_stores.items():
            if tid == tc.tenant_id and t_et == et:
                results[nat_key] = data

        # 2. If registered in MasterDataService, merge records
        try:
            m_records = self.master_service.list_records(
                et, tenant_id=tc.tenant_id, include_inactive=True
            )
            for mr in m_records:
                if mr.code not in results:
                    entry = {
                        "code": mr.code,
                        "display_name": mr.display_name,
                        "description": mr.description,
                        "sort_order": mr.sort_order,
                        "is_active": mr.is_active,
                    }
                    entry.update(mr.attributes)
                    results[mr.code] = entry
        except Exception:
            pass

        return results

    def _get_record(
        self, entity_type: str, natural_key: str, tenant_context: TenantContext
    ) -> dict[str, Any] | None:
        tc = require_tenant_context(tenant_context)
        return self._entity_stores.get((tc.tenant_id, entity_type.upper(), natural_key))

    def _persist_record(
        self,
        entity_type: str,
        natural_key: str,
        data: dict[str, Any],
        tenant_context: TenantContext,
    ) -> None:
        tc = require_tenant_context(tenant_context)
        et = entity_type.upper()
        self._entity_stores[(tc.tenant_id, et, natural_key)] = dict(data)

        # Also reflect into MasterDataService if it's a registered master
        try:
            existing = self.master_service.get_record(et, natural_key, tenant_id=tc.tenant_id)
            if existing:
                self.master_service.update_record(
                    master_type=et,
                    code=natural_key,
                    display_name=data.get("display_name", natural_key),
                    description=data.get("description"),
                    attributes={k: v for k, v in data.items() if not k.startswith("_")},
                    tenant_id=tc.tenant_id,
                    changed_by="bulk_import",
                )
            else:
                self.master_service.create_record(
                    master_type=et,
                    code=natural_key,
                    display_name=data.get("display_name", natural_key),
                    description=data.get("description"),
                    attributes={k: v for k, v in data.items() if not k.startswith("_")},
                    tenant_id=tc.tenant_id,
                    created_by="bulk_import",
                )
        except Exception:
            pass

    def _delete_record(
        self, entity_type: str, natural_key: str, tenant_context: TenantContext
    ) -> None:
        tc = require_tenant_context(tenant_context)
        key = (tc.tenant_id, entity_type.upper(), natural_key)
        self._entity_stores.pop(key, None)

    def _calculate_diff(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        """Calculates changed fields between existing and incoming records."""
        diff: dict[str, Any] = {}
        for k, new_v in incoming.items():
            if k.startswith("_"):
                continue
            old_v = existing.get(k)
            # Normalize comparisons
            if str(old_v or "") != str(new_v or ""):
                diff[k] = {"prior": old_v, "new": new_v}
        return diff

    def register_dependent_relation(
        self,
        tenant_id: str,
        entity_type: str,
        natural_key: str,
        dependent_id: str,
    ) -> None:
        """Registers a downstream dependent reference for dependency guard verification."""
        key = (tenant_id, entity_type.upper(), natural_key)
        if key not in self._record_dependents:
            self._record_dependents[key] = set()
        self._record_dependents[key].add(dependent_id)

    def mark_record_subsequently_modified(
        self,
        tenant_id: str,
        entity_type: str,
        natural_key: str,
        modified_at: dt.datetime | None = None,
    ) -> None:
        """Simulates subsequent modification of a record to test dependency guard."""
        key = (tenant_id, entity_type.upper(), natural_key)
        self._record_modified_at[key] = modified_at or dt.datetime.now(dt.UTC)


# Global singleton instance
_engine_instance = BulkImportEngine()


def get_bulk_import_engine() -> BulkImportEngine:
    """Returns the singleton BulkImportEngine."""
    return _engine_instance
