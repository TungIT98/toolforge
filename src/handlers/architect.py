"""Architect handlers — P1 real implementation.

Endpoints:
  POST /api/architect/spec                 Generate spec from pain point
  POST /api/architect/{spec_id}/approve    Owner approves spec → trigger Forge
  POST /api/architect/{spec_id}/reject     Owner rejects with feedback
  GET  /api/architect/list                 List all specs (filter by status)
  GET  /api/architect/{spec_id}            Get 1 spec
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from src.architect.spec_generator import generate_spec, validate_spec
from src.handlers.middleware import apply_rate_limit
from src.lib.log import get_logger
from src.lib.response import error_response, json_response
from src.llm import LLMError, get_client
from src.router import route

log = get_logger("architect.handler")


async def create_spec_from_pain_point(
    pain_point: dict,
    env: "object",
    category: str = "auto",
) -> dict:
    """Core Architect logic: generate spec from 1 pain point."""
    try:
        client = get_client(agent_name="architect", env=env)
    except LLMError as e:
        log.error("architect_no_llm_key", err=str(e))
        return {"ok": False, "error": str(e), "code": "LLM_KEY_MISSING"}

    # Generate spec via LLM
    try:
        spec_result = await generate_spec(pain_point, client, category=category)
    except LLMError as e:
        return {"ok": False, "error": str(e), "code": "LLM_FAILED"}

    # Validate spec (10 sections present)
    is_valid, issues = validate_spec(spec_result)
    if not is_valid:
        log.warn("spec_incomplete", issues=issues, title=pain_point.get("title", "?"))
        # Don't fail — save anyway with warning

    # Generate IDs
    spec_id = f"spec-{pain_point.get('tool_id_hint', uuid.uuid4().hex[:8])}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    tool_id = spec_id.replace("spec-", "tool-", 1)
    handoff_id = f"handoff-{tool_id}"

    # Save to D1
    saved_spec = False
    saved_handoff = False
    try:
        db = getattr(env, "DB", None)
        if db is not None:
            # 1. Save spec
            await db.prepare(
                """INSERT OR REPLACE INTO specs
                   (id, tool_id, brief_id, content, status, effort_estimate_hours, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)"""
            ).bind(
                spec_id,
                tool_id,
                pain_point.get("brief_id"),
                spec_result["spec_markdown"],
                "pending_owner_review",
                spec_result.get("effort_estimate_hours"),
                datetime.now(timezone.utc).isoformat(),
            ).run()
            saved_spec = True

            # 2. Create handoff record (status pending, awaits owner approval)
            await db.prepare(
                """INSERT OR REPLACE INTO handoff
                   (id, tool_id, spec_id, status, priority, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)"""
            ).bind(
                handoff_id,
                tool_id,
                spec_id,
                "pending",
                "high" if pain_point.get("severity", 0) >= 8 else "medium",
                datetime.now(timezone.utc).isoformat(),
            ).run()
            saved_handoff = True

            # 3. Log token usage
            usage = spec_result.get("llm_usage", {})
            await db.prepare(
                """INSERT INTO llm_usage (agent, model, prompt_tokens, completion_tokens, total_tokens, cost_usd, task)
                   VALUES (?, ?, ?, ?, ?, ?, ?)"""
            ).bind(
                "architect",
                usage.get("model", "minimax/MiniMax-M3"),
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
                usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                None,
                f"spec_{tool_id}",
            ).run()
    except Exception as e:
        log.warn("architect_save_failed", err=str(e))

    return {
        "ok": True,
        "spec_id": spec_id,
        "tool_id": tool_id,
        "handoff_id": handoff_id,
        "saved_to_d1": saved_spec and saved_handoff,
        "is_valid": is_valid,
        "validation_issues": issues,
        "effort_estimate_hours": spec_result.get("effort_estimate_hours"),
        "spec_preview": spec_result["spec_markdown"][:800] + "..." if len(spec_result["spec_markdown"]) > 800 else spec_result["spec_markdown"],
        "llm_usage": spec_result.get("llm_usage", {}),
    }


@route("POST", "/api/architect/spec")
async def architect_spec_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Generate spec from pain point.

    Request body:
    {
        "pain_point": {
            "title": "...",
            "description": "...",
            "audience": "...",
            "severity": 9,
            "market_size_vn": "100K+",
            "current_solutions": "...",
            "gap": "...",
            "opportunity": "M",
            "estimated_monthly_revenue_vnd": 50000000,
            "source_signals": ["url1"],
            "tool_id_hint": "capcut-reup"  // optional, default uuid
        },
        "category": "auto"  // optional
    }
    """
    # Rate limit (10 req/min — LLM call)
    blocked = await apply_rate_limit(request, env, "/api/architect/spec")
    if blocked:
        return blocked

    try:
        body = await request.json()  # type: ignore[attr-defined]
    except Exception as e:
        return error_response(f"Invalid JSON: {e}", status=400, code="INVALID_JSON")

    if not isinstance(body, dict):
        return error_response("Body must be JSON object", status=400, code="INVALID_JSON")

    pain_point = body.get("pain_point")
    if not pain_point or not isinstance(pain_point, dict):
        return error_response("Missing 'pain_point' object", status=400, code="MISSING_PAIN_POINT")
    if not pain_point.get("title"):
        return error_response("pain_point.title is required", status=400, code="MISSING_TITLE")

    category = body.get("category", "auto")
    result = await create_spec_from_pain_point(pain_point, env, category=category)

    if not result["ok"]:
        code = result.get("code", "ARCHITECT_FAILED")
        status = 500 if code in ("LLM_KEY_MISSING", "LLM_FAILED") else 400
        return error_response(result.get("error", "unknown"), status=status, code=code)
    return json_response(result)


async def _update_handoff_status(
    spec_id: str,
    new_status: str,
    owner_feedback: str | None,
    env: "object",
) -> dict:
    """Update handoff status (approve/reject) and return handoff record."""
    db = getattr(env, "DB", None)
    if db is None:
        return {"ok": False, "error": "D1 not bound", "code": "DB_NOT_BOUND"}

    # Get handoff by spec_id
    handoff = await db.prepare(
        "SELECT id, tool_id, status FROM handoff WHERE spec_id = ?"
    ).bind(spec_id).first()
    if not handoff:
        return {"ok": False, "error": f"Spec {spec_id} not found", "code": "SPEC_NOT_FOUND"}

    now = datetime.now(timezone.utc).isoformat()
    update_fields = {
        "status": new_status,
        "owner_feedback": owner_feedback,
        "approved_at": now if new_status == "approved" else None,
        "forge_handoff_at": now if new_status == "approved" else None,
    }

    await db.prepare(
        """UPDATE handoff
           SET status = ?, owner_feedback = ?, approved_at = COALESCE(?, approved_at),
               forge_handoff_at = COALESCE(?, forge_handoff_at)
           WHERE spec_id = ?"""
    ).bind(
        new_status,
        owner_feedback,
        update_fields["approved_at"],
        update_fields["forge_handoff_at"],
        spec_id,
    ).run()

    # Also update spec status
    spec_status = "approved" if new_status == "approved" else "rejected"
    await db.prepare(
        "UPDATE specs SET status = ?, owner_feedback = ?, approved_at = ? WHERE id = ?"
    ).bind(spec_status, owner_feedback, now if new_status == "approved" else None, spec_id).run()

    return {
        "ok": True,
        "spec_id": spec_id,
        "tool_id": handoff["tool_id"],
        "handoff_id": handoff["id"],
        "new_status": new_status,
        "owner_feedback": owner_feedback,
        "ready_for_forge": new_status == "approved",
    }


@route("POST", "/api/architect/approve")
async def architect_approve_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Owner approves a spec. Triggers Forge pipeline.

    Request body: { "spec_id": "spec-...", "feedback": "optional" }
    """
    try:
        body = await request.json()  # type: ignore[attr-defined]
    except Exception as e:
        return error_response(f"Invalid JSON: {e}", status=400, code="INVALID_JSON")
    spec_id = body.get("spec_id") if isinstance(body, dict) else None
    if not spec_id:
        return error_response("Missing spec_id", status=400, code="MISSING_SPEC_ID")
    feedback = body.get("feedback") if isinstance(body, dict) else None
    result = await _update_handoff_status(spec_id, "approved", feedback, env)
    if not result["ok"]:
        code = result.get("code", "APPROVE_FAILED")
        status = 500 if code == "DB_NOT_BOUND" else 404
        return error_response(result.get("error", "unknown"), status=status, code=code)
    return json_response(result)


@route("POST", "/api/architect/reject")
async def architect_reject_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Owner rejects a spec with feedback (Architect re-generates).

    Request body: { "spec_id": "spec-...", "feedback": "lý do reject" }
    """
    try:
        body = await request.json()  # type: ignore[attr-defined]
    except Exception as e:
        return error_response(f"Invalid JSON: {e}", status=400, code="INVALID_JSON")
    spec_id = body.get("spec_id") if isinstance(body, dict) else None
    feedback = body.get("feedback") if isinstance(body, dict) else None
    if not spec_id:
        return error_response("Missing spec_id", status=400, code="MISSING_SPEC_ID")
    if not feedback:
        return error_response("Missing feedback (lý do reject)", status=400, code="MISSING_FEEDBACK")
    result = await _update_handoff_status(spec_id, "rejected", feedback, env)
    if not result["ok"]:
        code = result.get("code", "REJECT_FAILED")
        status = 500 if code == "DB_NOT_BOUND" else 404
        return error_response(result.get("error", "unknown"), status=status, code=code)
    return json_response(result)


@route("GET", "/api/architect/list")
async def architect_list_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """List specs, optional filter by status."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    # Optional ?status=approved
    url = request.url if hasattr(request, "url") else ""  # type: ignore[attr-defined]
    status_filter = None
    try:
        if "?" in url:
            qs = url.split("?", 1)[1]
            for pair in qs.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    if k == "status":
                        status_filter = v
    except Exception:
        pass

    if status_filter:
        rows = await db.prepare(
            "SELECT id, tool_id, status, effort_estimate_hours, created_at, approved_at "
            "FROM specs WHERE status = ? ORDER BY created_at DESC LIMIT 50"
        ).bind(status_filter).all()
    else:
        rows = await db.prepare(
            "SELECT id, tool_id, status, effort_estimate_hours, created_at, approved_at "
            "FROM specs ORDER BY created_at DESC LIMIT 50"
        ).all()
    return json_response({"ok": True, "count": len(rows or []), "specs": rows or []})


@route("GET", "/api/architect/get")
async def architect_get_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Get 1 spec by id (?id=spec-...)."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    spec_id = None
    try:
        url = request.url if hasattr(request, "url") else ""  # type: ignore[attr-defined]
        if "?" in url:
            qs = url.split("?", 1)[1]
            for pair in qs.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    if k == "id":
                        spec_id = v
    except Exception:
        pass
    if not spec_id:
        return error_response("Missing ?id=spec-...", status=400, code="MISSING_ID")
    spec = await db.prepare(
        "SELECT id, tool_id, content, status, owner_feedback, effort_estimate_hours, created_at, approved_at "
        "FROM specs WHERE id = ?"
    ).bind(spec_id).first()
    if not spec:
        return error_response(f"Spec {spec_id} not found", status=404, code="SPEC_NOT_FOUND")
    return json_response({"ok": True, "spec": spec})
