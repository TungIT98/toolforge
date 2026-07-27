"""Forge handlers — P1 + P4 implementation.

P1: generate code from approved spec, save to D1.
P4: trigger GH Action for Tauri build, handle webhook callback.

Endpoints:
  POST /api/forge/build         Generate code from approved spec (P1)
  POST /api/forge/build-binary  Trigger Tauri build via GH Action (P4)
  POST /api/forge/webhook/built Handle GH Action callback (P4)
  GET  /api/forge/download/{id} Get signed download URL (P4)
  POST /api/forge/license       Generate license key
  GET  /api/forge/list          List builds
  GET  /api/forge/get           Get 1 build by id
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from src.forge.build_orchestrator import trigger_github_workflow
from src.forge.code_generator import (
    compile_check_python,
    generate_code_from_spec,
    validate_code_files,
)
from src.forge.license import generate_license_key
from src.forge.r2_uploader import (
    build_r2_path,
    generate_signed_url,
    is_valid_r2_config,
)
from src.forge.webhook import handle_build_complete, verify_webhook_secret
from src.handlers.middleware import apply_rate_limit
from src.lib.log import get_logger
from src.lib.response import error_response, json_response
from src.llm import LLMError, get_client
from src.router import route

log = get_logger("forge.handler")


async def run_forge_build(
    spec_id: str,
    env: "object",
    triggered_by: str = "manual",
) -> dict:
    """Core Forge logic: get spec → generate code → save to D1.

    Returns dict with build_id, file_count, total_lines, etc.
    """
    db = getattr(env, "DB", None)
    if db is None:
        return {"ok": False, "error": "D1 not bound", "code": "DB_NOT_BOUND"}

    # 1. Get spec + handoff
    spec = await db.prepare(
        "SELECT id, tool_id, content, status FROM specs WHERE id = ?"
    ).bind(spec_id).first()
    if not spec:
        return {"ok": False, "error": f"Spec {spec_id} not found", "code": "SPEC_NOT_FOUND"}

    if spec["status"] != "approved":
        return {
            "ok": False,
            "error": f"Spec status is '{spec['status']}', must be 'approved'",
            "code": "SPEC_NOT_APPROVED",
        }

    handoff = await db.prepare(
        "SELECT id, status FROM handoff WHERE spec_id = ?"
    ).bind(spec_id).first()
    if not handoff or handoff["status"] != "approved":
        return {
            "ok": False,
            "error": f"Handoff status is '{handoff['status'] if handoff else 'not found'}', must be 'approved'",
            "code": "HANDOFF_NOT_APPROVED",
        }

    tool_id = spec["tool_id"]
    build_id = f"build-{tool_id}-v0.1.0"

    # 2. Update handoff status to in_progress
    now = datetime.now(timezone.utc).isoformat()
    await db.prepare(
        "UPDATE handoff SET status = ?, done_at = ? WHERE spec_id = ?"
    ).bind("in_progress", None, spec_id).run()

    # 3. Get LLM client + generate code
    try:
        client = get_client(agent_name="forge", env=env)
    except LLMError as e:
        await db.prepare(
            "UPDATE handoff SET status = ? WHERE spec_id = ?"
        ).bind("pending", spec_id).run()
        return {"ok": False, "error": str(e), "code": "LLM_KEY_MISSING"}

    try:
        code_result = await generate_code_from_spec(spec["content"], client, tool_id)
    except LLMError as e:
        await db.prepare(
            "UPDATE handoff SET status = ? WHERE spec_id = ?"
        ).bind("pending", spec_id).run()
        return {"ok": False, "error": str(e), "code": "LLM_FAILED"}

    # 4. Validate code
    is_valid, issues = validate_code_files(code_result["files"])

    # 5. Run py_compile check on Python files
    py_check = compile_check_python(code_result["files"])
    py_passed = all(v == "ok" for v in py_check.values()) if py_check else True

    test_result = "pass" if (is_valid and py_passed) else ("partial" if code_result["file_count"] > 0 else "fail")

    # 6. Save build to D1 (P1: store code as JSON in D1; P4+: upload to R2)
    files_json = json.dumps(code_result["files"], ensure_ascii=False)
    saved = False
    try:
        await db.prepare(
            """INSERT OR REPLACE INTO builds
               (id, tool_id, handoff_id, version, code_path, test_result, test_report, effort_actual_hours, size_bytes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        ).bind(
            build_id,
            tool_id,
            handoff["id"],
            "0.1.0",
            f"d1://builds/{tool_id}/code.json",  # P1 stub
            test_result,
            json.dumps({
                "validation_issues": issues,
                "py_compile_check": py_check,
                "file_count": code_result["file_count"],
                "total_lines": code_result["total_lines"],
            }, ensure_ascii=False),
            None,  # effort_actual_hours (filled in P2)
            len(files_json.encode("utf-8")),
            now,
        ).run()
        saved = True

        # Update handoff status to done
        await db.prepare(
            "UPDATE handoff SET status = ?, done_at = ? WHERE spec_id = ?"
        ).bind("done", now, spec_id).run()

        # Log token usage
        usage = code_result.get("llm_usage", {})
        await db.prepare(
            """INSERT INTO llm_usage (agent, model, prompt_tokens, completion_tokens, total_tokens, cost_usd, task)
               VALUES (?, ?, ?, ?, ?, ?, ?)"""
        ).bind(
            "forge",
            usage.get("model", "minimax/MiniMax-M3"),
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
            usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            None,
            f"build_{tool_id}",
        ).run()
    except Exception as e:
        log.warn("forge_save_failed", err=str(e), build_id=build_id)

    return {
        "ok": True,
        "build_id": build_id,
        "tool_id": tool_id,
        "saved_to_d1": saved,
        "test_result": test_result,
        "file_count": code_result["file_count"],
        "total_lines": code_result["total_lines"],
        "files_preview": {
            fp: content[:200] + "..." if len(content) > 200 else content
            for fp, content in list(code_result["files"].items())[:5]
        },
        "validation_issues": issues,
        "py_compile_check": py_check,
        "llm_usage": code_result.get("llm_usage", {}),
        "triggered_by": triggered_by,
        "next_step": "Owner test binary (P2: actual Tauri build via GH Action; P4: R2 upload)",
    }


@route("POST", "/api/forge/build")
async def forge_build_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Generate code from approved spec.

    Request body: { "spec_id": "spec-..." }
    """
    # Rate limit (10 req/min — LLM call)
    blocked = await apply_rate_limit(request, env, "/api/forge/build")
    if blocked:
        return blocked

    try:
        body = await request.json()  # type: ignore[attr-defined]
    except Exception as e:
        return error_response(f"Invalid JSON: {e}", status=400, code="INVALID_JSON")
    spec_id = body.get("spec_id") if isinstance(body, dict) else None
    if not spec_id:
        return error_response("Missing spec_id", status=400, code="MISSING_SPEC_ID")

    result = await run_forge_build(spec_id, env, triggered_by="manual_api")
    if not result["ok"]:
        code = result.get("code", "FORGE_FAILED")
        status_map = {
            "DB_NOT_BOUND": 500, "SPEC_NOT_FOUND": 404, "SPEC_NOT_APPROVED": 400,
            "HANDOFF_NOT_APPROVED": 400, "LLM_KEY_MISSING": 500, "LLM_FAILED": 500,
        }
        status = status_map.get(code, 500)
        return error_response(result.get("error", "unknown"), status=status, code=code)
    return json_response(result)


@route("POST", "/api/forge/license")
async def forge_license_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Generate a license key for a tool.

    Request body: { "tool_id": "capcut-reup", "customer_email": "optional", "customer_telegram": "optional" }
    """
    # Rate limit (10 req/min — license gen is sensitive)
    blocked = await apply_rate_limit(request, env, "/api/forge/license")
    if blocked:
        return blocked

    try:
        body = await request.json()  # type: ignore[attr-defined]
    except Exception as e:
        return error_response(f"Invalid JSON: {e}", status=400, code="INVALID_JSON")
    if not isinstance(body, dict):
        return error_response("Body must be JSON object", status=400, code="INVALID_JSON")
    tool_id = body.get("tool_id")
    if not tool_id:
        return error_response("Missing tool_id", status=400, code="MISSING_TOOL_ID")

    customer_email = body.get("customer_email")
    customer_telegram = body.get("customer_telegram")
    license_key = generate_license_key()

    # Save to D1
    saved = False
    try:
        db = getattr(env, "DB", None)
        if db is not None:
            await db.prepare(
                """INSERT OR REPLACE INTO licenses
                   (key, tool_id, status, customer_email, customer_telegram, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)"""
            ).bind(
                license_key,
                tool_id,
                "active",
                customer_email,
                customer_telegram,
                datetime.now(timezone.utc).isoformat(),
            ).run()
            saved = True
    except Exception as e:
        log.warn("license_save_failed", err=str(e))

    return json_response({
        "ok": True,
        "license_key": license_key,
        "tool_id": tool_id,
        "saved_to_d1": saved,
        "customer_email": customer_email,
        "customer_telegram": customer_telegram,
    })


@route("GET", "/api/forge/list")
async def forge_list_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """List builds."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    rows = await db.prepare(
        "SELECT id, tool_id, version, test_result, file_count_via_test_report, created_at "
        "FROM builds ORDER BY created_at DESC LIMIT 50"
    ).all()
    return json_response({"ok": True, "count": len(rows or []), "builds": rows or []})


@route("GET", "/api/forge/get")
async def forge_get_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Get 1 build by id (?id=build-...)."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    build_id = None
    try:
        url = request.url if hasattr(request, "url") else ""  # type: ignore[attr-defined]
        if "?" in url:
            qs = url.split("?", 1)[1]
            for pair in qs.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    if k == "id":
                        build_id = v
    except Exception:
        pass
    if not build_id:
        return error_response("Missing ?id=build-...", status=400, code="MISSING_ID")
    build = await db.prepare(
        "SELECT id, tool_id, handoff_id, version, code_path, test_result, test_report, effort_actual_hours, size_bytes, created_at "
        "FROM builds WHERE id = ?"
    ).bind(build_id).first()
    if not build:
        return error_response(f"Build {build_id} not found", status=404, code="BUILD_NOT_FOUND")
    return json_response({"ok": True, "build": build})
