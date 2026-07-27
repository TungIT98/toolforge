"""Rate limit middleware helper — apply to handlers manually.

CF Workers Python doesn't have decorator syntax that works on top-level
handler functions (decorators run at import time, but we need env at request
time). So we use a helper function called from each handler.

Usage in handler:
    async def my_handler(request, env, ctx):
        allowed, count, limit = await check_rate_limit(request, env, "/api/foo")
        if not allowed:
            return rate_limit_response()
        # ... rest of handler
"""
from __future__ import annotations

from src.lib.rate_limit import check_rate_limit, rate_limit_response


async def apply_rate_limit(request, env, endpoint: str, limit: int | None = None):
    """Apply rate limit. Returns Response if blocked, None if allowed."""
    allowed, count, limit = await check_rate_limit(request, env, endpoint, limit=limit)
    if not allowed:
        return rate_limit_response()
    return None
