"""Request monitoring + critical error logging to KV.

Features:
- Generate unique request_id per request (UUID v4)
- Log critical errors to KV with 7-day TTL (queriable via /api/admin/errors)
- Module state for request_id (consistent with CORS pattern)
- Includes Vary: Origin etc considerations

Usage:
    from src.lib.monitoring import generate_request_id, log_error_to_kv, get_request_id

    rid = generate_request_id()
    set_request_id(rid)
    ...
    await log_error_to_kv(env, severity="error", endpoint="/api/foo",
                          error="DB failed", code="DB_ERROR")
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

# === Module-level state for request_id ===
# CF Workers: module persists across requests in same isolate
# Always set fresh on every request via set_request_id() in dispatch
_current_request_id: str = ""


def generate_request_id() -> str:
    """Generate a unique request ID (UUID v4)."""
    try:
        return str(uuid.uuid4())
    except Exception:
        # Fallback if uuid not available
        return f"req-{int(time.time() * 1000000)}-{os.urandom(4).hex()}"


def set_request_id(request_id: str) -> None:
    """Set the current request ID. Call at the start of every request."""
    global _current_request_id
    _current_request_id = request_id


def get_request_id() -> str:
    """Get the current request ID. Returns empty string if not set."""
    return _current_request_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


async def log_error_to_kv(
    env: Any,
    severity: str,
    endpoint: str,
    error: str,
    code: str | None = None,
    request_id: str | None = None,
    **fields: Any,
) -> bool:
    """Log a critical error to KV for later retrieval.

    Stored at key `error:{iso_ts}:{request_id}` with 7-day TTL.

    Severity levels: "error" (5xx), "warn" (4xx), "info" (notable)
    Returns True if logged successfully, False if KV not bound or error.

    NEVER raises — monitoring must not break the request path.
    """
    try:
        cache = getattr(env, "CACHE", None)
        if cache is None:
            return False
        ts = _now_iso()
        rid = request_id or get_request_id() or "unknown"
        payload = {
            "ts": ts,
            "request_id": rid,
            "severity": severity,
            "endpoint": endpoint,
            "error": error[:500] if error else "",  # cap to avoid huge KV values
            "code": code,
            **{k: str(v)[:200] for k, v in fields.items()},  # cap field values
        }
        # Sort key: error:{ts}:{rid} — lexicographic sort = chronological
        key = f"error:{ts}:{rid}"
        await cache.put(key, json.dumps(payload, ensure_ascii=False), expiration_ttl=7 * 24 * 3600)
        return True
    except Exception as e:
        # Never let monitoring break the request
        try:
            print(f"log_error_to_kv failed silently: {e}")
        except Exception:
            pass
        return False


async def list_recent_errors(env: Any, limit: int = 50, severity: str | None = None) -> list[dict]:
    """List recent errors from KV (newest first).

    Args:
        env: Worker env
        limit: Max errors to return (1-200)
        severity: Filter by severity ("error", "warn", "info"). None = all.

    Returns:
        List of error dicts, newest first. Empty list if KV not bound.
    """
    try:
        cache = getattr(env, "CACHE", None)
        if cache is None:
            return []
        limit = max(1, min(200, limit))
        result = await cache.list(prefix="error:", limit=limit)
        # CF Workers: list() returns dict with 'keys' (each key has 'name', 'expiration')
        keys = result.get("keys", []) if isinstance(result, dict) else (result or [])
        errors: list[dict] = []
        for item in keys:
            if isinstance(item, dict):
                key = item.get("name")
            else:
                key = item
            if not key:
                continue
            value = await cache.get(key, "text")
            if not value:
                continue
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except Exception:
                    continue
            if not isinstance(value, dict):
                continue
            # Filter by severity if specified
            if severity and value.get("severity") != severity:
                continue
            errors.append(value)
        # Sort by ts descending (newest first). KV list may not be sorted.
        errors.sort(key=lambda e: e.get("ts", ""), reverse=True)
        return errors[:limit]
    except Exception:
        return []


def get_error_count_by_severity(errors: list[dict]) -> dict[str, int]:
    """Aggregate error counts by severity for admin dashboard."""
    counts = {"error": 0, "warn": 0, "info": 0}
    for e in errors:
        sev = e.get("severity", "info")
        counts[sev] = counts.get(sev, 0) + 1
    return counts
