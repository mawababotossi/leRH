from __future__ import annotations

import logging
from datetime import datetime, timedelta
from functools import lru_cache

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, max_requests: int = 20, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window = timedelta(seconds=window_seconds)
        self._buckets: dict[str, list[datetime]] = {}

    def check(self, key: str) -> bool:
        now = datetime.now()
        window_start = now - self.window

        if key not in self._buckets:
            self._buckets[key] = []

        self._buckets[key] = [t for t in self._buckets[key] if t > window_start]

        if len(self._buckets[key]) >= self.max_requests:
            logger.warning("Rate limit exceeded for %s (%d requests)", key, self.max_requests)
            return False

        self._buckets[key].append(now)
        return True


@lru_cache
def get_rate_limiter() -> RateLimiter:
    return RateLimiter()
