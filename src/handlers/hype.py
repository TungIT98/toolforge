"""Hype HTTP handlers — marketing campaign generation.

Endpoints:
  POST /api/hype/generate      Generate campaign from tool_id
  GET  /api/hype/campaigns     List all campaigns
  GET  /api/hype/campaign/{id} Get 1 campaign
"""
from __future__ import annotations

from src.hype import generate_campaign, get_campaign, save_campaign
from src.lib.log import get_logger
from src.lib.response import error_response, json_response
from src.router import route

log = get_logger("hype.handler")


@route("POST", "/api/hype/generate")
async def hype_generate_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Generate a marketing campaign for a tool.

    Body: {
        "tool_id": "capcut-reup",
        "tool_name": "CapCut Desktop Reup",   // optional, fetched from DB if missing
        "pricing_vnd": 1200000,                 // optional
        "target_audience": "MMO TikTok creator", // optional, defaults to MMO VN
        "spec": { ... }                          // optional, fetched from specs table
    }
    """
    try:
        body = await request.json()  # type: ignore[attr-defined]
    except Exception as e:
        return error_response(f"Invalid JSON: {e}", status=400, code="INVALID_JSON")
    if not isinstance(body, dict):
        return error_response("Body must be JSON object", status=400, code="INVALID_JSON")

    tool_id = body.get("tool_id")
    if not tool_id:
        return error_response("Missing tool_id", status=400, code="MISSING_TOOL_ID")

    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")

    tool_name = body.get("tool_name") or tool_id
    pricing_vnd = body.get("pricing_vnd", 0)
    target_audience = body.get("target_audience", "MMO TikTok creator Việt Nam")
    spec = body.get("spec") or {}

    # If no spec provided, try to fetch from specs table
    if not spec:
        try:
            row = await db.prepare(
                "SELECT tool_id, content FROM specs WHERE tool_id = ? LIMIT 1"
            ).bind(tool_id).first()
            if row and row.get("content"):
                spec = {"problem": row["content"][:1000]}  # first 1000 chars as context
        except Exception as e:
            log.warn("spec_fetch_failed", err=str(e), tool_id=tool_id)

    # Generate
    result = await generate_campaign(
        env, tool_name, spec, pricing_vnd, target_audience,
    )
    if not result["ok"]:
        return error_response(
            result.get("error", "Generation failed"),
            status=500, code=result.get("code", "HYPE_FAILED"),
        )

    # Save to DB
    save_result = await save_campaign(
        db, tool_id, tool_name, result["campaign"], pricing_vnd,
    )

    return json_response({
        "ok": True,
        "tool_id": tool_id,
        "tool_name": tool_name,
        "campaign": result["campaign"],
        "saved": save_result.get("ok", False),
        "llm_usage": result.get("llm_usage", {}),
        "latency_ms": result.get("latency_ms", 0),
    })


@route("GET", "/api/hype/campaigns")
async def hype_list_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """List all generated campaigns."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    rows = await db.prepare(
        "SELECT tool_id, tool_name, pricing_vnd, created_at, updated_at "
        "FROM campaigns ORDER BY updated_at DESC LIMIT 50"
    ).bind().all()
    return json_response({"ok": True, "count": len(rows or []), "campaigns": rows or []})


@route("GET", "/api/hype/campaign/{tool_id}")
async def hype_get_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Get 1 campaign by tool_id."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    path = getattr(request, "path", "")
    tool_id = path.split("/api/hype/campaign/")[-1].strip("/")
    if not tool_id:
        return error_response("Missing tool_id", status=400, code="MISSING_TOOL_ID")
    campaign = await get_campaign(db, tool_id)
    if not campaign:
        return error_response(f"No campaign for {tool_id}", status=404, code="NOT_FOUND")
    return json_response({"ok": True, "campaign": campaign})
