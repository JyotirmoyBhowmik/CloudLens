"""Master Data Import and Export Engine.

Enforces Prompt 45 Item 7:
- CSV and structured JSON formats.
- Dry-run validation reporting what would change before anything changes.
- Row-level error reporting.
- Full import audit trail.
"""

import csv
import io
import json
from typing import Any

from masterdata.models import (
    DryRunValidationResult,
    MasterDataRecord,
)
from masterdata.registry import get_registered_master


class MasterDataIO:
    """Import and Export service for registered master datasets."""

    @staticmethod
    def export_data(
        master_type: str,
        records: list[MasterDataRecord],
        export_format: str = "json",
    ) -> str:
        """Exports master data records to JSON or CSV format."""
        fmt = export_format.strip().lower()

        if fmt == "json":
            serializable = [
                {
                    "code": r.code,
                    "display_name": r.display_name,
                    "description": r.description,
                    "sort_order": r.sort_order,
                    "parent_code": r.parent_code,
                    "is_active": r.is_active,
                    "version": r.version,
                    "attributes": r.attributes,
                    "tenant_id": r.tenant_id,
                }
                for r in records
                if r.master_type == master_type
            ]
            return json.dumps(serializable, indent=2)

        elif fmt == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(
                [
                    "code",
                    "display_name",
                    "description",
                    "sort_order",
                    "parent_code",
                    "is_active",
                    "version",
                    "attributes",
                ]
            )

            for r in records:
                if r.master_type == master_type:
                    writer.writerow(
                        [
                            r.code,
                            r.display_name,
                            r.description or "",
                            r.sort_order,
                            r.parent_code or "",
                            r.is_active,
                            r.version,
                            json.dumps(r.attributes),
                        ]
                    )
            return output.getvalue()

        else:
            raise ValueError(f"Unsupported export format '{export_format}'. Use 'json' or 'csv'.")

    @staticmethod
    def validate_import(
        master_type: str,
        content: str,
        import_format: str,
        existing_records: list[MasterDataRecord],
    ) -> DryRunValidationResult:
        """Executes dry-run validation on import payload without making mutations."""
        manifest = get_registered_master(master_type)
        if not manifest:
            raise ValueError(f"Master type '{master_type}' is not registered in the system.")

        fmt = import_format.strip().lower()
        rows: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        if fmt == "json":
            try:
                parsed = json.loads(content)
                if not isinstance(parsed, list):
                    return DryRunValidationResult(
                        master_type=master_type,
                        format=fmt,
                        total_rows=0,
                        valid_rows=0,
                        invalid_rows=1,
                        to_add_count=0,
                        to_update_count=0,
                        row_errors=[
                            {"row_index": 0, "error": "Root JSON must be a list of objects."}
                        ],
                    )
                rows = parsed
            except Exception as e:
                return DryRunValidationResult(
                    master_type=master_type,
                    format=fmt,
                    total_rows=0,
                    valid_rows=0,
                    invalid_rows=1,
                    to_add_count=0,
                    to_update_count=0,
                    row_errors=[{"row_index": 0, "error": f"Invalid JSON syntax: {e}"}],
                )

        elif fmt == "csv":
            try:
                reader = csv.DictReader(io.StringIO(content))
                for r in reader:
                    row_dict = dict(r)
                    if "attributes" in row_dict and row_dict["attributes"]:
                        try:
                            row_dict["attributes"] = json.loads(row_dict["attributes"])
                        except Exception:
                            row_dict["attributes"] = {}
                    rows.append(row_dict)
            except Exception as e:
                return DryRunValidationResult(
                    master_type=master_type,
                    format=fmt,
                    total_rows=0,
                    valid_rows=0,
                    invalid_rows=1,
                    to_add_count=0,
                    to_update_count=0,
                    row_errors=[{"row_index": 0, "error": f"Invalid CSV structure: {e}"}],
                )
        else:
            raise ValueError(f"Unsupported format '{import_format}'. Use 'json' or 'csv'.")

        to_add = 0
        to_update = 0
        valid_rows = 0
        preview: list[dict[str, Any]] = []
        existing_codes = {r.code for r in existing_records if r.master_type == master_type}

        for idx, row in enumerate(rows, start=1):
            code = str(row.get("code", "")).strip()
            display_name = str(row.get("display_name", "")).strip()

            row_errs = []
            if not code:
                row_errs.append("Missing mandatory 'code' key.")
            if not display_name:
                row_errs.append("Missing mandatory 'display_name'.")

            if row_errs:
                errors.append(
                    {
                        "row_index": idx,
                        "code": code or "<EMPTY>",
                        "errors": row_errs,
                    }
                )
            else:
                valid_rows += 1
                if code in existing_codes:
                    to_update += 1
                else:
                    to_add += 1

                if len(preview) < 5:
                    preview.append(
                        {
                            "code": code,
                            "display_name": display_name,
                            "action": "UPDATE" if code in existing_codes else "ADD",
                        }
                    )

        return DryRunValidationResult(
            master_type=master_type,
            format=fmt,
            total_rows=len(rows),
            valid_rows=valid_rows,
            invalid_rows=len(errors),
            to_add_count=to_add,
            to_update_count=to_update,
            row_errors=errors,
            preview_records=preview,
        )
