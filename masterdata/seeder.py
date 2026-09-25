"""Idempotent Master Data Seed Loader.

Enforces Prompt 45 Item 6:
- Every master is seeded from a versioned, human-readable seed file in the repository.
- Seeding is idempotent: re-running produces no duplicates and zero changes if unchanged.
- Every seeded row is marked is_system=True so a user cannot delete what the product depends on.
"""

import json
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from masterdata.models import DEFAULT_MASTER_EPOCH, LifecycleStatus, MasterDataRecord
from masterdata.registry import SYSTEM_MASTER_REGISTRY


class SeedExecutionReport(BaseModel):
    """Execution summary of master data seeding."""

    total_masters_scanned: int = 0
    total_records_processed: int = 0
    created_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    errors: list[str] = Field(default_factory=list)

    @property
    def records_created(self) -> int:
        return self.created_count

    @property
    def records_updated(self) -> int:
        return self.updated_count

    @property
    def total_mutations(self) -> int:
        return self.created_count + self.updated_count


class MasterDataSeeder:
    """Idempotent seed engine populating master data from human-readable repository files."""

    def __init__(self, seeds_dir: Path | None = None) -> None:
        self._seeds_dir = seeds_dir or (Path(__file__).resolve().parent / "seeds")

    def seed(self, store: dict[str, list[MasterDataRecord]]) -> SeedExecutionReport:
        """Seeds all registered master data into the provided storage backend.

        Args:
            store: Dictionary mapping master_type -> list of MasterDataRecord entries.
        """
        report = SeedExecutionReport()

        for master_code, entry in SYSTEM_MASTER_REGISTRY.items():
            report.total_masters_scanned += 1
            seed_file = Path(entry.seed_file)
            if not seed_file.is_absolute():
                # Resolve relative to repo root or seeds dir
                repo_root = Path(__file__).resolve().parent.parent
                resolved_seed_path = repo_root / seed_file
                if not resolved_seed_path.exists():
                    resolved_seed_path = self._seeds_dir / seed_file.name
            else:
                resolved_seed_path = seed_file

            if not resolved_seed_path.exists():
                report.errors.append(
                    f"Seed file not found for master '{master_code}': {resolved_seed_path}"
                )
                continue

            try:
                raw_data = json.loads(resolved_seed_path.read_text(encoding="utf-8"))
            except Exception as e:
                report.errors.append(f"Failed parsing seed file for '{master_code}': {e}")
                continue

            existing_list = store.setdefault(master_code, [])

            for item in raw_data:
                report.total_records_processed += 1
                code = item["code"]

                # Find if active system record already exists
                existing = next(
                    (
                        r
                        for r in existing_list
                        if r.code == code and r.tenant_id is None and r.is_active
                    ),
                    None,
                )

                if existing is None:
                    # New record insertion
                    rec_id = f"md-{master_code.lower()}-{uuid.uuid4().hex[:8]}"
                    new_record = MasterDataRecord(
                        id=rec_id,
                        master_type=master_code,
                        code=code,
                        display_name=item["display_name"],
                        description=item.get("description"),
                        sort_order=item.get("sort_order", 0),
                        is_system=True,  # Mandatory Prompt 45 Item 6
                        is_active=True,
                        effective_from=DEFAULT_MASTER_EPOCH,
                        effective_to=None,
                        version=1,
                        parent_code=item.get("parent_code"),
                        attributes=item.get("attributes", {}),
                        tenant_id=None,
                        created_by="SYSTEM_SEEDER",
                        approved_by="SYSTEM_SEEDER",
                        lifecycle_status=LifecycleStatus.PUBLISHED,
                    )
                    existing_list.append(new_record)
                    report.created_count += 1
                else:
                    # Compare for drift (idempotence verification)
                    is_same_display = existing.display_name == item["display_name"]
                    is_same_desc = existing.description == item.get("description")
                    is_same_order = existing.sort_order == item.get("sort_order", 0)
                    is_same_attrs = existing.attributes == item.get("attributes", {})
                    is_same_parent = existing.parent_code == item.get("parent_code")

                    if (
                        is_same_display
                        and is_same_desc
                        and is_same_order
                        and is_same_attrs
                        and is_same_parent
                    ):
                        report.unchanged_count += 1
                    else:
                        # Systematic update without duplication
                        existing.display_name = item["display_name"]
                        existing.description = item.get("description")
                        existing.sort_order = item.get("sort_order", 0)
                        existing.attributes = item.get("attributes", {})
                        existing.parent_code = item.get("parent_code")
                        report.updated_count += 1

        return report
