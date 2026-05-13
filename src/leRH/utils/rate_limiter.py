from __future__ import annotations

from leRH.utils.shared_rate_limiter import SharedRateLimiter

# Shared instance is fine since it uses the DB
_limiter = SharedRateLimiter()


async def check_rate_limit(key: str) -> bool:
    return await _limiter.check(key)
