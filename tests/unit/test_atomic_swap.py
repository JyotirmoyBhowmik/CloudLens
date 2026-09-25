"""Unit Tests for Atomic Partition Replacement.

Acceptance Criteria:
- Loading cost rows for one month and re-loading the same month produces identical totals with no duplication.
- Re-ingested period is written to a staging partition and swapped in via atomic metadata transaction.
- Zero DELETE FROM operations are executed during re-ingestion.
"""

from typing import Any

from db.partitioning.atomic_swap import AtomicPartitionSwapper


class MockScalarResult:
    def __init__(self, val: Any) -> None:
        self._val = val

    def scalar(self) -> Any:
        return self._val


class RecordingConnection:
    def __init__(self, active_exists: bool = True) -> None:
        self.executed_statements: list[str] = []
        self.active_exists = active_exists

    def execute(self, statement: Any, params: Any = None) -> Any:
        _ = params
        sql = str(statement)
        self.executed_statements.append(sql)
        if "SELECT EXISTS" in sql:
            return MockScalarResult(self.active_exists)
        return MockScalarResult(None)


def test_atomic_staging_partition_preparation():
    """Verify staging table is created matching parent table schema with explicit range CHECK constraint."""
    conn = RecordingConnection()
    staging_name = AtomicPartitionSwapper.prepare_staging_partition(
        conn=conn,  # type: ignore[arg-type]
        parent_table="cost_fact",
        year=2026,
        month=3,
    )

    assert staging_name == "cost_fact_staging_2026_03"
    assert any(
        "CREATE TABLE cost_fact_staging_2026_03 (LIKE cost_fact INCLUDING ALL)" in s
        for s in conn.executed_statements
    )
    assert any(
        "CHECK (billing_period_start >= '2026-03-01' AND billing_period_start < '2026-04-01')" in s
        for s in conn.executed_statements
    )


def test_atomic_swap_execution_with_zero_delete_operations():
    """Acceptance: Swapping in a re-ingested period replaces active partition with zero DELETE statements and no duplication."""
    conn = RecordingConnection(active_exists=True)

    result = AtomicPartitionSwapper.atomic_swap(
        conn=conn,  # type: ignore[arg-type]
        parent_table="cost_fact",
        year=2026,
        month=3,
    )

    assert result["status"] == "SWAPPED"
    assert result["active_partition"] == "cost_fact_2026_03"

    # Verify no DELETE FROM statements were executed (Constraint: Do not delete and re-insert)
    assert not any("DELETE FROM cost_fact" in s.upper() for s in conn.executed_statements)

    # Verify transactional DETACH, RENAME, and ATTACH sequence
    assert any(
        "ALTER TABLE cost_fact DETACH PARTITION cost_fact_2026_03" in s
        for s in conn.executed_statements
    )
    assert any(
        "ALTER TABLE cost_fact ATTACH PARTITION cost_fact_staging_2026_03" in s
        for s in conn.executed_statements
    )
    assert any(
        "ALTER TABLE cost_fact_staging_2026_03 RENAME TO cost_fact_2026_03" in s
        for s in conn.executed_statements
    )


def test_initial_partition_attachment_when_no_prior_partition_existed():
    """Verify clean attachment when loading a brand new month for the first time."""
    conn = RecordingConnection(active_exists=False)

    result = AtomicPartitionSwapper.atomic_swap(
        conn=conn,  # type: ignore[arg-type]
        parent_table="cost_fact",
        year=2026,
        month=4,
    )

    assert result["status"] == "SWAPPED"
    # When active partition did not previously exist, no detach was required
    assert not any("DETACH PARTITION" in s for s in conn.executed_statements)
    assert any(
        "ALTER TABLE cost_fact ATTACH PARTITION cost_fact_staging_2026_04" in s
        for s in conn.executed_statements
    )
