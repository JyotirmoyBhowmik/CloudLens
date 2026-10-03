"""Unified Analytics, BI Feed & Semantic Layer Service Facade (Prompt 56).

Coordinates:
- Scheduled FOCUS-format partitioned extracts with versioned schemas.
- Star-schema semantic layer with conformed dimensions and business-friendly naming.
- Pre-computed derived measures (billed, effective, list, contracted, discount, budget, variance, utilisation, forecast, unallocated, allocated, estimated, reconciliation variance).
- Preserved four null states (ZERO/NO_COST, NO_DATA, NOT_APPLICABLE, NOT_SUPPORTED).
- Incremental extraction with watermark and unambiguous restatement handling.
- Rate-limited read-only analytical access path strictly isolated from transactional OLTP database.
- Scope-bound extract identity with verifiable manifest.
- Observability and alerting for late or empty extracts.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
from typing import Any

from domain.analytics.data_dictionary import get_semantic_data_dictionary
from domain.analytics.extract_engine import AnalyticsExtractEngine
from domain.analytics.models import (
    AnalyticalExtractManifest,
    AnalyticalQueryRequest,
    AnalyticalQueryResponse,
    AnalyticsExtractJob,
    SemanticDataDictionaryField,
)
from domain.analytics.observability import ExtractObservabilityEngine
from domain.analytics.query_engine import AnalyticsQueryEngine
from domain.analytics.repository import (
    AnalyticsRepository,
    get_analytics_repository,
    reset_analytics_repository,
)
from domain.analytics.semantic_layer import SemanticLayerEngine
from domain.analytics.watermark import WatermarkTracker
from domain.models.exceptions import (
    AnalyticsExtractNotFoundException,
    TransactionalPathAccessForbiddenException,
)
from domain.tenant.context import TenantContext, require_tenant_context

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Enterprise domain service facade for analytics export, BI feed, and semantic layer."""

    def __init__(
        self,
        repository: AnalyticsRepository | None = None,
        semantic_engine: SemanticLayerEngine | None = None,
        extract_engine: AnalyticsExtractEngine | None = None,
        query_engine: AnalyticsQueryEngine | None = None,
        watermark_tracker: WatermarkTracker | None = None,
        observability_engine: ExtractObservabilityEngine | None = None,
    ) -> None:
        self.repository = repository or get_analytics_repository()
        self.semantic_engine = semantic_engine or SemanticLayerEngine()
        self.watermark_tracker = watermark_tracker or WatermarkTracker()
        self.extract_engine = extract_engine or AnalyticsExtractEngine(
            semantic_engine=self.semantic_engine,
            watermark_tracker=self.watermark_tracker,
        )
        self.query_engine = query_engine or AnalyticsQueryEngine()
        self.observability_engine = observability_engine or ExtractObservabilityEngine()

    # ==========================================================================
    # 1. Scheduled & Ad-Hoc Partitioned Extracts
    # ==========================================================================

    def run_extract(
        self,
        *,
        period: str,
        service_identity_id: str,
        service_identity_name: str,
        scope_grants: list[str],
        tenant_context: TenantContext,
        is_restatement: bool = False,
        raw_facts: list[dict[str, Any]] | None = None,
        raise_on_empty: bool = False,
    ) -> tuple[AnalyticsExtractJob, AnalyticalExtractManifest]:
        """Executes a partitioned analytical extract, stores the job, and updates observability."""
        tc = require_tenant_context(tenant_context)

        # 1. Generate extract via ExtractEngine
        job, manifest = self.extract_engine.generate_extract(
            period=period,
            service_identity_id=service_identity_id,
            service_identity_name=service_identity_name,
            scope_grants=scope_grants,
            tenant_context=tc,
            raw_facts=raw_facts,
            is_restatement=is_restatement,
        )

        # 2. Persist job in repository
        self.repository.save_job(job, tenant_context=tc)

        # 3. Cache snapshot for isolated analytical query engine
        facts, dims, _, _ = self.semantic_engine.generate_star_schema_dataset(
            raw_rows=raw_facts
            if raw_facts is not None
            else self.extract_engine._build_synthetic_period_facts(period, tc),
            tenant_context=tc,
            period=period,
            version=job.version,
        )
        self.repository.save_snapshot(period, facts, dims, tenant_context=tc)

        # 4. Observability: Record job completion in audit stream
        self.observability_engine.record_job_completion(job, tenant_context=tc)

        # 5. Observability: Check for emptiness
        self.observability_engine.evaluate_emptiness(
            job, tenant_context=tc, raise_exception=raise_on_empty
        )

        return job, manifest

    def get_extract(self, extract_id: str, *, tenant_context: TenantContext) -> AnalyticsExtractJob:
        """Retrieves an extract job record or raises AnalyticsExtractNotFoundException."""
        job = self.repository.get_job(extract_id, tenant_context=tenant_context)
        if not job:
            raise AnalyticsExtractNotFoundException(extract_id)
        return job

    def get_manifest(
        self, extract_id: str, *, tenant_context: TenantContext
    ) -> AnalyticalExtractManifest:
        """Retrieves an extract manifest or raises AnalyticsExtractNotFoundException."""
        job = self.get_extract(extract_id, tenant_context=tenant_context)
        if not job.manifest:
            raise AnalyticsExtractNotFoundException(f"{extract_id}-manifest")
        return job.manifest

    def list_extracts(
        self, *, tenant_context: TenantContext, limit: int = 50, offset: int = 0
    ) -> list[AnalyticsExtractJob]:
        """Lists extract run history for the tenant."""
        return self.repository.list_jobs(tenant_context=tenant_context, limit=limit, offset=offset)

    # ==========================================================================
    # 2. Isolated Read-Only Analytical Query Path
    # ==========================================================================

    def execute_query(
        self,
        request: AnalyticalQueryRequest,
        *,
        tenant_context: TenantContext,
        oltp_connection: Any = None,
    ) -> AnalyticalQueryResponse:
        """Executes a multi-dimensional analytical query against the isolated semantic projection.

        Hard rule: Never touches the transactional database path.
        """
        # Architectural isolation guard
        if oltp_connection is not None:
            raise TransactionalPathAccessForbiddenException(
                "Violation detected: Analytical queries are strictly prohibited from utilizing transactional database connections."
            )

        tc = require_tenant_context(tenant_context)
        target_period = request.period or dt.datetime.now(dt.UTC).strftime("%Y-%m")

        # Retrieve cached star-schema snapshot or build from default synthetic facts
        snapshot = self.repository.get_snapshot(target_period, tenant_context=tc)
        if not snapshot:
            raw_facts = self.extract_engine._build_facts_for_query(target_period, tc)
            facts, dims, _, _ = self.semantic_engine.generate_star_schema_dataset(
                raw_rows=raw_facts,
                tenant_context=tc,
                period=target_period,
            )
            self.repository.save_snapshot(target_period, facts, dims, tenant_context=tc)
            snapshot = (facts, dims)

        facts, dims = snapshot
        return self.query_engine.execute_query(
            request,
            facts=facts,
            dimensions=dims,
            tenant_context=tc,
            oltp_connection=None,
        )

    # ==========================================================================
    # 3. Observability SLA Enforcement
    # ==========================================================================

    def check_extract_sla(
        self,
        *,
        schedule_id: str,
        scheduled_for: dt.datetime,
        actual_completion: dt.datetime | None,
        sla_window_minutes: float = 60.0,
        tenant_context: TenantContext,
        raise_on_violation: bool = False,
    ) -> bool:
        """Enforces SLA lateness check and dispatches alerts on breach."""
        return self.observability_engine.evaluate_lateness(
            scheduled_for=scheduled_for,
            actual_completion=actual_completion,
            sla_window_minutes=sla_window_minutes,
            schedule_id=schedule_id,
            tenant_context=tenant_context,
            raise_exception=raise_on_violation,
        )

    # ==========================================================================
    # 4. Data Dictionary & Reference Artefacts
    # ==========================================================================

    def get_data_dictionary(self) -> list[SemanticDataDictionaryField]:
        """Returns the published Semantic Layer Data Dictionary."""
        return get_semantic_data_dictionary()

    def get_reference_monthly_cost_pack(
        self, *, tenant_context: TenantContext, period: str = "2026-09"
    ) -> dict[str, Any]:
        """Generates the reference monthly cost pack directly from the semantic layer."""
        tc = require_tenant_context(tenant_context)
        # Query 1: Cost by Business Unit with Budget and Variance
        q_bu = AnalyticalQueryRequest(
            dimensions=["BusinessUnitName"],
            measures=[
                "BilledCostAmount",
                "EffectiveCostAmount",
                "BudgetAmount",
                "BudgetVarianceAmount",
                "RealisedDiscountAmount",
            ],
            period=period,
        )
        res_bu = self.execute_query(q_bu, tenant_context=tc)

        # Query 2: Cost by Provider
        q_prov = AnalyticalQueryRequest(
            dimensions=["ProviderKey"],
            measures=["BilledCostAmount", "RealisedDiscountAmount"],
            period=period,
        )
        res_prov = self.execute_query(q_prov, tenant_context=tc)

        # Aggregate totals
        total_billed = sum(float(r.get("BilledCostAmount", 0.0)) for r in res_bu.rows)
        total_budget = sum(float(r.get("BudgetAmount", 0.0)) for r in res_bu.rows)
        total_discount = sum(float(r.get("RealisedDiscountAmount", 0.0)) for r in res_bu.rows)
        total_variance = total_billed - total_budget

        return {
            "title": f"Monthly Cloud Executive Spend & Performance Pack ({period})",
            "period": period,
            "generated_at": dt.datetime.now(dt.UTC).isoformat(),
            "currency": "USD",
            "executive_summary": {
                "total_billed_cost": round(total_billed, 2),
                "total_budget": round(total_budget, 2),
                "total_variance": round(total_variance, 2),
                "total_realised_discounts": round(total_discount, 2),
                "overall_budget_status": "OVER_BUDGET" if total_variance > 0 else "ON_TRACK",
            },
            "spend_by_business_unit": res_bu.rows,
            "spend_by_provider": res_prov.rows,
            "governance_note": (
                "Data rendered exclusively from CloudLens Semantic Layer. "
                "Zero direct application database queries executed."
            ),
        }

    def get_semantic_to_focus_mapping(self) -> list[dict[str, str]]:
        """Returns the mapping table from CloudLens Semantic Layer columns to FOCUS 1.0 columns."""
        return [
            {
                "SemanticLayerColumn": "BilledCostAmount",
                "FocusColumn": "BilledCost",
                "Description": "Invoiced charge amount before or after customer discounts.",
            },
            {
                "SemanticLayerColumn": "EffectiveCostAmount",
                "FocusColumn": "EffectiveCost",
                "Description": "Amortised cost of usage including reservation amortisation and blended rates.",
            },
            {
                "SemanticLayerColumn": "ListCostAmount",
                "FocusColumn": "ListCost",
                "Description": "Published undiscounted retail catalog cost.",
            },
            {
                "SemanticLayerColumn": "ContractedCostAmount",
                "FocusColumn": "ContractedCost",
                "Description": "Negotiated enterprise contracted discount schedule cost.",
            },
            {
                "SemanticLayerColumn": "RealisedDiscountAmount",
                "FocusColumn": "CommitmentDiscountSavings",
                "Description": "Monetary value of realised savings from commitments.",
            },
            {
                "SemanticLayerColumn": "ProviderKey",
                "FocusColumn": "ProviderName",
                "Description": "Standardised cloud provider code.",
            },
            {
                "SemanticLayerColumn": "ServiceKey",
                "FocusColumn": "ServiceName",
                "Description": "Normalized provider cloud service name.",
            },
            {
                "SemanticLayerColumn": "ResourceKey",
                "FocusColumn": "ResourceId",
                "Description": "Canonical or native resource identifier.",
            },
            {
                "SemanticLayerColumn": "RegionKey",
                "FocusColumn": "RegionId",
                "Description": "Standardized geographic region code.",
            },
            {
                "SemanticLayerColumn": "ChargeCategoryKey",
                "FocusColumn": "ChargeCategory",
                "Description": "Primary FOCUS charge category: Usage, Purchase, Credit, Tax, Refund.",
            },
            {
                "SemanticLayerColumn": "UsageQuantity",
                "FocusColumn": "UsageQuantity",
                "Description": "Measured consumable metric quantity.",
            },
            {
                "SemanticLayerColumn": "ScopeKey",
                "FocusColumn": "SubAccountId",
                "Description": "Organizational scope or sub-account identifier.",
            },
            {
                "SemanticLayerColumn": "Currency",
                "FocusColumn": "BillingCurrency",
                "Description": "ISO 4217 currency code.",
            },
        ]


_global_analytics_service: AnalyticsService | None = None
_service_lock = threading.Lock()


def get_analytics_service() -> AnalyticsService:
    """Returns singleton instance of AnalyticsService."""
    global _global_analytics_service
    if _global_analytics_service is None:
        with _service_lock:
            if _global_analytics_service is None:
                _global_analytics_service = AnalyticsService()
    return _global_analytics_service


def reset_analytics_service() -> None:
    """Resets singleton instance for testing isolation."""
    global _global_analytics_service
    with _service_lock:
        _global_analytics_service = None
    reset_analytics_repository()
