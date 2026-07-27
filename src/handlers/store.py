"""Store handlers — public catalog API + admin endpoints.

Endpoints:
  GET  /api/store/tools                 List tools (filters: niche, status, q, sort, limit, offset)
  GET  /api/store/tools/{tool_id}       1 tool detail with build + license count
  GET  /api/store/stats                 Catalog overview stats
  POST /api/store/tools                 Admin: add new tool
  PUT  /api/store/tools/{tool_id}       Admin: update tool
  POST /api/store/seed                  First-time seed mock data (idempotent)
"""
from __future__ import annotations

from src.handlers.middleware import apply_rate_limit
from src.lib.log import get_logger
from src.lib.response import error_response, json_response
from src.router import route
from src.store.admin import add_tool, update_tool
from src.store.catalog import (
    ALLOWED_NICHES,
    ALLOWED_SORT,
    ALLOWED_STATUSES,
    get_catalog_stats,
    get_tool_detail,
    get_tools,
)
from src.store.seed import SEED_TOOLS, seed_to_d1

log = get_logger("store")


def _parse_query_string(url: str) -> dict:
    """Parse query string from URL into dict."""
    out: dict = {}
    if "?" not in url:
        return out
    try:
        qs = url.split("?", 1)[1]
        for pair in qs.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                out[k.strip()] = v.strip()
    except Exception:
        pass
    return out


@route("GET", "/api/store/tools")
async def store_list_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """List tools with filters."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    qs = _parse_query_string(getattr(request, "url", "") or "")
    try:
        tools = await get_tools(
            db,
            niche=qs.get("niche"),
            status=qs.get("status"),
            q=qs.get("q"),
            sort=qs.get("sort", "created_at"),
            order=qs.get("order", "DESC"),
            limit=int(qs.get("limit", 50)),
            offset=int(qs.get("offset", 0)),
        )
    except Exception as e:
        return error_response(f"Query failed: {e}", status=500, code="QUERY_FAILED")
    return json_response({
        "ok": True,
        "count": len(tools),
        "tools": tools,
        "filters": {
            "niche": qs.get("niche"),
            "status": qs.get("status"),
            "q": qs.get("q"),
            "sort": qs.get("sort", "created_at"),
            "order": qs.get("order", "DESC"),
        },
    })


@route("GET", "/api/store/tools/{tool_id}")
async def store_detail_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Get 1 tool with build + license count."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    # Extract tool_id from path
    path = getattr(request, "path", "")
    # Path: /api/store/tools/{tool_id}
    tool_id = path.split("/api/store/tools/")[-1].strip("/")
    if not tool_id:
        return error_response("Missing tool_id", status=400, code="MISSING_TOOL_ID")
    tool = await get_tool_detail(db, tool_id)
    if not tool:
        return error_response(f"Tool {tool_id} not found", status=404, code="TOOL_NOT_FOUND")
    return json_response({"ok": True, "tool": tool})


@route("GET", "/api/store/stats")
async def store_stats_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Catalog overview stats."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    stats = await get_catalog_stats(db)
    return json_response({"ok": True, "stats": stats})


@route("POST", "/api/store/tools")
async def store_add_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Admin: add new tool."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    try:
        body = await request.json()  # type: ignore[attr-defined]
    except Exception as e:
        return error_response(f"Invalid JSON: {e}", status=400, code="INVALID_JSON")
    if not isinstance(body, dict):
        return error_response("Body must be JSON object", status=400, code="INVALID_JSON")
    result = await add_tool(db, body)
    if not result["ok"]:
        status = 400 if result.get("code") in ("MISSING_FIELD", "INVALID_NICHE", "INVALID_STATUS", "INVALID_PRICE") else 500
        return error_response(result.get("error", "unknown"), status=status, code=result.get("code", "ADD_FAILED"))
    return json_response(result)


@route("PUT", "/api/store/tools/{tool_id}")
async def store_update_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Admin: update tool."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    path = getattr(request, "path", "")
    tool_id = path.split("/api/store/tools/")[-1].strip("/")
    if not tool_id:
        return error_response("Missing tool_id", status=400, code="MISSING_TOOL_ID")
    try:
        body = await request.json()  # type: ignore[attr-defined]
    except Exception as e:
        return error_response(f"Invalid JSON: {e}", status=400, code="INVALID_JSON")
    if not isinstance(body, dict):
        return error_response("Body must be JSON object", status=400, code="INVALID_JSON")
    result = await update_tool(db, tool_id, body)
    if not result["ok"]:
        status = 400 if result.get("code", "").startswith("INVALID") or result.get("code") == "NO_FIELDS" else 500
        return error_response(result.get("error", "unknown"), status=status, code=result.get("code", "UPDATE_FAILED"))
    return json_response(result)


@route("POST", "/api/store/seed")
async def store_seed_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """First-time seed: insert SEED_TOOLS into D1. Idempotent (skips existing)."""
    # Rate limit (5 req/min — owner only, prevent abuse)
    blocked = await apply_rate_limit(request, env, "/api/store/seed")
    if blocked:
        return blocked

    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    result = await seed_to_d1(db)
    return json_response({
        "ok": True,
        "seeded": result,
        "catalog_url": "/api/store/tools",
    })
