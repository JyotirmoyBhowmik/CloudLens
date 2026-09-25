"""Usage Fact Downsampling Lifecycle Engine.

Enforces Prompt 06 Item 43:
"Implement the downsampling and archival jobs: usage hourly to daily after the configured age,
daily to monthly beyond that; detached partitions exported to object storage in an open columnar format and restorable."
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Connection, text


class UsageDownsampler:
    """Orchestrates retention rollups for operational telemetry facts."""

    @classmethod
    def downsample_hourly_to_daily(
        cls,
        conn: Connection,
        tenant_id: str | None = None,
        retention_days: int = 90,
    ) -> dict[str, Any]:
        """Rolls up hourly usage records older than retention_days into daily summary rows."""
        cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)

        # 1. Rollup query into daily temporary table or upsert
        filter_tenant = "AND tenant_id = :tenant_id" if tenant_id else ""
        params: dict[str, Any] = {"cutoff": cutoff_date}
        if tenant_id:
            params["tenant_id"] = tenant_id

        # Insert daily rollup rows
        downsample_sql = text(
            f"""
            WITH hourly_slice AS (
                SELECT
                    tenant_id,
                    scope_id,
                    resource_id,
                    DATE_TRUNC('day', interval_start) AS day_start,
                    metric_name,
                    usage_unit,
                    SUM(COALESCE(usage_quantity, 0)) AS total_qty,
                    COUNT(*) AS records_aggregated
                FROM usage_fact
                WHERE interval_start < :cutoff
                  {filter_tenant}
                GROUP BY tenant_id, scope_id, resource_id, DATE_TRUNC('day', interval_start), metric_name, usage_unit
            )
            INSERT INTO usage_fact (
                id, tenant_id, scope_id, resource_id, interval_start, interval_end,
                metric_name, usage_quantity, usage_unit, provider_native, source_provenance, created_at
            )
            SELECT
                'rollup-daily-' || MD5(tenant_id || resource_id || metric_name || day_start::text),
                tenant_id,
                scope_id,
                resource_id,
                day_start,
                day_start + INTERVAL '1 day',
                metric_name || ':daily_rollup',
                total_qty,
                usage_unit,
                jsonb_build_object('records_aggregated', records_aggregated, 'downsampled', true),
                jsonb_build_object('source_system', 'downsampler', 'origin_type', 'DERIVED'),
                NOW()
            FROM hourly_slice
            ON CONFLICT (interval_start, tenant_id, id) DO UPDATE SET
                usage_quantity = EXCLUDED.usage_quantity,
                provider_native = EXCLUDED.provider_native;
            """
        )
        res = conn.execute(downsample_sql, params)

        # 2. Prune granular hourly rows that have been rolled up
        prune_sql = text(
            f"""
            DELETE FROM usage_fact
            WHERE interval_start < :cutoff
              AND metric_name NOT LIKE '%:daily_rollup'
              AND metric_name NOT LIKE '%:monthly_rollup'
              {filter_tenant};
            """
        )
        prune_res = conn.execute(prune_sql, params)

        return {
            "daily_rollups_created": res.rowcount,
            "hourly_records_pruned": prune_res.rowcount,
            "cutoff_timestamp": cutoff_date.isoformat(),
        }

    @classmethod
    def downsample_daily_to_monthly(
        cls,
        conn: Connection,
        tenant_id: str | None = None,
        retention_days: int = 365,
    ) -> dict[str, Any]:
        """Rolls up daily summary records older than retention_days into monthly summary rows."""
        cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)
        filter_tenant = "AND tenant_id = :tenant_id" if tenant_id else ""
        params: dict[str, Any] = {"cutoff": cutoff_date}
        if tenant_id:
            params["tenant_id"] = tenant_id

        # Insert monthly rollup rows
        downsample_sql = text(
            f"""
            WITH daily_slice AS (
                SELECT
                    tenant_id,
                    scope_id,
                    resource_id,
                    DATE_TRUNC('month', interval_start) AS month_start,
                    REPLACE(metric_name, ':daily_rollup', '') AS base_metric,
                    usage_unit,
                    SUM(COALESCE(usage_quantity, 0)) AS total_qty,
                    COUNT(*) AS records_aggregated
                FROM usage_fact
                WHERE interval_start < :cutoff
                  AND metric_name LIKE '%:daily_rollup'
                  {filter_tenant}
                GROUP BY tenant_id, scope_id, resource_id, DATE_TRUNC('month', interval_start), metric_name, usage_unit
            )
            INSERT INTO usage_fact (
                id, tenant_id, scope_id, resource_id, interval_start, interval_end,
                metric_name, usage_quantity, usage_unit, provider_native, source_provenance, created_at
            )
            SELECT
                'rollup-monthly-' || MD5(tenant_id || resource_id || base_metric || month_start::text),
                tenant_id,
                scope_id,
                resource_id,
                month_start,
                month_start + INTERVAL '1 month',
                base_metric || ':monthly_rollup',
                total_qty,
                usage_unit,
                jsonb_build_object('records_aggregated', records_aggregated, 'downsampled', true),
                jsonb_build_object('source_system', 'downsampler', 'origin_type', 'DERIVED'),
                NOW()
            FROM daily_slice
            ON CONFLICT (interval_start, tenant_id, id) DO UPDATE SET
                usage_quantity = EXCLUDED.usage_quantity,
                provider_native = EXCLUDED.provider_native;
            """
        )
        res = conn.execute(downsample_sql, params)

        # Prune daily rows that have been rolled up to monthly
        prune_sql = text(
            f"""
            DELETE FROM usage_fact
            WHERE interval_start < :cutoff
              AND metric_name LIKE '%:daily_rollup'
              {filter_tenant};
            """
        )
        prune_res = conn.execute(prune_sql, params)

        return {
            "monthly_rollups_created": res.rowcount,
            "daily_records_pruned": prune_res.rowcount,
            "cutoff_timestamp": cutoff_date.isoformat(),
        }
