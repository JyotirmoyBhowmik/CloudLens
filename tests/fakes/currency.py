"""In-memory fake service for Currency Conversion (Prompt P06)."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import Decimal

from domain.cost.models import ConvertedCostFigure, CostPresentationBasis, CurrencyExchangeRate
from domain.models.exceptions import CurrencyConversionException

logger = logging.getLogger(__name__)


class InMemoryCurrencyConversionService:
    """Manages effective-dated currency conversion rate tables in memory."""

    is_in_memory: bool = True

    def __init__(self) -> None:
        self._rates: dict[tuple[str, str, date], CurrencyExchangeRate] = {}
        self._seed_default_rates()

    def _seed_default_rates(self) -> None:
        sample_rates = [
            CurrencyExchangeRate(
                from_currency="USD",
                to_currency="EUR",
                effective_date=date(2026, 1, 1),
                rate=Decimal("0.9200"),
            ),
            CurrencyExchangeRate(
                from_currency="USD",
                to_currency="GBP",
                effective_date=date(2026, 1, 1),
                rate=Decimal("0.7850"),
            ),
            CurrencyExchangeRate(
                from_currency="USD",
                to_currency="CAD",
                effective_date=date(2026, 1, 1),
                rate=Decimal("1.3500"),
            ),
            CurrencyExchangeRate(
                from_currency="USD",
                to_currency="AUD",
                effective_date=date(2026, 1, 1),
                rate=Decimal("1.5200"),
            ),
            CurrencyExchangeRate(
                from_currency="USD",
                to_currency="JPY",
                effective_date=date(2026, 1, 1),
                rate=Decimal("152.50"),
            ),
            CurrencyExchangeRate(
                from_currency="USD",
                to_currency="EUR",
                effective_date=date(2026, 2, 1),
                rate=Decimal("0.9220"),
            ),
            CurrencyExchangeRate(
                from_currency="USD",
                to_currency="GBP",
                effective_date=date(2026, 2, 1),
                rate=Decimal("0.7880"),
            ),
            CurrencyExchangeRate(
                from_currency="USD",
                to_currency="EUR",
                effective_date=date(2026, 3, 1),
                rate=Decimal("0.9250"),
            ),
            CurrencyExchangeRate(
                from_currency="USD",
                to_currency="GBP",
                effective_date=date(2026, 3, 1),
                rate=Decimal("0.7900"),
            ),
            CurrencyExchangeRate(
                from_currency="EUR",
                to_currency="USD",
                effective_date=date(2026, 3, 1),
                rate=Decimal("1.0810"),
            ),
            CurrencyExchangeRate(
                from_currency="GBP",
                to_currency="USD",
                effective_date=date(2026, 3, 1),
                rate=Decimal("1.2658"),
            ),
        ]
        for r in sample_rates:
            self.register_rate(r)

    def register_rate(self, rate_record: CurrencyExchangeRate) -> None:
        key = (
            rate_record.from_currency.upper(),
            rate_record.to_currency.upper(),
            rate_record.effective_date,
        )
        self._rates[key] = rate_record

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

        matching_rates = [
            rec
            for (f, t, ed), rec in self._rates.items()
            if f == fc and t == tc and ed <= as_of_date
        ]

        if not matching_rates:
            return None

        return max(matching_rates, key=lambda r: r.effective_date)

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
