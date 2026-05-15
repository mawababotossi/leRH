from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select

from leRH.db.base import async_session_factory
from leRH.db.models import RateLimitEntry

logger = logging.getLogger(__name__)


class SharedRateLimiter:
    """Rate limiter utilisant la base de données pour fonctionner entre plusieurs processus."""

    def __init__(self, max_requests: int = 20, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window = window_seconds

    async def check(self, key: str) -> bool:
        now = datetime.now()
        window_start = now - timedelta(seconds=self.window)

        try:
            async with async_session_factory() as session:
                await session.execute(
                    delete(RateLimitEntry).where(RateLimitEntry.timestamp < window_start)
                )

                result = await session.execute(
                    select(func.count(RateLimitEntry.key)).where(
                        RateLimitEntry.key == key, RateLimitEntry.timestamp > window_start
                    )
                )
                count = result.scalar() or 0

                if count >= self.max_requests:
                    logger.warning(
                        "Rate limit exceeded for %s (%d requests)", key, self.max_requests
                    )
                    await session.commit()
                    return False

                session.add(RateLimitEntry(key=key, timestamp=now))
                await session.commit()
                return True
        except Exception as e:
            logger.error("Rate limiter error: %s", e)
            return True
