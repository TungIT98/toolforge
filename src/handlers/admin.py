"""Admin handlers — owner dashboard endpoints.

All endpoints require X-Admin-Key header. Set via:
    wrangler secret put ADMIN_API_KEY

Endpoints:
  GET  /api/admin/overview       Aggregated stats (tools, orders, licenses, pipeline)
  GET  /api/admin/orders         List recent orders (filter ?status=)
  GET  /api/admin/licenses       List licenses (filter ?status=)
  GET  /api/admin/pending-specs  Specs awaiting owner review
  GET  /api/admin/briefs         Recent Scout briefs
  GET  /api/admin/builds         Recent builds
"""
from __future__ import annotations

import os

from src.admin.auth import admin_required
from src.admin.overview import get_admin_overview
from src.lib.log import get_logger
from src.lib.response import error_response, json_response
from src.router import route

log = get_logger("admin")


def _get_admin_key(env: "object") -> str:
    return (
        getattr(env, "ADMIN_API_KEY", "") or os.environ.get("ADMIN_API_KEY", "")
    )


def _check(request: "object", env: "object"):
    """Check admin auth. Returns error response or None."""
    key = _get_admin_key(env)
    provided = (
        request.headers.get("X-Admin-Key")  # type: ignore[attr-defined]
        or request.headers.get("x-admin-key")  # type: ignore[attr-defined]
    )
    return admin_required(provided, key)


@route("GET", "/api/admin/overview")
async def admin_overview_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Aggregated stats for admin dashboard."""
    err = _check(request, env)
    if err:
        return err
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    overview = await get_admin_overview(db)
    return json_response({"ok": True, "overview": overview})


@route("GET", "/api/admin/orders")
async def admin_orders_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """List recent orders."""
    err = _check(request, env)
    if err:
        return err
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    # Optional ?status=pending|paid|failed|refunded
    url = getattr(request, "url", "") or ""
    status_filter = None
    if "?" in url:
        qs = url.split("?", 1)[1]
        for pair in qs.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                if k == "status":
                    status_filter = v
    if status_filter:
        rows = await db.prepare(
            "SELECT id, tool_id, tool_name, customer_email, customer_telegram, "
            "amount_vnd, status, paid_at, created_at, license_key "
            "FROM orders WHERE status = ? ORDER BY created_at DESC LIMIT 100"
        ).bind(status_filter).all()
    else:
        rows = await db.prepare(
            "SELECT id, tool_id, tool_name, customer_email, customer_telegram, "
            "amount_vnd, status, paid_at, created_at, license_key "
            "FROM orders ORDER BY created_at DESC LIMIT 100"
        ).bind().all()
    return json_response({"ok": True, "count": len(rows or []), "orders": rows or []})


@route("GET", "/api/admin/licenses")
async def admin_licenses_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """List licenses."""
    err = _check(request, env)
    if err:
        return err
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    url = getattr(request, "url", "") or ""
    status_filter = None
    if "?" in url:
        qs = url.split("?", 1)[1]
        for pair in qs.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                if k == "status":
                    status_filter = v
    if status_filter:
        rows = await db.prepare(
            "SELECT key, tool_id, status, customer_email, customer_telegram, "
            "activated_at, expires_at, created_at "
            "FROM licenses WHERE status = ? ORDER BY created_at DESC LIMIT 200"
        ).bind(status_filter).all()
    else:
        rows = await db.prepare(
            "SELECT key, tool_id, status, customer_email, customer_telegram, "
            "activated_at, expires_at, created_at "
            "FROM licenses ORDER BY created_at DESC LIMIT 200"
        ).bind().all()
    return json_response({"ok": True, "count": len(rows or []), "licenses": rows or []})


@route("GET", "/api/admin/pending-specs")
async def admin_pending_specs_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """List specs awaiting owner review."""
    err = _check(request, env)
    if err:
        return err
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    rows = await db.prepare(
        "SELECT id, tool_id, status, effort_estimate_hours, created_at "
        "FROM specs WHERE status = 'pending_owner_review' ORDER BY created_at DESC LIMIT 50"
    ).bind().all()
    return json_response({"ok": True, "count": len(rows or []), "specs": rows or []})


@route("GET", "/api/admin/briefs")
async def admin_briefs_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """List recent Scout briefs."""
    err = _check(request, env)
    if err:
        return err
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    rows = await db.prepare(
        "SELECT id, scout_date, severity_avg, source_count, created_at "
        "FROM briefs ORDER BY created_at DESC LIMIT 30"
    ).bind().all()
    return json_response({"ok": True, "count": len(rows or []), "briefs": rows or []})


@route("GET", "/api/admin/builds")
async def admin_builds_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """List recent builds."""
    err = _check(request, env)
    if err:
        return err
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    rows = await db.prepare(
        "SELECT id, tool_id, version, test_result, size_bytes, created_at "
        "FROM builds ORDER BY created_at DESC LIMIT 50"
    ).bind().all()
    return json_response({"ok": True, "count": len(rows or []), "builds": rows or []})
