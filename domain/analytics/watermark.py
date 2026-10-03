"""Incremental Watermark Tracking & Restatement Versioning Engine (Prompt 56 / BBP Section 36).

Enforces:
- High-watermark extraction state tracking per tenant and partition period.
- Deterministic restatement handling: restated periods are re-emitted in full
  with an incremented version number rather than patched in-place.
- Downstream supersession rule enforcement: higher version numbers unconditionally
  supersede previous version extracts.
"""

from __future__ import annotations

import datetime as dt
import threading

from pydantic import BaseModel, Field


class PartitionWatermark(BaseModel):
    """Watermark and version tracking state for a single tenant partition period."""

    tenant_id: str
    period: str
    current_version: int = 1
    last_watermark_timestamp: str = Field(
        default_factory=lambda: dt.datetime.now(dt.UTC).isoformat()
    )
    last_extract_timestamp: str | None = None
    is_restated: bool = False
    superseded_versions: list[int] = Field(default_factory=list)


class WatermarkTracker:
    """Thread-safe watermark and version coordinator for analytical extracts."""

    AUTHORITATIVE_SUPERSESSION_POLICY = (
        "Higher version number unconditionally supersedes earlier versions for this tenant and period partition. "
        "Downstream BI consumers must drop or replace records from superseded versions."
    )

    def __init__(self) -> None:
        self._watermarks: dict[tuple[str, str], PartitionWatermark] = {}
        self._lock = threading.RLock()

    def get_watermark(self, tenant_id: str, period: str) -> PartitionWatermark:
        """Retrieves or initializes the watermark record for a tenant partition period."""
        key = (tenant_id, period)
        with self._lock:
            if key not in self._watermarks:
                self._watermarks[key] = PartitionWatermark(
                    tenant_id=tenant_id,
                    period=period,
                    current_version=1,
                    last_watermark_timestamp=dt.datetime.now(dt.UTC).isoformat(),
                )
            return self._watermarks[key].model_copy()

    def update_watermark(
        self, tenant_id: str, period: str, new_watermark_ts: str
    ) -> PartitionWatermark:
        """Updates high watermark timestamp for incremental extract."""
        key = (tenant_id, period)
        with self._lock:
            wm = self.get_watermark(tenant_id, period)
            wm.last_watermark_timestamp = new_watermark_ts
            wm.last_extract_timestamp = dt.datetime.now(dt.UTC).isoformat()
            self._watermarks[key] = wm
            return wm.model_copy()

    def trigger_restatement(
        self, tenant_id: str, period: str, reason: str = "Invoice Restatement"
    ) -> tuple[int, int]:
        """Bumps version on restatement and returns (new_version, superseded_version).

        Restatement Rule (Prompt 56):
        A restated period is re-emitted in full with a new version stamp rather than patched,
        so downstream consumers have an unambiguous rule for what supersedes what.
        """
        _ = reason
        key = (tenant_id, period)
        with self._lock:
            wm = self.get_watermark(tenant_id, period)
            old_version = wm.current_version
            new_version = old_version + 1
            wm.superseded_versions.append(old_version)
            wm.current_version = new_version
            wm.is_restated = True
            wm.last_watermark_timestamp = dt.datetime.now(dt.UTC).isoformat()
            self._watermarks[key] = wm
            return new_version, old_version
