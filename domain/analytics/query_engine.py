"""Isolated Read-Only Analytical Query Engine (Prompt 56 / BBP Section 38).

Enforces:
- Hard rule: Analytical queries NEVER touch the transactional OLTP database path.
- In-memory & columnar analytical projection evaluation isolated from production database connections.
- Flexible multi-dimensional star-schema aggregation (e.g. Cost by Business Unit).
- Enforces caller's scope grants so queries never bypass RBAC.
- Per-tenant rate limiting and structured query execution profiling.
"""

from __future__ import annotations

import collections
import threading
import time
from typing import Any

from domain.analytics.models import (
    AnalyticalQueryRequest,
    AnalyticalQueryResponse,
    FactCostAndUsageRecord,
)
from domain.models.exceptions import (
    AnalyticsRateLimitExceededException,
    TransactionalPathAccessForbiddenException,
)
from domain.tenant.context import TenantContext


class AnalyticsQueryEngine:
    """Isolated read-only analytical query processor decoupled from the transactional database."""

    def __init__(self, max_queries_per_minute: int = 120) -> None:
        self.max_queries_per_minute = max_queries_per_minute
        self._rate_limit_lock = threading.Lock()
        self._request_timestamps: dict[str, list[float]] = collections.defaultdict(list)

    def _check_rate_limit(self, tenant_id: str) -> None:
        """Enforces sliding-window rate limit for analytical queries."""
        now = time.time()
        one_min_ago = now - 60.0
        with self._rate_limit_lock:
            # Filter timestamps in window
            valid_ts = [t for t in self._request_timestamps[tenant_id] if t > one_min_ago]
            if len(valid_ts) >= self.max_queries_per_minute:
                raise AnalyticsRateLimitExceededException(
                    retry_after_seconds=int(60 - (now - valid_ts[0]))
                )
            valid_ts.append(now)
            self._request_timestamps[tenant_id] = valid_ts

    def execute_query(
        self,
        request: AnalyticalQueryRequest,
        *,
        facts: list[FactCostAndUsageRecord],
        dimensions: dict[str, list[Any]],
        tenant_context: TenantContext,
        oltp_connection: Any = None,
    ) -> AnalyticalQueryResponse:
        """Executes a multi-dimensional analytical aggregation query against the semantic layer.

        Raises TransactionalPathAccessForbiddenException if an OLTP connection is supplied.
        """
        # Hard Rule Enforcement: Never touch transactional OLTP path
        if oltp_connection is not None:
            raise TransactionalPathAccessForbiddenException(
                "Violation detected: Analytical queries are strictly prohibited from utilizing transactional database connections."
            )

        self._check_rate_limit(tenant_context.tenant_id)
        start_time = time.perf_counter()

        # Enforce scope authorization
        user_scopes = set(tenant_context.roles) if hasattr(tenant_context, "roles") else set()
        is_admin = tenant_context.is_superuser or any(
            r in ("GLOBAL_ADMIN", "FINOPS_ADMIN", "*") for r in user_scopes
        )
        allowed_scope_ids: set[str] | None = None
        if not is_admin:
            allowed_scope_ids = {
                r.split("SCOPE:")[1] for r in user_scopes if r.startswith("SCOPE:")
            }

        # Build lookup tables for requested dimensions if needed
        # Dimension mappings: e.g. BusinessUnitKey -> BusinessUnitName
        bu_map: dict[str, str] = {}
        for r in dimensions.get("DimBusinessUnit", []):
            if isinstance(r, dict):
                k = r.get("BusinessUnitKey")
                name = r.get("BusinessUnitName")
            else:
                k = getattr(r, "BusinessUnitKey", None)
                name = getattr(r, "BusinessUnitName", None)
            if k and name:
                bu_map[str(k)] = str(name)

        svc_map: dict[str, str] = {}
        for r in dimensions.get("DimService", []):
            if isinstance(r, dict):
                k = r.get("ServiceKey")
                name = r.get("ServiceName")
            else:
                k = getattr(r, "ServiceKey", None)
                name = getattr(r, "ServiceName", None)
            if k and name:
                svc_map[str(k)] = str(name)

        # Filter facts
        filtered_facts: list[FactCostAndUsageRecord] = []
        for f in facts:
            if allowed_scope_ids is not None and f.ScopeKey not in allowed_scope_ids:
                continue
            if request.period and f.ChargePeriod != request.period:
                continue

            # Additional filters
            match = True
            for fk, fv in request.filters.items():
                val = getattr(f, fk, None)
                if val is not None and str(val).lower() != str(fv).lower():
                    match = False
                    break
            if match:
                filtered_facts.append(f)

        # Multi-dimensional aggregation
        grouped_data: dict[tuple[Any, ...], dict[str, float]] = collections.defaultdict(
            lambda: collections.defaultdict(float)
        )

        for f in filtered_facts:
            # Extract dimension values
            dim_vals: list[Any] = []
            for dim in request.dimensions:
                if dim == "BusinessUnitName":
                    dim_vals.append(bu_map.get(f.BusinessUnitKey, f.BusinessUnitKey))
                elif dim == "ServiceName":
                    dim_vals.append(svc_map.get(f.ServiceKey, f.ServiceKey))
                elif hasattr(f, dim):
                    dim_vals.append(getattr(f, dim))
                else:
                    dim_vals.append("UNKNOWN")

            group_key = tuple(dim_vals)

            # Sum requested measures
            for m in request.measures:
                if hasattr(f, m):
                    val = getattr(f, m)
                    if isinstance(val, (int, float)):
                        grouped_data[group_key][m] += float(val)

        # Format rows
        output_rows: list[dict[str, Any]] = []
        for gkey, m_aggregates in grouped_data.items():
            row_dict: dict[str, Any] = {}
            for dim_idx, dim_name in enumerate(request.dimensions):
                row_dict[dim_name] = gkey[dim_idx]
            for m_name in request.measures:
                val = m_aggregates.get(m_name, 0.0)
                # Compute ratios if needed
                if m_name == "BudgetUtilisationPercentage":
                    bgt = m_aggregates.get("BudgetAmount", 0.0)
                    billed = m_aggregates.get("BilledCostAmount", 0.0)
                    row_dict[m_name] = round((billed / bgt * 100.0), 2) if bgt > 0 else 0.0
                else:
                    row_dict[m_name] = round(val, 4)
            output_rows.append(row_dict)

        # Sorting: default sort descending by first measure if present
        if request.measures and output_rows:
            primary_measure = request.measures[0]
            output_rows.sort(key=lambda r: r.get(primary_measure, 0.0), reverse=True)

        total_rows = len(output_rows)
        sliced_rows = output_rows[request.offset : request.offset + request.limit]
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        all_cols = request.dimensions + request.measures

        return AnalyticalQueryResponse(
            columns=all_cols,
            rows=sliced_rows,
            total_rows=total_rows,
            execution_time_ms=round(duration_ms, 2),
            isolation_mode="ISOLATED_ANALYTICAL_REPLICA",
        )
