"""Admin auth — simple API key check via header.

Production-grade: use OAuth or signed cookies.
P2 MVP: X-Admin-Key header. Set secret via `wrangler secret put ADMIN_API_KEY`.
"""
from __future__ import annotations

import hmac

from src.lib.response import error_response


def check_admin_key(provided_key: str | None, expected_key: str) -> bool:
    """Constant-time check of admin API key."""
    if not provided_key or not expected_key:
        return False
    return hmac.compare_digest(provided_key, expected_key)


def admin_required(provided_key: str | None, expected_key: str):
    """Return error response if not authorized, None if OK."""
    if not check_admin_key(provided_key, expected_key):
        return error_response(
            "Admin API key required. Pass X-Admin-Key header.",
            status=401,
            code="ADMIN_AUTH_FAILED",
        )
    return None
