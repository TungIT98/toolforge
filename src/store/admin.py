"""Store admin — add/update tools (owner only).
"""
from __future__ import annotations

from datetime import datetime, timezone


ALLOWED_NICHES = {"mmo_reup", "content_creator", "productivity"}
ALLOWED_STATUSES = {"draft", "approved", "live", "deprecated"}


async def add_tool(db: "object", tool: dict) -> dict:
    """Insert 1 tool. Returns {ok, tool_id} or {ok: false, error}."""
    # Validate
    required = ["id", "name", "description", "niche"]
    for f in required:
        if not tool.get(f):
            return {"ok": False, "error": f"Missing field: {f}", "code": "MISSING_FIELD"}

    if tool["niche"] not in ALLOWED_NICHES:
        return {"ok": False, "error": f"Invalid niche: {tool['niche']}", "code": "INVALID_NICHE"}

    status = tool.get("status", "draft")
    if status not in ALLOWED_STATUSES:
        return {"ok": False, "error": f"Invalid status: {status}", "code": "INVALID_STATUS"}

    pricing = int(tool.get("pricing_vnd", 0))
    if pricing < 0:
        return {"ok": False, "error": "pricing_vnd must be >= 0", "code": "INVALID_PRICE"}

    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.prepare(
            """INSERT INTO tools
               (id, name, description, niche, status, build_id, pricing_vnd, binary_url,
                license_required, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        ).bind(
            tool["id"],
            tool["name"],
            tool["description"],
            tool["niche"],
            status,
            tool.get("build_id"),
            pricing,
            tool.get("binary_url", ""),
            1 if tool.get("license_required") else 0,
            ",".join(tool.get("tags", [])) if isinstance(tool.get("tags"), list) else tool.get("tags", ""),
            now,
            now,
        ).run()
    except Exception as e:
        return {"ok": False, "error": f"DB error: {e}", "code": "DB_ERROR"}

    return {"ok": True, "tool_id": tool["id"]}


async def update_tool(db: "object", tool_id: str, updates: dict) -> dict:
    """Update 1 tool (partial). Returns {ok} or {ok: false, error}."""
    # Build dynamic UPDATE (only allow whitelisted fields)
    allowed_fields = {"name", "description", "niche", "status", "pricing_vnd",
                      "binary_url", "license_required", "tags", "build_id"}
    set_clauses = []
    params = []
    for k, v in updates.items():
        if k not in allowed_fields:
            continue
        if k == "niche" and v not in ALLOWED_NICHES:
            return {"ok": False, "error": f"Invalid niche: {v}", "code": "INVALID_NICHE"}
        if k == "status" and v not in ALLOWED_STATUSES:
            return {"ok": False, "error": f"Invalid status: {v}", "code": "INVALID_STATUS"}
        if k == "pricing_vnd":
            v = max(0, int(v))
        if k == "license_required":
            v = 1 if v else 0
        if k == "tags" and isinstance(v, list):
            v = ",".join(v)
        set_clauses.append(f"{k} = ?")
        params.append(v)

    if not set_clauses:
        return {"ok": False, "error": "No valid fields to update", "code": "NO_FIELDS"}

    set_clauses.append("updated_at = ?")
    params.append(datetime.now(timezone.utc).isoformat())
    params.append(tool_id)

    sql = f"UPDATE tools SET {', '.join(set_clauses)} WHERE id = ?"
    try:
        await db.prepare(sql).bind(*params).run()
    except Exception as e:
        return {"ok": False, "error": f"DB error: {e}", "code": "DB_ERROR"}
    return {"ok": True, "tool_id": tool_id}
