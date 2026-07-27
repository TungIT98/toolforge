"""Builder Tool HTTP endpoints — user-facing product.

Endpoints:
  POST /api/builder/session                  Create new chat session
  POST /api/builder/session/{id}/message     Send user message, get AI response
  GET  /api/builder/session/{id}             Get session + full chat history
  POST /api/builder/session/{id}/build       Generate code from spec
  GET  /api/builder/job/{id}                 Get job + code files
  GET  /api/builder/jobs                     List recent jobs (?session_id=)
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from src.builder.chat import chat_with_user, create_chat_session, get_session
from src.builder.generator import generate_code_from_spec
from src.forge.code_generator import validate_code_files
from src.lib.log import get_logger
from src.lib.response import error_response, json_response
from src.llm import LLMError, get_client
from src.router import route

log = get_logger("builder")


@route("POST", "/api/builder/session")
async def create_session_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Create new chat session."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    user_ip = (
        request.headers.get("CF-Connecting-IP")  # type: ignore[attr-defined]
        or request.headers.get("X-Forwarded-For")  # type: ignore[attr-defined]
    )
    user_email = None
    try:
        if request.headers.get("content-type", "").startswith("application/json"):  # type: ignore[attr-defined]
            body = await request.json()  # type: ignore[attr-defined]
            if isinstance(body, dict):
                user_email = body.get("user_email")
    except Exception:
        pass
    result = await create_chat_session(db, user_ip=user_ip, user_email=user_email)
    return json_response({"ok": True, **result})


@route("POST", "/api/builder/session/{session_id}/message")
async def session_message_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Send user message → AI response. May mark session ready_to_build."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    path = getattr(request, "path", "")
    session_id = path.split("/api/builder/session/")[-1].split("/message")[0].strip("/")
    if not session_id:
        return error_response("Missing session_id", status=400, code="MISSING_SESSION_ID")
    try:
        body = await request.json()  # type: ignore[attr-defined]
    except Exception as e:
        return error_response(f"Invalid JSON: {e}", status=400, code="INVALID_JSON")
    if not isinstance(body, dict):
        return error_response("Body must be JSON object", status=400, code="INVALID_JSON")
    user_message = body.get("message")
    if not user_message:
        return error_response("Missing 'message' field", status=400, code="MISSING_MESSAGE")

    try:
        client = get_client(agent_name="builder", env=env)
    except LLMError as e:
        return error_response(str(e), status=500, code="LLM_KEY_MISSING")

    result = await chat_with_user(db, session_id, user_message, client)
    if not result["ok"]:
        code = result.get("code", "CHAT_FAILED")
        status = 500 if code in ("LLM_KEY_MISSING", "LLM_FAILED") else 400
        return error_response(result.get("error", "unknown"), status=status, code=code)
    return json_response(result)


@route("GET", "/api/builder/session/{session_id}")
async def get_session_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Get session + chat history."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    path = getattr(request, "path", "")
    session_id = path.split("/api/builder/session/")[-1].strip("/")
    session = await get_session(db, session_id)
    if not session:
        return error_response(f"Session {session_id} not found", status=404, code="SESSION_NOT_FOUND")
    return json_response({"ok": True, "session": session})


@route("POST", "/api/builder/session/{session_id}/build")
async def build_session_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Generate code from a ready session."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    path = getattr(request, "path", "")
    session_id = path.split("/api/builder/session/")[-1].split("/build")[0].strip("/")
    if not session_id:
        return error_response("Missing session_id", status=400, code="MISSING_SESSION_ID")

    # Get session
    session = await get_session(db, session_id)
    if not session:
        return error_response(f"Session {session_id} not found", status=404, code="SESSION_NOT_FOUND")
    if session["status"] != "ready_to_build":
        return error_response(
            f"Session status is '{session['status']}', must be 'ready_to_build'. Continue chatting first.",
            status=400, code="NOT_READY",
        )

    # Mark building
    now = datetime.now(timezone.utc).isoformat()
    await db.prepare(
        "UPDATE builder_sessions SET status = 'building', updated_at = ? WHERE id = ?"
    ).bind(now, session_id).run()

    # Get LLM client
    try:
        client = get_client(agent_name="builder_generator", env=env)
    except LLMError as e:
        await db.prepare("UPDATE builder_sessions SET status = 'ready_to_build' WHERE id = ?").bind(session_id).run()
        return error_response(str(e), status=500, code="LLM_KEY_MISSING")

    # Generate code
    try:
        gen_result = await generate_code_from_spec(
            session["final_spec"] or "",
            client,
            tool_name=session.get("tool_name", "Tool"),
        )
    except LLMError as e:
        await db.prepare("UPDATE builder_sessions SET status = 'ready_to_build' WHERE id = ?").bind(session_id).run()
        return error_response(str(e), status=500, code="LLM_FAILED")

    # Validate
    is_valid, issues = validate_code_files(gen_result["files"])
    test_result = "pass" if is_valid else ("partial" if gen_result["file_count"] > 0 else "fail")

    # Save job
    job_id = f"job-{uuid.uuid4().hex[:12]}"
    files_json = json.dumps(gen_result["files"], ensure_ascii=False)
    size = len(files_json.encode("utf-8"))
    try:
        await db.prepare(
            """INSERT INTO builder_jobs
               (id, session_id, code_files_json, file_count, total_lines, test_result, status, size_bytes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        ).bind(
            job_id, session_id, files_json, gen_result["file_count"],
            gen_result["total_lines"], test_result, "done", size, now,
        ).run()
        await db.prepare(
            "UPDATE builder_sessions SET status = ?, updated_at = ? WHERE id = ?"
        ).bind("done", now, session_id).run()
    except Exception as e:
        log.error("save_job_failed", err=str(e))
        return error_response(f"DB error: {e}", status=500, code="DB_ERROR")

    return json_response({
        "ok": True,
        "job_id": job_id,
        "session_id": session_id,
        "tool_name": session.get("tool_name"),
        "file_count": gen_result["file_count"],
        "total_lines": gen_result["total_lines"],
        "test_result": test_result,
        "files": gen_result["files"],
        "files_preview": {
            fp: content[:300] + "..." if len(content) > 300 else content
            for fp, content in list(gen_result["files"].items())[:5]
        },
        "download_hint": "Copy files individually or wait for ZIP feature in P5",
        "llm_usage": gen_result.get("llm_usage", {}),
    })


@route("GET", "/api/builder/job/{job_id}")
async def get_job_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Get job + full code files."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    path = getattr(request, "path", "")
    job_id = path.split("/api/builder/job/")[-1].strip("/")
    job = await db.prepare(
        "SELECT id, session_id, code_files_json, file_count, total_lines, test_result, status, size_bytes, created_at "
        "FROM builder_jobs WHERE id = ?"
    ).bind(job_id).first()
    if not job:
        return error_response(f"Job {job_id} not found", status=404, code="JOB_NOT_FOUND")
    # Parse files_json
    try:
        files = json.loads(job.get("code_files_json") or "{}")
    except json.JSONDecodeError:
        files = {}
    return json_response({
        "ok": True,
        "job": {**job, "files": files},
    })


@route("GET", "/api/builder/jobs")
async def list_jobs_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """List recent jobs."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    url = getattr(request, "url", "") or ""
    session_filter = None
    if "?" in url:
        qs = url.split("?", 1)[1]
        for pair in qs.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                if k == "session_id":
                    session_filter = v
    if session_filter:
        rows = await db.prepare(
            "SELECT id, session_id, file_count, total_lines, test_result, status, size_bytes, created_at "
            "FROM builder_jobs WHERE session_id = ? ORDER BY created_at DESC LIMIT 50"
        ).bind(session_filter).all()
    else:
        rows = await db.prepare(
            "SELECT id, session_id, file_count, total_lines, test_result, status, size_bytes, created_at "
            "FROM builder_jobs ORDER BY created_at DESC LIMIT 50"
        ).bind().all()
    return json_response({"ok": True, "count": len(rows or []), "jobs": rows or []})
