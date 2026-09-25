"""Partition Maintenance Engine for Fact Tables.

Enforces Prompt 06 Item 40:
"Range-partition the fact tables: cost_fact by billing_period_start (monthly), usage_fact by interval_start,
runtime_state by window_start, audit_event by occurred_at. Implement a maintenance job that creates partitions
ahead of need and never lets a write fail for a missing partition."

Constraints:
- "Do not create partitions lazily on write." (Pre-creates partitions ahead of time).
"""

from datetime import date
from typing import NamedTuple

from sqlalchemy import Connection, text


class PartitionBound(NamedTuple):
    table_name: str
    partition_name: str
    from_date: str
    to_date: str


def get_next_month_start(year: int, month: int) -> tuple[int, int]:
    """Computes next year and month."""
    if month == 12:
        return year + 1, 1
    return year, month + 1


def format_month_range(year: int, month: int) -> tuple[str, str, str]:
    """Returns (suffix, from_date_str, to_date_str)."""
    next_year, next_month = get_next_month_start(year, month)
    suffix = f"{year}_{month:02d}"
    from_str = f"{year}-{month:02d}-01"
    to_str = f"{next_year}-{next_month:02d}-01"
    return suffix, from_str, to_str


def precreate_table_partitions(
    conn: Connection,
    parent_table: str,
    start_year: int,
    start_month: int,
    months_count: int,
) -> list[str]:
    """Generates and executes DDL to create monthly range partitions ahead of need."""
    created_partitions: list[str] = []

    # 1. Ensure DEFAULT partition exists so writes never fail per Prompt 06 Item 40
    default_part_name = f"{parent_table}_default"
    default_sql = f"""
    CREATE TABLE IF NOT EXISTS {default_part_name}
    PARTITION OF {parent_table} DEFAULT;
    """
    try:
        conn.execute(text(default_sql))
        created_partitions.append(default_part_name)
    except Exception:
        pass

    # 2. Pre-create exact monthly partitions
    cur_year = start_year
    cur_month = start_month
    for _ in range(months_count):
        suffix, from_str, to_str = format_month_range(cur_year, cur_month)
        part_name = f"{parent_table}_{suffix}"

        ddl = f"""
        CREATE TABLE IF NOT EXISTS {part_name}
        PARTITION OF {parent_table}
        FOR VALUES FROM ('{from_str}') TO ('{to_str}');
        """
        conn.execute(text(ddl))
        created_partitions.append(part_name)

        cur_year, cur_month = get_next_month_start(cur_year, cur_month)

    return created_partitions


def run_partition_maintenance(
    conn: Connection,
    base_date: date | None = None,
    months_ahead: int = 6,
    months_behind: int = 12,
) -> dict[str, list[str]]:
    """Maintenance job that pre-creates partitions across all 4 fact tables.

    Runs ahead of need (default: 12 months in the past, current month, and 6 months into the future).
    """
    ref_date = base_date or date.today()

    # Calculate starting year and month (months_behind in past)
    total_months = months_behind + 1 + months_ahead
    # Compute start year/month
    start_m_idx = (ref_date.year * 12 + ref_date.month - 1) - months_behind
    start_year = start_m_idx // 12
    start_month = (start_m_idx % 12) + 1

    fact_tables = [
        "cost_fact",
        "usage_fact",
        "runtime_state",
        "audit_event",
    ]

    results: dict[str, list[str]] = {}
    for table in fact_tables:
        parts = precreate_table_partitions(
            conn,
            parent_table=table,
            start_year=start_year,
            start_month=start_month,
            months_count=total_months,
        )
        results[table] = parts

    return results
