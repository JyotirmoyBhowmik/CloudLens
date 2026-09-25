"""Atomic Partition Replacement Engine.

Enforces Prompt 06 Item 41 & Acceptance:
"Implement atomic partition replacement: a re-ingested period is written to a staging partition
and swapped in, so a reader never sees a half-loaded period."
"Do not delete and re-insert to re-ingest a period."
"Acceptance: Loading 50 million cost rows for one month and re-loading the same month produces
identical totals with no duplication."
"""

from typing import Any

from sqlalchemy import Connection, text

from db.partitioning.manager import format_month_range


class AtomicPartitionSwapper:
    """Orchestrates zero-downtime atomic partition swap for re-ingested billing periods."""

    @staticmethod
    def get_staging_table_name(parent_table: str, year: int, month: int) -> str:
        suffix, _, _ = format_month_range(year, month)
        return f"{parent_table}_staging_{suffix}"

    @staticmethod
    def get_active_partition_name(parent_table: str, year: int, month: int) -> str:
        suffix, _, _ = format_month_range(year, month)
        return f"{parent_table}_{suffix}"

    @classmethod
    def prepare_staging_partition(
        cls,
        conn: Connection,
        parent_table: str,
        year: int,
        month: int,
    ) -> str:
        """Creates a standalone staging partition with identical schema and an explicit check constraint."""
        staging_name = cls.get_staging_table_name(parent_table, year, month)
        _, from_str, to_str = format_month_range(year, month)
        check_col = "billing_period_start" if parent_table == "cost_fact" else "interval_start"

        # 1. Clean previous staging table if exists
        conn.execute(text(f"DROP TABLE IF EXISTS {staging_name} CASCADE;"))

        # 2. Create staging table copying table structure and indexes
        conn.execute(text(f"CREATE TABLE {staging_name} (LIKE {parent_table} INCLUDING ALL);"))

        # 3. Add explicit range CHECK constraint matching partition bounds (required for ATTACH)
        chk_constraint = f"chk_{staging_name}"
        conn.execute(
            text(
                f"""
                ALTER TABLE {staging_name}
                ADD CONSTRAINT {chk_constraint}
                CHECK ({check_col} >= '{from_str}' AND {check_col} < '{to_str}');
                """
            )
        )
        return staging_name

    @classmethod
    def atomic_swap(
        cls,
        conn: Connection,
        parent_table: str,
        year: int,
        month: int,
    ) -> dict[str, Any]:
        """Atomically swaps the newly populated staging partition into the active partition hierarchy.

        Executed inside a single transaction so readers never see half-loaded or duplicated data.
        """
        staging_name = cls.get_staging_table_name(parent_table, year, month)
        active_name = cls.get_active_partition_name(parent_table, year, month)
        old_backup_name = f"{parent_table}_old_{year}_{month:02d}"
        _, from_str, to_str = format_month_range(year, month)
        chk_constraint = f"chk_{staging_name}"

        # Check if active partition currently exists
        check_active_sql = text(
            f"""
            SELECT EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = '{active_name}'
            );
            """
        )
        active_exists = conn.execute(check_active_sql).scalar()

        if active_exists:
            # Atomic detach of old active partition
            conn.execute(text(f"ALTER TABLE {parent_table} DETACH PARTITION {active_name};"))
            conn.execute(text(f"DROP TABLE IF EXISTS {old_backup_name} CASCADE;"))
            conn.execute(text(f"ALTER TABLE {active_name} RENAME TO {old_backup_name};"))

        # Attach new staging partition to parent table
        conn.execute(
            text(
                f"""
                ALTER TABLE {parent_table} ATTACH PARTITION {staging_name}
                FOR VALUES FROM ('{from_str}') TO ('{to_str}');
                """
            )
        )

        # Drop the now redundant check constraint
        try:
            conn.execute(
                text(f"ALTER TABLE {staging_name} DROP CONSTRAINT IF EXISTS {chk_constraint};")
            )
        except Exception:
            pass

        # Rename attached partition to canonical active partition name
        conn.execute(text(f"ALTER TABLE {staging_name} RENAME TO {active_name};"))

        # Clean old detached backup partition
        if active_exists:
            conn.execute(text(f"DROP TABLE IF EXISTS {old_backup_name} CASCADE;"))

        return {
            "status": "SWAPPED",
            "parent_table": parent_table,
            "active_partition": active_name,
            "period": f"{from_str} to {to_str}",
        }
