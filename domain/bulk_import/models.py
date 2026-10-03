"""Object Models and DTOs for Generic Bulk Import and Data Onboarding (Prompt 53).

Defines:
- ImportMode: INSERT_ONLY, UPDATE_ONLY, UPSERT, DEACTIVATE_MISSING.
- AtomicityPolicy: ALL_OR_NOTHING, PARTIAL_SUCCESS.
- ImportProvenance: Full row-level provenance attached to every imported record.
- ColumnDefinition & EntityImportMetadata: Template and validation specifications.
- MappingProfile: Saved column mappings for repeat imports.
- DryRunRowResult & DryRunSummary: Mandatory complete dry-run validation results.
- ImportRunRecord: Historical run execution, status, and rollback snapshots.
- ScheduledImportJob: Scheduled unattended import configurations.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ImportMode(StrEnum):
    """Execution mode for record mutation during bulk import (Prompt 53)."""

    INSERT_ONLY = "INSERT_ONLY"
    UPDATE_ONLY = "UPDATE_ONLY"
    UPSERT = "UPSERT"
    DEACTIVATE_MISSING = "DEACTIVATE_MISSING"


class AtomicityPolicy(StrEnum):
    """Transaction atomicity policy configured per entity type as master data (Prompt 53)."""

    ALL_OR_NOTHING = "ALL_OR_NOTHING"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"


class ImportStatus(StrEnum):
    """Lifecycle states of an import run."""

    DRY_RUN_COMPLETED = "DRY_RUN_COMPLETED"
    APPLIED = "APPLIED"
    REVERSED = "REVERSED"
    FAILED = "FAILED"


class RowOutcome(StrEnum):
    """Individual row-level evaluation outcome."""

    CREATED = "CREATED"
    UPDATED = "UPDATED"
    SKIPPED = "SKIPPED"
    REJECTED = "REJECTED"
    DEACTIVATED = "DEACTIVATED"


class ImportProvenance(BaseModel):
    """Row-level provenance stamped on every imported record (Prompt 53)."""

    imported: bool = Field(default=True, description="True if record originated from bulk import")
    source_filename: str = Field(..., description="Name of source file")
    source_file_hash: str = Field(..., description="SHA-256 cryptographic hash of uploaded file")
    import_run_id: str = Field(..., description="Unique import execution identifier")
    imported_by: str = Field(..., description="Identity of importing actor or automated job")
    imported_at: dt.datetime = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC), description="Import timestamp in UTC"
    )
    source_row_number: int = Field(..., description="1-based row number within source file")


class ColumnDefinition(BaseModel):
    """Definition of an individual column for template download and schema validation."""

    name: str = Field(..., description="Field name in canonical entity")
    data_type: str = Field(
        default="string", description="Expected type: string, number, boolean, date, json"
    )
    required: bool = Field(default=False, description="Whether field is strictly mandatory")
    description: str = Field(
        default="", description="Field purpose and help text for business users"
    )
    master_reference: str | None = Field(
        default=None,
        description="Registered master type code validating allowed values (e.g. BUSINESS_UNIT)",
    )
    allowed_values: list[str] = Field(
        default_factory=list, description="Explicit static allowed values if not referencing master"
    )
    sample_value: Any = Field(
        default=None, description="Example value used for template generation"
    )


class EntityImportMetadata(BaseModel):
    """Master-data driven specification for an importable entity type (Prompt 53)."""

    entity_type: str = Field(
        ..., description="Unique entity type identifier (e.g. APPLICATION, RESOURCE_CURATION)"
    )
    display_name: str = Field(..., description="Human-readable title")
    description: str = Field(..., description="Functional description of entity dataset")
    columns: list[ColumnDefinition] = Field(
        default_factory=list, description="Complete column definitions"
    )
    natural_key_columns: list[str] = Field(
        ..., description="List of columns uniquely identifying a record for matching and diffing"
    )
    default_atomicity_policy: AtomicityPolicy = Field(
        default=AtomicityPolicy.PARTIAL_SUCCESS,
        description="Master-data configured default atomicity policy",
    )
    allowed_modes: list[ImportMode] = Field(
        default_factory=lambda: [
            ImportMode.INSERT_ONLY,
            ImportMode.UPDATE_ONLY,
            ImportMode.UPSERT,
            ImportMode.DEACTIVATE_MISSING,
        ],
        description="Supported import modes for this entity type",
    )
    rollback_window_hours: int = Field(
        default=24, description="Configured time window in hours within which reversal is permitted"
    )


class MappingProfile(BaseModel):
    """Saved column mapping configuration for repeated imports (Prompt 53)."""

    id: str = Field(..., description="Unique mapping profile ID")
    tenant_id: str = Field(..., description="Owning tenant identifier")
    name: str = Field(
        ..., description="User-friendly name of mapping profile (e.g. ServiceNow CMDB Feed)"
    )
    entity_type: str = Field(..., description="Target importable entity type")
    column_mappings: dict[str, str] = Field(
        default_factory=dict, description="Source column name -> Target canonical field name"
    )
    default_values: dict[str, Any] = Field(
        default_factory=dict, description="Default fallback values for unmapped required fields"
    )
    created_by: str = Field(default="SYSTEM", description="Actor who created profile")
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    updated_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))


class DryRunRowResult(BaseModel):
    """Detailed evaluation result for a single row during dry-run validation."""

    row_number: int = Field(..., description="1-based row number in source file")
    outcome: RowOutcome = Field(
        ..., description="Simulated outcome: CREATED, UPDATED, SKIPPED, REJECTED, DEACTIVATED"
    )
    natural_key: str = Field(..., description="Natural key value identifying target record")
    entity_data: dict[str, Any] = Field(
        default_factory=dict, description="Mapped incoming record values"
    )
    changes_diff: dict[str, Any] = Field(
        default_factory=dict,
        description="Prior values vs new values for UPDATED or DEACTIVATED rows",
    )
    errors: list[str] = Field(
        default_factory=list, description="Validation error messages explaining rejection"
    )
    failed_master: str | None = Field(
        default=None, description="Registered master code that caused validation failure"
    )
    reasons: list[str] = Field(
        default_factory=list, description="Informational reasons explaining skip, create, or update"
    )


class DryRunSummary(BaseModel):
    """Genuinely complete dry-run validation result (Prompt 53)."""

    dry_run_id: str = Field(..., description="Unique dry-run token required to commit import")
    tenant_id: str = Field(..., description="Tenant identifier")
    entity_type: str = Field(..., description="Target entity type")
    mode: ImportMode = Field(..., description="Selected import mode")
    atomicity_policy: AtomicityPolicy = Field(..., description="Applied atomicity policy")
    source_filename: str = Field(..., description="Original filename")
    source_file_hash: str = Field(..., description="SHA-256 hash of file content")
    total_rows: int = Field(..., description="Total rows in source file")
    created_count: int = Field(..., description="Rows that would be created")
    updated_count: int = Field(..., description="Rows that would be updated")
    skipped_count: int = Field(..., description="Rows that would be skipped")
    rejected_count: int = Field(..., description="Rows that would be rejected")
    deactivated_count: int = Field(..., description="Existing records that would be deactivated")
    is_valid: bool = Field(..., description="True if import can proceed under its atomicity policy")
    executed_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    row_results: list[DryRunRowResult] = Field(
        default_factory=list, description="Per-row evaluation results"
    )


class ImportRunRecord(BaseModel):
    """Audit and lineage record of an executed import run with rollback capability (Prompt 53)."""

    id: str = Field(..., description="Unique import run ID (e.g. imp-8fa12c)")
    tenant_id: str = Field(..., description="Tenant identifier")
    entity_type: str = Field(..., description="Target entity type")
    mode: ImportMode = Field(..., description="Explicitly chosen import mode")
    atomicity_policy: AtomicityPolicy = Field(..., description="Applied atomicity policy")
    source_filename: str = Field(..., description="Original source file name")
    source_file_hash: str = Field(..., description="SHA-256 cryptographic hash of source file")
    actor_id: str = Field(..., description="Importing actor or scheduled job identity")
    status: ImportStatus = Field(..., description="Current status: APPLIED, REVERSED, FAILED")
    total_rows: int = Field(..., description="Total rows processed")
    created_count: int = Field(..., description="Successfully created records")
    updated_count: int = Field(..., description="Successfully updated records")
    skipped_count: int = Field(..., description="Skipped records")
    rejected_count: int = Field(..., description="Rejected records")
    deactivated_count: int = Field(..., description="Deactivated records")
    started_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    completed_at: dt.datetime | None = Field(default=None)
    duration_seconds: float = Field(default=0.0)
    dry_run_id: str = Field(..., description="Associated dry-run token")
    rollback_window_hours: int = Field(default=24)
    can_rollback: bool = Field(
        default=True, description="True if reversal is currently permissible within window"
    )
    reversal_record: dict[str, Any] | None = Field(
        default=None, description="Audit record of rollback if reversed"
    )
    row_results: list[DryRunRowResult] = Field(
        default_factory=list, description="Full per-row execution outcomes"
    )
    snapshot_before: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Point-in-time snapshot of affected records prior to mutation",
    )


class ScheduledImportJob(BaseModel):
    """Scheduled unattended import configuration for CMDB, HR, or Finance feeds (Prompt 53)."""

    id: str = Field(..., description="Unique scheduled job identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    name: str = Field(..., description="Descriptive job title")
    entity_type: str = Field(..., description="Target importable entity type")
    cron_expression: str = Field(
        ..., description="Standard 5-part cron expression (e.g. '0 2 * * *')"
    )
    mapping_profile_id: str = Field(..., description="Saved mapping profile ID to apply")
    mode: ImportMode = Field(..., description="Explicitly chosen import mode")
    source_type: str = Field(default="CMDB_CONNECTOR", description="Feed provider type")
    source_uri: str = Field(..., description="Location URI or feed identifier")
    enabled: bool = Field(default=True, description="Whether schedule is active")
    last_run_at: dt.datetime | None = Field(default=None)
    last_status: str | None = Field(default=None)
    last_run_id: str | None = Field(default=None)
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
