"""JSON response helpers for ToolForge Workers.

Standardize response format across all endpoints. Cloudflare Workers
use the JS Response class; we wrap it with Python-friendly helpers.

Falls back to a local shim when `workers` module is not available
(local dev / tests on CPython).
"""
from __future__ import annotations

import json
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


def json_response(
    data: Any,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> Response:
    """Return a JSON response with CORS headers.

    Args:
        data: Any JSON-serializable object
        status: HTTP status code (default 200)
        headers: Additional headers to merge

    Returns:
        Response object (CF Workers in prod, local shim in tests)
    """
    base_headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
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
    return json_response({"ok": False, "error": err}, status=status)


def handle_cors_preflight() -> Response:
    """Handle OPTIONS preflight request."""
    return Response(
        "",
        status=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "86400",
        },
    )
