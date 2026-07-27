"""License verification handler — public endpoint (no admin key required).

Tauri app calls POST /api/license/verify with {key, tool_id}.
"""
from __future__ import annotations

from src.forge.license_verifier import verify_license
from src.lib.log import get_logger
from src.lib.response import error_response, json_response
from src.router import route

log = get_logger("license.handler")


@route("POST", "/api/license/verify")
async def license_verify_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Verify a license key.

    Request body: { "key": "XXXX-XXXX-XXXX-XXXX", "tool_id": "capcut-reup" }
    Response: { ok, valid, reason, license }
    """
    try:
        body = await request.json()  # type: ignore[attr-defined]
    except Exception as e:
        return error_response(f"Invalid JSON: {e}", status=400, code="INVALID_JSON")
    if not isinstance(body, dict):
        return error_response("Body must be JSON object", status=400, code="INVALID_JSON")

    license_key = body.get("key", "").strip()
    tool_id = body.get("tool_id", "").strip()
    if not license_key or not tool_id:
        return error_response("Missing 'key' or 'tool_id'", status=400, code="MISSING_FIELDS")

    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")

    result = await verify_license(db, license_key, tool_id)
    if not result["ok"]:
        return error_response(result.get("error", "unknown"), status=500, code=result.get("code", "VERIFY_FAILED"))
    return json_response(result)


@route("GET", "/api/license/check")
async def license_check_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Quick health check: GET ?key=...&tool_id=...

    For Tauri apps that prefer GET over POST (e.g. browser-based).
    """
    # Parse query string
    url = getattr(request, "url", "") or ""
    key = tool_id = ""
    if "?" in url:
        qs = url.split("?", 1)[1]
        for pair in qs.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                if k == "key":
                    key = v
                elif k == "tool_id":
                    tool_id = v
    if not key or not tool_id:
        return error_response("Missing ?key=...&tool_id=...", status=400, code="MISSING_PARAMS")

    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")

    result = await verify_license(db, key, tool_id)
    return json_response(result)
