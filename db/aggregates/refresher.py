"""Materialized Aggregate Table Refresh Engine.

Enforces Prompt 06 Item 42 & Acceptance:
"Implement materialised aggregate tables for (scope, service, day) and (scope, day),
refreshed after each successful ingestion, and prove they are reproducible from the underlying facts."
"Acceptance: A thirteen-month aggregation query grouped by three dimensions completes
within the stated performance target on the synthetic estate."
"""

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, text


class AggregateRefresher:
    """Manages materialized daily cost rollups by (scope, service, day) and (scope, day)."""

    @classmethod
    def refresh_aggregates(
        cls,
        conn: Connection,
        tenant_id: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> dict[str, int]:
        """Refreshes daily aggregate slices from cost_fact rows using upsert (ON CONFLICT)."""
        where_clauses = ["1=1"]
        params: dict[str, Any] = {}

        if tenant_id:
            where_clauses.append("tenant_id = :tenant_id")
            params["tenant_id"] = tenant_id
        if from_date:
            where_clauses.append("billing_period_start >= :from_date")
            params["from_date"] = from_date
        if to_date:
            where_clauses.append("billing_period_start < :to_date")
            params["to_date"] = to_date

        filter_sql = " AND ".join(where_clauses)

        # 1. Upsert into agg_cost_scope_service_day
        upsert_svc_sql = text(
            f"""
            INSERT INTO agg_cost_scope_service_day (
                tenant_id, scope_id, service_id, day, billed_cost, effective_cost, row_count, refreshed_at
            )
            SELECT
                tenant_id,
                scope_id,
                service_id,
                DATE(charge_period_start) AS day,
                COALESCE(SUM(billed_cost), 0) AS billed_cost,
                COALESCE(SUM(effective_cost), 0) AS effective_cost,
                COUNT(*) AS row_count,
                NOW() AS refreshed_at
            FROM cost_fact
            WHERE {filter_sql}
            GROUP BY tenant_id, scope_id, service_id, DATE(charge_period_start)
            ON CONFLICT (tenant_id, scope_id, service_id, day)
            DO UPDATE SET
                billed_cost = EXCLUDED.billed_cost,
                effective_cost = EXCLUDED.effective_cost,
                row_count = EXCLUDED.row_count,
                refreshed_at = EXCLUDED.refreshed_at;
            """
        )
        res_svc = conn.execute(upsert_svc_sql, params)

        # 2. Upsert into agg_cost_scope_day (rolled up from service breakdown)
        upsert_scope_sql = text(
            f"""
            INSERT INTO agg_cost_scope_day (
                tenant_id, scope_id, day, billed_cost, effective_cost, row_count, refreshed_at
            )
            SELECT
                tenant_id,
                scope_id,
                day,
                COALESCE(SUM(billed_cost), 0) AS billed_cost,
                COALESCE(SUM(effective_cost), 0) AS effective_cost,
                COALESCE(SUM(row_count), 0) AS row_count,
                NOW() AS refreshed_at
            FROM agg_cost_scope_service_day
            WHERE {"tenant_id = :tenant_id" if tenant_id else "1=1"}
            GROUP BY tenant_id, scope_id, day
            ON CONFLICT (tenant_id, scope_id, day)
            DO UPDATE SET
                billed_cost = EXCLUDED.billed_cost,
                effective_cost = EXCLUDED.effective_cost,
                row_count = EXCLUDED.row_count,
                refreshed_at = EXCLUDED.refreshed_at;
            """
        )
        res_scope = conn.execute(upsert_scope_sql, params if tenant_id else {})

        return {
            "scope_service_day_rows": res_svc.rowcount,
            "scope_day_rows": res_scope.rowcount,
        }

    @classmethod
    def verify_reproducibility(
        cls,
        conn: Connection,
        tenant_id: str,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        """Proves aggregates are mathematically reproducible with zero drift from raw cost_fact rows."""
        # Query raw sums
        raw_sql = text(
            """
            SELECT
                COALESCE(SUM(billed_cost), 0) AS raw_billed,
                COALESCE(SUM(effective_cost), 0) AS raw_effective,
                COUNT(*) AS raw_count
            FROM cost_fact
            WHERE tenant_id = :tenant_id
              AND DATE(charge_period_start) >= :start_date
              AND DATE(charge_period_start) < :end_date;
            """
        )
        raw_res = conn.execute(
            raw_sql, {"tenant_id": tenant_id, "start_date": start_date, "end_date": end_date}
        ).fetchone()

        # Query aggregate table sums
        agg_sql = text(
            """
            SELECT
                COALESCE(SUM(billed_cost), 0) AS agg_billed,
                COALESCE(SUM(effective_cost), 0) AS agg_effective,
                COALESCE(SUM(row_count), 0) AS agg_count
            FROM agg_cost_scope_service_day
            WHERE tenant_id = :tenant_id
              AND day >= :start_date
              AND day < :end_date;
            """
        )
        agg_res = conn.execute(
            agg_sql, {"tenant_id": tenant_id, "start_date": start_date, "end_date": end_date}
        ).fetchone()

        assert raw_res is not None and agg_res is not None

        raw_billed = Decimal(str(raw_res[0]))
        agg_billed = Decimal(str(agg_res[0]))
        billed_drift = abs(raw_billed - agg_billed)

        raw_effective = Decimal(str(raw_res[1]))
        agg_effective = Decimal(str(agg_res[1]))
        effective_drift = abs(raw_effective - agg_effective)

        is_reproducible = (
            (billed_drift == Decimal("0.00"))
            and (effective_drift == Decimal("0.00"))
            and (raw_res[2] == agg_res[2])
        )

        return {
            "reproducible": is_reproducible,
            "raw_billed": raw_billed,
            "agg_billed": agg_billed,
            "billed_drift": billed_drift,
            "raw_effective": raw_effective,
            "agg_effective": agg_effective,
            "effective_drift": effective_drift,
            "raw_row_count": raw_res[2],
            "agg_row_count": agg_res[2],
        }
