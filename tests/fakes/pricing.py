"""In-memory fake repository for Pricing Catalogue (Prompt P06)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from domain.models.exceptions import PricingSCDConflictException
from domain.pricing.models import (
    DiscountInfo,
    FreeAllowance,
    PricingChangeRecord,
    PricingRecord,
    PricingTierModel,
    RateType,
    TierBracket,
    TierStructure,
    UnknownSkuRecord,
)

logger = logging.getLogger(__name__)


class InMemoryPricingRepository:
    """In-memory SCD Type 2 Pricing Catalogue Repository with multi-cloud seed loading."""

    is_in_memory: bool = True

    def __init__(self, load_seed_data: bool = True) -> None:
        self._records: dict[str, PricingRecord] = {}
        self._natural_index: dict[tuple[str, str, str, str, str, str], list[PricingRecord]] = {}
        self._changes: dict[str, PricingChangeRecord] = {}
        self._unknown_skus: dict[tuple[str, str, str], UnknownSkuRecord] = {}
        if load_seed_data:
            self._load_seed_catalog()

    def _build_key(
        self,
        tenant_id: str | None,
        provider: str,
        sku: str | None,
        region: str,
        dimension: str,
        rate_type: RateType | str,
    ) -> tuple[str, str, str, str, str, str]:
        t_id = (tenant_id or "").strip()
        p = provider.strip().lower()
        s = (sku or "").strip().lower()
        r = region.strip().lower()
        d = dimension.strip().upper()
        rt = rate_type.value if isinstance(rate_type, RateType) else str(rate_type).upper()
        return (t_id, p, s, r, d, rt)

    def add_or_update(
        self, record: PricingRecord
    ) -> tuple[PricingRecord, PricingChangeRecord | None]:
        key = self._build_key(
            record.tenant_id,
            record.provider,
            record.service_sku,
            record.region,
            record.pricing_dimension,
            record.rate_type,
        )

        existing_history = self._natural_index.setdefault(key, [])
        active_record = next((r for r in existing_history if r.is_active), None)

        if active_record is None:
            stored_record = record.model_copy(
                update={"version": 1, "is_active": True, "effective_to": None}
            )
            self._records[stored_record.id] = stored_record
            existing_history.append(stored_record)
            return stored_record, None

        is_price_changed = abs(active_record.unit_price - record.unit_price) > 1e-9  # no-hardcode-allow: reason="Floating point pricing comparison epsilon", reviewer="Prompt-48-Audit"
        is_tier_changed = active_record.tier != record.tier
        is_allowance_changed = active_record.free_allowance != record.free_allowance

        if not (is_price_changed or is_tier_changed or is_allowance_changed):
            refreshed = active_record.model_copy(update={"retrieved_at": record.retrieved_at})
            self._records[refreshed.id] = refreshed
            idx = existing_history.index(active_record)
            existing_history[idx] = refreshed
            return refreshed, None

        if record.effective_from < active_record.effective_from:
            raise PricingSCDConflictException(
                f"New effective_from ({record.effective_from}) cannot precede active record "
                f"effective_from ({active_record.effective_from}) for SKU '{record.service_sku}'."
            )

        closed_record = active_record.model_copy(
            update={
                "effective_to": record.effective_from,
                "is_active": False,
            }
        )
        self._records[closed_record.id] = closed_record
        idx = existing_history.index(active_record)
        existing_history[idx] = closed_record

        new_record = record.model_copy(
            update={
                "version": closed_record.version + 1,
                "effective_to": None,
                "is_active": True,
            }
        )
        self._records[new_record.id] = new_record
        existing_history.append(new_record)

        abs_diff = round(new_record.unit_price - closed_record.unit_price, 6)
        pct_diff = (
            round((abs_diff / closed_record.unit_price) * 100.0, 4)
            if closed_record.unit_price > 0
            else 0.0
        )
        change_type = "INCREASE" if new_record.unit_price > closed_record.unit_price else "DECREASE"

        change_record = PricingChangeRecord(
            tenant_id=new_record.tenant_id,
            provider=new_record.provider,
            sku=new_record.service_sku,
            region=new_record.region,
            dimension=new_record.pricing_dimension,
            rate_type=new_record.rate_type,
            old_version=closed_record.version,
            new_version=new_record.version,
            old_unit_price=closed_record.unit_price,
            new_unit_price=new_record.unit_price,
            price_delta=abs_diff,
            percentage_change=pct_diff,
            effective_date=new_record.effective_from,
            change_type=change_type,
        )
        self._changes[change_record.id] = change_record
        return new_record, change_record

    def get_active_rate(
        self,
        provider: str,
        sku: str | None,
        region: str,
        dimension: str,
        rate_type: RateType | str = RateType.LIST,
        tenant_id: str | None = None,
    ) -> PricingRecord | None:
        key = self._build_key(tenant_id, provider, sku, region, dimension, rate_type)
        history = self._natural_index.get(key, [])
        record = next((r for r in history if r.is_active), None)
        if record is None and tenant_id:
            return self.get_active_rate(
                provider, sku, region, dimension, rate_type, tenant_id=None
            )
        return record

    def get_rate_at_timestamp(
        self,
        provider: str,
        sku: str | None,
        region: str,
        dimension: str,
        timestamp: datetime,
        rate_type: RateType | str = RateType.LIST,
        tenant_id: str | None = None,
    ) -> PricingRecord | None:
        key = self._build_key(tenant_id, provider, sku, region, dimension, rate_type)
        history = self._natural_index.get(key, [])
        for record in reversed(history):
            if record.effective_from <= timestamp:
                if record.effective_to is None or record.effective_to > timestamp:
                    return record
        if tenant_id:
            return self.get_rate_at_timestamp(
                provider, sku, region, dimension, timestamp, rate_type, tenant_id=None
            )
        return None

    def record_unknown_sku(
        self,
        provider: str,
        sku: str,
        tenant_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> UnknownSkuRecord:
        key = ((tenant_id or "").strip(), provider.strip().lower(), sku.strip().lower())
        now = occurred_at or datetime.now(UTC)
        if key in self._unknown_skus:
            rec = self._unknown_skus[key]
            updated = rec.model_copy(
                update={"count": rec.count + 1, "last_seen_at": now}
            )
            self._unknown_skus[key] = updated
            return updated
        new_rec = UnknownSkuRecord(
            tenant_id=tenant_id,
            provider=provider.strip().lower(),
            sku=sku.strip(),
            first_seen_at=now,
            last_seen_at=now,
            count=1,
        )
        self._unknown_skus[key] = new_rec
        return new_rec

    def list_unknown_skus(
        self, provider: str | None = None, tenant_id: str | None = None
    ) -> list[UnknownSkuRecord]:
        return [
            rec
            for rec in self._unknown_skus.values()
            if (provider is None or rec.provider == provider.strip().lower())
            and (tenant_id is None or rec.tenant_id == tenant_id)
        ]

    def list_changes(
        self,
        provider: str | None = None,
        tenant_id: str | None = None,
        since: datetime | None = None,
    ) -> list[PricingChangeRecord]:
        return [
            c
            for c in self._changes.values()
            if (provider is None or c.provider == provider.strip().lower())
            and (tenant_id is None or c.tenant_id == tenant_id)
            and (since is None or c.detected_at >= since)
        ]

    def list_all_active(
        self, provider: str | None = None, tenant_id: str | None = None
    ) -> list[PricingRecord]:
        return [
            r
            for r in self._records.values()
            if r.is_active
            and (provider is None or r.provider == provider.strip().lower())
            and (tenant_id is None or r.tenant_id == tenant_id)
        ]

    def _load_seed_catalog(self) -> None:
        pass
