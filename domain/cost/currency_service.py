"""Query-Time Currency Conversion Service (Prompt P06).

Enforces:
- Storing cost strictly in native billing currency inside the fact record.
- Converting only at query time using effective-dated exchange rates in PostgreSQL.
- Mandatory disclosure displaying applied exchange rate and rate effective date.
- Pattern P1: Protocol + SqlCurrencyConversionService (SQLAlchemy 2.0 async + asyncpg).
- Pattern P3: Injected dependency, zero mutable dict singletons in production.
- Pattern P6: Startup guard preventing InMemory service outside development.
- STRICT PROHIBITION: Never convert currency inside a fact record.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_tenant_session, run_async, verify_persistence_startup_guard
from domain.cost.models import ConvertedCostFigure, CostPresentationBasis, CurrencyExchangeRate
from domain.models.exceptions import CurrencyConversionException

logger = logging.getLogger(__name__)


@runtime_checkable
class CurrencyConversionService(Protocol):
    """Authoritative protocol for currency conversion."""

    def register_rate(self, rate_record: CurrencyExchangeRate) -> None:
        ...

    def get_effective_rate(
        self,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> CurrencyExchangeRate | None:
        ...

    def convert_at_query_time(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of_date: date | None = None,
        presentation_basis: CostPresentationBasis = CostPresentationBasis.BILLED,
        basis: CostPresentationBasis | None = None,
    ) -> ConvertedCostFigure:
        ...


class SqlCurrencyConversionService:
    """PostgreSQL implementation of CurrencyConversionService backed by exchange_rates table."""

    is_in_memory: bool = False

    def __init__(self) -> None:
        self._seed_default_rates_if_needed()

    def _run_async(self, coro: Any) -> Any:
        return run_async(coro)

    def _seed_default_rates_if_needed(self) -> None:
        async def _seed():
            sample_rates = [
                ("USD", "EUR", date(2026, 1, 1), Decimal("0.9200")),
                ("USD", "GBP", date(2026, 1, 1), Decimal("0.7850")),
                ("USD", "CAD", date(2026, 1, 1), Decimal("1.3500")),
                ("USD", "AUD", date(2026, 1, 1), Decimal("1.5200")),
                ("USD", "JPY", date(2026, 1, 1), Decimal("152.50")),
                ("USD", "EUR", date(2026, 2, 1), Decimal("0.9220")),
                ("USD", "GBP", date(2026, 2, 1), Decimal("0.7880")),
                ("USD", "EUR", date(2026, 3, 1), Decimal("0.9250")),
                ("USD", "GBP", date(2026, 3, 1), Decimal("0.7900")),
                ("EUR", "USD", date(2026, 3, 1), Decimal("1.0810")),
                ("GBP", "USD", date(2026, 3, 1), Decimal("1.2658")),
            ]
            async with get_tenant_session() as session:
                query = text("""
                    INSERT INTO exchange_rates (from_currency, to_currency, effective_date, rate, created_at)
                    VALUES (:fc, :tc, :ed, :rate, NOW())
                    ON CONFLICT (from_currency, to_currency, effective_date) DO NOTHING;
                """)
                for fc, tc, ed, r in sample_rates:
                    await session.execute(query, {"fc": fc, "tc": tc, "ed": ed, "rate": r})
                await session.commit()

        try:
            self._run_async(_seed())
        except Exception as e:
            logger.debug("Exchange rates initialization note: %s", e)

    def register_rate(self, rate_record: CurrencyExchangeRate) -> None:
        async def _reg():
            async with get_tenant_session() as session:
                query = text("""
                    INSERT INTO exchange_rates (from_currency, to_currency, effective_date, rate, created_at)
                    VALUES (:fc, :tc, :ed, :rate, NOW())
                    ON CONFLICT (from_currency, to_currency, effective_date) DO UPDATE
                    SET rate = EXCLUDED.rate;
                """)
                await session.execute(
                    query,
                    {
                        "fc": rate_record.from_currency.upper(),
                        "tc": rate_record.to_currency.upper(),
                        "ed": rate_record.effective_date,
                        "rate": rate_record.rate,
                    },
                )
                await session.commit()

        self._run_async(_reg())

    def get_effective_rate(
        self,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> CurrencyExchangeRate | None:
        fc = from_currency.upper()
        tc = to_currency.upper()

        if fc == tc:
            return CurrencyExchangeRate(
                from_currency=fc,
                to_currency=tc,
                effective_date=as_of_date,
                rate=Decimal("1.0"),
                source="IDENTITY",
            )

        async def _get():
            async with get_tenant_session() as session:
                query = text("""
                    SELECT from_currency, to_currency, effective_date, rate
                    FROM exchange_rates
                    WHERE from_currency = :fc AND to_currency = :tc AND effective_date <= :ed
                    ORDER BY effective_date DESC
                    LIMIT 1;
                """)
                res = await session.execute(query, {"fc": fc, "tc": tc, "ed": as_of_date})
                row = res.first()
                if not row:
                    return None
                return CurrencyExchangeRate(
                    from_currency=row[0],
                    to_currency=row[1],
                    effective_date=row[2],
                    rate=Decimal(str(row[3])),
                    source="POSTGRESQL_EXCHANGE_RATES",
                )

        return self._run_async(_get())

    def convert_at_query_time(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        as_of_date: date | None = None,
        presentation_basis: CostPresentationBasis = CostPresentationBasis.BILLED,
        basis: CostPresentationBasis | None = None,
    ) -> ConvertedCostFigure:
        fc = from_currency.upper()
        tc = to_currency.upper()
        effective_date = as_of_date or datetime.now(UTC).date()
        effective_basis = basis if basis is not None else presentation_basis

        if fc == tc:
            return ConvertedCostFigure(
                original_amount=amount,
                original_currency=fc,
                target_amount=amount,
                target_currency=tc,
                exchange_rate=Decimal("1.0"),
                rate_effective_date=effective_date,
                presentation_basis=effective_basis,
                disclosure=f"Native currency: {amount:.2f} {fc} (basis: {effective_basis.value}).",
            )

        rate_record = self.get_effective_rate(fc, tc, effective_date)
        if not rate_record:
            raise CurrencyConversionException(
                from_currency=fc,
                to_currency=tc,
                as_of_date=effective_date.isoformat(),
            )

        target_amount = round(amount * rate_record.rate, 2)
        disclosure = (
            f"Converted from {amount:.2f} {fc} to {target_amount:.2f} {tc} "
            f"at effective rate {rate_record.rate} as of {rate_record.effective_date.isoformat()} "
            f"(basis: {effective_basis.value}, source: {rate_record.source})."
        )

        return ConvertedCostFigure(
            original_amount=amount,
            original_currency=fc,
            target_amount=target_amount,
            target_currency=tc,
            exchange_rate=rate_record.rate,
            rate_effective_date=rate_record.effective_date,
            presentation_basis=effective_basis,
            disclosure=disclosure,
        )

    convert_query_time = convert_at_query_time


_DEFAULT_CURRENCY_SERVICE: Any = None


def get_currency_service() -> Any:
    """Returns singleton instance of CurrencyConversionService with startup guard."""
    global _DEFAULT_CURRENCY_SERVICE
    if _DEFAULT_CURRENCY_SERVICE is None:
        _DEFAULT_CURRENCY_SERVICE = SqlCurrencyConversionService()
        verify_persistence_startup_guard(_DEFAULT_CURRENCY_SERVICE)
    return _DEFAULT_CURRENCY_SERVICE


def reset_currency_service(service: Any = None) -> Any:
    """Resets singleton instance for test isolation."""
    global _DEFAULT_CURRENCY_SERVICE
    _DEFAULT_CURRENCY_SERVICE = service
    return _DEFAULT_CURRENCY_SERVICE or get_currency_service()


__all__ = [
    "CurrencyConversionService",
    "SqlCurrencyConversionService",
    "get_currency_service",
    "reset_currency_service",
]
