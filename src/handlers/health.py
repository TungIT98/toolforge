"""GET /api/health — liveness check. No auth, no LLM call.
"""
from __future__ import annotations

import os
import time

from src.lib.log import get_logger
from src.lib.response import json_response
from src.router import route

log = get_logger("health")

_START_TIME = time.time()


@route("GET", "/api/health")
async def health_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Return 200 OK with environment + uptime info."""
    env_name = os.environ.get("ENVIRONMENT", "development")
    version = os.environ.get("TOOLFORGE_VERSION", "unknown")

    # Best-effort D1 ping (don't fail health if D1 unreachable)
    db_status = "unknown"
    try:
        db = getattr(env, "DB", None)
        if db is not None:
            result = await db.prepare("SELECT 1 AS ok").first()
            db_status = "ok" if (result and result.get("ok") == 1) else "error"
        else:
            db_status = "not_bound"
    except Exception as e:
        db_status = f"error: {e}"

    return json_response(
        {
            "ok": True,
            "status": "ok",
            "service": "toolforge-api",
            "version": version,
            "environment": env_name,
            "uptime_s": int(time.time() - _START_TIME),
            "d1": db_status,
            "ts": time.time(),
        }
    )
