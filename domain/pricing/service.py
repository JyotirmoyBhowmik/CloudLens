"""Pricing Catalogue Service (Prompt 20 / Track E).

Enforces:
- Centralised multi-cloud pricing catalogue management.
- Slowly Changing Dimension (SCD Type 2) point-in-time rate resolution.
- Contracted rate precedence: Where negotiated/contracted rate exists, list rate is
  NEVER presented as the organisation's rate, but both are retained for discount realization.
- Rate change detection and signal dispatching.
- Unknown-SKU on-demand fetching and gap tracking without failing ingestion.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from domain.models.exceptions import PricingRecordNotFoundException
from domain.pricing.models import (
    DiscountInfo,
    PricingChangeRecord,
    PricingRecord,
    RateType,
    ResolvedPriceQuote,
    UnknownSkuRecord,
)
from domain.pricing.repository import PricingRepository, get_pricing_repository

logger = logging.getLogger(__name__)

PricingChangeListener = Callable[[PricingChangeRecord], None]


class PricingCatalogueService:
    """Enterprise Pricing Catalogue Service providing point-in-time historical rate resolution."""

    def __init__(
        self,
        repository: PricingRepository | None = None,
        enable_connector_lookups: bool = True,
    ) -> None:
        self.repository = repository or get_pricing_repository()
        self.enable_connector_lookups = enable_connector_lookups
        self._change_listeners: list[PricingChangeListener] = []

    def register_change_listener(self, listener: PricingChangeListener) -> None:
        """Subscribes an event listener to be notified on rate changes (Pricing Change Signal)."""
        self._change_listeners.append(listener)

    def ingest_price_record(
        self, record: PricingRecord
    ) -> tuple[PricingRecord, PricingChangeRecord | None]:
        """Ingests a pricing record following SCD Type 2 semantics.

        If a rate change is detected:
        - Closes superseded record and versions new record.
        - Generates a PricingChangeRecord.
        - Emits Pricing Change Signal to all registered listeners.
        - Automatically resolves any matching open UnknownSkuRecord.
        """
        stored_record, change_record = self.repository.add_or_update(record)

        if change_record:
            self._emit_pricing_change_signal(change_record)

        # Mark unknown SKU gap as resolved if previously pending
        if record.service_sku:
            self.repository.mark_unknown_sku_resolved(
                provider=record.provider,
                service_sku=record.service_sku,
                resolved_pricing_id=stored_record.id,
                tenant_id=record.tenant_id,
                notes=f"Resolved via ingestion of PricingRecord {stored_record.id}",
            )

        return stored_record, change_record

    def _emit_pricing_change_signal(self, change: PricingChangeRecord) -> None:
        """Dispatches Pricing Change signal to listeners and writes structured audit logs."""
        logger.info(
            "PRICING_CHANGE_SIGNAL: Provider=%s SKU=%s OldPrice=%.4f NewPrice=%.4f Diff=%+.2f%% Effective=%s",
            change.provider,
            change.service_sku,
            change.old_unit_price,
            change.new_unit_price,
            change.percentage_change,
            change.effective_from.isoformat(),
            extra={
                "event_type": "pricing_change_signal",
                "change_id": change.id,
                "provider": change.provider,
                "sku": change.service_sku,
                "old_price": change.old_unit_price,
                "new_price": change.new_unit_price,
                "percentage_change": change.percentage_change,
            },
        )
        for listener in self._change_listeners:
            try:
                listener(change)
            except Exception as e:
                logger.error("Error executing pricing change listener: %s", e, exc_info=True)

    def resolve_price_at_date(
        self,
        provider: str,
        region: str,
        pricing_dimension: str = "DIM-03",
        query_date: datetime | None = None,
        service_sku: str | None = None,
        service: str | None = None,
        tenant_id: str | None = None,
        prefer_contracted: bool = True,
    ) -> ResolvedPriceQuote:
        """Evaluates point-in-time effective price for an organisation on query_date.

        Precedence Rules:
        - Historical accuracy: Evaluates exact rate effective on query_date (SCD Type 2).
        - Precedence: Where a contracted rate exists, list rate is NEVER presented as
          the organisation's rate, but both are retained so realized discount is tracked.
        - Fallback: If no records match, attempts an on-demand connector fetch before raising
          PricingRecordNotFoundException.
        """
        target_date = (
            query_date
            if query_date and query_date.tzinfo
            else (query_date.replace(tzinfo=UTC) if query_date else datetime.now(UTC))
        )

        # 1. Search for records effective on query_date
        records = self.repository.find_at_date(
            provider=provider,
            sku=service_sku,
            region=region,
            dimension=pricing_dimension,
            query_date=target_date,
            tenant_id=tenant_id,
            service=service,
        )

        # 2. If nothing found and SKU is provided, trigger on-demand unknown SKU fetch
        if not records and service_sku and self.enable_connector_lookups:
            fetched = self.handle_unknown_sku(
                provider=provider,
                sku=service_sku,
                service_hint=service,
                region_hint=region,
                tenant_id=tenant_id,
            )
            if fetched:
                records = self.repository.find_at_date(
                    provider=provider,
                    sku=service_sku,
                    region=region,
                    dimension=pricing_dimension,
                    query_date=target_date,
                    tenant_id=tenant_id,
                    service=service,
                )

        if not records:
            raise PricingRecordNotFoundException(
                provider=provider,
                sku=service_sku or service or "unknown",
                region=region,
                date_str=target_date.isoformat(),
            )

        # 3. Categorize records by rate_type
        contracted_record = next((r for r in records if r.rate_type == RateType.CONTRACTED), None)
        list_record = next((r for r in records if r.rate_type == RateType.LIST), None)

        if contracted_record is None and list_record is None:
            # Fallback to the first available record
            selected_rec = records[0]
            list_price = selected_rec.unit_price
            effective_price = selected_rec.unit_price
            applied_rate_type = selected_rec.rate_type
            is_contracted = applied_rate_type == RateType.CONTRACTED
            discount_amount = 0.0
            discount_pct = 0.0
        elif prefer_contracted and contracted_record is not None:
            # Contracted Precedence Applied
            selected_rec = contracted_record
            effective_price = contracted_record.unit_price
            list_price = list_record.unit_price if list_record else contracted_record.unit_price
            applied_rate_type = RateType.CONTRACTED
            is_contracted = True
            discount_amount = round(max(0.0, list_price - effective_price), 6)
            discount_pct = (
                round((discount_amount / list_price) * 100.0, 4) if list_price > 0 else 0.0
            )
        else:
            # List Rate Applied
            selected_rec = list_record if list_record else records[0]
            effective_price = selected_rec.unit_price
            list_price = selected_rec.unit_price
            applied_rate_type = RateType.LIST
            is_contracted = False
            discount_amount = 0.0
            discount_pct = 0.0

        return ResolvedPriceQuote(
            provider=selected_rec.provider,
            service=selected_rec.service,
            service_sku=selected_rec.service_sku,
            region=selected_rec.region,
            pricing_dimension=selected_rec.pricing_dimension,
            query_date=target_date,
            effective_price=effective_price,
            list_price=list_price,
            rate_type_applied=applied_rate_type,
            realized_discount_amount=discount_amount,
            realized_discount_percent=discount_pct,
            currency=selected_rec.currency,
            unit=selected_rec.unit,
            tier=selected_rec.tier,
            free_allowance=selected_rec.free_allowance,
            minimum_charge=selected_rec.minimum_charge,
            record_id=selected_rec.id,
            record_version=selected_rec.version,
            pricing_source=selected_rec.source,
            is_contracted_precedence_applied=is_contracted,
        )

    def handle_unknown_sku(
        self,
        provider: str,
        sku: str,
        raw_payload: dict[str, Any] | None = None,
        service_hint: str | None = None,
        region_hint: str | None = None,
        tenant_id: str | None = None,
    ) -> PricingRecord | None:
        """Handles an unrecognised SKU encountered during cost or usage ingestion.

        1. Attempts an on-demand pricing lookup via the appropriate provider pricing service.
        2. If resolved, ingests the rate as an effective-dated record and returns it.
        3. If unresolved, records an UnknownSkuRecord gap report and returns None
           without failing the caller's ingestion pipeline.
        """
        p = provider.strip().lower()
        now = datetime.now(UTC)

        # Attempt on-demand lookup against provider connectors
        resolved_record: PricingRecord | None = None

        try:
            if p == "aws":
                from connectors.aws.pricing import AWSPricingService

                aws_svc = AWSPricingService(management_account_id="on-demand")
                aws_quote = aws_svc.get_effective_quote(sku)
                if aws_quote:
                    # Ingest public retail rate
                    retail_rec = PricingRecord(
                        provider="aws",
                        service=aws_quote.service_code,
                        service_sku=aws_quote.sku,
                        resource_type="compute_instance"
                        if "EC2" in aws_quote.service_code
                        else "cloud_resource",
                        region=region_hint or aws_quote.attributes.get("location", "us-east-1"),
                        pricing_dimension="DIM-03" if aws_quote.pricing_unit == "Hrs" else "DIM-11",
                        unit=aws_quote.pricing_unit,
                        unit_price=aws_quote.retail_price,
                        currency=aws_quote.currency,
                        effective_from=now,
                        source="aws_on_demand_lookup",
                        attributes=aws_quote.attributes,
                    )
                    self.repository.add_or_update(retail_rec)

                    # Ingest negotiated rate if present
                    if aws_quote.negotiated_price is not None:
                        neg_rec = PricingRecord(
                            tenant_id=tenant_id,
                            provider="aws",
                            service=aws_quote.service_code,
                            service_sku=aws_quote.sku,
                            resource_type="compute_instance"
                            if "EC2" in aws_quote.service_code
                            else "cloud_resource",
                            region=region_hint or aws_quote.attributes.get("location", "us-east-1"),
                            pricing_dimension="DIM-03"
                            if aws_quote.pricing_unit == "Hrs"
                            else "DIM-11",
                            unit=aws_quote.pricing_unit,
                            unit_price=aws_quote.negotiated_price,
                            currency=aws_quote.currency,
                            effective_from=now,
                            rate_type=RateType.CONTRACTED,
                            source="aws_edp_on_demand",
                            discount_info=DiscountInfo(
                                discount_type="PERCENTAGE",
                                discount_percentage=round(
                                    (
                                        (aws_quote.retail_price - aws_quote.negotiated_price)
                                        / aws_quote.retail_price
                                    )
                                    * 100.0,
                                    2,
                                ),
                            ),
                        )
                        resolved_record, _ = self.repository.add_or_update(neg_rec)
                    else:
                        resolved_record = retail_rec

            elif p == "azure":
                from connectors.azure.pricing import AzurePricingService

                az_svc = AzurePricingService(tenant_id=tenant_id or "on-demand")
                az_quote = az_svc.get_effective_quote(sku)
                if az_quote:
                    rec = PricingRecord(
                        tenant_id=tenant_id if az_quote.is_negotiated else None,
                        provider="azure",
                        service=az_quote.service_name,
                        service_sku=az_quote.meter_id,
                        resource_type="cloud_resource",
                        region=region_hint or "eastus",
                        pricing_dimension="DIM-03",
                        unit="1 Hour",
                        unit_price=az_quote.effective_price,
                        currency=az_quote.effective_currency,
                        effective_from=now,
                        rate_type=RateType.CONTRACTED if az_quote.is_negotiated else RateType.LIST,
                        source="azure_on_demand_lookup",
                    )
                    resolved_record, _ = self.repository.add_or_update(rec)

            elif p == "gcp":
                from connectors.gcp.pricing import GCPPricingService

                gcp_svc = GCPPricingService(billing_account_id="on-demand")
                gcp_quote = gcp_svc.get_effective_quote(sku)
                if gcp_quote:
                    rec = PricingRecord(
                        tenant_id=tenant_id if gcp_quote.is_contract_rate else None,
                        provider="gcp",
                        service=gcp_quote.service_name,
                        service_sku=gcp_quote.sku_id,
                        resource_type="cloud_resource",
                        region=region_hint or "us-central1",
                        pricing_dimension="DIM-15",
                        unit="h",
                        unit_price=gcp_quote.effective_price,
                        currency=gcp_quote.currency,
                        effective_from=now,
                        rate_type=RateType.CONTRACTED
                        if gcp_quote.is_contract_rate
                        else RateType.LIST,
                        source="gcp_on_demand_lookup",
                    )
                    resolved_record, _ = self.repository.add_or_update(rec)

            elif p == "oci":
                from connectors.oci.pricing import OCIPricingService

                oci_svc = OCIPricingService(tenancy_id="on-demand")
                oci_quote = oci_svc.get_effective_quote(sku)
                if oci_quote:
                    rec = PricingRecord(
                        tenant_id=tenant_id if oci_quote.is_contract_rate else None,
                        provider="oci",
                        service=oci_quote.service,
                        service_sku=oci_quote.part_number,
                        resource_type="cloud_resource",
                        region=region_hint or "us-ashburn-1",
                        pricing_dimension="DIM-14",
                        unit=oci_quote.metric_unit,
                        unit_price=oci_quote.effective_price,
                        currency=oci_quote.currency,
                        effective_from=now,
                        rate_type=RateType.CONTRACTED
                        if oci_quote.is_contract_rate
                        else RateType.LIST,
                        source="oci_on_demand_lookup",
                    )
                    resolved_record, _ = self.repository.add_or_update(rec)

        except Exception as e:
            logger.warning(
                "On-demand pricing lookup encountered an error for %s SKU %s: %s",
                provider,
                sku,
                e,
                exc_info=True,
            )

        if resolved_record:
            logger.info("Successfully resolved unknown SKU %s on-demand from %s.", sku, provider)
            return resolved_record

        # Unresolved: record in unknown SKU gap registry without crashing ingestion
        gap_record = self.repository.record_unknown_sku(
            provider=provider,
            service_sku=sku,
            raw_payload=raw_payload,
            service_hint=service_hint,
            region_hint=region_hint,
            tenant_id=tenant_id,
        )
        logger.warning(
            "UNKNOWN_SKU_RECORDED: provider=%s sku=%s occurrences=%d (Ingestion continues uninterrupted)",
            provider,
            sku,
            gap_record.occurrence_count,
        )
        return None

    def list_catalog(
        self,
        provider: str | None = None,
        service: str | None = None,
        sku: str | None = None,
        region: str | None = None,
        dimension: str | None = None,
        rate_type: RateType | None = None,
        effective_date: datetime | None = None,
        include_historical: bool = False,
        tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[PricingRecord], int]:
        """Queries the catalogue with dimensional filters and effective dates."""
        return self.repository.list_catalog(
            provider=provider,
            service=service,
            sku=sku,
            region=region,
            dimension=dimension,
            rate_type=rate_type,
            effective_date=effective_date,
            include_historical=include_historical,
            tenant_id=tenant_id,
            page=page,
            page_size=page_size,
        )

    def list_pricing_changes(
        self,
        provider: str | None = None,
        sku: str | None = None,
        since: datetime | None = None,
    ) -> list[PricingChangeRecord]:
        """Lists detected rate change variance records."""
        return self.repository.list_changes(provider=provider, sku=sku, since=since)

    def list_unknown_skus(
        self,
        provider: str | None = None,
        status: str | None = None,
    ) -> list[UnknownSkuRecord]:
        """Lists unmapped SKU gap items."""
        return self.repository.list_unknown_skus(provider=provider, status=status)


_global_pricing_service: PricingCatalogueService | None = None


def get_pricing_service() -> PricingCatalogueService:
    """Returns singleton instance of PricingCatalogueService."""
    global _global_pricing_service
    if _global_pricing_service is None:
        _global_pricing_service = PricingCatalogueService()
    return _global_pricing_service


def reset_pricing_service() -> None:
    """Resets singleton for testing environments."""
    global _global_pricing_service
    _global_pricing_service = None
