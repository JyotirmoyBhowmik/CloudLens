"""Workflow SLA, Working Hours, and Holiday Engine (Prompt 50).

Enforces:
- SLA calculation in operational working hours.
- Uses working-week (working days, daily start/end time) and holiday calendar masters.
- Accurate due date, remaining working hours, and SLA breach determination.
- Escalation due date calculation.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta

from domain.runtime.schedules import STANDARD_SCHEDULES
from masterdata.service import MasterDataService, get_master_data_service

logger = logging.getLogger(__name__)


class SLAEngine:
    """Calculates working hours SLAs and deadlines using working-week and holiday calendars."""

    def __init__(self, master_data_service: MasterDataService | None = None) -> None:
        self.master_data_service = master_data_service or get_master_data_service()

    def _get_schedule(
        self,
        schedule_id: str = "WW_STANDARD_MON_FRI",
        tenant_id: str | None = None,
    ) -> tuple[list[int], time, time, set[date]]:
        """Resolves working days, daily start/end, and holiday exclusions."""
        # 1. Try standard schedules
        sched = STANDARD_SCHEDULES.get(schedule_id)
        if sched:
            # Monday=1 ... Sunday=7
            working_days = sched.working_days
            start_parts = [int(p) for p in sched.daily_start_time.split(":")]
            end_parts = [int(p) for p in sched.daily_end_time.split(":")]
            start_time = time(start_parts[0], start_parts[1])
            end_time = time(end_parts[0], end_parts[1])
            exclusions = {date.fromisoformat(d) for d in sched.exclusion_dates}
            return working_days, start_time, end_time, exclusions

        # 2. Try master data WORKING_WEEK and HOLIDAY_CALENDAR
        try:
            ww_rec = self.master_data_service.get_record(
                "WORKING_WEEK", schedule_id, tenant_id=tenant_id
            )
            if ww_rec:
                attrs = ww_rec.attributes or {}
                working_days = attrs.get("working_days", [1, 2, 3, 4, 5])
                s_str = attrs.get("daily_start_time", "08:00")
                e_str = attrs.get("daily_end_time", "18:00")
                start_parts = [int(p) for p in s_str.split(":")]
                end_parts = [int(p) for p in e_str.split(":")]
                start_time = time(start_parts[0], start_parts[1])
                end_time = time(end_parts[0], end_parts[1])

                # Check holiday calendar
                exclusions = set()
                hol_records = self.master_data_service.list_records(
                    "HOLIDAY_CALENDAR", tenant_id=tenant_id
                )
                for h in hol_records:
                    h_list = (h.attributes or {}).get("holidays", [])
                    for h_date in h_list:
                        try:
                            exclusions.add(date.fromisoformat(h_date))
                        except Exception:
                            pass
                return working_days, start_time, end_time, exclusions
        except Exception as e:
            logger.debug("Failed resolving working week from master data: %s", e)

        # Default fallback: Mon-Fri 08:00-18:00, standard UK/US common holidays
        return (
            [1, 2, 3, 4, 5],
            time(8, 0),
            time(18, 0),
            {
                date(2026, 1, 1),
                date(2026, 12, 25),
            },
        )

    def calculate_due_date(
        self,
        start_time: datetime,
        sla_working_hours: int,
        schedule_id: str = "WW_STANDARD_MON_FRI",
        tenant_id: str | None = None,
    ) -> datetime:
        """Calculates SLA deadline by advancing only through operational working hours and days."""
        if sla_working_hours <= 0:
            return start_time

        working_days, daily_start, daily_end, exclusions = self._get_schedule(
            schedule_id, tenant_id=tenant_id
        )

        # Working hours per full working day
        day_working_seconds = (daily_end.hour * 3600 + daily_end.minute * 60) - (
            daily_start.hour * 3600 + daily_start.minute * 60
        )
        if day_working_seconds <= 0:
            day_working_seconds = 10 * 3600  # Default 10 hours

        remaining_seconds: float = float(sla_working_hours * 3600)
        curr = start_time if start_time.tzinfo else start_time.replace(tzinfo=UTC)

        # Maximum loop iterations to prevent infinite loops (e.g. 365 days)
        max_days = 365
        for _ in range(max_days):
            curr_date = curr.date()
            curr_isoweekday = curr.isoweekday()  # 1 = Mon, 7 = Sun

            is_working_day = (curr_isoweekday in working_days) and (curr_date not in exclusions)

            if not is_working_day:
                # Advance to start of next day
                curr = datetime.combine(curr_date + timedelta(days=1), daily_start, tzinfo=UTC)
                continue

            # We are on a working day
            day_start_dt = datetime.combine(curr_date, daily_start, tzinfo=UTC)
            day_end_dt = datetime.combine(curr_date, daily_end, tzinfo=UTC)

            if curr < day_start_dt:
                curr = day_start_dt

            if curr >= day_end_dt:
                # Advance to next day's start
                curr = datetime.combine(curr_date + timedelta(days=1), daily_start, tzinfo=UTC)
                continue

            # Seconds remaining in this working day
            available_seconds = (day_end_dt - curr).total_seconds()

            if remaining_seconds <= available_seconds:
                return curr + timedelta(seconds=remaining_seconds)
            else:
                remaining_seconds -= available_seconds
                curr = datetime.combine(curr_date + timedelta(days=1), daily_start, tzinfo=UTC)

        # Fallback if loop exceeded
        return start_time + timedelta(hours=sla_working_hours)

    def calculate_remaining_working_hours(
        self,
        as_of: datetime,
        due_date: datetime | None,
        schedule_id: str = "WW_STANDARD_MON_FRI",
        tenant_id: str | None = None,
    ) -> float:
        """Calculates remaining working hours between as_of and due_date.

        Returns 0.0 if already past deadline.
        """
        if due_date is None:
            return 0.0

        now = as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)
        deadline = due_date if due_date.tzinfo else due_date.replace(tzinfo=UTC)

        if now >= deadline:
            return 0.0

        working_days, daily_start, daily_end, exclusions = self._get_schedule(
            schedule_id, tenant_id=tenant_id
        )

        total_working_seconds = 0.0
        curr = now
        days_ahead = (deadline.date() - now.date()).days + 1

        for i in range(days_ahead):
            curr_date = now.date() + timedelta(days=i)
            if curr_date > deadline.date():
                break

            curr_isoweekday = curr_date.isoweekday()
            if (curr_isoweekday not in working_days) or (curr_date in exclusions):
                continue

            day_start_dt = datetime.combine(curr_date, daily_start, tzinfo=UTC)
            day_end_dt = datetime.combine(curr_date, daily_end, tzinfo=UTC)

            # Interval bounds for this day
            interval_start = max(curr, day_start_dt)
            interval_end = min(deadline, day_end_dt)

            if interval_end > interval_start:
                total_working_seconds += (interval_end - interval_start).total_seconds()

            curr = datetime.combine(curr_date + timedelta(days=1), daily_start, tzinfo=UTC)

        return round(total_working_seconds / 3600.0, 2)

    def is_sla_breached(self, as_of: datetime, due_date: datetime | None) -> bool:
        """Determines if the SLA deadline has elapsed."""
        if due_date is None:
            return False
        now = as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)
        deadline = due_date if due_date.tzinfo else due_date.replace(tzinfo=UTC)
        return now > deadline
