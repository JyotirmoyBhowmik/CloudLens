"""Cost Reconciliation Engine (Prompt 24 Items 1-7).

Enforces:
- Prompt 24 Item 1 & BBP Section 12 (BP-17): Authoritative period comparison with finalisation lag guard.
- Prompt 24 Item 2: Deterministic variance classification taxonomy.
- Prompt 24 Item 3: Explicit framing rule: presents both figures and classification without editorialising.
- Prompt 24 Item 4: Configurable per-provider tolerance with PASS/FAILED and investigation item on failure.
- Prompt 24 Item 5: Executive dashboard trust indicator (single most important number for adoption; never suppressed on failure).
- Prompt 24 Item 6: Separate comparison of estimated cost against actual billed cost (evaluating platform estimation accuracy).
- Prompt 24 Item 7: Retain reconciliation history so the trend in variance is visible over time.
- Prompt 24 Strict Negative Constraints:
  * Do not adjust ingested cost data to force a match.
  * Do not suppress a failed reconciliation from the dashboard.
"""

from __future__ import annotations

import calendar
import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from domain.cost.reconciliation.models import (
    EstimateVsActualItem,
    EstimateVsActualReport,
    EstimationBias,
    ExecutiveTrustIndicator,
    ExecutiveTrustStatus,
    InvestigationPriority,
    InvestigationStatus,
    ProviderToleranceConfig,
    ReconciliationHistorySummary,
    ReconciliationInvestigationItem,
    ReconciliationReport,
    ReconciliationStatus,
    RunReconciliationRequest,
    VarianceClassification,
)
from domain.cost.reconciliation.repository import (
    ReconciliationRepository,
    get_reconciliation_repository,
)
from domain.cost.repository import CostFactRepository, get_cost_repository
from domain.models.base import ProvenanceRecord
from domain.models.exceptions import (
    ReconciliationPeriodNotClosedException,
)
from domain.tenant.context import TenantContext

logger = logging.getLogger(__name__)

# Standard authoritative finalisation lag days per provider (Prompt 24 Item 1)
DEFAULT_PROVIDER_TOLERANCES: dict[str, ProviderToleranceConfig] = {
    "aws": ProviderToleranceConfig(
        provider="aws",
        absolute_tolerance=Decimal("5.00"),
        percentage_tolerance=Decimal("0.50"),
        currency="USD",
        finalisation_lag_days=3,
    ),
    "azure": ProviderToleranceConfig(
        provider="azure",
        absolute_tolerance=Decimal("5.00"),
        percentage_tolerance=Decimal("0.50"),
        currency="USD",
        finalisation_lag_days=3,
    ),
    "gcp": ProviderToleranceConfig(
        provider="gcp",
        absolute_tolerance=Decimal("5.00"),
        percentage_tolerance=Decimal("0.50"),
        currency="USD",
        finalisation_lag_days=4,
    ),
    "oci": ProviderToleranceConfig(
        provider="oci",
        absolute_tolerance=Decimal("5.00"),
        percentage_tolerance=Decimal("0.50"),
        currency="USD",
        finalisation_lag_days=2,
    ),
    "default": ProviderToleranceConfig(
        provider="default",
        absolute_tolerance=Decimal("5.00"),
        percentage_tolerance=Decimal("0.50"),
        currency="USD",
        finalisation_lag_days=3,
    ),
}


class CostReconciliationEngine:
    """Enterprise reconciliation engine managing provider billing comparison, variance classification, and trust scoring."""

    def __init__(
        self,
        reconciliation_repo: ReconciliationRepository | None = None,
        cost_repo: CostFactRepository | None = None,
    ) -> None:
        self._reconciliation_repo = reconciliation_repo or get_reconciliation_repository()
        self._cost_repo = cost_repo or get_cost_repository()
        self._tolerances = self._load_tolerances_from_master_data()

    def _load_tolerances_from_master_data(self) -> dict[str, ProviderToleranceConfig]:
        """Loads provider tolerances from master data registry with fallback defaults."""
        tolerances = dict(DEFAULT_PROVIDER_TOLERANCES)
        try:
            from masterdata.service import get_master_data_service
            md_service = get_master_data_service()
            records = md_service.list_records("RECONCILIATION_TOLERANCE")
            for r in records:
                if r.code.startswith("PROVIDER_TOLERANCE_") and r.attributes:
                    prov = r.attributes.get("provider", "").lower()
                    if prov:
                        tolerances[prov] = ProviderToleranceConfig(
                            provider=prov,
                            absolute_tolerance=Decimal(str(r.attributes.get("absolute_tolerance", 5.0))),
                            percentage_tolerance=Decimal(str(r.attributes.get("percentage_tolerance", 0.5))),
                            currency=str(r.attributes.get("currency", "USD")),
                            finalisation_lag_days=int(r.attributes.get("finalisation_lag_days", 3)),
                        )
        except Exception as e:
            logger.debug("Reconciliation master data tolerance lookup fallback: %s", e)
        return tolerances

    def _get_severity_bands(self, tenant_id: str | None = None) -> dict[str, Decimal]:
        """Fetches investigation priority severity bands from master data."""
        try:
            from masterdata.service import get_master_data_service
            md_service = get_master_data_service()
            record = md_service.get_record("RECONCILIATION_TOLERANCE", "RECONCILIATION_SEVERITY_BANDS", tenant_id=tenant_id)
            if record and record.attributes:
                return {
                    "critical_pct": Decimal(str(record.attributes.get("critical_pct"))),
                    "critical_amount": Decimal(str(record.attributes.get("critical_amount"))),
                    "high_pct": Decimal(str(record.attributes.get("high_pct"))),
                    "high_amount": Decimal(str(record.attributes.get("high_amount"))),
                }
        except Exception as e:
            logger.debug("Failed to fetch severity bands from master data: %s", e)
        # Seeded master data fallback values
        return {
            "critical_pct": Decimal("5.0"),
            "critical_amount": Decimal("1000.0"),
            "high_pct": Decimal("1.0"),
            "high_amount": Decimal("100.0"),
        }

    def set_provider_tolerance(self, config: ProviderToleranceConfig) -> None:
        """Sets custom tolerance and finalisation lag for a specific provider."""
        self._tolerances[config.provider.lower()] = config

    def get_provider_tolerance(self, provider: str) -> ProviderToleranceConfig:
        """Retrieves active tolerance configuration for a provider."""
        return self._tolerances.get(provider.lower(), self._tolerances["default"])

    # --------------------------------------------------------------------------
    # Prompt 24 Item 1 & 3: Reconciliation Execution & Framing
    # --------------------------------------------------------------------------

    def run_reconciliation(
        self,
        request: RunReconciliationRequest,
        *,
        tenant_context: TenantContext,
    ) -> ReconciliationReport:
        """Executes period reconciliation comparing platform normalised total against authoritative provider total.

        Enforces:
        - Period close plus provider finalisation lag check.
        - Per-provider tolerance evaluation (PASS / FAILED).
        - Deterministic variance classification taxonomy.
        - Explicit framing rule: presents both figures without editorialising.
        - Automatic creation of investigation item on failure.
        - Retains both figures in immutable report.
        """
        provider_key = request.provider.lower()
        tolerance = self.get_provider_tolerance(provider_key)
        now = datetime.now(UTC)

        # 1. Period close & finalisation lag guard (Prompt 24 Item 1)
        if not request.bypass_lag_check:
            self._verify_period_finalisation(request.billing_period, tolerance, now)

        # 2. Retrieve platform normalised total from FOCUS facts
        facts = self._cost_repo.get_all_facts(
            tenant_context=tenant_context,
            billing_period=request.billing_period,
            scope_id=request.scope_id,
        )
        # Filter to provider if facts contain multiple providers
        provider_facts = [f for f in facts if f.provider.lower() == provider_key]
        if not provider_facts and facts:
            # Fall back to all facts for scope if provider tag is generic
            provider_facts = facts

        platform_total = sum(
            (f.billed_cost.value for f in provider_facts if f.billed_cost.is_present),
            Decimal("0.0"),
        )
        provider_total = request.provider_authoritative_total

        # 3. Compute absolute, signed, and percentage variance
        signed_variance = platform_total - provider_total
        absolute_variance = abs(signed_variance)
        if provider_total > Decimal("0.0"):
            percentage_variance = (
                (absolute_variance / provider_total) * Decimal("100.0")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            percentage_variance = (
                Decimal("0.00") if platform_total == Decimal("0.0") else Decimal("100.00")
            )

        # 4. Evaluate tolerance (PASS / FAILED)
        is_pass = (
            absolute_variance <= tolerance.absolute_tolerance
            or percentage_variance <= tolerance.percentage_tolerance
        )
        reconcile_status = ReconciliationStatus.PASS if is_pass else ReconciliationStatus.FAILED

        # 5. Deterministic variance classification (Prompt 24 Item 2)
        classification, class_details = self._classify_variance(
            is_pass=is_pass,
            absolute_variance=absolute_variance,
            signed_variance=signed_variance,
            request=request,
            provider_facts=provider_facts,
            tenant_context=tenant_context,
            tolerance=tolerance,
        )

        # 6. Compose explicit non-editorialised framing statement (Prompt 24 Item 3)
        framing_statement = self._compose_framing_statement(
            billing_period=request.billing_period,
            provider=request.provider,
            scope_id=request.scope_id,
            platform_total=platform_total,
            provider_total=provider_total,
            signed_variance=signed_variance,
            percentage_variance=percentage_variance,
            classification=classification,
            currency=request.currency,
        )

        report_id = f"recon-{tenant_context.tenant_id}-{provider_key}-{request.billing_period}-{uuid.uuid4().hex[:8]}"

        # 7. Create investigation item on failure (Prompt 24 Item 4)
        investigation_item_id: str | None = None
        if reconcile_status == ReconciliationStatus.FAILED:
            investigation_item = self._create_investigation_item(
                report_id=report_id,
                tenant_context=tenant_context,
                request=request,
                platform_total=platform_total,
                provider_total=provider_total,
                variance_amount=absolute_variance,
                percentage_variance=percentage_variance,
                classification=classification,
                now=now,
            )
            self._reconciliation_repo.save_investigation_item(
                investigation_item, tenant_context=tenant_context
            )
            investigation_item_id = investigation_item.id

        # 8. Create and persist reconciliation report
        report = ReconciliationReport(
            id=report_id,
            tenant_id=tenant_context.tenant_id,
            provider=request.provider,
            billing_period=request.billing_period,
            scope_id=request.scope_id,
            reconciled_at=now,
            platform_total=platform_total.quantize(Decimal("0.01")),
            provider_total=provider_total.quantize(Decimal("0.01")),
            absolute_variance=absolute_variance.quantize(Decimal("0.01")),
            signed_variance=signed_variance.quantize(Decimal("0.01")),
            percentage_variance=percentage_variance,
            status=reconcile_status,
            classification=classification,
            classification_details=class_details,
            framing_statement=framing_statement,
            tolerance_config=tolerance,
            investigation_item_id=investigation_item_id,
            currency=request.currency,
            source_provenance=ProvenanceRecord(
                source_system=f"reconciliation-engine-{provider_key}",
                discovered_at=now,
                ingested_at=now,
            ),
        )

        return self._reconciliation_repo.save(report, tenant_context=tenant_context)

    # --------------------------------------------------------------------------
    # Prompt 24 Item 5: Executive Dashboard Trust Indicator
    # --------------------------------------------------------------------------

    def compute_executive_trust_indicator(
        self,
        *,
        tenant_context: TenantContext,
    ) -> ExecutiveTrustIndicator:
        """Computes executive adoption trust metric across all reconciled periods and providers.

        STRICT RULE: Never suppress failed reconciliations from the dashboard.
        """
        all_reports = self._reconciliation_repo.list(
            tenant_context=tenant_context, limit=1000, offset=0
        )
        active_investigations = self._reconciliation_repo.list_investigation_items(
            tenant_context=tenant_context,
            status=InvestigationStatus.OPEN,
        )

        total_spend = Decimal("0.0")
        total_variance = Decimal("0.0")
        pass_count = 0
        fail_count = 0
        last_timestamp: datetime | None = None

        provider_stats: dict[str, dict[str, Any]] = {}

        for r in all_reports:
            total_spend += r.provider_total
            total_variance += r.absolute_variance
            if r.status == ReconciliationStatus.PASS:
                pass_count += 1
            else:
                fail_count += 1

            if last_timestamp is None or r.reconciled_at > last_timestamp:
                last_timestamp = r.reconciled_at

            pkey = r.provider.lower()
            if pkey not in provider_stats:
                provider_stats[pkey] = {
                    "total_spend": Decimal("0.0"),
                    "total_variance": Decimal("0.0"),
                    "pass_count": 0,
                    "fail_count": 0,
                }
            provider_stats[pkey]["total_spend"] += r.provider_total
            provider_stats[pkey]["total_variance"] += r.absolute_variance
            if r.status == ReconciliationStatus.PASS:
                provider_stats[pkey]["pass_count"] += 1
            else:
                provider_stats[pkey]["fail_count"] += 1

        total_reports = len(all_reports)
        if total_spend > Decimal("0.0"):
            # Match percentage weighted by spend
            spend_match = Decimal("100.0") - ((total_variance / total_spend) * Decimal("100.0"))
            trust_score = max(Decimal("0.0"), spend_match).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        elif total_reports > 0:
            trust_score = (
                (Decimal(pass_count) / Decimal(total_reports)) * Decimal("100.0")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            trust_score = Decimal("100.00")

        # Health status determination
        if trust_score >= Decimal("99.50") and fail_count == 0:  # no-hardcode-allow: reason="Executive trust score tier thresholds (99.5% and 98.0%)", reviewer="Prompt-48-Audit"
            health_status = ExecutiveTrustStatus.EXCELLENT
        elif trust_score >= Decimal("98.00"):  # no-hardcode-allow: reason="Executive trust score tier thresholds (99.5% and 98.0%)", reviewer="Prompt-48-Audit"
            health_status = ExecutiveTrustStatus.HEALTHY
        else:
            health_status = ExecutiveTrustStatus.NEEDS_ATTENTION

        return ExecutiveTrustIndicator(
            tenant_id=tenant_context.tenant_id,
            trust_score_pct=trust_score,
            status=health_status,
            total_spend_evaluated=total_spend.quantize(Decimal("0.01")),
            total_variance_evaluated=total_variance.quantize(Decimal("0.01")),
            periods_evaluated_count=total_reports,
            reconciliation_pass_count=pass_count,
            reconciliation_fail_count=fail_count,
            active_investigations_count=len(active_investigations),
            last_reconciliation_timestamp=last_timestamp,
            provider_breakdowns=provider_stats,
            is_suppressed=False,  # Strictly never suppressed!
        )

    # --------------------------------------------------------------------------
    # Prompt 24 Item 6: Estimate vs Actual Comparison
    # --------------------------------------------------------------------------

    def evaluate_estimate_vs_actual(
        self,
        billing_period: str,
        estimates: list[dict[str, Any]],
        *,
        tenant_context: TenantContext,
    ) -> EstimateVsActualReport:
        """Evaluates pre-deployment estimates against actual billed FOCUS costs.

        Separate and distinct from platform-versus-provider reconciliation.
        Enables the organization to measure how accurate its own pre-deployment estimates are.
        """
        facts = self._cost_repo.get_all_facts(
            tenant_context=tenant_context,
            billing_period=billing_period,
        )

        # Aggregate actual billed cost by service_id
        actual_by_service: dict[str, Decimal] = {}
        for f in facts:
            if f.billed_cost.is_present:
                sid = f.service_id
                actual_by_service[sid] = (
                    actual_by_service.get(sid, Decimal("0.0")) + f.billed_cost.value
                )

        comparison_items: list[EstimateVsActualItem] = []
        total_estimated = Decimal("0.0")
        total_actual = Decimal("0.0")
        total_abs_error = Decimal("0.0")
        percentage_errors: list[Decimal] = []

        now = datetime.now(UTC)
        for est in estimates:
            service_id = est.get("service_id", "unknown-service")
            resource_id = est.get("resource_id")
            est_cost = Decimal(str(est.get("estimated_cost", "0.0")))
            assumptions = est.get("assumptions_summary")

            act_cost = actual_by_service.get(service_id, Decimal("0.0"))
            abs_err = abs(est_cost - act_cost)
            if act_cost > Decimal("0.0"):
                pct_err = ((abs_err / act_cost) * Decimal("100.0")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            else:
                pct_err = Decimal("0.00") if est_cost == Decimal("0.0") else Decimal("100.00")

            # Directional bias (5% threshold for accurate)
            if est_cost > act_cost * Decimal("1.05"):
                bias = EstimationBias.OVER_ESTIMATED
            elif est_cost < act_cost * Decimal("0.95"):
                bias = EstimationBias.UNDER_ESTIMATED
            else:
                bias = EstimationBias.ACCURATE

            item = EstimateVsActualItem(
                id=f"eva-{uuid.uuid4().hex[:10]}",
                tenant_id=tenant_context.tenant_id,
                service_id=service_id,
                resource_id=resource_id,
                billing_period=billing_period,
                estimated_cost=est_cost.quantize(Decimal("0.01")),
                actual_billed_cost=act_cost.quantize(Decimal("0.01")),
                absolute_error=abs_err.quantize(Decimal("0.01")),
                percentage_error=pct_err,
                bias=bias,
                assumptions_summary=assumptions,
            )
            comparison_items.append(item)
            self._reconciliation_repo.save_estimate_vs_actual(item, tenant_context=tenant_context)

            total_estimated += est_cost
            total_actual += act_cost
            total_abs_error += abs_err
            percentage_errors.append(pct_err)

        # Compute MAPE (Mean Absolute Percentage Error)
        if percentage_errors:
            mape = (sum(percentage_errors) / Decimal(len(percentage_errors))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            mape = Decimal("0.00")

        # Overall platform bias
        if total_estimated > total_actual * Decimal("1.05"):
            overall_bias = EstimationBias.OVER_ESTIMATED
        elif total_estimated < total_actual * Decimal("0.95"):
            overall_bias = EstimationBias.UNDER_ESTIMATED
        else:
            overall_bias = EstimationBias.ACCURATE

        return EstimateVsActualReport(
            id=f"evar-{tenant_context.tenant_id}-{billing_period}-{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_context.tenant_id,
            billing_period=billing_period,
            items=comparison_items,
            total_estimated=total_estimated.quantize(Decimal("0.01")),
            total_actual=total_actual.quantize(Decimal("0.01")),
            absolute_error_total=total_abs_error.quantize(Decimal("0.01")),
            mape_pct=mape,
            overall_bias=overall_bias,
            items_count=len(comparison_items),
            evaluated_at=now,
        )

    # --------------------------------------------------------------------------
    # Prompt 24 Item 7: Historical Trends
    # --------------------------------------------------------------------------

    def get_reconciliation_history_trend(
        self,
        *,
        tenant_context: TenantContext,
        provider: str | None = None,
        scope_id: str | None = None,
    ) -> ReconciliationHistorySummary:
        """Computes multi-period historical reconciliation variance trend."""
        reports = self._reconciliation_repo.get_history(
            tenant_context=tenant_context,
            provider=provider,
            scope_id=scope_id,
        )

        if not reports:
            return ReconciliationHistorySummary(
                tenant_id=tenant_context.tenant_id,
                provider=provider,
                scope_id=scope_id,
                reports=[],
                trend_direction="STABLE",
                average_absolute_variance=Decimal("0.00"),
                average_percentage_variance=Decimal("0.00"),
                total_periods_evaluated=0,
            )

        avg_abs = sum((r.absolute_variance for r in reports), Decimal("0.0")) / Decimal(
            len(reports)
        )
        avg_pct = sum((r.percentage_variance for r in reports), Decimal("0.0")) / Decimal(
            len(reports)
        )

        # Determine trend direction (comparing first half vs second half if multiple)
        if len(reports) >= 2:  # no-hardcode-allow: reason="Minimum sample size for half-split trend comparison", reviewer="Prompt-48-Audit"
            mid = len(reports) // 2
            first_half_avg = sum(
                (r.absolute_variance for r in reports[:mid]), Decimal("0.0")
            ) / Decimal(mid)
            second_half_avg = sum(
                (r.absolute_variance for r in reports[mid:]), Decimal("0.0")
            ) / Decimal(len(reports) - mid)
            if second_half_avg < first_half_avg * Decimal("0.90"):
                direction = "IMPROVING"
            elif second_half_avg > first_half_avg * Decimal("1.10"):
                direction = "DEGRADING"
            else:
                direction = "STABLE"
        else:
            direction = "STABLE"

        return ReconciliationHistorySummary(
            tenant_id=tenant_context.tenant_id,
            provider=provider,
            scope_id=scope_id,
            reports=reports,
            trend_direction=direction,
            average_absolute_variance=avg_abs.quantize(Decimal("0.01")),
            average_percentage_variance=avg_pct.quantize(Decimal("0.01")),
            total_periods_evaluated=len(reports),
        )

    # --------------------------------------------------------------------------
    # Prompt 24 Strict Negative Constraint Guard
    # --------------------------------------------------------------------------

    def adjust_cost_data_for_match(
        self,
        cost_fact_id: str,
        *,
        tenant_context: TenantContext,
    ) -> None:
        """Strictly forbidden operation per Prompt 24: 'Do not adjust ingested cost data to force a match.'"""
        self._reconciliation_repo.prevent_cost_adjustment(
            cost_fact_id, tenant_context=tenant_context
        )

    # --------------------------------------------------------------------------
    # Internal Classification and Helpers
    # --------------------------------------------------------------------------

    def _verify_period_finalisation(
        self,
        billing_period: str,
        tolerance: ProviderToleranceConfig,
        now: datetime,
    ) -> None:
        """Verifies that the period is closed and the provider's finalisation lag has elapsed."""
        try:
            year, month = map(int, billing_period.split("-"))
            _, last_day = calendar.monthrange(year, month)
            period_close = datetime(year, month, last_day, 23, 59, 59, tzinfo=UTC)
            finalisation_date = period_close + timedelta(days=tolerance.finalisation_lag_days)
            if now < finalisation_date:
                raise ReconciliationPeriodNotClosedException(
                    billing_period=billing_period,
                    provider=tolerance.provider,
                    finalisation_date=finalisation_date.strftime("%Y-%m-%d %H:%M:%S UTC"),
                )
        except ValueError as e:
            if isinstance(e, ReconciliationPeriodNotClosedException):
                raise
            # Invalid period format handled by model validation

    def _classify_variance(
        self,
        is_pass: bool,
        absolute_variance: Decimal,
        signed_variance: Decimal,
        request: RunReconciliationRequest,
        provider_facts: list[Any],
        tenant_context: TenantContext,
        tolerance: ProviderToleranceConfig,
    ) -> tuple[VarianceClassification, str | None]:
        """Deterministically classifies variance based on provider context and cost facts."""
        if is_pass:
            return (
                VarianceClassification.WITHIN_TOLERANCE,
                f"Variance is within provider tolerance of {tolerance.absolute_tolerance:.2f} {tolerance.currency} or {tolerance.percentage_tolerance:.2f}%.",
            )

        # Check in-flight data sync
        if request.is_sync_in_flight:
            return (
                VarianceClassification.DATA_FRESHNESS_GAP,
                "Delta billing sync is currently in flight or provider lag has not finalized.",
            )

        # Check missing scopes
        if request.unlinked_scopes:
            scopes_str = ", ".join(request.unlinked_scopes)
            return (
                VarianceClassification.MISSING_SCOPE,
                f"Provider authoritative invoice references unlinked or unregistered scopes: [{scopes_str}].",
            )

        # Check restatements for this period
        restatements = self._cost_repo.list_restatements(
            tenant_context=tenant_context, provider=request.provider
        )
        period_restatements = [
            r for r in restatements if r.billing_period == request.billing_period
        ]
        if period_restatements:
            total_delta = sum((r.billed_delta for r in period_restatements), Decimal("0.0"))
            if abs(absolute_variance - abs(total_delta)) <= tolerance.absolute_tolerance:
                return (
                    VarianceClassification.RESTATEMENT,
                    f"Variance aligns with retroactive provider restatement audit records ({len(period_restatements)} restatements detected).",
                )

        # Check unallocated credits
        if request.unallocated_credits > Decimal("0.0"):
            if abs(absolute_variance - request.unallocated_credits) <= tolerance.absolute_tolerance:
                return (
                    VarianceClassification.CREDIT,
                    f"Variance matches invoice-level credit of {request.unallocated_credits:.2f} {request.currency} not present in usage rows.",
                )

        # Check assessed taxes
        if request.assessed_taxes > Decimal("0.0"):
            if abs(absolute_variance - request.assessed_taxes) <= tolerance.absolute_tolerance:
                return (
                    VarianceClassification.TAX,
                    f"Variance matches invoice assessed jurisdictional tax of {request.assessed_taxes:.2f} {request.currency}.",
                )

        # Check unrecognised SKU/charges
        if request.unrecognised_charges > Decimal("0.0"):
            return (
                VarianceClassification.UNRECOGNISED_CHARGE,
                f"Provider invoice includes uncatalogued charges or SKU mismatches totaling {request.unrecognised_charges:.2f} {request.currency}.",
            )

        # Check pricing rate mismatch
        if request.rate_mismatch_amount > Decimal("0.0"):
            return (
                VarianceClassification.PRICING_MISMATCH,
                f"Rate card contract discrepancy detected totaling {request.rate_mismatch_amount:.2f} {request.currency}.",
            )

        # Check amortisation basis difference (upfront purchase fee vs spread)
        billed_sum = sum(
            (f.billed_cost.value for f in provider_facts if f.billed_cost.is_present),
            Decimal("0.0"),
        )
        effective_sum = sum(
            (f.effective_cost.value for f in provider_facts if f.effective_cost.is_present),
            Decimal("0.0"),
        )
        basis_delta = abs(billed_sum - effective_sum)
        if (
            basis_delta > Decimal("0.0")
            and abs(absolute_variance - basis_delta) <= tolerance.absolute_tolerance
        ):
            return (
                VarianceClassification.AMORTISATION_BASIS_DIFFERENCE,
                f"Variance is attributable to presentation basis difference (Billed vs Amortised delta of {basis_delta:.2f} {request.currency}).",
            )

        return (
            VarianceClassification.UNCLASSIFIED,
            f"Unclassified discrepancy of {signed_variance:+.2f} {request.currency} requires auditor investigation.",
        )

    def _compose_framing_statement(
        self,
        billing_period: str,
        provider: str,
        scope_id: str,
        platform_total: Decimal,
        provider_total: Decimal,
        signed_variance: Decimal,
        percentage_variance: Decimal,
        classification: VarianceClassification,
        currency: str,
    ) -> str:
        """Composes non-editorialised framing statement complying strictly with Prompt 24 Item 3."""
        return (
            f"Reconciliation comparison for billing period {billing_period} (Scope: {scope_id}, Provider: {provider.upper()}): "
            f"Platform normalised FOCUS total is {platform_total:.2f} {currency}; "
            f"Provider authoritative billed total is {provider_total:.2f} {currency}. "
            f"Reconciliation variance is {signed_variance:+.2f} {currency} ({percentage_variance:.2f}%). "
            f"Classification: {classification.value}. "
            f"Both figures are recorded objectively as reported without presumption of inaccuracy."
        )

    def _create_investigation_item(
        self,
        report_id: str,
        tenant_context: TenantContext,
        request: RunReconciliationRequest,
        platform_total: Decimal,
        provider_total: Decimal,
        variance_amount: Decimal,
        percentage_variance: Decimal,
        classification: VarianceClassification,
        now: datetime,
    ) -> ReconciliationInvestigationItem:
        """Constructs an investigation item for a failed reconciliation."""
        # Priority rules from master data bands
        bands = self._get_severity_bands(tenant_context.tenant_id)
        if percentage_variance >= bands["critical_pct"] or variance_amount >= bands["critical_amount"]:
            priority = InvestigationPriority.CRITICAL
        elif percentage_variance >= bands["high_pct"] or variance_amount >= bands["high_amount"]:
            priority = InvestigationPriority.HIGH
        else:
            priority = InvestigationPriority.MEDIUM

        item_id = f"inv-{tenant_context.tenant_id}-{uuid.uuid4().hex[:8]}"
        notes = (
            f"Automated investigation raised for {request.provider.upper()} in period {request.billing_period}. "
            f"Variance of {variance_amount:.2f} {request.currency} ({percentage_variance:.2f}%) exceeds configured tolerance. "
            f"Initial classification: {classification.value}."
        )

        return ReconciliationInvestigationItem(
            id=item_id,
            report_id=report_id,
            tenant_id=tenant_context.tenant_id,
            provider=request.provider,
            scope_id=request.scope_id,
            billing_period=request.billing_period,
            platform_total=platform_total.quantize(Decimal("0.01")),
            provider_total=provider_total.quantize(Decimal("0.01")),
            variance_amount=variance_amount.quantize(Decimal("0.01")),
            percentage_variance=percentage_variance,
            classification=classification,
            priority=priority,
            status=InvestigationStatus.OPEN,
            created_at=now,
            notes=notes,
        )


_GLOBAL_RECONCILIATION_ENGINE = CostReconciliationEngine()


def get_cost_reconciliation_engine() -> CostReconciliationEngine:
    """Dependency injection provider for CostReconciliationEngine."""
    return _GLOBAL_RECONCILIATION_ENGINE


def reset_cost_reconciliation_engine() -> CostReconciliationEngine:
    """Resets the CostReconciliationEngine singleton in-place."""
    _GLOBAL_RECONCILIATION_ENGINE._tolerances = dict(DEFAULT_PROVIDER_TOLERANCES)
    _GLOBAL_RECONCILIATION_ENGINE._reconciliation_repo = get_reconciliation_repository()
    _GLOBAL_RECONCILIATION_ENGINE._cost_repo = get_cost_repository()
    return _GLOBAL_RECONCILIATION_ENGINE


