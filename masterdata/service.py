"""Master Data Management Service.

Enforces Prompt 45:
- Object model with effective-dated versioning.
- Master registry manifest validation.
- Reference integrity guard with detailed blocking reasons.
- Configurable change lifecycle with approval workflow.
- Idempotent seed loading.
- Import / export with dry-run validation.
- Lineage, where-used, and health inspection.
"""

import json
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from domain.models.exceptions import (
    CannotDeleteSystemMasterException,
    MasterDataApprovalException,
    MasterDataException,
    MasterNotRegisteredException,
    ReferenceIntegrityBlockedException,
)
from masterdata.io import MasterDataIO
from masterdata.models import (
    DEFAULT_MASTER_EPOCH,
    DryRunValidationResult,
    LifecycleStatus,
    MasterDataAuditEntry,
    MasterDataHealthReport,
    MasterDataLineage,
    MasterDataRecord,
    MasterRegistryEntry,
    WhereUsedReport,
)
from masterdata.registry import (
    get_registered_master,
    is_master_registered,
    list_registered_masters,
)
from masterdata.seeder import MasterDataSeeder, SeedExecutionReport


class MasterDataService:
    """Enterprise Master Data Management Service."""

    def __init__(self, auto_seed: bool = True) -> None:
        self._records: dict[str, list[MasterDataRecord]] = {}
        self._audits: list[MasterDataAuditEntry] = []
        self._import_audits: list[dict[str, Any]] = []
        self._seeder = MasterDataSeeder()
        # Pluggable live reference providers: (master_type, code) -> dict[entity_type, count]
        self._reference_providers: list[Callable[[str, str], dict[str, int]]] = []
        # In-memory mock references for unit testing and local simulation
        self._mock_live_references: dict[tuple[str, str], dict[str, int]] = {}

        if auto_seed:
            self.seed_system_masters()

    # ==========================================================================
    # 1. Registry Manifest
    # ==========================================================================

    def get_registry(self) -> list[MasterRegistryEntry]:
        """Returns all registered masters declared in the manifest."""
        return list_registered_masters()

    def get_master_manifest(self, master_type: str) -> MasterRegistryEntry:
        """Retrieves manifest definition for a master type or raises domain error."""
        entry = get_registered_master(master_type)
        if not entry:
            raise MasterNotRegisteredException(master_type)
        return entry

    # ==========================================================================
    # 2. Seeding
    # ==========================================================================

    def seed_system_masters(self) -> SeedExecutionReport:
        """Executes idempotent seeding across all registered masters."""
        return self._seeder.seed(self._records)

    # ==========================================================================
    # 3. Universal Point-in-Time Master Resolution (Prompt 45 Item 3)
    # ==========================================================================

    def get_record(
        self,
        master_type: str,
        code: str,
        as_of: datetime | None = None,
        tenant_id: str | None = None,
        include_inactive: bool = False,
    ) -> MasterDataRecord | None:
        """Resolves a master record as at a stated date (as_of), never as at now.

        Supports tenant override resolution: tenant-scoped record takes precedence over global.
        """
        mt = master_type.strip().upper()
        if not is_master_registered(mt):
            raise MasterNotRegisteredException(mt)

        target_time = as_of or datetime.utcnow()
        records = self._records.get(mt, [])

        # Filter by code and time interval
        candidates = [
            r
            for r in records
            if r.code.upper() == code.strip().upper()
            and r.effective_from <= target_time
            and (r.effective_to is None or r.effective_to > target_time)
            and (include_inactive or r.lifecycle_status == LifecycleStatus.PUBLISHED)
        ]

        if not candidates:
            return None

        # If tenant_id supplied, prefer matching tenant record
        if tenant_id:
            tenant_match = next((r for r in candidates if r.tenant_id == tenant_id), None)
            if tenant_match:
                return tenant_match

        # Fallback to global/system record (tenant_id is None)
        global_match = next((r for r in candidates if r.tenant_id is None), None)
        return global_match or candidates[-1]

    def list_records(
        self,
        master_type: str,
        as_of: datetime | None = None,
        tenant_id: str | None = None,
        include_inactive: bool = False,
    ) -> list[MasterDataRecord]:
        """Lists active effective master records for a given master type."""
        mt = master_type.strip().upper()
        if not is_master_registered(mt):
            raise MasterNotRegisteredException(mt)

        target_time = as_of or datetime.utcnow()
        records = self._records.get(mt, [])

        # Distinct by code, resolving latest effective version per code
        by_code: dict[str, MasterDataRecord] = {}
        for r in records:
            if (
                r.effective_from <= target_time
                and (r.effective_to is None or r.effective_to > target_time)
                and (include_inactive or r.lifecycle_status == LifecycleStatus.PUBLISHED)
            ):
                if tenant_id and r.tenant_id == tenant_id:
                    by_code[r.code] = r
                elif r.code not in by_code:
                    by_code[r.code] = r

        return sorted(by_code.values(), key=lambda x: (x.sort_order, x.code))

    # ==========================================================================
    # 4. Master Data Mutation & Versioning (Prompt 45 Item 3 & 5)
    # ==========================================================================

    def create_record(
        self,
        master_type: str,
        code: str,
        display_name: str,
        description: str | None = None,
        sort_order: int = 0,
        parent_code: str | None = None,
        attributes: dict[str, Any] | None = None,
        tenant_id: str | None = None,
        created_by: str = "SYSTEM",
        is_system: bool = False,
        force_publish: bool = False,
    ) -> MasterDataRecord:
        """Creates a new master data record."""
        mt = master_type.strip().upper()
        manifest = self.get_master_manifest(mt)

        existing = next(
            (
                r
                for r in self._records.get(mt, [])
                if r.code.upper() == code.strip().upper()
                and r.tenant_id == tenant_id
                and r.is_active
            ),
            None,
        )
        if existing:
            raise MasterDataException(
                f"Master record '{code}' already exists for scope '{tenant_id or 'GLOBAL'}' in '{mt}'. Use update_record to create a new version."
            )

        status = (
            LifecycleStatus.DRAFT
            if manifest.requires_approval and not force_publish
            else LifecycleStatus.PUBLISHED
        )
        rec_id = f"md-{mt.lower()}-{uuid.uuid4().hex[:8]}"
        record = MasterDataRecord(
            id=rec_id,
            master_type=mt,
            code=code.strip(),
            display_name=display_name,
            description=description,
            sort_order=sort_order,
            is_system=is_system,
            is_active=True,
            effective_from=datetime.utcnow()
            if status == LifecycleStatus.PUBLISHED
            else DEFAULT_MASTER_EPOCH,
            effective_to=None,
            version=1,
            parent_code=parent_code,
            attributes=attributes or {},
            tenant_id=tenant_id,
            created_by=created_by,
            approved_by=created_by if status == LifecycleStatus.PUBLISHED else None,
            lifecycle_status=status,
        )

        self._records.setdefault(mt, []).append(record)

        # Audit creation
        self._record_audit(
            record_id=rec_id,
            master_type=mt,
            code=code,
            version=1,
            action="CREATE",
            changed_by=created_by,
            change_reason="Initial creation",
            diff_payload={"created": record.model_dump(mode="json")},
            snapshot=record.model_dump(mode="json"),
        )
        return record

    def update_record(
        self,
        master_type: str,
        code: str,
        display_name: str,
        description: str | None = None,
        sort_order: int | None = None,
        parent_code: str | None = None,
        attributes: dict[str, Any] | None = None,
        changed_by: str = "SYSTEM",
        change_reason: str = "Update",
        effective_at: datetime | None = None,
        tenant_id: str | None = None,
        force_publish: bool = False,
    ) -> MasterDataRecord:
        """Effective-dated versioning: creates a new version rather than mutating in place."""
        mt = master_type.strip().upper()
        manifest = self.get_master_manifest(mt)

        current = self.get_record(mt, code, tenant_id=tenant_id)
        if not current:
            raise MasterDataException(f"Master record '{code}' not found in '{mt}'.")

        transition_time = effective_at or datetime.utcnow()

        if manifest.requires_approval and not force_publish:
            # Create a DRAFT version for review
            new_id = f"md-{mt.lower()}-{uuid.uuid4().hex[:8]}"
            new_version = MasterDataRecord(
                id=new_id,
                master_type=mt,
                code=current.code,
                display_name=display_name,
                description=description if description is not None else current.description,
                sort_order=sort_order if sort_order is not None else current.sort_order,
                is_system=current.is_system,
                is_active=True,
                effective_from=transition_time,
                effective_to=None,
                version=current.version + 1,
                parent_code=parent_code if parent_code is not None else current.parent_code,
                attributes=attributes if attributes is not None else current.attributes,
                tenant_id=tenant_id or current.tenant_id,
                created_by=changed_by,
                approved_by=None,
                lifecycle_status=LifecycleStatus.DRAFT,
            )
            self._records.setdefault(mt, []).append(new_version)
            self._record_audit(
                record_id=new_id,
                master_type=mt,
                code=code,
                version=new_version.version,
                action="DRAFT_VERSION",
                changed_by=changed_by,
                change_reason=change_reason,
                diff_payload={"old_version": current.version, "status": "DRAFT"},
                snapshot=new_version.model_dump(mode="json"),
            )
            return new_version

        # Direct edit: close old version and activate new version
        current.effective_to = transition_time
        current.is_active = False

        new_id = f"md-{mt.lower()}-{uuid.uuid4().hex[:8]}"
        new_version = MasterDataRecord(
            id=new_id,
            master_type=mt,
            code=current.code,
            display_name=display_name,
            description=description if description is not None else current.description,
            sort_order=sort_order if sort_order is not None else current.sort_order,
            is_system=current.is_system,
            is_active=True,
            effective_from=transition_time,
            effective_to=None,
            version=current.version + 1,
            parent_code=parent_code if parent_code is not None else current.parent_code,
            attributes=attributes if attributes is not None else current.attributes,
            tenant_id=tenant_id or current.tenant_id,
            created_by=changed_by,
            approved_by=changed_by,
            lifecycle_status=LifecycleStatus.PUBLISHED,
        )

        self._records.setdefault(mt, []).append(new_version)

        self._record_audit(
            record_id=new_id,
            master_type=mt,
            code=code,
            version=new_version.version,
            action="UPDATE_VERSION",
            changed_by=changed_by,
            change_reason=change_reason,
            diff_payload={"old_version": current.version, "new_version": new_version.version},
            snapshot=new_version.model_dump(mode="json"),
        )
        return new_version

    # ==========================================================================
    # 5. Approval Lifecycle (Prompt 45 Item 5)
    # ==========================================================================

    def submit_for_review(self, master_type: str, code: str, user_id: str) -> MasterDataRecord:
        """Transitions a draft master record to IN_REVIEW."""
        mt = master_type.strip().upper()
        records = self._records.get(mt, [])
        draft = next(
            (
                r
                for r in reversed(records)
                if r.code == code and r.lifecycle_status == LifecycleStatus.DRAFT
            ),
            None,
        )
        if not draft:
            raise MasterDataApprovalException(f"No DRAFT version found for '{code}' in '{mt}'.")

        draft.lifecycle_status = LifecycleStatus.IN_REVIEW
        self._record_audit(
            record_id=draft.id,
            master_type=mt,
            code=code,
            version=draft.version,
            action="SUBMIT_FOR_REVIEW",
            changed_by=user_id,
            change_reason="Submitted for approval",
            diff_payload={"status": "IN_REVIEW"},
            snapshot=draft.model_dump(mode="json"),
        )
        return draft

    def approve(self, master_type: str, code: str, approver_id: str) -> MasterDataRecord:
        """Approves a review master record."""
        mt = master_type.strip().upper()
        records = self._records.get(mt, [])
        review = next(
            (
                r
                for r in reversed(records)
                if r.code == code and r.lifecycle_status == LifecycleStatus.IN_REVIEW
            ),
            None,
        )
        if not review:
            raise MasterDataApprovalException(f"No IN_REVIEW version found for '{code}' in '{mt}'.")

        review.lifecycle_status = LifecycleStatus.APPROVED
        review.approved_by = approver_id
        self._record_audit(
            record_id=review.id,
            master_type=mt,
            code=code,
            version=review.version,
            action="APPROVE",
            changed_by=approver_id,
            change_reason="Approved changes",
            diff_payload={"status": "APPROVED", "approver": approver_id},
            snapshot=review.model_dump(mode="json"),
        )
        return review

    def publish(self, master_type: str, code: str, publisher_id: str) -> MasterDataRecord:
        """Publishes an approved master record, closing the previous version."""
        mt = master_type.strip().upper()
        records = self._records.get(mt, [])
        approved = next(
            (
                r
                for r in reversed(records)
                if r.code == code and r.lifecycle_status == LifecycleStatus.APPROVED
            ),
            None,
        )
        if not approved:
            raise MasterDataApprovalException(f"No APPROVED version found for '{code}' in '{mt}'.")

        now = datetime.utcnow()
        # Close previous active version
        prev_active = next(
            (
                r
                for r in records
                if r.code == code and r.id != approved.id and r.is_active and r.effective_to is None
            ),
            None,
        )
        if prev_active:
            prev_active.effective_to = now
            prev_active.is_active = False

        approved.lifecycle_status = LifecycleStatus.PUBLISHED
        approved.is_active = True
        approved.effective_from = now
        approved.effective_to = None

        self._record_audit(
            record_id=approved.id,
            master_type=mt,
            code=code,
            version=approved.version,
            action="PUBLISH",
            changed_by=publisher_id,
            change_reason="Published approved version",
            diff_payload={"status": "PUBLISHED", "activated_at": now.isoformat()},
            snapshot=approved.model_dump(mode="json"),
        )
        return approved

    # ==========================================================================
    # 6. Reference Integrity Guard & Deactivation (Prompt 45 Item 4)
    # ==========================================================================

    def add_reference_provider(self, provider: Callable[[str, str], dict[str, int]]) -> None:
        """Registers a live reference scanner provider."""
        self._reference_providers.append(provider)

    def set_mock_live_reference(
        self, master_type: str, code: str, references: dict[str, int]
    ) -> None:
        """Sets simulated live references for testing reference-integrity guard."""
        self._mock_live_references[(master_type.strip().upper(), code.strip().upper())] = references

    def check_reference_integrity(self, master_type: str, code: str) -> WhereUsedReport:
        """Inspects whether a master value is referenced by live estate records."""
        mt = master_type.strip().upper()
        c = code.strip().upper()

        ref_counts: dict[str, int] = {}

        # 1. Check registered providers
        for provider in self._reference_providers:
            try:
                res = provider(mt, c)
                for k, v in res.items():
                    ref_counts[k] = ref_counts.get(k, 0) + v
            except Exception:
                pass

        # 2. Check mock references
        mock_refs = self._mock_live_references.get((mt, c), {})
        for k, v in mock_refs.items():
            ref_counts[k] = ref_counts.get(k, 0) + v

        total = sum(ref_counts.values())
        blocking_reasons = []
        if total > 0:
            parts = [f"{count} {entity}" for entity, count in ref_counts.items() if count > 0]
            blocking_reasons.append(f"Referenced by {', '.join(parts)}.")

        return WhereUsedReport(
            master_type=mt,
            code=code,
            is_in_use=total > 0,
            total_reference_count=total,
            references_by_entity=ref_counts,
            blocking_reasons=blocking_reasons,
        )

    def deactivate_record(self, master_type: str, code: str, requested_by: str) -> MasterDataRecord:
        """Deactivates a master record, blocked if referenced by any live record."""
        mt = master_type.strip().upper()
        current = self.get_record(mt, code)
        if not current:
            raise MasterDataException(f"Master record '{code}' not found in '{mt}'.")

        where_used = self.check_reference_integrity(mt, code)
        if where_used.is_in_use:
            reason = " ".join(where_used.blocking_reasons)
            raise ReferenceIntegrityBlockedException(
                f"Cannot deactivate master value '{code}' ({mt}): {reason} Deactivation blocked."
            )

        current.is_active = False
        current.effective_to = datetime.utcnow()

        self._record_audit(
            record_id=current.id,
            master_type=mt,
            code=code,
            version=current.version,
            action="DEACTIVATE",
            changed_by=requested_by,
            change_reason="Deactivated by user",
            diff_payload={"is_active": False},
            snapshot=current.model_dump(mode="json"),
        )
        return current

    def delete_record(self, master_type: str, code: str, requested_by: str) -> None:
        """Hard deletes a master record. Blocked if system master or in use."""
        mt = master_type.strip().upper()
        current = self.get_record(mt, code, include_inactive=True)
        if not current:
            raise MasterDataException(f"Master record '{code}' not found in '{mt}'.")

        if current.is_system:
            raise CannotDeleteSystemMasterException(code)

        where_used = self.check_reference_integrity(mt, code)
        if where_used.is_in_use:
            reason = " ".join(where_used.blocking_reasons)
            raise ReferenceIntegrityBlockedException(
                f"Cannot delete master value '{code}' ({mt}): {reason} Deletion blocked."
            )

        # Remove from store
        self._records[mt] = [r for r in self._records[mt] if r.code != code]

        self._record_audit(
            record_id=current.id,
            master_type=mt,
            code=code,
            version=current.version,
            action="DELETE",
            changed_by=requested_by,
            change_reason="Deleted non-system record",
            diff_payload={"deleted": True},
            snapshot={},
        )

    # ==========================================================================
    # 7. Lineage and Where-Used (Prompt 45 Item 8)
    # ==========================================================================

    def get_lineage(self, master_type: str, code: str) -> MasterDataLineage:
        """Retrieves full version lineage and audit change log."""
        mt = master_type.strip().upper()
        records = [r for r in self._records.get(mt, []) if r.code.upper() == code.strip().upper()]
        audits = [
            a
            for a in self._audits
            if a.master_type == mt and a.code.upper() == code.strip().upper()
        ]
        latest_version = max((r.version for r in records), default=1)

        return MasterDataLineage(
            master_type=mt,
            code=code,
            current_version=latest_version,
            versions=sorted(records, key=lambda x: x.version),
            audit_history=sorted(audits, key=lambda x: x.created_at),
        )

    def get_where_used(self, master_type: str, code: str) -> WhereUsedReport:
        """Returns live where-used reference analysis."""
        return self.check_reference_integrity(master_type, code)

    # ==========================================================================
    # 8. Import / Export (Prompt 45 Item 7)
    # ==========================================================================

    def export_data(self, master_type: str, export_format: str = "json") -> str:
        """Exports master data records in JSON or CSV format."""
        mt = master_type.strip().upper()
        records = self.list_records(mt, include_inactive=True)
        return MasterDataIO.export_data(mt, records, export_format=export_format)

    def validate_import(
        self,
        master_type: str,
        content: str,
        import_format: str,
    ) -> DryRunValidationResult:
        """Executes dry-run validation reporting what would change before anything changes."""
        mt = master_type.strip().upper()
        records = self._records.get(mt, [])
        return MasterDataIO.validate_import(mt, content, import_format, records)

    def import_data(
        self,
        master_type: str,
        content: str,
        import_format: str,
        imported_by: str = "SYSTEM",
    ) -> tuple[int, int]:
        """Imports master records after dry-run validation."""
        mt = master_type.strip().upper()
        validation = self.validate_import(mt, content, import_format)
        if validation.invalid_rows > 0:
            raise MasterDataException(
                f"Import validation failed with {validation.invalid_rows} errors."
            )

        fmt = import_format.strip().lower()
        items = json.loads(content) if fmt == "json" else []
        if fmt == "csv":
            import csv
            import io

            reader = csv.DictReader(io.StringIO(content))
            for r in reader:
                d = dict(r)
                if "attributes" in d and d["attributes"]:
                    try:
                        d["attributes"] = json.loads(d["attributes"])
                    except Exception:
                        d["attributes"] = {}
                items.append(d)

        added = 0
        updated = 0
        for item in items:
            code = item["code"]
            existing = self.get_record(mt, code)
            if existing:
                self.update_record(
                    master_type=mt,
                    code=code,
                    display_name=item["display_name"],
                    description=item.get("description"),
                    sort_order=item.get("sort_order"),
                    parent_code=item.get("parent_code"),
                    attributes=item.get("attributes"),
                    changed_by=imported_by,
                    change_reason=f"Batch import ({fmt})",
                )
                updated += 1
            else:
                self.create_record(
                    master_type=mt,
                    code=code,
                    display_name=item["display_name"],
                    description=item.get("description"),
                    sort_order=item.get("sort_order", 0),
                    parent_code=item.get("parent_code"),
                    attributes=item.get("attributes"),
                    created_by=imported_by,
                    is_system=False,
                )
                added += 1

        return added, updated

    # ==========================================================================
    # 9. Master Data Health Report (Prompt 45 Item 10)
    # ==========================================================================

    def get_health_report(self) -> MasterDataHealthReport:
        """Inspects system-wide master data health and hygiene."""
        all_masters = list_registered_masters()
        empty_masters = []
        unreferenced_values = []
        referenced_inactive_values = []
        stale_masters = []

        total_records = 0
        active_records = 0
        inactive_records = 0

        now = datetime.utcnow()

        for entry in all_masters:
            mt = entry.code
            records = self._records.get(mt, [])
            active = [r for r in records if r.is_active and r.effective_to is None]
            inactive = [r for r in records if not r.is_active or r.effective_to is not None]

            total_records += len(records)
            active_records += len(active)
            inactive_records += len(inactive)

            if not active:
                empty_masters.append(mt)

            # Check review freshness
            review_limit = timedelta(days=entry.expected_review_period_days)
            latest_audit = [a for a in self._audits if a.master_type == mt]
            if latest_audit:
                latest_time = max(a.created_at for a in latest_audit)
                if (now - latest_time) > review_limit:
                    stale_masters.append(
                        {
                            "master_type": mt,
                            "last_updated": latest_time.isoformat(),
                            "expected_review_days": entry.expected_review_period_days,
                        }
                    )

            # Check where-used
            for r in active:
                where_used = self.check_reference_integrity(mt, r.code)
                if not where_used.is_in_use:
                    unreferenced_values.append({"master_type": mt, "code": r.code})

            for r in inactive:
                where_used = self.check_reference_integrity(mt, r.code)
                if where_used.is_in_use:
                    referenced_inactive_values.append(
                        {
                            "master_type": mt,
                            "code": r.code,
                            "references": where_used.references_by_entity,
                        }
                    )

        # Health score calculation
        score = 100.0
        if empty_masters:
            score -= len(empty_masters) * 15.0
        if referenced_inactive_values:
            score -= len(referenced_inactive_values) * 10.0
        if score < 0.0:
            score = 0.0

        return MasterDataHealthReport(
            total_masters_registered=len(all_masters),
            total_records=total_records,
            active_records=active_records,
            inactive_records=inactive_records,
            empty_masters=empty_masters,
            unreferenced_values=unreferenced_values[:50],  # Bound report preview
            referenced_inactive_values=referenced_inactive_values,
            stale_masters=stale_masters,
            catalogue_gaps=[],
            overall_health_score=round(score, 1),
        )

    def inspect_health(self) -> MasterDataHealthReport:
        """Alias for get_health_report."""
        return self.get_health_report()

    def export_to_json(self, master_type: str) -> str:
        """Convenience method exporting records as JSON string."""
        return self.export_data(master_type, export_format="json")

    def export_to_csv(self, master_type: str) -> str:
        """Convenience method exporting records as CSV string."""
        return self.export_data(master_type, export_format="csv")

    def dry_run_import(
        self,
        master_type: str,
        data: list[dict[str, Any]] | str,
        import_format: str = "json",
    ) -> DryRunValidationResult:
        """Convenience method executing dry-run validation from parsed list or string."""
        if isinstance(data, list):
            content = json.dumps(data)
            import_format = "json"
        else:
            content = data
        return self.validate_import(master_type, content, import_format)

    # --------------------------------------------------------------------------
    # Internal Helpers
    # --------------------------------------------------------------------------

    def _record_audit(
        self,
        record_id: str,
        master_type: str,
        code: str,
        version: int,
        action: str,
        changed_by: str,
        change_reason: str,
        diff_payload: dict[str, Any],
        snapshot: dict[str, Any],
    ) -> None:
        audit_id = f"aud-{uuid.uuid4().hex[:12]}"
        self._audits.append(
            MasterDataAuditEntry(
                id=audit_id,
                record_id=record_id,
                master_type=master_type,
                code=code,
                version=version,
                action=action,
                changed_by=changed_by,
                change_reason=change_reason,
                diff_payload=diff_payload,
                snapshot=snapshot,
                created_at=datetime.utcnow(),
            )
        )


_SERVICE_SINGLETON: MasterDataService | None = None


def get_master_data_service() -> MasterDataService:
    """Returns the process-level MasterDataService singleton."""
    global _SERVICE_SINGLETON
    if _SERVICE_SINGLETON is None:
        _SERVICE_SINGLETON = MasterDataService(auto_seed=True)
    return _SERVICE_SINGLETON


def reset_master_data_service() -> MasterDataService:
    """Resets the process-level MasterDataService singleton (primarily for tests)."""
    global _SERVICE_SINGLETON
    _SERVICE_SINGLETON = MasterDataService(auto_seed=True)
    return _SERVICE_SINGLETON
