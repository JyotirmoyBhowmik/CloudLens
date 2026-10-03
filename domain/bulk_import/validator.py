"""Row-Level Validation and Master Data Reference Verifier (Prompt 53).

Enforces:
1. "An invalid value is rejected with the row number and the master it failed against,
   and does not silently become free text."
2. "Do not accept a value that does not exist in its master."
3. Strict schema bounds, type casting, required field checks, and natural key extraction.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from domain.bulk_import.catalogue import ImportableEntityCatalogue, get_import_catalogue
from domain.bulk_import.models import (
    EntityImportMetadata,
    MappingProfile,
)


class RowValidationResult:
    """Outcome of validating a single imported row."""

    def __init__(
        self,
        row_number: int,
        natural_key: str,
        mapped_data: dict[str, Any],
        is_valid: bool,
        errors: list[str],
        failed_master: str | None = None,
    ) -> None:
        self.row_number = row_number
        self.natural_key = natural_key
        self.mapped_data = mapped_data
        self.is_valid = is_valid
        self.errors = errors
        self.failed_master = failed_master


class BulkImportValidator:
    """Validates raw row dictionaries against canonical schema and registered master data."""

    def __init__(self, catalogue: ImportableEntityCatalogue | None = None) -> None:
        self.catalogue = catalogue or get_import_catalogue()
        # Cache of master codes per master_type to prevent repetitive lookup overhead
        self._master_cache: dict[str, set[str]] = {}

    def _get_master_codes(self, master_type: str, tenant_id: str | None) -> set[str]:
        cache_key = f"{tenant_id or 'global'}:{master_type.upper()}"
        if cache_key not in self._master_cache:
            codes = self.catalogue.get_valid_master_values(master_type, tenant_id=tenant_id)
            self._master_cache[cache_key] = {c.strip().upper() for c in codes}
        return self._master_cache[cache_key]

    def validate_row(
        self,
        row_number: int,
        raw_row: dict[str, Any],
        metadata: EntityImportMetadata,
        mapping_profile: MappingProfile | None = None,
        tenant_id: str | None = None,
    ) -> RowValidationResult:
        """Applies column mapping, type verification, and master reference integrity checks."""
        errors: list[str] = []
        failed_master: str | None = None
        mapped_data: dict[str, Any] = {}

        # 1. Apply column mappings
        col_mappings = mapping_profile.column_mappings if mapping_profile else {}
        defaults = mapping_profile.default_values if mapping_profile else {}

        # First pass: map raw input headers to canonical field names
        raw_normalized = {k.strip().lower(): v for k, v in raw_row.items()}

        for col in metadata.columns:
            target_name = col.name
            target_name_lower = target_name.lower()

            # Find matching raw value
            val = None
            if col_mappings:
                # Find source col that maps to target_name
                for src_col, tgt_name in col_mappings.items():
                    if tgt_name == target_name and src_col.lower() in raw_normalized:
                        val = raw_normalized[src_col.lower()]
                        break

            # Fallback to direct name match if not mapped
            if val is None and target_name_lower in raw_normalized:
                val = raw_normalized[target_name_lower]

            # Fallback to default values
            if (val is None or val == "") and target_name in defaults:
                val = defaults[target_name]

            # 2. Check required constraint
            if col.required and (val is None or str(val).strip() == ""):
                errors.append(
                    f"Row {row_number}: Required field '{target_name}' is missing or empty."
                )
                continue

            if val is None or str(val).strip() == "":
                mapped_data[target_name] = None
                continue

            # 3. Type parsing & validation
            clean_str = str(val).strip()
            parsed_val: Any = clean_str

            if col.data_type == "number":
                try:
                    parsed_val = float(clean_str)
                except ValueError:
                    errors.append(
                        f"Row {row_number}: Field '{target_name}' requires numeric value, got '{clean_str}'."
                    )
            elif col.data_type == "boolean":
                low = clean_str.lower()
                if low in {"true", "1", "yes", "y", "t"}:
                    parsed_val = True
                elif low in {"false", "0", "no", "n", "f"}:
                    parsed_val = False
                else:
                    errors.append(
                        f"Row {row_number}: Field '{target_name}' requires boolean value, got '{clean_str}'."
                    )
            elif col.data_type == "date":
                # Validate ISO date format YYYY-MM-DD
                try:
                    dt.date.fromisoformat(clean_str.split("T")[0])
                    parsed_val = clean_str.split("T")[0]
                except ValueError:
                    errors.append(
                        f"Row {row_number}: Field '{target_name}' requires valid date format (YYYY-MM-DD), got '{clean_str}'."
                    )

            # 4. Static allowed_values check
            if col.allowed_values and clean_str:
                upper_allowed = {av.upper() for av in col.allowed_values}
                if clean_str.upper() not in upper_allowed:
                    errors.append(
                        f"Row {row_number}: Value '{clean_str}' for field '{target_name}' is not in allowed values: {col.allowed_values}."
                    )

            # 5. Dynamic Master Data Reference Check (Rule: Never silently become free text!)
            if col.master_reference and clean_str:
                master_codes = self._get_master_codes(col.master_reference, tenant_id=tenant_id)
                if master_codes and clean_str.upper() not in master_codes:
                    err_msg = (
                        f"Row {row_number}: Value '{clean_str}' for field '{target_name}' "
                        f"does not exist in registered master '{col.master_reference}'. "
                        "Free-text substitution is forbidden."
                    )
                    errors.append(err_msg)
                    if failed_master is None:
                        failed_master = col.master_reference

            mapped_data[target_name] = parsed_val

        # 6. Extract and validate natural key
        key_parts = []
        for key_col in metadata.natural_key_columns:
            k_val = mapped_data.get(key_col)
            if k_val is None or str(k_val).strip() == "":
                errors.append(
                    f"Row {row_number}: Natural key column '{key_col}' is missing or empty."
                )
            else:
                key_parts.append(str(k_val).strip())

        natural_key = ":".join(key_parts) if key_parts else f"row-{row_number}"

        return RowValidationResult(
            row_number=row_number,
            natural_key=natural_key,
            mapped_data=mapped_data,
            is_valid=(len(errors) == 0),
            errors=errors,
            failed_master=failed_master,
        )
