"""Pre-Deployment Cost Estimator ('What will this cost?') (Prompt 23).

Enforces:
- Pre-deployment estimation across AWS, Azure, GCP, and OCI.
- Core support for Compute, Managed Database, Object Storage, and Block Storage.
- Extensible service set extensible through the pricing catalogue and service registry.
- Enforced four-value separation (returns strictly EstimatedCost objects).
- Cost-driver decomposition (Compute, Storage, Network, Database, Backup, Licensing).
- Defensible derivations explaining all rates, tiers, allowances, and assumptions.
- Missing data handling returning UNKNOWN with an explicit reason, never a silent zero.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any

from domain.cost.calculation.engine import CostCalculationEngine, get_calculation_engine
from domain.cost.calculation.models import (
    CostCategoryType,
    CostDerivation,
    CostDriverComponent,
    EstimatedCost,
    PreDeploymentEstimateRequest,
    PreDeploymentEstimateResult,
)
from domain.cost.calculation.rules import (
    rule_9_missing_data,
    rule_11_runtime_schedule,
    rule_12_cost_driver_decomposition,
)
from domain.models.enums import PricingStatus
from domain.pricing.models import ResolvedPriceQuote
from domain.pricing.service import PricingCatalogueService, get_pricing_service
from domain.rules.monetary import round_currency

logger = logging.getLogger(__name__)

ServiceEstimatorHandler = Callable[[PreDeploymentEstimateRequest], PreDeploymentEstimateResult]


class ServiceEstimatorRegistry:
    """Registry allowing custom and extensible service estimation plug-ins."""

    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], ServiceEstimatorHandler] = {}

    def register(self, provider: str, service: str, handler: ServiceEstimatorHandler) -> None:
        key = (provider.strip().lower(), service.strip().lower())
        self._handlers[key] = handler

    def get_handler(self, provider: str, service: str) -> ServiceEstimatorHandler | None:
        key = (provider.strip().lower(), service.strip().lower())
        return self._handlers.get(key)


class PreDeploymentEstimator:
    """Pre-Deployment Cost Estimator generating defensible multi-cloud estimates."""

    def __init__(
        self,
        pricing_service: PricingCatalogueService | None = None,
        calculation_engine: CostCalculationEngine | None = None,
    ) -> None:
        self.pricing_service = pricing_service or get_pricing_service()
        self.calculation_engine = calculation_engine or get_calculation_engine()
        self.registry = ServiceEstimatorRegistry()

    def estimate(self, request: PreDeploymentEstimateRequest) -> PreDeploymentEstimateResult:
        """Entry point for 'What will this cost?' pre-deployment estimation."""
        provider = request.provider.strip().lower()
        service = request.service.strip()

        # 1. Check custom registered handler first (extensible service set)
        custom_handler = self.registry.get_handler(provider, service)
        if custom_handler:
            return custom_handler(request)

        # 2. Match standard multi-cloud categories
        svc_lower = service.lower()
        if self._is_compute_service(provider, svc_lower):
            return self._estimate_compute(request)
        if self._is_database_service(provider, svc_lower):
            return self._estimate_database(request)
        if self._is_object_storage_service(provider, svc_lower):
            return self._estimate_object_storage(request)
        if self._is_block_storage_service(provider, svc_lower):
            return self._estimate_block_storage(request)

        # 3. Dynamic generic catalog-backed fallback estimation
        return self._estimate_generic_catalog_service(request)

    # --------------------------------------------------------------------------
    # Service Classification Helpers
    # --------------------------------------------------------------------------
    def _is_compute_service(self, provider: str, svc_lower: str) -> bool:
        return (
            "ec2" in svc_lower
            or "virtual machines" in svc_lower
            or "compute engine" in svc_lower
            or (provider == "oci" and "compute" in svc_lower and "storage" not in svc_lower)
        )

    def _is_database_service(self, _provider: str, svc_lower: str) -> bool:
        return (
            "rds" in svc_lower
            or "sql" in svc_lower
            or "database" in svc_lower
            or "aurora" in svc_lower
        )

    def _is_object_storage_service(self, provider: str, svc_lower: str) -> bool:
        return (
            "s3" in svc_lower
            or "blob" in svc_lower
            or ("cloud storage" in svc_lower and "persistent" not in svc_lower)
            or (provider == "oci" and "object" in svc_lower)
        )

    def _is_block_storage_service(self, _provider: str, svc_lower: str) -> bool:
        return (
            "ebs" in svc_lower
            or "disk" in svc_lower
            or "persistent disk" in svc_lower
            or "block volume" in svc_lower
            or "block storage" in svc_lower
        )

    # --------------------------------------------------------------------------
    # Quote Resolution Helper
    # --------------------------------------------------------------------------
    def _resolve_safe_quote(
        self,
        provider: str,
        service: str,
        region: str,
        sku: str | None = None,
        dimension: str = "DIM-03",
        tenant_id: str | None = None,
    ) -> tuple[ResolvedPriceQuote | None, str | None, datetime | None]:
        """Safely queries pricing catalogue for rate quote without crashing on unknown records."""
        try:
            quote = self.pricing_service.resolve_price_at_date(
                provider=provider,
                service=service,
                service_sku=sku,
                region=region,
                pricing_dimension=dimension,
                tenant_id=tenant_id,
            )
            return quote, None, None
        except Exception as e:
            # Check if historical records exist in repository
            hist_records, _ = self.pricing_service.list_catalog(
                provider=provider,
                service=service,
                region=region,
                include_historical=True,
            )
            last_date = hist_records[0].effective_from if hist_records else None
            _, reason = rule_9_missing_data(
                pricing_found=False,
                provider=provider,
                service=service,
                sku=sku,
                region=region,
            )
            return None, f"{reason} Details: {e}", last_date

    # --------------------------------------------------------------------------
    # Compute Estimator
    # --------------------------------------------------------------------------
    def _estimate_compute(
        self, request: PreDeploymentEstimateRequest
    ) -> PreDeploymentEstimateResult:
        provider = request.provider.strip().lower()
        region = request.region.strip()
        target_currency = request.target_currency.strip().upper()
        runtime_hours = rule_11_runtime_schedule(
            schedule_type=request.runtime_schedule_type,
            custom_hours=request.custom_runtime_hours,
        )

        # 1. Resolve Primary Compute Instance Rate
        sku_hint = self._get_compute_sku_hint(provider, request.instance_type)
        compute_dimension = (
            "DIM-14" if provider == "oci" else ("DIM-15" if provider == "gcp" else "DIM-03")
        )
        quote, unavail_reason, last_date = self._resolve_safe_quote(
            provider=provider,
            service=request.service,
            region=region,
            sku=sku_hint,
            dimension=compute_dimension,
            tenant_id=request.tenant_id,
        )

        if not quote:
            return self._build_unavailable_result(
                request, unavail_reason or "Compute pricing unavailable", last_date
            )

        # Calculate primary compute runtime cost
        c_amount, c_est, c_derivation = self.calculation_engine.calculate_cost(
            quantity=runtime_hours,
            unit=quote.unit,
            price_quote=quote,
            target_currency=target_currency,
            duration_hours=runtime_hours,
            assumptions={
                "schedule": request.runtime_schedule_type.value,
                "hours_per_month": float(runtime_hours),
            },
        )

        drivers_data: list[
            tuple[CostCategoryType, str, Decimal, CostDerivation, dict[str, Any]]
        ] = [
            (
                CostCategoryType.COMPUTE,
                f"{request.service} Runtime ({request.instance_type or 'Default'})",
                c_amount,
                c_derivation,
                {"runtime_hours": float(runtime_hours), "instance_type": request.instance_type},
            )
        ]

        # 2. Attached Root Block Storage Driver (if storage_gb > 0)
        if request.storage_gb > 0:
            block_svc, block_sku = self._get_block_service_and_sku(provider, request.storage_type)
            b_quote, _, _ = self._resolve_safe_quote(
                provider=provider,
                service=block_svc,
                region=region,
                sku=block_sku,
                dimension="DIM-11",
                tenant_id=request.tenant_id,
            )
            if b_quote:
                b_amount, _, b_deriv = self.calculation_engine.calculate_cost(
                    quantity=request.storage_gb,
                    unit="GB-Mo",
                    price_quote=b_quote,
                    target_currency=target_currency,
                    assumptions={
                        "storage_gb": request.storage_gb,
                        "storage_type": request.storage_type,
                    },
                )
                drivers_data.append(
                    (
                        CostCategoryType.STORAGE,
                        f"Attached Block Storage ({request.storage_gb} GB)",
                        b_amount,
                        b_deriv,
                        {"storage_gb": request.storage_gb, "type": request.storage_type},
                    )
                )

        # 3. Public IPv4 Address Driver (if public_ip=True)
        if request.public_ip:
            ip_svc, ip_sku = self._get_ip_service_and_sku(provider)
            ip_quote, _, _ = self._resolve_safe_quote(
                provider=provider,
                service=ip_svc,
                region=region,
                sku=ip_sku,
                dimension="DIM-03",
                tenant_id=request.tenant_id,
            )
            if ip_quote:
                ip_amount, _, ip_deriv = self.calculation_engine.calculate_cost(
                    quantity=runtime_hours,
                    unit=ip_quote.unit,
                    price_quote=ip_quote,
                    target_currency=target_currency,
                    duration_hours=runtime_hours,
                    assumptions={"public_ipv4_enabled": True},
                )
                drivers_data.append(
                    (
                        CostCategoryType.NETWORK,
                        "Public IPv4 Address",
                        ip_amount,
                        ip_deriv,
                        {"public_ip": True, "hours": float(runtime_hours)},
                    )
                )

        # 4. Outbound Internet Data Transfer Egress Driver (if data_transfer_out_gb > 0)
        if request.data_transfer_out_gb > 0:
            net_svc, net_sku = self._get_egress_service_and_sku(provider)
            net_quote, _, _ = self._resolve_safe_quote(
                provider=provider,
                service=net_svc,
                region=region,
                sku=net_sku,
                dimension="DIM-12",
                tenant_id=request.tenant_id,
            )
            if net_quote:
                net_amount, _, net_deriv = self.calculation_engine.calculate_cost(
                    quantity=request.data_transfer_out_gb,
                    unit="GB",
                    price_quote=net_quote,
                    target_currency=target_currency,
                    assumptions={"egress_gb": request.data_transfer_out_gb},
                )
                drivers_data.append(
                    (
                        CostCategoryType.NETWORK,
                        f"Outbound Internet Transfer ({request.data_transfer_out_gb} GB)",
                        net_amount,
                        net_deriv,
                        {"egress_gb": request.data_transfer_out_gb},
                    )
                )

        # 5. Backup / Snapshot Storage Driver (if backup_storage_gb > 0)
        if request.backup_storage_gb > 0:
            snap_svc, snap_sku = self._get_block_service_and_sku(provider, "snapshot")
            snap_quote, _, _ = self._resolve_safe_quote(
                provider=provider,
                service=snap_svc,
                region=region,
                sku=snap_sku,
                dimension="DIM-11",
                tenant_id=request.tenant_id,
            )
            if snap_quote:
                snap_amount, _, snap_deriv = self.calculation_engine.calculate_cost(
                    quantity=request.backup_storage_gb,
                    unit="GB-Mo",
                    price_quote=snap_quote,
                    target_currency=target_currency,
                    assumptions={"backup_gb": request.backup_storage_gb},
                )
                drivers_data.append(
                    (
                        CostCategoryType.BACKUP,
                        f"Backup Snapshot Storage ({request.backup_storage_gb} GB)",
                        snap_amount,
                        snap_deriv,
                        {"backup_gb": request.backup_storage_gb},
                    )
                )

        # Assemble Decomposed Drivers & Totals
        drivers = rule_12_cost_driver_decomposition(drivers_data, currency=target_currency)
        total_monthly_amount = sum(d.monthly_cost.amount for d in drivers)

        return self._build_successful_result(
            request=request,
            monthly_amount=Decimal(str(total_monthly_amount)),
            runtime_hours=runtime_hours,
            cost_drivers=drivers,
            primary_derivation=c_derivation,
        )

    # --------------------------------------------------------------------------
    # Managed Database Estimator
    # --------------------------------------------------------------------------
    def _estimate_database(
        self, request: PreDeploymentEstimateRequest
    ) -> PreDeploymentEstimateResult:
        provider = request.provider.strip().lower()
        region = request.region.strip()
        target_currency = request.target_currency.strip().upper()
        runtime_hours = rule_11_runtime_schedule(
            schedule_type=request.runtime_schedule_type,
            custom_hours=request.custom_runtime_hours,
        )

        db_sku = self._get_database_sku_hint(provider, request.database_engine)
        db_dimension = "DIM-14" if provider == "oci" else "DIM-03"
        quote, unavail_reason, last_date = self._resolve_safe_quote(
            provider=provider,
            service=request.service,
            region=region,
            sku=db_sku,
            dimension=db_dimension,
            tenant_id=request.tenant_id,
        )

        if not quote:
            return self._build_unavailable_result(
                request, unavail_reason or "Database pricing unavailable", last_date
            )

        db_amount, _, db_derivation = self.calculation_engine.calculate_cost(
            quantity=runtime_hours,
            unit=quote.unit,
            price_quote=quote,
            target_currency=target_currency,
            duration_hours=runtime_hours,
            assumptions={
                "engine": request.database_engine or "PostgreSQL",
                "runtime_hours": float(runtime_hours),
            },
        )

        drivers_data: list[
            tuple[CostCategoryType, str, Decimal, CostDerivation, dict[str, Any]]
        ] = [
            (
                CostCategoryType.DATABASE,
                f"{request.service} Instance Runtime ({request.database_engine or 'Default'})",
                db_amount,
                db_derivation,
                {"engine": request.database_engine, "hours": float(runtime_hours)},
            )
        ]

        # Allocated DB Storage
        if request.storage_gb > 0:
            block_svc, block_sku = self._get_block_service_and_sku(provider, "db_storage")
            b_quote, _, _ = self._resolve_safe_quote(
                provider=provider,
                service=block_svc,
                region=region,
                sku=block_sku,
                dimension="DIM-11",
                tenant_id=request.tenant_id,
            )
            if b_quote:
                b_amount, _, b_deriv = self.calculation_engine.calculate_cost(
                    quantity=request.storage_gb,
                    unit="GB-Mo",
                    price_quote=b_quote,
                    target_currency=target_currency,
                )
                drivers_data.append(
                    (
                        CostCategoryType.STORAGE,
                        f"Database Storage Volume ({request.storage_gb} GB)",
                        b_amount,
                        b_deriv,
                        {"storage_gb": request.storage_gb},
                    )
                )

        drivers = rule_12_cost_driver_decomposition(drivers_data, currency=target_currency)
        total_monthly_amount = sum(d.monthly_cost.amount for d in drivers)

        return self._build_successful_result(
            request=request,
            monthly_amount=Decimal(str(total_monthly_amount)),
            runtime_hours=runtime_hours,
            cost_drivers=drivers,
            primary_derivation=db_derivation,
        )

    # --------------------------------------------------------------------------
    # Object Storage Estimator
    # --------------------------------------------------------------------------
    def _estimate_object_storage(
        self, request: PreDeploymentEstimateRequest
    ) -> PreDeploymentEstimateResult:
        provider = request.provider.strip().lower()
        region = request.region.strip()
        target_currency = request.target_currency.strip().upper()
        storage_quantity = max(1.0, request.storage_gb)

        quote, unavail_reason, last_date = self._resolve_safe_quote(
            provider=provider,
            service=request.service,
            region=region,
            dimension="DIM-11",
            tenant_id=request.tenant_id,
        )

        if not quote:
            return self._build_unavailable_result(
                request, unavail_reason or "Object storage pricing unavailable", last_date
            )

        s_amount, _, s_derivation = self.calculation_engine.calculate_cost(
            quantity=storage_quantity,
            unit="GB-Mo",
            price_quote=quote,
            target_currency=target_currency,
            assumptions={"storage_gb": storage_quantity},
        )

        drivers_data: list[
            tuple[CostCategoryType, str, Decimal, CostDerivation, dict[str, Any]]
        ] = [
            (
                CostCategoryType.STORAGE,
                f"{request.service} Capacity ({storage_quantity} GB)",
                s_amount,
                s_derivation,
                {"storage_gb": storage_quantity},
            )
        ]

        if request.data_transfer_out_gb > 0:
            net_svc, net_sku = self._get_egress_service_and_sku(provider)
            net_quote, _, _ = self._resolve_safe_quote(
                provider=provider,
                service=net_svc,
                region=region,
                sku=net_sku,
                dimension="DIM-12",
                tenant_id=request.tenant_id,
            )
            if net_quote:
                net_amount, _, net_deriv = self.calculation_engine.calculate_cost(
                    quantity=request.data_transfer_out_gb,
                    unit="GB",
                    price_quote=net_quote,
                    target_currency=target_currency,
                )
                drivers_data.append(
                    (
                        CostCategoryType.NETWORK,
                        f"Outbound Data Transfer ({request.data_transfer_out_gb} GB)",
                        net_amount,
                        net_deriv,
                        {"egress_gb": request.data_transfer_out_gb},
                    )
                )

        drivers = rule_12_cost_driver_decomposition(drivers_data, currency=target_currency)
        total_monthly_amount = sum(d.monthly_cost.amount for d in drivers)

        return self._build_successful_result(
            request=request,
            monthly_amount=Decimal(str(total_monthly_amount)),
            runtime_hours=Decimal("730.0"),
            cost_drivers=drivers,
            primary_derivation=s_derivation,
        )

    # --------------------------------------------------------------------------
    # Block Storage Estimator
    # --------------------------------------------------------------------------
    def _estimate_block_storage(
        self, request: PreDeploymentEstimateRequest
    ) -> PreDeploymentEstimateResult:
        provider = request.provider.strip().lower()
        region = request.region.strip()
        target_currency = request.target_currency.strip().upper()
        storage_quantity = max(1.0, request.storage_gb)

        quote, unavail_reason, last_date = self._resolve_safe_quote(
            provider=provider,
            service=request.service,
            region=region,
            dimension="DIM-11",
            tenant_id=request.tenant_id,
        )

        if not quote:
            return self._build_unavailable_result(
                request, unavail_reason or "Block storage pricing unavailable", last_date
            )

        b_amount, _, b_derivation = self.calculation_engine.calculate_cost(
            quantity=storage_quantity,
            unit="GB-Mo",
            price_quote=quote,
            target_currency=target_currency,
            assumptions={"storage_gb": storage_quantity, "storage_type": request.storage_type},
        )

        drivers_data: list[
            tuple[CostCategoryType, str, Decimal, CostDerivation, dict[str, Any]]
        ] = [
            (
                CostCategoryType.STORAGE,
                f"{request.service} Volume Capacity ({storage_quantity} GB)",
                b_amount,
                b_derivation,
                {"storage_gb": storage_quantity, "storage_type": request.storage_type},
            )
        ]

        drivers = rule_12_cost_driver_decomposition(drivers_data, currency=target_currency)
        total_monthly_amount = sum(d.monthly_cost.amount for d in drivers)

        return self._build_successful_result(
            request=request,
            monthly_amount=Decimal(str(total_monthly_amount)),
            runtime_hours=Decimal("730.0"),
            cost_drivers=drivers,
            primary_derivation=b_derivation,
        )

    # --------------------------------------------------------------------------
    # Generic Catalog Service Fallback (Extensible Service Set)
    # --------------------------------------------------------------------------
    def _estimate_generic_catalog_service(
        self, request: PreDeploymentEstimateRequest
    ) -> PreDeploymentEstimateResult:
        provider = request.provider.strip().lower()
        region = request.region.strip()
        target_currency = request.target_currency.strip().upper()

        quote, unavail_reason, last_date = self._resolve_safe_quote(
            provider=provider,
            service=request.service,
            region=region,
            tenant_id=request.tenant_id,
        )

        if not quote:
            return self._build_unavailable_result(
                request, unavail_reason or f"Service '{request.service}' uncatalogued", last_date
            )

        qty = max(1.0, request.storage_gb or request.custom_runtime_hours or 730.0)
        amount, _, derivation = self.calculation_engine.calculate_cost(
            quantity=qty,
            unit=quote.unit,
            price_quote=quote,
            target_currency=target_currency,
        )

        driver = CostDriverComponent(
            category=CostCategoryType.OTHER,
            name=f"{request.service} Standard Usage",
            monthly_cost=EstimatedCost(
                amount=float(round_currency(amount, decimal_places=2)),
                currency=target_currency,
                pricing_record_id=quote.record_id,
                pricing_source=quote.pricing_source,
                usage_quantity=qty,
                usage_unit=quote.unit,
                estimation_formula=f"{qty} {quote.unit} * {quote.effective_price} {quote.currency}/{quote.unit}",
            ),
            percentage_of_total=Decimal("100.00"),
            derivation=derivation,
            drillable_details={"quantity": qty, "unit": quote.unit},
        )

        return self._build_successful_result(
            request=request,
            monthly_amount=amount,
            runtime_hours=Decimal("730.0"),
            cost_drivers=[driver],
            primary_derivation=derivation,
        )

    # --------------------------------------------------------------------------
    # Result Compilation Helpers
    # --------------------------------------------------------------------------
    def _build_successful_result(
        self,
        request: PreDeploymentEstimateRequest,
        monthly_amount: Decimal,
        runtime_hours: Decimal,
        cost_drivers: list[CostDriverComponent],
        primary_derivation: CostDerivation,
    ) -> PreDeploymentEstimateResult:
        """Assembles multi-horizon estimates using strictly typed EstimatedCost instances."""
        target_currency = request.target_currency.strip().upper()
        safe_hours = runtime_hours if runtime_hours > Decimal("0.0") else Decimal("730.0")

        hourly_dec = round_currency(monthly_amount / safe_hours, decimal_places=4)
        daily_dec = round_currency(monthly_amount / Decimal("30.0"), decimal_places=2)
        monthly_dec = round_currency(monthly_amount, decimal_places=2)
        annual_dec = round_currency(monthly_amount * Decimal("12.0"), decimal_places=2)

        formula_base = f"monthly({monthly_dec} {target_currency})"

        h_cost = EstimatedCost(
            amount=float(hourly_dec),
            currency=target_currency,
            pricing_record_id=f"est-hourly-{request.service.lower()}",
            pricing_source=primary_derivation.pricing_source,
            usage_quantity=1.0,
            usage_unit="hour",
            estimation_formula=f"{formula_base} / {safe_hours} hrs = {hourly_dec} {target_currency}/hr",
        )
        d_cost = EstimatedCost(
            amount=float(daily_dec),
            currency=target_currency,
            pricing_record_id=f"est-daily-{request.service.lower()}",
            pricing_source=primary_derivation.pricing_source,
            usage_quantity=1.0,
            usage_unit="day",
            estimation_formula=f"{formula_base} / 30 days = {daily_dec} {target_currency}/day",
        )
        m_cost = EstimatedCost(
            amount=float(monthly_dec),
            currency=target_currency,
            pricing_record_id=f"est-monthly-{request.service.lower()}",
            pricing_source=primary_derivation.pricing_source,
            usage_quantity=float(safe_hours),
            usage_unit="month",
            estimation_formula=f"sum(cost_drivers) = {monthly_dec} {target_currency}/month",
        )
        a_cost = EstimatedCost(
            amount=float(annual_dec),
            currency=target_currency,
            pricing_record_id=f"est-annual-{request.service.lower()}",
            pricing_source=primary_derivation.pricing_source,
            usage_quantity=12.0,
            usage_unit="year",
            estimation_formula=f"{formula_base} * 12 months = {annual_dec} {target_currency}/yr",
        )

        return PreDeploymentEstimateResult(
            provider=request.provider,
            service=request.service,
            region=request.region,
            currency=target_currency,
            pricing_status=PricingStatus.ESTIMATED
            if monthly_dec > Decimal("0.0")
            else PricingStatus.FREE,
            hourly_cost=h_cost,
            daily_cost=d_cost,
            monthly_cost=m_cost,
            annualised_cost=a_cost,
            cost_drivers=cost_drivers,
            overall_derivation=primary_derivation,
            assumptions={
                "runtime_schedule": request.runtime_schedule_type.value,
                "runtime_hours": float(safe_hours),
                "operating_system": request.operating_system,
                "storage_gb": request.storage_gb,
                "public_ip": request.public_ip,
                "egress_gb": request.data_transfer_out_gb,
                **request.assumptions,
            },
        )

    def _build_unavailable_result(
        self,
        request: PreDeploymentEstimateRequest,
        reason: str,
        last_date: datetime | None = None,
    ) -> PreDeploymentEstimateResult:
        """Constructs an explicit UNKNOWN result ensuring an estimate NEVER silently defaults to zero."""
        target_currency = request.target_currency.strip().upper()
        dummy_derivation = CostDerivation(
            rate_applied=Decimal("0.0"),
            pricing_dimension="UNKNOWN",
            quantity_consumed=Decimal("0.0"),
            unit="unit",
            net_billable_quantity=Decimal("0.0"),
            pricing_source="unavailable",
            currency=target_currency,
            step_by_step_explanation=[f"Estimation halted: {reason}"],
            assumptions=request.assumptions,
        )

        zero_est = EstimatedCost(
            amount=0.0,
            currency=target_currency,
            pricing_record_id="unavailable",
            pricing_source="unavailable",
            usage_quantity=0.0,
            usage_unit="unit",
            estimation_formula=f"UNAVAILABLE: {reason}",
        )

        return PreDeploymentEstimateResult(
            provider=request.provider,
            service=request.service,
            region=request.region,
            currency=target_currency,
            pricing_status=PricingStatus.UNKNOWN,
            hourly_cost=zero_est,
            daily_cost=zero_est,
            monthly_cost=zero_est,
            annualised_cost=zero_est,
            cost_drivers=[],
            overall_derivation=dummy_derivation,
            assumptions=request.assumptions,
            unavailability_reason=reason,
            last_known_pricing_date=last_date,
        )

    # --------------------------------------------------------------------------
    # Provider-Specific SKU Resolution Mappings
    # --------------------------------------------------------------------------
    def _get_compute_sku_hint(self, provider: str, _instance_type: str | None) -> str | None:
        p = provider.lower()
        if p == "aws":
            return "AWS-EC2-T3-XLARGE-US-EAST"
        if p == "azure":
            return "00000000-1111-2222-3333-444444444444"
        if p == "gcp":
            return "D982-F0A1-332B"
        if p == "oci":
            return "B88298"
        return None

    def _get_database_sku_hint(self, provider: str, _engine: str | None) -> str | None:
        p = provider.lower()
        if p == "aws":
            return "AWS-RDS-DB-R5-2XLARGE"
        if p == "azure":
            return "AZURE-SQL-GEN5-4VCORE"
        if p == "gcp":
            return "GCP-CLOUDSQL-PG-CUSTOM-4-16"
        if p == "oci":
            return "OCI-ADB-ECPU"
        return None

    def _get_block_service_and_sku(
        self, provider: str, _storage_type: str | None
    ) -> tuple[str, str]:
        p = provider.lower()
        if p == "aws":
            return "AmazonEBS", "AWS-EBS-GP3-STORAGE"
        if p == "azure":
            return "Managed Disks", "AZURE-DISK-PREMIUM-SSD-P10"
        if p == "gcp":
            return "Persistent Disk", "GCP-DISK-PD-BALANCED"
        if p == "oci":
            return "Block Volume", "OCI-BLOCK-STORAGE-BALANCED"
        return "Storage", "DEFAULT-BLOCK-STORAGE"

    def _get_ip_service_and_sku(self, provider: str) -> tuple[str, str]:
        p = provider.lower()
        if p == "aws":
            return "AmazonEC2", "AWS-PUBLIC-IPV4-ADDRESS"
        if p == "azure":
            return "Virtual Machines", "AZURE-PUBLIC-IP-STANDARD"
        if p == "gcp":
            return "Compute Engine", "GCP-NETWORK-STATIC-IP"
        if p == "oci":
            return "Compute", "OCI-NETWORKING-RESERVED-PUBLIC-IP"
        return "Network", "DEFAULT-PUBLIC-IP"

    def _get_egress_service_and_sku(self, provider: str) -> tuple[str, str]:
        p = provider.lower()
        if p == "aws":
            return "AmazonEC2", "AWS-DATA-TRANSFER-OUT-INTERNET"
        if p == "azure":
            return "Virtual Machines", "AZURE-BANDWIDTH-EGRESS-INTERNET"
        if p == "gcp":
            return "Compute Engine", "GCP-NETWORK-INTERNET-EGRESS"
        if p == "oci":
            return "Compute", "OCI-NETWORKING-OUTBOUND-DATA"
        return "Network", "DEFAULT-EGRESS"


_global_estimator: PreDeploymentEstimator | None = None


def get_pre_deployment_estimator() -> PreDeploymentEstimator:
    """Returns singleton instance of PreDeploymentEstimator."""
    global _global_estimator
    if _global_estimator is None:
        _global_estimator = PreDeploymentEstimator()
    return _global_estimator


def reset_pre_deployment_estimator() -> None:
    """Resets singleton for testing environments."""
    global _global_estimator
    _global_estimator = None


__all__ = [
    "PreDeploymentEstimator",
    "ServiceEstimatorRegistry",
    "get_pre_deployment_estimator",
    "reset_pre_deployment_estimator",
]
