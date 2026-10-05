"""Rate-Limiting, Abuse Detection & Account Lockout Tracker (Prompt R-FEAT / IMP-07).

Governs:
- 429 rate limit events recording per token / IP.
- Top API callers metrics and call volume aggregation.
- Authentication failure source tracking.
- Automated progressive lockout after N consecutive failures (M1/M2 driven).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from masterdata.improvement_features import get_feature_config

logger = logging.getLogger("cloudlens.domain.abuse")


class AbuseTracker:
    """Thread-safe tracker for API consumption metrics, rate limiting events, and abuse lockout."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._config = get_feature_config("IMP_07_RATE_LIMIT_ABUSE")
        self._rate_limit_hits: Counter[str] = Counter()
        self._caller_counts: Counter[str] = Counter()
        self._auth_failures: dict[str, list[float]] = {}
        self._locked_principals: dict[str, float] = {}  # key -> unlock_time_epoch
        self._recent_events: list[dict[str, Any]] = []

    def record_call(self, caller_id: str) -> None:
        """Records a successful or standard API call from caller."""
        with self._lock:
            self._caller_counts[caller_id] += 1

    def record_429(self, caller_id: str, path: str) -> None:
        """Records a 429 rate limit hit."""
        with self._lock:
            self._rate_limit_hits[caller_id] += 1
            event = {
                "type": "RATE_LIMIT_429",
                "caller_id": caller_id,
                "path": path,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            self._recent_events.append(event)
            if len(self._recent_events) > 500:
                self._recent_events = self._recent_events[-500:]

    def is_locked_out(self, principal_id: str) -> tuple[bool, int]:
        """Checks if principal (user or IP) is currently in lockout. Returns (is_locked, remaining_seconds)."""
        now = time.time()
        with self._lock:
            unlock_time = self._locked_principals.get(principal_id)
            if not unlock_time:
                return False, 0
            if now >= unlock_time:
                # Lockout expired
                self._locked_principals.pop(principal_id, None)
                self._auth_failures.pop(principal_id, None)
                return False, 0
            remaining = int(unlock_time - now)
            return True, remaining

    def record_auth_failure(self, principal_id: str, ip_address: str | None = None) -> tuple[bool, int]:
        """Records authentication failure and triggers lockout if max attempts exceeded.

        Returns (is_now_locked, remaining_seconds).
        """
        now = time.time()
        window_seconds = self._config.get("abuse_detection_window_seconds", 60)
        max_failures = self._config.get("lockout_max_failures", 5)
        lockout_duration = self._config.get("lockout_duration_seconds", 900)

        with self._lock:
            failures = self._auth_failures.setdefault(principal_id, [])
            # Evict failures outside the window
            failures = [ts for ts in failures if (now - ts) <= window_seconds]
            failures.append(now)
            self._auth_failures[principal_id] = failures

            if len(failures) >= max_failures:
                unlock_time = now + lockout_duration
                self._locked_principals[principal_id] = unlock_time
                event = {
                    "type": "ACCOUNT_LOCKOUT",
                    "principal_id": principal_id,
                    "ip_address": ip_address,
                    "duration_seconds": lockout_duration,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                self._recent_events.append(event)
                logger.warning(
                    "Security lockout activated for principal '%s' after %d failed attempts",
                    principal_id,
                    len(failures),
                )
                return True, lockout_duration

            return False, 0

    def record_auth_success(self, principal_id: str) -> None:
        """Clears failure count on successful sign-in."""
        with self._lock:
            self._auth_failures.pop(principal_id, None)

    def unlock_principal(self, principal_id: str) -> bool:
        """Manually unlocks a locked principal (admin override)."""
        with self._lock:
            existed = principal_id in self._locked_principals
            self._locked_principals.pop(principal_id, None)
            self._auth_failures.pop(principal_id, None)
            return existed

    def get_abuse_summary(self) -> dict[str, Any]:
        """Returns consolidated rate-limiting and abuse telemetry for Control Tower."""
        now = time.time()
        with self._lock:
            # Active lockouts
            active_lockouts = []
            for princ, unlock_ts in list(self._locked_principals.items()):
                if unlock_ts > now:
                    active_lockouts.append({
                        "principal_id": princ,
                        "remaining_seconds": int(unlock_ts - now),
                        "unlocks_at": datetime.fromtimestamp(unlock_ts, UTC).isoformat(),
                    })
                else:
                    self._locked_principals.pop(princ, None)

            top_callers = [
                {"caller": k, "requests": v}
                for k, v in self._caller_counts.most_common(10)
            ]
            top_429s = [
                {"caller": k, "rate_limited_count": v}
                for k, v in self._rate_limit_hits.most_common(10)
            ]

            return {
                "active_lockouts": active_lockouts,
                "lockout_count": len(active_lockouts),
                "total_429_events": sum(self._rate_limit_hits.values()),
                "top_callers": top_callers,
                "top_rate_limited_callers": top_429s,
                "recent_security_events": list(reversed(self._recent_events[-20:])),
                "timestamp": datetime.now(UTC).isoformat(),
            }


_ABUSE_TRACKER_INSTANCE = AbuseTracker()


def get_abuse_tracker() -> AbuseTracker:
    """Returns singleton abuse tracker instance."""
    return _ABUSE_TRACKER_INSTANCE
