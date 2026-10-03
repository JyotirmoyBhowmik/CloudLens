"""Domain Bulk Import Module (Prompt 53).

Exposes:
- Core models: ImportMode, AtomicityPolicy, ImportStatus, RowOutcome, ImportProvenance, etc.
- ImportableEntityCatalogue & metadata.
- File parser, encoding and delimiter detection.
- Row-level validator with master reference verification.
- BulkImportEngine: Dry-run, apply, rollback, and export symmetry.
- ScheduledImportScheduler: Unattended recurring feeds.
"""

from domain.bulk_import.catalogue import (
    ImportableEntityCatalogue,
    get_import_catalogue,
)
from domain.bulk_import.engine import (
    BulkImportEngine,
    get_bulk_import_engine,
)
from domain.bulk_import.file_parser import (
    compute_content_hash,
    detect_delimiter,
    detect_encoding,
    parse_file_content,
)
from domain.bulk_import.models import (
    AtomicityPolicy,
    ColumnDefinition,
    DryRunRowResult,
    DryRunSummary,
    EntityImportMetadata,
    ImportMode,
    ImportProvenance,
    ImportRunRecord,
    ImportStatus,
    MappingProfile,
    RowOutcome,
    ScheduledImportJob,
)
from domain.bulk_import.repository import (
    BulkImportRepository,
    get_bulk_import_repository,
)
from domain.bulk_import.scheduler import (
    ScheduledImportScheduler,
    get_scheduled_import_scheduler,
)
from domain.bulk_import.validator import (
    BulkImportValidator,
    RowValidationResult,
)

__all__ = [
    "AtomicityPolicy",
    "BulkImportEngine",
    "BulkImportRepository",
    "BulkImportValidator",
    "ColumnDefinition",
    "DryRunRowResult",
    "DryRunSummary",
    "EntityImportMetadata",
    "ImportMode",
    "ImportProvenance",
    "ImportRunRecord",
    "ImportStatus",
    "ImportableEntityCatalogue",
    "MappingProfile",
    "RowOutcome",
    "RowValidationResult",
    "ScheduledImportJob",
    "ScheduledImportScheduler",
    "compute_content_hash",
    "detect_delimiter",
    "detect_encoding",
    "get_bulk_import_engine",
    "get_bulk_import_repository",
    "get_import_catalogue",
    "get_scheduled_import_scheduler",
    "parse_file_content",
]
