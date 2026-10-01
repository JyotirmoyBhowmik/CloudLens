"""Tenant-Isolated Repository for Usage Telemetry, Overrides, and Expectations (Prompt 25).

Enforces:
- Prompt 13 Item 84: Mandatory TenantContext on every public repository method.
- Prompt 25: Storage of pre-aggregated usage facts, explicit gaps, and labeled interpolations.
- Prompt 25: Per-resource monitoring type overrides.
- Prompt 25: 4-level usage expectations (RESOURCE, SERVICE, SCOPE, TENANT).
"""

from __future__ import annotations

import builtins
import logging
from typing import Any

from domain.tenant.context import TenantContext
from domain.tenant.repository import TenantAwareRepository
from domain.usage.models import (
    ExpectationLevel,
    MonitoringTypeOverride,
    PreAggregatedUsageRecord,
    UsageExpectation,
    UsageQueryFilter,
)

logger = logging.getLogger(__name__)


class UsageRepository(TenantAwareRepository[PreAggregatedUsageRecord]):
    """Tenant-scoped repository storing usage records, overrides, and expectations."""

    def __init__(self) -> None:
        # Key: (tenant_id, record_id) -> PreAggregatedUsageRecord
        self._usage_records: dict[tuple[str, str], PreAggregatedUsageRecord] = {}
        # Key: (tenant_id, resource_id) -> MonitoringTypeOverride
        self._overrides: dict[tuple[str, str], MonitoringTypeOverride] = {}
        # Key: (tenant_id, expectation_id) -> UsageExpectation
        self._expectations: dict[tuple[str, str], UsageExpectation] = {}

    # ==========================================================================
    # 1. Pre-Aggregated Usage Facts
    # ==========================================================================

    def save_usage_record(
        self, record: PreAggregatedUsageRecord, *, tenant_context: TenantContext
    ) -> None:
        """Persists a single pre-aggregated usage record under tenant isolation."""
        self._validate_tenant_context(tenant_context)
        if record.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Usage record tenant '{record.tenant_id}' mismatches context '{tenant_context.tenant_id}'."
            )
        key = (tenant_context.tenant_id, record.id)
        self._usage_records[key] = record

    def save(
        self, entity: PreAggregatedUsageRecord, *, tenant_context: TenantContext
    ) -> PreAggregatedUsageRecord:
        """Persists or updates a usage record, ensuring tenant ownership integrity."""
        self.save_usage_record(entity, tenant_context=tenant_context)
        return entity

    def delete(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes a usage record within the tenant scope."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        if key in self._usage_records:
            del self._usage_records[key]
            return True
        return False

    def exists(self, entity_id: str, *, tenant_context: TenantContext) -> bool:
        """Checks if a usage record exists within the tenant scope."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, entity_id)
        return key in self._usage_records

    def save_usage_records(
        self, records: builtins.list[PreAggregatedUsageRecord], *, tenant_context: TenantContext
    ) -> int:
        """Persists a batch of pre-aggregated usage records under tenant isolation."""
        self._validate_tenant_context(tenant_context)
        count = 0
        for rec in records:
            self.save_usage_record(rec, tenant_context=tenant_context)
            count += 1
        return count

    def get(
        self, entity_id: str, *, tenant_context: TenantContext
    ) -> PreAggregatedUsageRecord | None:
        """Retrieves a single usage record by ID."""
        self._validate_tenant_context(tenant_context)
        return self._usage_records.get((tenant_context.tenant_id, entity_id))

    def list(
        self,
        *,
        tenant_context: TenantContext,
        filter_params: Any = None,
        limit: int = 50,
        offset: int = 0,
    ) -> builtins.list[PreAggregatedUsageRecord]:
        """Lists usage records belonging strictly to the tenant."""
        self._validate_tenant_context(tenant_context)
        records = [
            r for (t_id, _), r in self._usage_records.items() if t_id == tenant_context.tenant_id
        ]
        if isinstance(filter_params, dict):
            if "resource_id" in filter_params and filter_params["resource_id"]:
                records = [r for r in records if r.resource_id == filter_params["resource_id"]]
            if "metric_name" in filter_params and filter_params["metric_name"]:
                records = [r for r in records if r.metric_name == filter_params["metric_name"]]
        records.sort(key=lambda r: r.interval_start, reverse=True)
        return records[offset : offset + limit]

    def query_metrics(
        self, filter_params: UsageQueryFilter, *, tenant_context: TenantContext
    ) -> builtins.list[PreAggregatedUsageRecord]:
        """Queries pre-aggregated metric time series with multi-attribute filtering (API-031)."""
        self._validate_tenant_context(tenant_context)
        results = []

        for (t_id, _), rec in self._usage_records.items():
            if t_id != tenant_context.tenant_id:
                continue

            if filter_params.resource_id and rec.resource_id != filter_params.resource_id:
                continue

            if filter_params.scope_id and rec.scope_id != filter_params.scope_id:
                continue

            if filter_params.metric_name and rec.metric_name != filter_params.metric_name:
                continue

            if filter_params.granularity and rec.granularity != filter_params.granularity:
                continue

            if not filter_params.include_gaps and rec.is_gap:
                continue

            if (
                filter_params.interval_start_gte
                and rec.interval_start < filter_params.interval_start_gte
            ):
                continue

            if filter_params.interval_end_lte and rec.interval_end > filter_params.interval_end_lte:
                continue

            results.append(rec)

        results.sort(key=lambda r: r.interval_start)
        return results[filter_params.offset : filter_params.offset + filter_params.limit]

    # ==========================================================================
    # 2. Monitoring Type Overrides
    # ==========================================================================

    def save_override(
        self, override: MonitoringTypeOverride, *, tenant_context: TenantContext
    ) -> None:
        """Stores a per-resource monitoring type override."""
        self._validate_tenant_context(tenant_context)
        if override.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Override tenant '{override.tenant_id}' mismatches context '{tenant_context.tenant_id}'."
            )
        key = (tenant_context.tenant_id, override.resource_id)
        self._overrides[key] = override

    def get_override(
        self, resource_id: str, *, tenant_context: TenantContext
    ) -> MonitoringTypeOverride | None:
        """Retrieves active monitoring type override for a resource."""
        self._validate_tenant_context(tenant_context)
        return self._overrides.get((tenant_context.tenant_id, resource_id))

    def list_overrides(
        self, *, tenant_context: TenantContext
    ) -> builtins.list[MonitoringTypeOverride]:
        """Lists all active monitoring type overrides for the tenant."""
        self._validate_tenant_context(tenant_context)
        return [o for (t_id, _), o in self._overrides.items() if t_id == tenant_context.tenant_id]

    # ==========================================================================
    # 3. Usage Expectations (RESOURCE, SERVICE, SCOPE, TENANT)
    # ==========================================================================

    def save_expectation(
        self, expectation: UsageExpectation, *, tenant_context: TenantContext
    ) -> None:
        """Saves or updates an expectation record."""
        self._validate_tenant_context(tenant_context)
        if expectation.tenant_id != tenant_context.tenant_id:
            raise ValueError(
                f"Expectation tenant '{expectation.tenant_id}' mismatches context '{tenant_context.tenant_id}'."
            )
        key = (tenant_context.tenant_id, expectation.id)
        self._expectations[key] = expectation

    def get_expectation(
        self, expectation_id: str, *, tenant_context: TenantContext
    ) -> UsageExpectation | None:
        """Retrieves expectation by ID."""
        self._validate_tenant_context(tenant_context)
        return self._expectations.get((tenant_context.tenant_id, expectation_id))

    def list_expectations(
        self,
        *,
        tenant_context: TenantContext,
        level: ExpectationLevel | None = None,
        target_id: str | None = None,
    ) -> builtins.list[UsageExpectation]:
        """Lists expectations filtered optionally by level and target."""
        self._validate_tenant_context(tenant_context)
        results = []
        for (t_id, _), exp in self._expectations.items():
            if t_id != tenant_context.tenant_id:
                continue
            if level and exp.level != level:
                continue
            if target_id and exp.target_id != target_id:
                continue
            results.append(exp)
        return results

    def delete_expectation(self, expectation_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes an expectation record."""
        self._validate_tenant_context(tenant_context)
        key = (tenant_context.tenant_id, expectation_id)
        if key in self._expectations:
            del self._expectations[key]
            return True
        return False
