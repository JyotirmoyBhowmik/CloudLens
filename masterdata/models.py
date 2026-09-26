"""Master Data Management Object Models and DTOs.

Enforces Prompt 45 Items 1, 2, 7, 8, 10:
- Universal master-data object model conforming to strict schema.
- Registry manifest entry definition.
- Lineage, audit, and where-used models.
- Import/export dry-run validation DTOs.
- Master data health reporting model.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, computed_field

DEFAULT_MASTER_EPOCH = datetime(2000, 1, 1, 0, 0, 0)


class LifecycleStatus(StrEnum):
    """Change management workflow states for master data records."""

    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    DEPRECATED = "DEPRECATED"


class MasterRegistryEntry(BaseModel):
    """Manifest entry declaring a registered master type."""

    code: str
    name: str
    purpose: str
    schema_def: dict[str, Any] = Field(default_factory=dict)
    is_tenant_scoped: bool = False
    is_editable: bool = True
    requires_approval: bool = False
    consuming_modules: list[str] = Field(default_factory=list)
    seed_file: str
    expected_review_period_days: int = 180

    @property
    def master_type(self) -> str:
        """Alias for code to support both master_type and code accessors."""
        return self.code


class MasterDataRecord(BaseModel):
    """Universal master data record conforming to Prompt 45 Item 1."""

    id: str
    master_type: str
    code: str
    display_name: str
    description: str | None = None
    sort_order: int = 0
    is_system: bool = False
    is_active: bool = True
    effective_from: datetime = Field(default=DEFAULT_MASTER_EPOCH)
    effective_to: datetime | None = None
    version: int = 1
    parent_code: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str | None = None
    created_by: str = "SYSTEM"
    approved_by: str | None = None
    lifecycle_status: LifecycleStatus = LifecycleStatus.PUBLISHED


class MasterDataAuditEntry(BaseModel):
    """Full change history record for audit and point-in-time lineage."""

    id: str
    record_id: str
    master_type: str
    code: str
    version: int
    action: str
    changed_by: str
    change_reason: str
    diff_payload: dict[str, Any] = Field(default_factory=dict)
    snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MasterDataLineage(BaseModel):
    """Point-in-time version lineage and audit trail for a master value."""

    master_type: str
    code: str
    current_version: int
    versions: list[MasterDataRecord]
    audit_history: list[MasterDataAuditEntry]

    @property
    def total_versions(self) -> int:
        return len(self.versions)

    @property
    def history(self) -> list[MasterDataRecord]:
        return self.versions


class WhereUsedReport(BaseModel):
    """Reference analysis showing what live estate records consume this master."""

    master_type: str
    code: str
    is_in_use: bool
    total_reference_count: int
    references_by_entity: dict[str, int] = Field(default_factory=dict)
    blocking_reasons: list[str] = Field(default_factory=list)


class DryRunValidationResult(BaseModel):
    """Result of dry-run import validation before mutation."""

    master_type: str
    format: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    to_add_count: int
    to_update_count: int
    row_errors: list[dict[str, Any]] = Field(default_factory=list)
    preview_records: list[dict[str, Any]] = Field(default_factory=list)

    @computed_field
    def is_valid(self) -> bool:
        return self.invalid_rows == 0

    @computed_field
    def error_rows(self) -> int:
        return self.invalid_rows

    @property
    def errors(self) -> list[dict[str, Any]]:
        return self.row_errors


class MasterDataHealthReport(BaseModel):
    """System-wide master data health and hygiene inspection."""

    total_masters_registered: int
    total_records: int
    active_records: int
    inactive_records: int
    empty_masters: list[str] = Field(default_factory=list)
    unreferenced_values: list[dict[str, str]] = Field(default_factory=list)
    referenced_inactive_values: list[dict[str, Any]] = Field(default_factory=list)
    stale_masters: list[dict[str, Any]] = Field(default_factory=list)
    catalogue_gaps: list[dict[str, Any]] = Field(default_factory=list)
    overall_health_score: float = 100.0
