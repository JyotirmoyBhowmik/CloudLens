"""Open Columnar Archival and Partition Restoration Engine.

Enforces Prompt 06 Item 43 & Acceptance:
"detached partitions exported to object storage in an open columnar format and restorable."
"Acceptance: An archived partition can be restored to a queryable state."
"""

import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import Connection, text


class ColumnarArchivalEngine:
    """Manages exporting detached PostgreSQL partitions to Apache Parquet and restoring them on demand."""

    @classmethod
    def export_partition_to_parquet(
        cls,
        conn: Connection,
        partition_name: str,
        export_path: Path,
    ) -> dict[str, Any]:
        """Queries all rows from the partition and serializes them into open columnar Parquet format."""
        # 1. Fetch column names and records
        result = conn.execute(text(f"SELECT * FROM {partition_name};"))
        columns = list(result.keys())
        rows = result.fetchall()

        if not rows:
            # Create empty table schema
            arrays = [pa.array([], type=pa.string()) for _ in columns]
            table = pa.Table.from_arrays(arrays, names=columns)
        else:
            # Format row data for PyArrow columns
            col_data: dict[str, list[Any]] = {col: [] for col in columns}
            for row in rows:
                for idx, val in enumerate(row):
                    col_name = columns[idx]
                    # Convert dicts/JSONB to JSON strings for standard Parquet storage
                    if isinstance(val, dict):
                        col_data[col_name].append(json.dumps(val))
                    else:
                        col_data[col_name].append(str(val) if val is not None else None)

            arrays = [pa.array(col_data[col]) for col in columns]
            table = pa.Table.from_arrays(arrays, names=columns)

        # 2. Write Parquet file with Snappy compression
        export_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, str(export_path), compression="snappy")

        return {
            "partition_name": partition_name,
            "parquet_file": str(export_path),
            "rows_archived": len(rows),
            "file_size_bytes": export_path.stat().st_size,
        }

    @classmethod
    def detach_and_archive_partition(
        cls,
        conn: Connection,
        parent_table: str,
        partition_name: str,
        archive_root_dir: Path,
    ) -> dict[str, Any]:
        """Exports partition to Parquet, detaches partition from parent table, and drops physical table."""
        export_file = archive_root_dir / parent_table / f"{partition_name}.parquet"

        # 1. Export to open columnar Parquet
        meta = cls.export_partition_to_parquet(conn, partition_name, export_file)

        # 2. Detach partition
        conn.execute(text(f"ALTER TABLE {parent_table} DETACH PARTITION {partition_name};"))

        # 3. Drop physical table to release local disk space
        conn.execute(text(f"DROP TABLE IF EXISTS {partition_name} CASCADE;"))

        meta["status"] = "DETACHED_AND_ARCHIVED"
        return meta

    @classmethod
    def restore_partition_from_parquet(
        cls,
        conn: Connection,
        parent_table: str,
        parquet_file: Path,
        from_val: str,
        to_val: str,
    ) -> dict[str, Any]:
        """Acceptance: Restores an archived Parquet partition into PostgreSQL and re-attaches it to the queryable hierarchy."""
        if not parquet_file.exists():
            raise FileNotFoundError(f"Parquet archive file not found: {parquet_file}")

        partition_name = parquet_file.stem
        # 1. Read open columnar Parquet file
        table = pq.read_table(str(parquet_file))
        pydict = table.to_pydict()
        columns = table.column_names
        row_count = table.num_rows

        # 2. Create physical table matching parent table schema
        conn.execute(text(f"DROP TABLE IF EXISTS {partition_name} CASCADE;"))
        conn.execute(text(f"CREATE TABLE {partition_name} (LIKE {parent_table} INCLUDING ALL);"))

        # 3. Bulk insert rows if any
        if row_count > 0:
            col_list_str = ", ".join(columns)
            param_list_str = ", ".join([f":{col}" for col in columns])
            insert_sql = text(
                f"INSERT INTO {partition_name} ({col_list_str}) VALUES ({param_list_str});"
            )

            # Batch insert
            records_to_insert = []
            for i in range(row_count):
                row_dict = {}
                for col in columns:
                    val = pydict[col][i]
                    # Parse JSON strings back if applicable
                    if (
                        col
                        in (
                            "provider_native",
                            "source_provenance",
                            "tags",
                            "payload_before",
                            "payload_after",
                        )
                        and val
                    ):
                        try:
                            val = json.loads(val)
                        except Exception:
                            pass
                    row_dict[col] = val
                records_to_insert.append(row_dict)

            conn.execute(insert_sql, records_to_insert)

        # 4. Attach restored partition back to parent partitioned table
        conn.execute(
            text(
                f"""
                ALTER TABLE {parent_table} ATTACH PARTITION {partition_name}
                FOR VALUES FROM ('{from_val}') TO ('{to_val}');
                """
            )
        )

        return {
            "status": "RESTORED",
            "parent_table": parent_table,
            "partition_name": partition_name,
            "rows_restored": row_count,
        }
