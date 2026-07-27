"""Rate limit — KV-based fixed window counter.

Pattern:
- Key: rl:{ip}:{endpoint}:{minute_bucket}
- Value: count
- TTL: 90s (auto-cleanup)
- On each request: get → check → incr with TTL

Race condition: 2 concurrent requests may both pass. Acceptable for MVP
(can upgrade to sliding window with timestamps later).

CF KV: 100K reads/day, 1K writes/day free tier. With 90s TTL + per-minute
window, average writes per IP per endpoint: 1/min. 1K writes = 1K unique
IP+endpoint per day free. Realistic for small/medium traffic.

Production scale: upgrade to Durable Objects for atomic counters.
"""
from __future__ import annotations

import time
from typing import Any

from src.lib.log import get_logger

log = get_logger("rate_limit")


# Default rate limits per endpoint (requests per minute)
DEFAULT_LIMITS: dict[str, int] = {
    # Public endpoints — generous
    "/api/health": 300,             # 5/s — for health monitoring
    "/api/version": 60,              # 1/s
    "/api/store/tools": 120,         # 2/s
    "/api/store/tools/{tool_id}": 120,
    "/api/store/stats": 60,
    "/api/store/seed": 5,            # owner only
    "/api/builder/session": 30,      # 0.5/s — generous for chat
    "/api/builder/session/{session_id}/message": 60,  # 1/s
    "/api/builder/session/{session_id}/build": 10,   # build is expensive
    "/api/license/verify": 300,      # high — Tauri apps check on startup
    "/api/license/check": 300,
    # AI endpoints — strict (cost)
    "/api/llm/test": 10,             # 1/6s
    "/api/scout/run": 5,             # 1/12s — runs LLM + Tavily
    "/api/architect/spec": 10,       # 1/6s
    "/api/forge/build": 10,          # 1/6s
    "/api/forge/build-binary": 5,    # 1/12s — triggers GH Action
    "/api/forge/license": 10,        # license gen
    # Payment — strict
    "/api/payment/orders": 30,
    "/api/payment/sepay-webhook": 100,  # SePay can retry
    "/api/payment/test": 10,
    # Admin — strict
    "/api/admin/overview": 60,
    "/api/admin/orders": 60,
    "/api/admin/licenses": 60,
    "/api/admin/specs/{id}/approve": 30,
    # Webhook — internal, no limit (CF IP allowlist handles)
    "/api/forge/webhook/built": 1000,
}


def get_endpoint_limit(path: str) -> int:
    """Get rate limit for endpoint, with fallback default.

    Order:
    1. Exact match in DEFAULT_LIMITS
    2. Strip trailing path segments for parameterized routes
    3. Default 60 req/min
    """
    # Exact match
    if path in DEFAULT_LIMITS:
        return DEFAULT_LIMITS[path]
    # Try matching with wildcards (e.g. /api/admin/specs/123/approve -> /api/admin/specs/{id}/approve)
    for pattern, limit in DEFAULT_LIMITS.items():
        if "{" in pattern:
            # Simple pattern match
            regex = "^" + pattern.replace("{tool_id}", "[^/]+").replace("{id}", "[^/]+").replace("{session_id}", "[^/]+").replace("{job_id}", "[^/]+").replace("{build_id}", "[^/]+") + "$"
            import re
            if re.match(regex, path):
                return limit
    return 60  # default


def get_client_ip(request: Any) -> str:
    """Extract client IP from request headers (Cloudflare-specific)."""
    # Cloudflare provides CF-Connecting-IP header
    return (
        request.headers.get("CF-Connecting-IP")  # type: ignore[attr-defined]
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()  # type: ignore[attr-defined]
        or "unknown"
    )


async def check_rate_limit(
    request: Any,
    env: Any,
    endpoint: str,
    limit: int | None = None,
    window_seconds: int = 60,
) -> tuple[bool, int, int]:
    """Check if request is within rate limit.

    Args:
        request: Cloudflare request object
        env: Cloudflare env binding (has .CACHE KV)
        endpoint: Path being rate-limited (e.g. "/api/llm/test")
        limit: Custom limit (default: from DEFAULT_LIMITS or 60)
        window_seconds: Window size (default 60s = per minute)

    Returns:
        (allowed, current_count, limit_value)
        If allowed=False, caller should return 429
    """
    if limit is None:
        limit = get_endpoint_limit(endpoint)
    if limit <= 0:
        return True, 0, 0  # disabled

    cache = getattr(env, "CACHE", None)
    if cache is None:
        # No KV bound — fail open (allow request)
        log.warn("rate_limit_no_kv", endpoint=endpoint)
        return True, 0, limit

    ip = get_client_ip(request)
    now = int(time.time())
    bucket = now // window_seconds
    key = f"rl:{ip}:{endpoint}:{bucket}"

    try:
        # Get current count
        existing = await cache.get(key, "json")
        current = int(existing) if existing else 0
        if current >= limit:
            log.warn("rate_limit_exceeded", endpoint=endpoint, ip=ip, count=current, limit=limit)
            return False, current, limit
        # Increment (write with TTL)
        # KV doesn't have atomic INCR + EXPIRE; do read-then-write
        new_count = current + 1
        await cache.put(key, str(new_count), expiration_ttl=window_seconds + 30)
        return True, new_count, limit
    except Exception as e:
        # Fail open on error
        log.warn("rate_limit_error", err=str(e), endpoint=endpoint)
        return True, 0, limit


def rate_limit_response(retry_after: int = 60) -> "Response":
    """Return 429 Too Many Requests response."""
    from src.lib.response import error_response
    return error_response(
        f"Rate limit exceeded. Retry in {retry_after}s.",
        status=429,
        code="RATE_LIMITED",
    )
