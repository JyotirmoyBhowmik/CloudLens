"""Unified Usage & Monitoring Domain Service (Prompt 25).

Enforces:
- Prompt 25: Fourteen canonical monitoring types (MT-01 to MT-14) + Quota Headroom (MT-15).
- Prompt 25: Per-resource monitoring type defaulting and override with audit.
  "Changing a monitoring type is audited and changes which metrics are collected on the next cycle."
- Prompt 25: Cardinality discipline - collect only metrics required by monitoring type.
  "A storage resource collects storage metrics and not compute metrics."
- Prompt 25: Explicit gap recording as 'No Data' (never assumed zero).
- Prompt 25: Labeled interpolation only - silent interpolation is forbidden.
- Prompt 25: 4-level expectation inheritance (RESOURCE, SERVICE, SCOPE, TENANT).
- Prompt 25: Call-volume estimator and cost-materiality filtering.
"""

from __future__ import annotations

import builtins
import logging
import threading
from datetime import UTC, datetime
from typing import Any

from domain.audit.models import AuditEventCreate
from domain.audit.service import get_audit_service
from domain.models.enums import AuditEventType
from domain.models.exceptions import (
    ExpectationNotFoundException,
    OverrideValidationException,
)
from domain.models.measures import QuantityMeasure
from domain.tenant.context import TenantContext
from domain.usage.collector import UsageCollector
from domain.usage.estimator import CallVolumeEstimator
from domain.usage.expectations import ExpectationEngine
from domain.usage.materiality import CostMaterialityFilter
from domain.usage.models import (
    CallVolumeEstimate,
    CallVolumeEstimateRequest,
    ExpectationEvaluationResult,
    ExpectationLevel,
    MaterialityFilterConfig,
    MaterialityFilterResult,
    MonitoringType,
    MonitoringTypeDefinition,
    MonitoringTypeOverride,
    PreAggregatedUsageRecord,
    ResolvedMonitoringType,
    UsageExpectation,
    UsageIngestRequest,
    UsageQueryFilter,
)
from domain.usage.registry import (
    get_allowable_metrics,
    get_default_monitoring_type_for_resource,
    list_monitoring_types,
)
from domain.usage.repository import UsageRepository

logger = logging.getLogger(__name__)


class UsageService:
    """Unified service providing usage ingestion, expectation resolution, and estimation."""

    def __init__(self, repository: UsageRepository | None = None) -> None:
        self.repository = repository or UsageRepository()
        self.collector = UsageCollector(self.repository)
        self.expectation_engine = ExpectationEngine(self.repository)
        self.estimator = CallVolumeEstimator()
        self.materiality_filter = CostMaterialityFilter()

    # ==========================================================================
    # 1. Monitoring Type Catalogue & Resolution
    # ==========================================================================

    def list_monitoring_types(self) -> builtins.list[MonitoringTypeDefinition]:
        """Lists all fifteen canonical monitoring types."""
        return list_monitoring_types()

    def resolve_monitoring_type(
        self,
        resource_id: str,
        native_type_name: str = "",
        canonical_type: str | None = None,
        *,
        tenant_context: TenantContext,
    ) -> ResolvedMonitoringType:
        """Resolves active monitoring type for a resource, checking overrides before catalogue defaults.

        'Default the monitoring type from the resource type catalogue and allow a per-resource
        override with audit.'
        """
        # 1. Check for manual override
        override = self.repository.get_override(resource_id, tenant_context=tenant_context)
        if override:
            return ResolvedMonitoringType(
                resource_id=resource_id,
                monitoring_type=override.monitoring_type,
                is_overridden=True,
                source="RESOURCE_OVERRIDE",
                allowable_metrics=list(get_allowable_metrics(override.monitoring_type)),
                override_details=override,
            )

        # 2. Default from catalogue
        default_type = get_default_monitoring_type_for_resource(
            native_type_name=native_type_name, canonical_type=canonical_type
        )
        return ResolvedMonitoringType(
            resource_id=resource_id,
            monitoring_type=default_type,
            is_overridden=False,
            source="CATALOGUE_DEFAULT",
            allowable_metrics=list(get_allowable_metrics(default_type)),
            override_details=None,
        )

    def override_monitoring_type(
        self,
        resource_id: str,
        new_monitoring_type: MonitoringType,
        who: str,
        why: str,
        native_type_name: str = "",
        canonical_type: str | None = None,
        *,
        tenant_context: TenantContext,
    ) -> MonitoringTypeOverride:
        """Applies a per-resource monitoring type override with immutable audit logging.

        'Changing a monitoring type is audited and changes which metrics are collected on the next cycle.'
        """
        if not why or len(why.strip()) < 20:
            raise OverrideValidationException(
                "Mandatory rationale 'why' must be at least 20 characters describing the FinOps justification."
            )

        current = self.resolve_monitoring_type(
            resource_id=resource_id,
            native_type_name=native_type_name,
            canonical_type=canonical_type,
            tenant_context=tenant_context,
        )

        override = MonitoringTypeOverride(
            id=f"ovr-mt-{resource_id[:12]}",
            tenant_id=tenant_context.tenant_id,
            resource_id=resource_id,
            monitoring_type=new_monitoring_type,
            previous_monitoring_type=current.monitoring_type,
            who=who,
            why=why.strip(),
            applied_at=datetime.now(UTC),
        )

        self.repository.save_override(override, tenant_context=tenant_context)

        # Emit audit event to enterprise append-only stream
        try:
            audit_svc = get_audit_service()
            audit_svc.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.MONITORING_TYPE_OVERRIDDEN,
                    actor_id=who,
                    actor_roles=tenant_context.roles,
                    action="MONITORING_TYPE_OVERRIDDEN",
                    resource_type="RESOURCE",
                    resource_id=resource_id,
                    details={
                        "previous_monitoring_type": current.monitoring_type.value,
                        "new_monitoring_type": new_monitoring_type.value,
                        "why": why.strip(),
                        "previous_allowable_metrics": current.allowable_metrics,
                        "new_allowable_metrics": list(get_allowable_metrics(new_monitoring_type)),
                    },
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception as audit_err:
            logger.warning("Failed to append audit event for override: %s", audit_err)

        return override

    # ==========================================================================
    # 2. Ingestion & Pre-Aggregation
    # ==========================================================================

    def ingest_usage(
        self,
        request: UsageIngestRequest,
        native_type_name: str = "",
        canonical_type: str | None = None,
        *,
        tenant_context: TenantContext,
    ) -> PreAggregatedUsageRecord:
        """Ingests usage metric enforcing the active monitoring type's cardinality."""
        resolved = self.resolve_monitoring_type(
            resource_id=request.resource_id,
            native_type_name=native_type_name,
            canonical_type=canonical_type,
            tenant_context=tenant_context,
        )
        return self.collector.ingest_metric(
            request=request,
            resolved_monitoring_type=resolved.monitoring_type,
            tenant_context=tenant_context,
        )

    def query_metrics(
        self, filter_params: UsageQueryFilter, *, tenant_context: TenantContext
    ) -> builtins.list[PreAggregatedUsageRecord]:
        """Queries pre-aggregated metric series with multi-attribute filtering (API-031)."""
        return self.repository.query_metrics(filter_params, tenant_context=tenant_context)

    # ==========================================================================
    # 3. Usage Expectations (4-Level Hierarchy)
    # ==========================================================================

    def save_expectation(
        self, expectation: UsageExpectation, *, tenant_context: TenantContext
    ) -> UsageExpectation:
        """Saves or updates a usage expectation across RESOURCE, SERVICE, SCOPE, or TENANT level."""
        self.repository.save_expectation(expectation, tenant_context=tenant_context)

        try:
            audit_svc = get_audit_service()
            audit_svc.append_event(
                tenant_context=tenant_context,
                event_in=AuditEventCreate(
                    event_type=AuditEventType.USAGE_EXPECTATION_CHANGED,
                    actor_id=expectation.created_by,
                    actor_roles=tenant_context.roles,
                    action="USAGE_EXPECTATION_SAVED",
                    resource_type=f"EXPECTATION_{expectation.level.value}",
                    resource_id=expectation.target_id,
                    details={
                        "expectation_id": expectation.id,
                        "level": expectation.level.value,
                        "monitoring_type": expectation.monitoring_type.value,
                        "warning_threshold_pct": str(expectation.warning_threshold_pct),
                        "critical_threshold_pct": str(expectation.critical_threshold_pct),
                    },
                    correlation_id=tenant_context.correlation_id,
                ),
            )
        except Exception as audit_err:
            logger.warning("Failed to append audit event for expectation: %s", audit_err)

        return expectation

    def get_expectation(
        self, expectation_id: str, *, tenant_context: TenantContext
    ) -> UsageExpectation:
        """Retrieves expectation by ID."""
        exp = self.repository.get_expectation(expectation_id, tenant_context=tenant_context)
        if not exp:
            raise ExpectationNotFoundException(expectation_id)
        return exp

    def list_expectations(
        self,
        *,
        tenant_context: TenantContext,
        level: ExpectationLevel | None = None,
        target_id: str | None = None,
    ) -> builtins.list[UsageExpectation]:
        """Lists expectations filtered optionally by level and target."""
        return self.repository.list_expectations(
            tenant_context=tenant_context, level=level, target_id=target_id
        )

    def delete_expectation(self, expectation_id: str, *, tenant_context: TenantContext) -> bool:
        """Deletes expectation record."""
        return self.repository.delete_expectation(expectation_id, tenant_context=tenant_context)

    def evaluate_resource_usage(
        self,
        resource_id: str,
        service_id: str,
        scope_id: str,
        metric_name: str,
        observed_quantity: QuantityMeasure,
        observed_unit: str,
        native_type_name: str = "",
        canonical_type: str | None = None,
        *,
        tenant_context: TenantContext,
    ) -> ExpectationEvaluationResult:
        """Resolves the active expectation through the 4-level hierarchy and evaluates usage."""
        resolved_mt = self.resolve_monitoring_type(
            resource_id=resource_id,
            native_type_name=native_type_name,
            canonical_type=canonical_type,
            tenant_context=tenant_context,
        )

        resolved_exp = self.expectation_engine.resolve_expectation(
            resource_id=resource_id,
            service_id=service_id,
            scope_id=scope_id,
            monitoring_type=resolved_mt.monitoring_type,
            tenant_context=tenant_context,
        )

        return self.expectation_engine.evaluate_usage(
            resource_id=resource_id,
            metric_name=metric_name,
            observed_quantity=observed_quantity,
            observed_unit=observed_unit,
            resolved_expectation=resolved_exp,
        )

    # ==========================================================================
    # 4. Sizing Estimation & Cost-Materiality Filtering
    # ==========================================================================

    def estimate_call_volume(self, request: CallVolumeEstimateRequest) -> CallVolumeEstimate:
        """Predicts provider API call volume and costs before configuration is enabled."""
        return self.estimator.estimate(request)

    def filter_by_materiality(
        self,
        candidates: builtins.list[dict[str, Any]],
        config: MaterialityFilterConfig | None = None,
    ) -> MaterialityFilterResult:
        """Filters candidate resources to exclude those below cost materiality threshold."""
        return self.materiality_filter.filter_resources(candidates, config)


_GLOBAL_USAGE_SERVICE: UsageService | None = None
_USAGE_LOCK = threading.Lock()


def get_usage_service() -> UsageService:
    """Singleton accessor for UsageService."""
    global _GLOBAL_USAGE_SERVICE
    with _USAGE_LOCK:
        if _GLOBAL_USAGE_SERVICE is None:
            _GLOBAL_USAGE_SERVICE = UsageService()
        return _GLOBAL_USAGE_SERVICE


def reset_usage_service() -> None:
    """Resets UsageService for test isolation."""
    global _GLOBAL_USAGE_SERVICE
    with _USAGE_LOCK:
        _GLOBAL_USAGE_SERVICE = UsageService()
