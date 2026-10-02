"""Budget Calendar & Fiscal Period Boundary Resolver (Prompt 28).

Enforces:
- Prompt 28: Support monthly, quarterly, annual, fiscal-year and custom periods
  aligned to the tenant fiscal calendar.
- Dynamic fiscal calendar period boundary recalculation without code changes.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date

from domain.budgets.models import BudgetEntity
from domain.models.enums import BudgetPeriod
from masterdata.business_engines import FinancialCalendarEngine
from masterdata.service import MasterDataService, get_master_data_service


class BudgetPeriodCalendar:
    """Calculates active period window boundaries for budgets."""

    def __init__(self, master_service: MasterDataService | None = None) -> None:
        self._master_service = master_service or get_master_data_service()
        self._fiscal_engine = FinancialCalendarEngine(self._master_service)

    def resolve_period_bounds(
        self,
        budget: BudgetEntity,
        as_of: date | None = None,
        fiscal_calendar_code: str = "FC_STANDARD",
    ) -> tuple[date, date]:
        """Resolves the active (start_date, end_date) period window for the budget."""
        ref_date = as_of or date.today()

        if budget.period == BudgetPeriod.CUSTOM:
            start = budget.effective_date
            end = budget.expiry_date or date(budget.effective_date.year, 12, 31)
            return start, end

        if budget.period == BudgetPeriod.MONTHLY:
            # Check if fiscal calendar has custom monthly boundaries
            try:
                p = self._fiscal_engine.get_period_for_date(fiscal_calendar_code, ref_date)
                return p.start_date, p.end_date
            except Exception:
                # Standard Gregorian month boundary
                _, last_day = monthrange(ref_date.year, ref_date.month)
                return date(ref_date.year, ref_date.month, 1), date(
                    ref_date.year, ref_date.month, last_day
                )

        if budget.period == BudgetPeriod.QUARTERLY:
            try:
                # Determine quarter based on fiscal calendar start month
                cal = self._master_service.get_record("FISCAL_CALENDAR", fiscal_calendar_code)
                start_month = int(cal.attributes.get("fiscal_year_start_month", 1)) if cal else 1
            except Exception:
                start_month = 1

            # Quarter index 0..3 relative to fiscal year start month
            month_offset = (ref_date.month - start_month) % 12
            q_index = month_offset // 3
            q_start_month = ((start_month - 1 + q_index * 3) % 12) + 1
            q_end_month = ((start_month - 1 + q_index * 3 + 2) % 12) + 1

            start_year = (
                ref_date.year
                if q_start_month <= ref_date.month
                else (ref_date.year - 1 if start_month > 1 else ref_date.year)
            )
            end_year = start_year if q_end_month >= q_start_month else start_year + 1
            _, last_day = monthrange(end_year, q_end_month)
            return date(start_year, q_start_month, 1), date(end_year, q_end_month, last_day)

        if budget.period == BudgetPeriod.ANNUAL:
            return date(ref_date.year, 1, 1), date(ref_date.year, 12, 31)

        if budget.period == BudgetPeriod.FISCAL_YEAR:
            try:
                periods = self._fiscal_engine.get_fiscal_periods(
                    fiscal_calendar_code, ref_date.year
                )
                if periods:
                    # Check if ref_date is inside this year's periods
                    if periods[0].start_date <= ref_date <= periods[-1].end_date:
                        return periods[0].start_date, periods[-1].end_date
                    # Otherwise check previous or next fiscal year
                    prev_p = self._fiscal_engine.get_fiscal_periods(
                        fiscal_calendar_code, ref_date.year - 1
                    )
                    if prev_p and prev_p[0].start_date <= ref_date <= prev_p[-1].end_date:
                        return prev_p[0].start_date, prev_p[-1].end_date
                    next_p = self._fiscal_engine.get_fiscal_periods(
                        fiscal_calendar_code, ref_date.year + 1
                    )
                    if next_p and next_p[0].start_date <= ref_date <= next_p[-1].end_date:
                        return next_p[0].start_date, next_p[-1].end_date
                    return periods[0].start_date, periods[-1].end_date
            except Exception:
                pass
            return date(ref_date.year, 1, 1), date(ref_date.year, 12, 31)

        # Fallback
        return date(ref_date.year, 1, 1), date(ref_date.year, 12, 31)
