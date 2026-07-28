"""Orchestrator HTTP handlers — showpiece pipeline API.

Endpoints:
  POST /api/orchestrator/run           Start a new pipeline run
  GET  /api/orchestrator/run/{id}      Get run + all steps (for live trace)
  GET  /api/orchestrator/runs          List recent runs
"""
from __future__ import annotations

from src.lib.log import get_logger
from src.lib.response import error_response, json_response
from src.orchestrator import get_run, run_pipeline
from src.router import route

log = get_logger("orchestrator.handler")


@route("POST", "/api/orchestrator/run")
async def orchestrator_run_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Start a new pipeline run.

    Body: {
        "input": "Pain point or topic (required)",
        "tool_name": "Optional override for tool name",
        "trigger": "manual" | "showcase" | "auto" (default: manual)
    }
    """
    try:
        body = await request.json()  # type: ignore[attr-defined]
    except Exception as e:
        return error_response(f"Invalid JSON: {e}", status=400, code="INVALID_JSON")
    if not isinstance(body, dict):
        return error_response("Body must be JSON object", status=400, code="INVALID_JSON")

    input_text = body.get("input", "").strip()
    if not input_text:
        return error_response("Missing 'input' field", status=400, code="MISSING_INPUT")
    tool_name = body.get("tool_name")
    trigger = body.get("trigger", "manual")

    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")

    result = await run_pipeline(env, input_text, trigger=trigger, tool_name=tool_name)
    return json_response(result, status=200 if result["ok"] else 500)


@route("GET", "/api/orchestrator/run/{run_id}")
async def orchestrator_get_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Get run + all steps (for live trace)."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    path = getattr(request, "path", "")
    run_id = path.split("/api/orchestrator/run/")[-1].strip("/")
    if not run_id:
        return error_response("Missing run_id", status=400, code="MISSING_RUN_ID")
    run = await get_run(db, run_id)
    if not run:
        return error_response(f"Run {run_id} not found", status=404, code="RUN_NOT_FOUND")
    return json_response({"ok": True, "run": run})


@route("GET", "/api/orchestrator/runs")
async def orchestrator_list_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """List recent runs."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    rows = await db.prepare(
        "SELECT id, trigger, input_text, status, current_step, tool_id, tool_name, started_at, ended_at "
        "FROM pipeline_runs ORDER BY started_at DESC LIMIT 20"
    ).bind().all()
    return json_response({"ok": True, "count": len(rows or []), "runs": rows or []})
