"""Phase 2 Idle and Underutilisation Signal Detection (Prompt 26 Item 164).

Enforces:
- Prompt 26: Ready but disabled behind a feature flag (ENABLE_IDLE_DETECTION = False).
- Prompt 26 Negative Constraint: 'Do not enable idle detection in MVP.'
- Five canonical idle signals:
  1. Idle compute below a utilisation floor across an evaluation window.
  2. Idle storage with no read/write activity across an evaluation window.
  3. Orphaned resources with no parent attachment (unattached disks, IPs).
  4. Zero-usage services incurring billed costs.
  5. Oversized resources with peak utilisation well below provisioned capacity.
- Configurable sensitivity: CONSERVATIVE, BALANCED, AGGRESSIVE.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from decimal import Decimal

from domain.models.exceptions import IdleDetectionDisabledException
from domain.rules.monetary import round_currency
from domain.runtime.models import (
    IdleDetectionSensitivity,
    IdleResourceFinding,
    IdleSignalType,
)

logger = logging.getLogger(__name__)


class IdleSensitivityProfile:
    """Configurable threshold profiles for idle resource detection."""

    def __init__(
        self,
        *,
        cpu_floor_pct: Decimal,
        storage_iops_floor: Decimal,
        cpu_ceiling_pct: Decimal,
        mem_ceiling_pct: Decimal,
        compute_window_days: int,
        storage_window_days: int,
    ) -> None:
        self.cpu_floor_pct = cpu_floor_pct
        self.storage_iops_floor = storage_iops_floor
        self.cpu_ceiling_pct = cpu_ceiling_pct
        self.mem_ceiling_pct = mem_ceiling_pct
        self.compute_window_days = compute_window_days
        self.storage_window_days = storage_window_days


SENSITIVITY_PROFILES: dict[IdleDetectionSensitivity, IdleSensitivityProfile] = {
    IdleDetectionSensitivity.CONSERVATIVE: IdleSensitivityProfile(
        cpu_floor_pct=Decimal("1.0"),
        storage_iops_floor=Decimal("0.0"),
        cpu_ceiling_pct=Decimal("10.0"),
        mem_ceiling_pct=Decimal("15.0"),
        compute_window_days=14,
        storage_window_days=30,
    ),
    IdleDetectionSensitivity.BALANCED: IdleSensitivityProfile(
        cpu_floor_pct=Decimal("5.0"),
        storage_iops_floor=Decimal("0.0"),
        cpu_ceiling_pct=Decimal("20.0"),
        mem_ceiling_pct=Decimal("30.0"),
        compute_window_days=14,
        storage_window_days=14,
    ),
    IdleDetectionSensitivity.AGGRESSIVE: IdleSensitivityProfile(
        cpu_floor_pct=Decimal("10.0"),
        storage_iops_floor=Decimal("5.0"),
        cpu_ceiling_pct=Decimal("35.0"),
        mem_ceiling_pct=Decimal("50.0"),
        compute_window_days=7,
        storage_window_days=7,
    ),
}


class IdleDetector:
    """Detection engine for idle and underutilised cloud capacity.

    STRICT:
    - Feature flag is False by default ('Do not enable idle detection in MVP').
    - Ready and fully tested for Phase 2 activation.
    """

    def __init__(self, enabled: bool = False) -> None:
        # Prompt 26 constraint: Disabled by default in MVP
        self._enabled = enabled

    @property
    def is_enabled(self) -> bool:
        """Returns whether the Phase 2 idle detection feature flag is active."""
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """Enables or disables the idle detection feature flag."""
        self._enabled = enabled

    def _require_enabled(self) -> None:
        """Guards against execution when disabled in MVP."""
        if not self._enabled:
            raise IdleDetectionDisabledException()

    # ==========================================================================
    # 1. Idle Compute Detection
    # ==========================================================================

    def detect_idle_compute(
        self,
        resource_id: str,
        cpu_utilization_series: Sequence[Decimal],
        *,
        sensitivity: IdleDetectionSensitivity = IdleDetectionSensitivity.BALANCED,
        monthly_cost: Decimal = Decimal("72.00"),
        currency: str = "USD",
        bypass_flag_for_test: bool = False,
    ) -> IdleResourceFinding | None:
        """Detects compute instances whose average CPU utilization stays below the floor threshold."""
        if not bypass_flag_for_test:
            self._require_enabled()

        if not cpu_utilization_series:
            return None

        profile = SENSITIVITY_PROFILES[sensitivity]
        avg_cpu = sum(cpu_utilization_series) / Decimal(str(len(cpu_utilization_series)))

        if avg_cpu < profile.cpu_floor_pct:
            return IdleResourceFinding(
                resource_id=resource_id,
                signal_type=IdleSignalType.IDLE_COMPUTE,
                description=(
                    f"Compute resource '{resource_id}' average CPU utilization is {avg_cpu:.1f}%, "
                    f"which is below the {profile.cpu_floor_pct:.1f}% idle floor over {profile.compute_window_days} days."
                ),
                observed_metric_value=avg_cpu,
                threshold_value=profile.cpu_floor_pct,
                waste_estimate_monthly=round_currency(monthly_cost),
                currency=currency,
                recommended_action="Stop or decommission idle instance to eliminate compute spend.",
            )

        return None

    # ==========================================================================
    # 2. Idle Storage Detection
    # ==========================================================================

    def detect_idle_storage(
        self,
        resource_id: str,
        activity_iops_series: Sequence[Decimal],
        *,
        sensitivity: IdleDetectionSensitivity = IdleDetectionSensitivity.BALANCED,
        monthly_cost: Decimal = Decimal("25.00"),
        currency: str = "USD",
        bypass_flag_for_test: bool = False,
    ) -> IdleResourceFinding | None:
        """Detects block/object storage with zero or near-zero read/write activity."""
        if not bypass_flag_for_test:
            self._require_enabled()

        if not activity_iops_series:
            return None

        profile = SENSITIVITY_PROFILES[sensitivity]
        max_activity = max(activity_iops_series)

        if max_activity <= profile.storage_iops_floor:
            return IdleResourceFinding(
                resource_id=resource_id,
                signal_type=IdleSignalType.IDLE_STORAGE,
                description=(
                    f"Storage volume '{resource_id}' has recorded no read/write IOPS activity "
                    f"(max: {max_activity:.1f}) across {profile.storage_window_days} days."
                ),
                observed_metric_value=max_activity,
                threshold_value=profile.storage_iops_floor,
                waste_estimate_monthly=round_currency(monthly_cost),
                currency=currency,
                recommended_action="Create snapshot backup and release unattached or inactive volume.",
            )

        return None

    # ==========================================================================
    # 3. Orphaned Resource Detection
    # ==========================================================================

    def detect_orphaned_resource(
        self,
        resource_id: str,
        *,
        resource_type: str,
        has_parent_attachment: bool,
        monthly_cost: Decimal = Decimal("15.00"),
        currency: str = "USD",
        bypass_flag_for_test: bool = False,
    ) -> IdleResourceFinding | None:
        """Detects resources with no parent attachment (e.g. unattached EBS, unassociated Elastic IP)."""
        if not bypass_flag_for_test:
            self._require_enabled()

        if not has_parent_attachment:
            return IdleResourceFinding(
                resource_id=resource_id,
                signal_type=IdleSignalType.ORPHANED_RESOURCE,
                description=(
                    f"{resource_type} '{resource_id}' is orphaned with no active parent host or gateway attachment."
                ),
                observed_metric_value=Decimal("0.0"),
                threshold_value=Decimal("1.0"),
                waste_estimate_monthly=round_currency(monthly_cost),
                currency=currency,
                recommended_action="Release or delete unattached resource to stop ongoing reservation charges.",
            )

        return None

    # ==========================================================================
    # 4. Zero-Usage Services Incurring Cost
    # ==========================================================================

    def detect_zero_usage_incurring_cost(
        self,
        resource_id: str,
        usage_records_count: int,
        billed_cost_monthly: Decimal,
        *,
        currency: str = "USD",
        bypass_flag_for_test: bool = False,
    ) -> IdleResourceFinding | None:
        """Detects provisioned services incurring monthly charges with zero consumption/requests."""
        if not bypass_flag_for_test:
            self._require_enabled()

        if usage_records_count == 0 and billed_cost_monthly > Decimal("0.0"):
            return IdleResourceFinding(
                resource_id=resource_id,
                signal_type=IdleSignalType.ZERO_USAGE_INCURRING_COST,
                description=(
                    f"Service '{resource_id}' incurred {currency} {billed_cost_monthly:.2f} but recorded zero usage."
                ),
                observed_metric_value=Decimal("0.0"),
                threshold_value=Decimal("1.0"),
                waste_estimate_monthly=round_currency(billed_cost_monthly),
                currency=currency,
                recommended_action="Decommission unused service or downscale to pay-per-request tier.",
            )

        return None

    # ==========================================================================
    # 5. Oversized Resources Detection
    # ==========================================================================

    def detect_oversized_resource(
        self,
        resource_id: str,
        *,
        peak_cpu_pct: Decimal,
        peak_memory_pct: Decimal,
        monthly_waste_estimate: Decimal = Decimal("120.00"),
        sensitivity: IdleDetectionSensitivity = IdleDetectionSensitivity.BALANCED,
        currency: str = "USD",
        bypass_flag_for_test: bool = False,
    ) -> IdleResourceFinding | None:
        """Detects provisioned resources whose peak utilisation is well below capacity."""
        if not bypass_flag_for_test:
            self._require_enabled()

        profile = SENSITIVITY_PROFILES[sensitivity]

        if peak_cpu_pct < profile.cpu_ceiling_pct and peak_memory_pct < profile.mem_ceiling_pct:
            return IdleResourceFinding(
                resource_id=resource_id,
                signal_type=IdleSignalType.OVERSIZED_RESOURCE,
                description=(
                    f"Resource '{resource_id}' is oversized: peak CPU is {peak_cpu_pct:.1f}% "
                    f"(ceiling {profile.cpu_ceiling_pct:.1f}%) and peak RAM is {peak_memory_pct:.1f}% "
                    f"(ceiling {profile.mem_ceiling_pct:.1f}%)."
                ),
                observed_metric_value=max(peak_cpu_pct, peak_memory_pct),
                threshold_value=min(profile.cpu_ceiling_pct, profile.mem_ceiling_pct),
                waste_estimate_monthly=round_currency(monthly_waste_estimate),
                currency=currency,
                recommended_action="Right-size to a smaller instance SKU to reduce overprovisioned capacity.",
            )

        return None
