"""Incremental Watermark Tracking & Restatement Versioning Engine (Prompt P08 / BBP Section 36).

Enforces:
- High-watermark extraction state tracking per tenant and partition period in PostgreSQL.
- Deterministic restatement handling: restated periods are re-emitted in full
  with an incremented version number rather than patched in-place.
- Downstream supersession rule enforcement: higher version numbers unconditionally
  supersede previous version extracts.
- Persistence across server restarts via partition_watermarks table.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text

from db.session import get_tenant_session, run_async

logger = logging.getLogger("cloudlens.analytics.watermark")


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
    """Thread-safe persistent watermark and version coordinator for analytical extracts."""

    AUTHORITATIVE_SUPERSESSION_POLICY = (
        "Higher version number unconditionally supersedes earlier versions for this tenant and period partition. "
        "Downstream BI consumers must drop or replace records from superseded versions."
    )

    def get_watermark(self, tenant_id: str, period: str) -> PartitionWatermark:
        """Retrieves or initializes the watermark record for a tenant partition period."""
        async def _get():
            async with get_tenant_session(tenant_id) as sess:
                res = await sess.execute(
                    text("""
                        SELECT current_version, last_watermark_timestamp, last_extract_timestamp, is_restated, superseded_versions
                        FROM partition_watermarks
                        WHERE tenant_id = :tenant_id AND period = :period
                        LIMIT 1;
                    """),
                    {"tenant_id": tenant_id, "period": period},
                )
                row = res.fetchone()
                if row:
                    raw_sup = row[4]
                    sup = raw_sup if isinstance(raw_sup, list) else (json.loads(raw_sup) if raw_sup else [])
                    return PartitionWatermark(
                        tenant_id=tenant_id,
                        period=period,
                        current_version=row[0],
                        last_watermark_timestamp=row[1] or dt.datetime.now(dt.UTC).isoformat(),
                        last_extract_timestamp=row[2],
                        is_restated=bool(row[3]),
                        superseded_versions=sup,
                    )

                # Initialize in DB
                now_iso = dt.datetime.now(dt.UTC).isoformat()
                wid = f"wm-{tenant_id}-{period}"
                await sess.execute(
                    text("""
                        INSERT INTO partition_watermarks (
                            id, tenant_id, period, current_version, last_watermark_timestamp,
                            last_extract_timestamp, is_restated, superseded_versions, updated_at
                        )
                        VALUES (
                            :id, :tenant_id, :period, 1, :now_iso, NULL, false, '[]'::jsonb, :now
                        )
                        ON CONFLICT (tenant_id, period) DO NOTHING;
                    """),
                    {
                        "id": wid,
                        "tenant_id": tenant_id,
                        "period": period,
                        "now_iso": now_iso,
                        "now": dt.datetime.now(dt.UTC),
                    },
                )
                await sess.commit()
                return PartitionWatermark(
                    tenant_id=tenant_id,
                    period=period,
                    current_version=1,
                    last_watermark_timestamp=now_iso,
                )

        return run_async(_get())

    def update_watermark(
        self, tenant_id: str, period: str, new_watermark_ts: str
    ) -> PartitionWatermark:
        """Updates high watermark timestamp for incremental extract."""
        async def _update():
            extract_ts = dt.datetime.now(dt.UTC).isoformat()
            wid = f"wm-{tenant_id}-{period}"
            now = dt.datetime.now(dt.UTC)
            async with get_tenant_session(tenant_id) as sess:
                await sess.execute(
                    text("""
                        INSERT INTO partition_watermarks (
                            id, tenant_id, period, current_version, last_watermark_timestamp,
                            last_extract_timestamp, is_restated, superseded_versions, updated_at
                        )
                        VALUES (
                            :id, :tenant_id, :period, 1, :new_ts, :extract_ts, false, '[]'::jsonb, :now
                        )
                        ON CONFLICT (tenant_id, period) DO UPDATE SET
                            last_watermark_timestamp = EXCLUDED.last_watermark_timestamp,
                            last_extract_timestamp = EXCLUDED.last_extract_timestamp,
                            updated_at = EXCLUDED.updated_at;
                    """),
                    {
                        "id": wid,
                        "tenant_id": tenant_id,
                        "period": period,
                        "new_ts": new_watermark_ts,
                        "extract_ts": extract_ts,
                        "now": now,
                    },
                )
                await sess.commit()

        run_async(_update())
        return self.get_watermark(tenant_id, period)

    def trigger_restatement(
        self, tenant_id: str, period: str, reason: str = "Invoice Restatement"
    ) -> tuple[int, int]:
        """Bumps version on restatement and returns (new_version, superseded_version)."""
        _ = reason
        wm = self.get_watermark(tenant_id, period)
        old_version = wm.current_version
        new_version = old_version + 1
        superseded = list(wm.superseded_versions)
        superseded.append(old_version)
        now_iso = dt.datetime.now(dt.UTC).isoformat()

        async def _trigger():
            wid = f"wm-{tenant_id}-{period}"
            now = dt.datetime.now(dt.UTC)
            async with get_tenant_session(tenant_id) as sess:
                await sess.execute(
                    text("""
                        UPDATE partition_watermarks
                        SET current_version = :new_ver,
                            is_restated = true,
                            superseded_versions = :sup,
                            last_watermark_timestamp = :now_iso,
                            updated_at = :now
                        WHERE tenant_id = :tenant_id AND period = :period;
                    """),
                    {
                        "new_ver": new_version,
                        "sup": json.dumps(superseded),
                        "now_iso": now_iso,
                        "now": now,
                        "tenant_id": tenant_id,
                        "period": period,
                    },
                )
                await sess.commit()

        run_async(_trigger())
        return new_version, old_version
