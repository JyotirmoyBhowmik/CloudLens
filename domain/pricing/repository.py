"""Pricing Catalogue Repository and Protocol (Prompt P06).

Enforces:
- Slowly Changing Dimension (SCD Type 2) persistence and versioning in PostgreSQL.
- Pattern P1: Protocol + SqlPricingRepository (SQLAlchemy 2.0 async + asyncpg).
- Pattern P3: Injected dependency, zero mutable dict singletons in production.
- Pattern P4: Transactional RLS isolation via get_tenant_session().
- Pattern P6: Startup guard preventing InMemory repository outside development.
- Point-in-time historical queries without rate overwrites.
- Strict isolation and non-lossy tracking of LIST and CONTRACTED rates.
- Pricing variance change record persistence in pricing_changes.
- Unknown-SKU gap reporting and tracking.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
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


@runtime_checkable
class PricingRepository(Protocol):
    """Authoritative protocol for SCD Type 2 Pricing Catalogue."""

    def add_or_update(
        self, record: PricingRecord
    ) -> tuple[PricingRecord, PricingChangeRecord | None]:
        ...

    def get_active_rate(
        self,
        provider: str,
        sku: str | None,
        region: str,
        dimension: str,
        rate_type: RateType | str = RateType.LIST,
        tenant_id: str | None = None,
    ) -> PricingRecord | None:
        ...

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
        ...

    def record_unknown_sku(
        self,
        provider: str,
        sku: str,
        tenant_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> UnknownSkuRecord:
        ...

    def list_unknown_skus(
        self, provider: str | None = None, tenant_id: str | None = None, status: str | None = None
    ) -> list[UnknownSkuRecord]:
        ...

    def list_changes(
        self,
        provider: str | None = None,
        tenant_id: str | None = None,
        since: datetime | None = None,
        sku: str | None = None,
    ) -> list[PricingChangeRecord]:
        ...

    def list_all_active(
        self, provider: str | None = None, tenant_id: str | None = None
    ) -> list[PricingRecord]:
        ...

    def list_catalog(
        self,
        provider: str | None = None,
        service: str | None = None,
        sku: str | None = None,
        region: str | None = None,
        dimension: str | None = None,
        rate_type: Any | None = None,
        effective_date: datetime | None = None,
        include_historical: bool = False,
        tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[PricingRecord], int]:
        ...


class SqlPricingRepository:
    """PostgreSQL implementation of SCD Type 2 Pricing Catalogue."""

    is_in_memory: bool = False

    def __init__(self) -> None:
        pass

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    def _row_to_record(self, row: Any) -> PricingRecord:
        m = dict(row._mapping)
        raw = m.get("attributes") or m.get("record_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return PricingRecord.model_validate(raw)

        return PricingRecord(
            id=m["id"],
            tenant_id=m.get("tenant_id"),
            provider=m["provider"],
            service_sku=m.get("sku") or "default-sku",
            region=m["region"],
            pricing_dimension=m.get("pricing_dimension") or m.get("dimension") or "USAGE",
            rate_type=RateType(m["rate_type"]) if m.get("rate_type") else RateType.LIST,
            unit_price=float(m.get("rate") or m.get("unit_rate") or 0.0),
            currency=m.get("currency") or "USD",
            effective_from=m.get("effective_from") or m.get("effective_start") or datetime.now(UTC),
            effective_to=m.get("effective_to") or m.get("effective_end"),
            is_active=bool(m.get("is_active", m.get("is_current", True))),
        )

    def _row_to_change(self, row: Any) -> PricingChangeRecord:
        m = dict(row._mapping)
        raw = m.get("attributes") or m.get("record_payload")
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict) and "id" in raw:
            return PricingChangeRecord.model_validate(raw)

        return PricingChangeRecord(
            id=m["id"],
            tenant_id=m.get("tenant_id"),
            provider=m["provider"],
            sku=m.get("sku") or "default-sku",
            region=m.get("region") or "global",
            dimension=m.get("pricing_dimension") or "USAGE",
            rate_type=RateType(m["rate_type"]) if m.get("rate_type") else RateType.LIST,
            old_version=1,
            new_version=2,
            old_unit_price=float(m["old_rate"]) if m.get("old_rate") is not None else 0.0,
            new_unit_price=float(m["new_rate"]) if m.get("new_rate") is not None else 0.0,
            price_delta=round(float(m.get("new_rate") or 0.0) - float(m.get("old_rate") or 0.0), 6),
            percentage_change=float(m["percentage_change"]) if m.get("percentage_change") is not None else 0.0,
            effective_date=m.get("changed_at") or m.get("effective_date") or datetime.now(UTC),
            change_type=m.get("change_reason") or m.get("change_type") or "UPDATE",
            detected_at=m.get("changed_at") or m.get("created_at") or datetime.now(UTC),
        )

    def add_or_update(
        self, record: PricingRecord
    ) -> tuple[PricingRecord, PricingChangeRecord | None]:
        async def _add():
            tid = record.tenant_id
            p = record.provider.strip().lower()
            sku = (record.service_sku or "").strip().lower()
            reg = record.region.strip().lower()
            dim = record.pricing_dimension.strip().upper()
            rt = record.rate_type.value if hasattr(record.rate_type, "value") else str(record.rate_type).upper()

            async with get_tenant_session(tid) as session:
                # 1. Look for existing active record
                query = text("""
                    SELECT * FROM pricing_records
                    WHERE (tenant_id = :tid OR (:tid IS NULL AND tenant_id IS NULL))
                      AND provider = :p
                      AND sku = :sku
                      AND region = :reg
                      AND pricing_dimension = :dim
                      AND rate_type = :rt
                      AND is_active = TRUE
                    LIMIT 1;
                """)
                res = await session.execute(query, {"tid": tid, "p": p, "sku": sku, "reg": reg, "dim": dim, "rt": rt})
                row = res.first()

                if not row:
                    stored_record = record.model_copy(
                        update={"version": 1, "is_active": True, "effective_to": None}
                    )
                    ins = text("""
                        INSERT INTO pricing_records (
                            id, tenant_id, provider, sku, region, pricing_dimension,
                            rate_type, currency, unit, effective_from, effective_to,
                            is_active, rate, attributes, created_at
                        ) VALUES (
                            :id, :tid, :p, :sku, :reg, :dim,
                            :rt, :cur, :unit, :eff_start, :eff_end,
                            :is_cur, :rate, CAST(:payload AS jsonb), NOW()
                        );
                    """)
                    await session.execute(
                        ins,
                        {
                            "id": stored_record.id,
                            "tid": tid,
                            "p": p,
                            "sku": sku,
                            "reg": reg,
                            "dim": dim,
                            "rt": rt,
                            "cur": stored_record.currency,
                            "unit": getattr(stored_record, "unit", "Hour") or "Hour",
                            "eff_start": stored_record.effective_from,
                            "eff_end": stored_record.effective_to,
                            "is_cur": True,
                            "rate": stored_record.unit_price,
                            "payload": json.dumps(stored_record.model_dump(mode="json")),
                        },
                    )
                    await session.commit()
                    return stored_record, None

                active_record = self._row_to_record(row)
                is_price_changed = active_record.unit_price != record.unit_price
                is_tier_changed = active_record.tier != record.tier
                is_allowance_changed = active_record.free_allowance != record.free_allowance

                if not (is_price_changed or is_tier_changed or is_allowance_changed):
                    refreshed = active_record.model_copy(update={"retrieved_at": record.retrieved_at})
                    upd = text("""
                        UPDATE pricing_records
                        SET attributes = CAST(:payload AS jsonb)
                        WHERE id = :id;
                    """)
                    await session.execute(upd, {"id": refreshed.id, "payload": json.dumps(refreshed.model_dump(mode="json"))})
                    await session.commit()
                    return refreshed, None

                if record.effective_from < active_record.effective_from:
                    raise PricingSCDConflictException(
                        f"New effective_from ({record.effective_from}) cannot precede active record "
                        f"effective_from ({active_record.effective_from}) for SKU '{record.service_sku}'."
                    )

                # Close old record
                await session.execute(
                    text("""
                        UPDATE pricing_records
                        SET is_active = FALSE, effective_to = :end_dt
                        WHERE id = :id;
                    """),
                    {"id": active_record.id, "end_dt": record.effective_from},
                )

                # Insert new version
                new_record = record.model_copy(
                    update={
                        "version": active_record.version + 1,
                        "effective_to": None,
                        "is_active": True,
                    }
                )
                ins = text("""
                    INSERT INTO pricing_records (
                        id, tenant_id, provider, sku, region, pricing_dimension,
                        rate_type, currency, unit, effective_from, effective_to,
                        is_active, rate, attributes, created_at
                    ) VALUES (
                        :id, :tid, :p, :sku, :reg, :dim,
                        :rt, :cur, :unit, :eff_start, :eff_end,
                        :is_cur, :rate, CAST(:payload AS jsonb), NOW()
                    );
                """)
                await session.execute(
                    ins,
                    {
                        "id": new_record.id,
                        "tid": tid,
                        "p": p,
                        "sku": sku,
                        "reg": reg,
                        "dim": dim,
                        "rt": rt,
                        "cur": new_record.currency,
                        "unit": getattr(new_record, "unit", "Hour") or "Hour",
                        "eff_start": new_record.effective_from,
                        "eff_end": None,
                        "is_cur": True,
                        "rate": new_record.unit_price,
                        "payload": json.dumps(new_record.model_dump(mode="json")),
                    },
                )

                # Create change record
                abs_diff = round(new_record.unit_price - active_record.unit_price, 6)
                pct_diff = (
                    round((abs_diff / active_record.unit_price) * 100.0, 4)
                    if active_record.unit_price > 0
                    else 0.0
                )
                change_type = "INCREASE" if new_record.unit_price > active_record.unit_price else "DECREASE"
                change_record = PricingChangeRecord(
                    tenant_id=new_record.tenant_id,
                    provider=new_record.provider,
                    sku=new_record.service_sku,
                    region=new_record.region,
                    dimension=new_record.pricing_dimension,
                    rate_type=new_record.rate_type,
                    old_version=active_record.version,
                    new_version=new_record.version,
                    old_unit_price=active_record.unit_price,
                    new_unit_price=new_record.unit_price,
                    price_delta=abs_diff,
                    percentage_change=pct_diff,
                    effective_date=new_record.effective_from,
                    change_type=change_type,
                )
                ins_change = text("""
                    INSERT INTO pricing_changes (
                        id, tenant_id, provider, sku, region, pricing_dimension,
                        rate_type, old_rate, new_rate, percentage_change,
                        changed_at, change_reason
                    ) VALUES (
                        :id, :tid, :p, :sku, :reg, :dim,
                        :rt, :old_r, :new_r, :pct,
                        :changed_at, :reason
                    );
                """)
                await session.execute(
                    ins_change,
                    {
                        "id": change_record.id,
                        "tid": tid,
                        "p": p,
                        "sku": sku,
                        "reg": reg,
                        "dim": dim,
                        "rt": rt,
                        "old_r": change_record.old_unit_price,
                        "new_r": change_record.new_unit_price,
                        "pct": change_record.percentage_change,
                        "changed_at": change_record.effective_date,
                        "reason": change_type,
                    },
                )

                await session.commit()
                return new_record, change_record

        return self._run_async(_add())

    def get_active_rate(
        self,
        provider: str,
        sku: str | None,
        region: str,
        dimension: str,
        rate_type: RateType | str = RateType.LIST,
        tenant_id: str | None = None,
    ) -> PricingRecord | None:
        async def _get():
            p = provider.strip().lower()
            s = (sku or "").strip().lower()
            reg = region.strip().lower()
            dim = dimension.strip().upper()
            rt = rate_type.value if hasattr(rate_type, "value") else str(rate_type).upper()

            async with get_tenant_session(tenant_id) as session:
                query = text("""
                    SELECT * FROM pricing_records
                    WHERE (tenant_id = :tid OR tenant_id IS NULL)
                      AND provider = :p
                      AND sku = :s
                      AND region = :reg
                      AND pricing_dimension = :dim
                      AND rate_type = :rt
                      AND is_active = TRUE
                    ORDER BY tenant_id NULLS LAST
                    LIMIT 1;
                """)
                res = await session.execute(query, {"tid": tenant_id, "p": p, "s": s, "reg": reg, "dim": dim, "rt": rt})
                row = res.first()
                return self._row_to_record(row) if row else None

        return self._run_async(_get())

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
        async def _get_ts():
            p = provider.strip().lower()
            s = (sku or "").strip().lower()
            reg = region.strip().lower()
            dim = dimension.strip().upper()
            rt = rate_type.value if hasattr(rate_type, "value") else str(rate_type).upper()

            async with get_tenant_session(tenant_id) as session:
                query = text("""
                    SELECT * FROM pricing_records
                    WHERE (tenant_id = :tid OR tenant_id IS NULL)
                      AND provider = :p
                      AND sku = :s
                      AND region = :reg
                      AND pricing_dimension = :dim
                      AND rate_type = :rt
                      AND effective_from <= :ts
                      AND (effective_to IS NULL OR effective_to > :ts)
                    ORDER BY tenant_id NULLS LAST, effective_from DESC
                    LIMIT 1;
                """)
                res = await session.execute(query, {"tid": tenant_id, "p": p, "s": s, "reg": reg, "dim": dim, "rt": rt, "ts": timestamp})
                row = res.first()
                return self._row_to_record(row) if row else None

        return self._run_async(_get_ts())

    def record_unknown_sku(
        self,
        provider: str,
        sku: str,
        tenant_id: str | None = None,
        occurred_at: datetime | None = None,
    ) -> UnknownSkuRecord:
        now = occurred_at or datetime.now(UTC)
        p = provider.strip().lower()
        s = sku.strip()
        tid = tenant_id or "system"
        gid = f"gap-sku-{p}-{s}"

        async def _record():
            async with get_tenant_session(tid) as session:
                q = text("""
                    INSERT INTO catalogue_gaps (id, tenant_id, catalogue_type, provider, native_identifier, status, occurrence_count, first_seen_at, last_seen_at, context_payload)
                    VALUES (:id, :tid, 'PRICING_SKU', :p, :sku, 'OPEN', 1, :now, :now, '{}'::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        occurrence_count = catalogue_gaps.occurrence_count + 1,
                        last_seen_at = :now
                    RETURNING id, tenant_id, provider, native_identifier, occurrence_count, first_seen_at, last_seen_at;
                """)
                res = await session.execute(q, {"id": gid, "tid": tid, "p": p, "sku": s, "now": now})
                row = res.fetchone()
                return UnknownSkuRecord(
                    tenant_id=row.tenant_id,
                    provider=row.provider,
                    sku=row.native_identifier,
                    count=row.occurrence_count,
                    first_seen_at=row.first_seen_at,
                    last_seen_at=row.last_seen_at,
                )

        return self._run_async(_record())

    def list_unknown_skus(
        self, provider: str | None = None, tenant_id: str | None = None, status: str | None = None
    ) -> list[UnknownSkuRecord]:
        async def _list():
            async with get_tenant_session(tenant_id or "system") as session:
                sql = "SELECT tenant_id, provider, native_identifier, occurrence_count, first_seen_at, last_seen_at FROM catalogue_gaps WHERE catalogue_type = 'PRICING_SKU'"
                params: dict[str, Any] = {}
                if provider:
                    sql += " AND provider = :p"
                    params["p"] = provider.strip().lower()
                if tenant_id:
                    sql += " AND tenant_id = :tid"
                    params["tid"] = tenant_id
                sql += " ORDER BY last_seen_at DESC;"
                res = await session.execute(text(sql), params)
                return [
                    UnknownSkuRecord(
                        tenant_id=r.tenant_id,
                        provider=r.provider,
                        sku=r.native_identifier,
                        count=r.occurrence_count,
                        first_seen_at=r.first_seen_at,
                        last_seen_at=r.last_seen_at,
                    )
                    for r in res.fetchall()
                ]

        return self._run_async(_list())

    def list_changes(
        self,
        provider: str | None = None,
        tenant_id: str | None = None,
        since: datetime | None = None,
        sku: str | None = None,
    ) -> list[PricingChangeRecord]:
        async def _changes():
            sql = "SELECT * FROM pricing_changes WHERE 1=1"
            params: dict[str, Any] = {}
            if tenant_id:
                sql += " AND (tenant_id = :tid OR tenant_id IS NULL)"
                params["tid"] = tenant_id
            if provider:
                sql += " AND provider = :p"
                params["p"] = provider.strip().lower()
            if sku:
                sql += " AND sku = :sku"
                params["sku"] = sku.strip()
            if since:
                sql += " AND changed_at >= :since"
                params["since"] = since
            sql += " ORDER BY changed_at DESC;"

            async with get_tenant_session(tenant_id) as session:
                res = await session.execute(text(sql), params)
                return [self._row_to_change(r) for r in res.fetchall()]

        return self._run_async(_changes())

    def list_all_active(
        self, provider: str | None = None, tenant_id: str | None = None
    ) -> list[PricingRecord]:
        async def _all():
            sql = "SELECT * FROM pricing_records WHERE is_active = TRUE"
            params: dict[str, Any] = {}
            if tenant_id:
                sql += " AND (tenant_id = :tid OR tenant_id IS NULL)"
                params["tid"] = tenant_id
            if provider:
                sql += " AND provider = :p"
                params["p"] = provider.strip().lower()
            sql += " ORDER BY created_at DESC;"

            async with get_tenant_session(tenant_id) as session:
                res = await session.execute(text(sql), params)
                return [self._row_to_record(r) for r in res.fetchall()]

        return self._run_async(_all())

    def list_catalog(
        self,
        provider: str | None = None,
        service: str | None = None,
        sku: str | None = None,
        region: str | None = None,
        dimension: str | None = None,
        rate_type: Any | None = None,
        effective_date: datetime | None = None,
        include_historical: bool = False,
        tenant_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[PricingRecord], int]:
        async def _query():
            sql = "SELECT * FROM pricing_records WHERE 1=1"
            params: dict[str, Any] = {}
            if not include_historical:
                sql += " AND is_active = TRUE"
            if tenant_id:
                sql += " AND (tenant_id = :tid OR tenant_id IS NULL)"
                params["tid"] = tenant_id
            if provider:
                sql += " AND LOWER(provider) = :p"
                params["p"] = provider.strip().lower()
            if service:
                sql += " AND LOWER(attributes->>'service_name') = :s"
                params["s"] = service.strip().lower()
            if sku:
                sql += " AND LOWER(sku) = :sku"
                params["sku"] = sku.strip().lower()
            if region:
                sql += " AND LOWER(region) = :reg"
                params["reg"] = region.strip().lower()
            if dimension:
                sql += " AND LOWER(pricing_dimension) = :dim"
                params["dim"] = dimension.strip().lower()
            if rate_type:
                sql += " AND rate_type = :rt"
                params["rt"] = rate_type.value if hasattr(rate_type, "value") else str(rate_type)

            sql += " ORDER BY created_at DESC;"

            async with get_tenant_session(tenant_id) as session:
                res = await session.execute(text(sql), params)
                all_records = [self._row_to_record(r) for r in res.fetchall()]
                total = len(all_records)
                offset = (page - 1) * page_size
                paginated = all_records[offset : offset + page_size]
                return paginated, total

        return self._run_async(_query())


_pricing_repository: Any = None


def get_pricing_repository() -> Any:
    """Returns singleton PricingRepository instance with production startup guard."""
    global _pricing_repository
    if _pricing_repository is None:
        _pricing_repository = SqlPricingRepository()
        verify_persistence_startup_guard(_pricing_repository)
    return _pricing_repository


def reset_pricing_repository(repo: Any = None) -> Any:
    """Resets the singleton PricingRepository for testing."""
    global _pricing_repository
    _pricing_repository = repo
    return _pricing_repository or get_pricing_repository()


__all__ = [
    "PricingRepository",
    "SqlPricingRepository",
    "get_pricing_repository",
    "reset_pricing_repository",
]
