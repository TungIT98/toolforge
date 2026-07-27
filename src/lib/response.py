"""JSON response helpers for ToolForge Workers.

Standardize response format across all endpoints. Cloudflare Workers
use the JS Response class; we wrap it with Python-friendly helpers.

Falls back to a local shim when `workers` module is not available
(local dev / tests on CPython).

CORS configuration:
- Empty list (default) → "Access-Control-Allow-Origin: *" (dev mode)
- Non-empty list → match Origin header against list
  - Match → return that origin
  - No match → return empty (browser will block)
- Set via configure_cors() at worker startup
"""
from __future__ import annotations

import json
import os
from typing import Any

# Lazy import Response with fallback shim for local dev / pytest
try:
    from workers import Response as _CfResponse  # type: ignore
    Response = _CfResponse
except ImportError:
    class Response:  # type: ignore[no-redef]
        """Local shim matching CF Workers Response interface for unit tests."""

        def __init__(self, body: str, status: int = 200, headers: dict | None = None):
            self.body = body
            self.status = status
            self.headers = headers or {}


# === CORS configuration (module-level state) ===
# CF Workers: module persists across requests in same isolate → safe to use module state
# Empty list = wildcard (dev mode)
_allowed_origins: list[str] = []


def configure_cors(origins_csv: str | None = None, env: Any | None = None) -> None:
    """Configure allowed CORS origins. Call from worker dispatch() at request start.

    Args:
        origins_csv: Comma-separated origins. Empty/None = '*' (dev mode).
        env: Optional env object. If provided, reads ALLOWED_ORIGINS from env.

    Example:
        configure_cors(env=env)  # reads env.ALLOWED_ORIGINS or os.environ["ALLOWED_ORIGINS"]
    """
    global _allowed_origins
    # Resolve from env if not directly passed
    if env is not None and not origins_csv:
        origins_csv = getattr(env, "ALLOWED_ORIGINS", "") or os.environ.get("ALLOWED_ORIGINS", "")
    if not origins_csv:
        _allowed_origins = []
        return
    _allowed_origins = [o.strip() for o in origins_csv.split(",") if o.strip()]


def _get_cors_origin(request: Any | None = None) -> str:
    """Resolve the right Access-Control-Allow-Origin value for this request.

    - No allowed origins configured → '*' (dev mode)
    - Allowed origins configured:
        - If request has Origin header matching one of them → return that origin
        - If no match → return '' (browser will block)
    """
    if not _allowed_origins:
        return "*"
    origin = None
    if request is not None:
        try:
            origin = (
                request.headers.get("Origin")  # type: ignore[attr-defined]
                or request.headers.get("origin")
            )
        except Exception:
            origin = None
    if origin and origin in _allowed_origins:
        return origin
    return ""


def json_response(
    data: Any,
    status: int = 200,
    headers: dict[str, str] | None = None,
    request: Any | None = None,
) -> Response:
    """Return a JSON response with CORS headers.

    Args:
        data: Any JSON-serializable object
        status: HTTP status code (default 200)
        headers: Additional headers to merge
        request: Optional request for per-request CORS origin matching

    Returns:
        Response object (CF Workers in prod, local shim in tests)
    """
    base_headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": _get_cors_origin(request),
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Webhook-Secret",
        "Access-Control-Max-Age": "86400",
    }
    if headers:
        base_headers.update(headers)

    body = json.dumps(data, ensure_ascii=False, default=str)
    return Response(body, status=status, headers=base_headers)


def error_response(
    message: str,
    status: int = 400,
    code: str | None = None,
    details: Any = None,
    request: Any | None = None,
) -> Response:
    """Return a standardized error response.

    Format:
        {
            "ok": false,
            "error": {
                "code": "INVALID_INPUT",
                "message": "...",
                "details": {...}
            }
        }
    """
    err: dict[str, Any] = {"message": message}
    if code:
        err["code"] = code
    if details is not None:
        err["details"] = details
    return json_response({"ok": False, "error": err}, status=status, request=request)


def handle_cors_preflight(request: Any | None = None) -> Response:
    """Handle OPTIONS preflight request."""
    origin = _get_cors_origin(request)
    headers = {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Webhook-Secret",
        "Access-Control-Max-Age": "86400",
    }
    # Vary on Origin when using a specific origin (so caches don't mix)
    if origin and origin != "*":
        headers["Vary"] = "Origin"
    return Response("", status=204, headers=headers)
