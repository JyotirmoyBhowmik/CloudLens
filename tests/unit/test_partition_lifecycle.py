"""Unit Tests for Partition Pre-creation, Downsampling, and Parquet Columnar Archival.

Acceptance Criteria:
- An archived partition can be exported to open columnar format and restored to a queryable state.
- Partition maintenance creates partitions ahead of need and never lets a write fail for a missing partition.
"""

import tempfile
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from db.lifecycle.archival import ColumnarArchivalEngine
from db.partitioning.manager import precreate_table_partitions


class MockCursorResult:
    def __init__(self, columns: list[str], rows: list[tuple]):
        self._columns = columns
        self._rows = rows

    def keys(self) -> list[str]:
        return self._columns

    def fetchall(self) -> list[tuple]:
        return self._rows


class RecordingConnection:
    """Simulates database connection recording executed SQL statements and returning mock datasets."""

    def __init__(self, query_responses: dict[str, Any] | None = None) -> None:
        self.executed_statements: list[str] = []
        self.query_responses: dict[str, Any] = query_responses or {}

    def execute(self, statement: Any, params: Any = None) -> Any:
        _ = params
        sql = str(statement)
        self.executed_statements.append(sql)
        for key, resp in self.query_responses.items():
            if key in sql:
                return resp
        return MockCursorResult([], [])


def test_partition_maintenance_precreates_ahead_and_ensures_default():
    """Verify partition manager creates monthly partitions ahead of need plus DEFAULT partition."""
    conn = RecordingConnection()
    partitions = precreate_table_partitions(
        conn=conn,  # type: ignore[arg-type]
        parent_table="cost_fact",
        start_year=2026,
        start_month=1,
        months_count=6,
    )

    # 1. Assert default partition is created so writes never fail
    assert "cost_fact_default" in partitions
    assert any("PARTITION OF cost_fact DEFAULT" in stmt for stmt in conn.executed_statements)

    # 2. Assert 6 monthly partitions created ahead
    assert len(partitions) == 7  # default + 6 months
    assert "cost_fact_2026_01" in partitions
    assert "cost_fact_2026_06" in partitions
    assert any(
        "FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')" in stmt
        for stmt in conn.executed_statements
    )


def test_open_columnar_parquet_archival_and_restoration():
    """Acceptance: An archived partition can be exported to Parquet and restored to a queryable state."""
    columns = [
        "billing_period_start",
        "tenant_id",
        "id",
        "scope_id",
        "service_id",
        "charge_period_start",
        "charge_period_end",
        "charge_category",
        "billed_cost",
        "effective_cost",
        "billing_currency",
        "provider_native",
        "source_provenance",
    ]
    sample_rows = [
        (
            "2026-01-01",
            "tenant-acme",
            "fact-001",
            "scope-sub-1",
            "AmazonEC2",
            "2026-01-15T12:00:00+00:00",
            "2026-01-15T13:00:00+00:00",
            "Usage",
            "1250.500000",
            "1180.250000",
            "USD",
            {"instanceType": "c5.xlarge"},
            {"source_system": "aws-cur"},
        ),
        (
            "2026-01-01",
            "tenant-acme",
            "fact-002",
            "scope-sub-2",
            "Virtual Network",
            "2026-01-15T12:00:00+00:00",
            "2026-01-15T13:00:00+00:00",
            "Usage",
            "45.200000",
            "45.200000",
            "USD",
            {"bandwidthGb": "100"},
            {"source_system": "azure-ea"},
        ),
    ]

    mock_result = MockCursorResult(columns, sample_rows)
    conn = RecordingConnection(query_responses={"SELECT * FROM cost_fact_2026_01": mock_result})

    with tempfile.TemporaryDirectory() as tmp_dir:
        archive_root = Path(tmp_dir) / "archive"

        # 1. Export partition to open columnar Parquet format
        export_meta = ColumnarArchivalEngine.detach_and_archive_partition(
            conn=conn,  # type: ignore[arg-type]
            parent_table="cost_fact",
            partition_name="cost_fact_2026_01",
            archive_root_dir=archive_root,
        )

        assert export_meta["rows_archived"] == 2
        parquet_path = Path(export_meta["parquet_file"])
        assert parquet_path.exists()
        assert parquet_path.suffix == ".parquet"

        # Verify Parquet file can be read by standard Arrow reader
        parquet_table = pq.read_table(str(parquet_path))
        assert parquet_table.num_rows == 2
        assert "billed_cost" in parquet_table.column_names

        # Verify partition was detached and dropped from PostgreSQL
        assert any("DETACH PARTITION cost_fact_2026_01" in s for s in conn.executed_statements)
        assert any("DROP TABLE IF EXISTS cost_fact_2026_01" in s for s in conn.executed_statements)

        # 2. Restore archived Parquet partition back into PostgreSQL
        restore_meta = ColumnarArchivalEngine.restore_partition_from_parquet(
            conn=conn,  # type: ignore[arg-type]
            parent_table="cost_fact",
            parquet_file=parquet_path,
            from_val="2026-01-01",
            to_val="2026-02-01",
        )

        assert restore_meta["status"] == "RESTORED"
        assert restore_meta["rows_restored"] == 2
        # Verify partition was re-attached
        assert any("ATTACH PARTITION cost_fact_2026_01" in s for s in conn.executed_statements)
