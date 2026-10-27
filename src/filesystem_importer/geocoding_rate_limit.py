
# =============================================================================
#
# Filesystem Importer
#
# Copyright (c) 2026 Geoff <dev.photomanager@gmail.com>
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# =============================================================================

"""Shared rate limiter for geocoding requests."""

import threading
import time
from collections.abc import Callable

from filesystem_importer.app_logging import get_logger

logger = get_logger(__name__)


class GeocodingRateLimiter:
    """Enforce a minimum interval between the starts of requests."""

    def __init__(
        self,
        min_interval_seconds: float = 1.0,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if min_interval_seconds < 0:
            raise ValueError("Minimum interval cannot be negative.")

        self._min_interval_seconds = float(min_interval_seconds)
        self._clock = clock
        self._sleep = sleep
        self._last_request_started_at: float | None = None
        self._lock = threading.Lock()

        logger.debug(
            "Created geocoding rate limiter with minimum interval %.3f "
            "seconds.",
            self._min_interval_seconds,
        )

    def set_min_interval_seconds(self, interval: float) -> None:
        """Update the interval while preserving this shared limiter instance."""
        if isinstance(interval, bool) or not isinstance(interval, (int, float)):
            raise TypeError("Minimum interval must be a number.")

        if interval < 0:
            raise ValueError("Minimum interval cannot be negative.")

        with self._lock:
            self._min_interval_seconds = float(interval)
            logger.info(
                "Geocoding minimum request interval set to %.3f seconds.",
                self._min_interval_seconds,
            )

    def wait_for_slot(self) -> float:
        """Wait until a request may start, then reserve its time slot.

        Returns the monotonic timestamp reserved for this request.

        Call this immediately before making each geocoding HTTP request.
        The lock ensures concurrent callers share the same schedule.
        """
        with self._lock:
            now = self._clock()

            if self._last_request_started_at is not None:
                elapsed = now - self._last_request_started_at
                remaining = self._min_interval_seconds - elapsed

                while remaining > 0:
                    logger.debug(
                        "Geocoding request waiting %.3f seconds for "
                        "the rate limit.",
                        remaining,
                    )
                    self._sleep(remaining)

                    now = self._clock()
                    elapsed = now - self._last_request_started_at
                    remaining = self._min_interval_seconds - elapsed

            # Reserve the next slot before releasing the lock. This prevents
            # another caller from being granted the same time slot.
            request_started_at = self._clock()
            self._last_request_started_at = request_started_at

            logger.debug(
                "Geocoding request slot granted at monotonic time %.3f.",
                request_started_at,
            )

            return request_started_at


# All forward and reverse geocoding modules must share this instance.
geocoding_rate_limiter = GeocodingRateLimiter()

