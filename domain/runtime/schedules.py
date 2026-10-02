"""Named Schedule Definitions, Timezone Calculations, and Inheritance Engine (Prompt 26).

Enforces:
- Prompt 26: Named schedules with timezone, working days, daily start/end, exclusion dates, and maintenance windows.
- Prompt 26: Standard inheritance chain: RESOURCE -> SERVICE -> SCOPE -> ENVIRONMENT -> TENANT.
- Prompt 26: BR-007 Non-production workloads must not run 24x7 without business justification.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from domain.models.exceptions import InvalidScheduleException, ScheduleNotFoundException
from domain.runtime.models import (
    NamedSchedule,
    ScheduleAttachment,
    ScheduleLevel,
    WorkloadType,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. Standard Built-in Operational Schedules
# ==============================================================================

STANDARD_SCHEDULES: dict[str, NamedSchedule] = {
    "WW_STANDARD_MON_FRI": NamedSchedule(
        id="WW_STANDARD_MON_FRI",
        name="Standard Western Working Week (Mon - Fri)",
        description="Standard business days Monday through Friday, 08:00 to 18:00 local time.",
        timezone="UTC",
        workload_type=WorkloadType.SCHEDULE_BASED,
        working_days=[1, 2, 3, 4, 5],
        daily_start_time="08:00",
        daily_end_time="18:00",
        exclusion_dates=[
            "2026-01-01",
            "2026-04-03",
            "2026-04-06",
            "2026-05-04",
            "2026-05-25",
            "2026-08-31",
            "2026-12-25",
            "2026-12-28",
        ],
        warning_tolerance_hours=Decimal("1.0"),
        critical_tolerance_hours=Decimal("4.0"),
    ),
    "WW_MIDDLE_EAST_SUN_THU": NamedSchedule(
        id="WW_MIDDLE_EAST_SUN_THU",
        name="Middle East Working Week (Sun - Thu)",
        description="Regional working week Sunday through Thursday, 08:00 to 18:00 local time.",
        timezone="Asia/Dubai",
        workload_type=WorkloadType.SCHEDULE_BASED,
        working_days=[7, 1, 2, 3, 4],
        daily_start_time="08:00",
        daily_end_time="18:00",
        exclusion_dates=["2026-01-01", "2026-12-25"],
        warning_tolerance_hours=Decimal("1.0"),
        critical_tolerance_hours=Decimal("4.0"),
    ),
    "WW_CONTINUOUS_24X7": NamedSchedule(
        id="WW_CONTINUOUS_24X7",
        name="Continuous Operation 24x7",
        description="Always-on production infrastructure with no scheduled downtime windows.",
        timezone="UTC",
        workload_type=WorkloadType.CONTINUOUS_24X7,
        working_days=[1, 2, 3, 4, 5, 6, 7],
        daily_start_time="00:00",
        daily_end_time="23:59",
        exclusion_dates=[],
        warning_tolerance_hours=Decimal("0.0"),
        critical_tolerance_hours=Decimal("0.0"),
    ),
    "WEEKEND_SHUTDOWN": NamedSchedule(
        id="WEEKEND_SHUTDOWN",
        name="Weekend Shutdown (24x5)",
        description="Continuous weekday execution with mandatory shutdown across Saturday and Sunday.",
        timezone="UTC",
        workload_type=WorkloadType.SCHEDULE_BASED,
        working_days=[1, 2, 3, 4, 5],
        daily_start_time="00:00",
        daily_end_time="23:59",
        exclusion_dates=[],
        warning_tolerance_hours=Decimal("2.0"),
        critical_tolerance_hours=Decimal("6.0"),
    ),
    "BATCH_NIGHTLY": NamedSchedule(
        id="BATCH_NIGHTLY",
        name="Nightly Batch Processing Window",
        description="Scheduled off-peak batch processing approved to execute between 22:00 and 06:00.",
        timezone="UTC",
        workload_type=WorkloadType.SCHEDULE_BASED,
        working_days=[1, 2, 3, 4, 5, 6, 7],
        daily_start_time="22:00",
        daily_end_time="06:00",
        exclusion_dates=[],
        warning_tolerance_hours=Decimal("1.0"),
        critical_tolerance_hours=Decimal("2.0"),
    ),
}


# ==============================================================================
# 2. Timezone & Slot Helper Functions
# ==============================================================================


def _parse_time(time_str: str) -> time:
    """Parses HH:MM into a datetime.time object."""
    try:
        parts = time_str.strip().split(":")
        return time(hour=int(parts[0]), minute=int(parts[1]))
    except Exception as err:
        raise InvalidScheduleException(
            f"Invalid time format '{time_str}'. Expected HH:MM (24-hour format)."
        ) from err


def _get_zoneinfo(tz_name: str) -> ZoneInfo:
    """Safe ZoneInfo loader falling back to UTC on unrecognized timezone names."""
    try:
        return ZoneInfo(tz_name.strip())
    except (ZoneInfoNotFoundError, Exception):
        logger.warning("Unrecognized timezone '%s', defaulting to UTC.", tz_name)
        return ZoneInfo("UTC")


def is_approved_running_slot(schedule: NamedSchedule, check_dt: datetime) -> bool:
    """Evaluates whether a specific instant is an approved execution slot under the schedule.

    Walks:
    1. Timezone translation
    2. Exclusion dates (public holidays / shutdown days)
    3. Maintenance windows (override exclusion)
    4. Working days & daily start/end window
    """
    tz = _get_zoneinfo(schedule.timezone)
    local_dt = check_dt.astimezone(tz)
    date_str = local_dt.strftime("%Y-%m-%d")
    iso_weekday = local_dt.isoweekday()  # 1=Mon ... 7=Sun
    slot_time = local_dt.time()

    # 1. Continuous 24x7 workloads are always approved unless an explicit exclusion applies
    if schedule.workload_type == WorkloadType.CONTINUOUS_24X7:
        if date_str in schedule.exclusion_dates:
            return False
        return True

    # 2. Check maintenance windows (maintenance allows execution outside core hours)
    for mw in schedule.maintenance_windows:
        if mw.specific_date and mw.specific_date == date_str:
            mw_start = _parse_time(mw.start_time)
            mw_end = _parse_time(mw.end_time)
            if _is_time_in_range(slot_time, mw_start, mw_end):
                return True
        elif mw.is_recurring and mw.day_of_week == iso_weekday:
            mw_start = _parse_time(mw.start_time)
            mw_end = _parse_time(mw.end_time)
            if _is_time_in_range(slot_time, mw_start, mw_end):
                return True

    # 3. Check public holiday / exclusion dates
    if date_str in schedule.exclusion_dates:
        return False

    # 4. Check working days
    if iso_weekday not in schedule.working_days:
        return False

    # 5. Check daily execution hours
    start_t = _parse_time(schedule.daily_start_time)
    end_t = _parse_time(schedule.daily_end_time)

    return _is_time_in_range(slot_time, start_t, end_t)


def _is_time_in_range(target: time, start: time, end: time) -> bool:
    """Determines if target time falls within start and end, including overnight spans."""
    if start <= end:
        return start <= target <= end
    # Overnight window (e.g. 22:00 to 06:00)
    return target >= start or target <= end


def compute_expected_running_hours(
    schedule: NamedSchedule, start_dt: datetime, end_dt: datetime
) -> Decimal:
    """Computes total expected approved running hours across an evaluation window.

    Walks the window in 1-hour increments and computes deterministic approved hours.
    """
    if start_dt >= end_dt:
        return Decimal("0.0")

    approved_slots = 0
    total_slots = 0
    curr = start_dt
    step = timedelta(hours=1)

    while curr < end_dt:
        total_slots += 1
        # Check midpoint of the hour slot
        midpoint = curr + timedelta(minutes=30)
        if is_approved_running_slot(schedule, midpoint):
            approved_slots += 1
        curr += step

    return Decimal(str(approved_slots))


# ==============================================================================
# 3. Standard Schedule Inheritance Engine
# ==============================================================================


class ScheduleEngine:
    """Resolves operational runtime schedules following standard hierarchy precedence.

    Precedence:
    1. RESOURCE level attachment
    2. SERVICE level attachment
    3. SCOPE level attachment
    4. ENVIRONMENT level attachment
    5. BR-007 Non-production rule (dev/staging without schedule defaults to WW_STANDARD_MON_FRI)
    6. TENANT level attachment
    7. Default fallback (WW_STANDARD_MON_FRI)
    """

    NON_PROD_ENVIRONMENTS = {"development", "dev", "staging", "test", "sandbox", "qa"}

    def __init__(self, schedules: dict[str, NamedSchedule] | None = None) -> None:
        self._schedules = dict(schedules or STANDARD_SCHEDULES)

    def register_schedule(self, schedule: NamedSchedule) -> None:
        """Registers a named operational runtime schedule."""
        self._schedules[schedule.id] = schedule

    def get_schedule(self, schedule_id: str) -> NamedSchedule:
        """Retrieves a named schedule by ID."""
        if schedule_id not in self._schedules:
            raise ScheduleNotFoundException(schedule_id=schedule_id)
        return self._schedules[schedule_id]

    def list_schedules(self) -> list[NamedSchedule]:
        """Lists all registered named schedules."""
        return list(self._schedules.values())

    def resolve_schedule(
        self,
        resource_id: str,
        *,
        service_id: str | None = None,
        scope_id: str | None = None,
        environment: str | None = None,
        tenant_id: str | None = None,
        attachments: list[ScheduleAttachment] | None = None,
    ) -> tuple[NamedSchedule, ScheduleLevel]:
        """Resolves the applicable schedule following strict 5-level inheritance and BR-007."""
        att_list = attachments or []

        # 1. RESOURCE level
        for att in att_list:
            if att.level == ScheduleLevel.RESOURCE and att.target_id == resource_id:
                return self.get_schedule(att.schedule_id), ScheduleLevel.RESOURCE

        # 2. SERVICE level
        if service_id:
            for att in att_list:
                if att.level == ScheduleLevel.SERVICE and att.target_id == service_id:
                    return self.get_schedule(att.schedule_id), ScheduleLevel.SERVICE

        # 3. SCOPE level
        if scope_id:
            for att in att_list:
                if att.level == ScheduleLevel.SCOPE and att.target_id == scope_id:
                    return self.get_schedule(att.schedule_id), ScheduleLevel.SCOPE

        # 4. ENVIRONMENT level
        env_norm = (environment or "").strip().lower()
        if env_norm:
            for att in att_list:
                if (
                    att.level == ScheduleLevel.ENVIRONMENT
                    and att.target_id.strip().lower() == env_norm
                ):
                    return self.get_schedule(att.schedule_id), ScheduleLevel.ENVIRONMENT

        # 5. Non-production rule (BR-007):
        # Non-production workloads must not run 24x7 without business justification.
        # If no explicit schedule is set for non-prod, assign standard business hours schedule.
        if env_norm in self.NON_PROD_ENVIRONMENTS:
            return self.get_schedule("WW_STANDARD_MON_FRI"), ScheduleLevel.ENVIRONMENT

        # 6. TENANT level
        if tenant_id:
            for att in att_list:
                if att.level == ScheduleLevel.TENANT and att.target_id == tenant_id:
                    return self.get_schedule(att.schedule_id), ScheduleLevel.TENANT

        # 7. Default fallback: Production workloads default to 24x7, others to standard business hours
        if env_norm in ("production", "prod"):
            return self.get_schedule("WW_CONTINUOUS_24X7"), ScheduleLevel.TENANT

        return self.get_schedule("WW_STANDARD_MON_FRI"), ScheduleLevel.TENANT
