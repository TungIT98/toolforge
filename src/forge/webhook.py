"""Webhook handler — GH Action callback when build completes.

GH Action POSTs here after building + uploading to R2. We update D1
with binary URL + test result.
"""
from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from typing import Any

from src.lib.log import get_logger
from src.lib.response import error_response, json_response

log = get_logger("forge.webhook")


def verify_webhook_secret(provided: str | None, expected: str) -> bool:
    """Verify X-Webhook-Secret header matches shared secret."""
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided, expected)


async def handle_build_complete(
    payload: dict,
    env: "object",
) -> dict[str, Any]:
    """Process webhook payload from GH Action.

    Expected payload:
    {
        "build_id": "build-capcut-reup-0.1.0",
        "tool_id": "capcut-reup",
        "version": "0.1.0",
        "status": "success" | "failed",
        "binary_url": "https://...",
        "size_bytes": 12345678,
        "test_result": "pass" | "partial" | "fail",
        "error": "optional error msg"
    }
    """
    db = getattr(env, "DB", None)
    if db is None:
        return {"ok": False, "error": "D1 not bound", "code": "DB_NOT_BOUND"}

    build_id = payload.get("build_id")
    if not build_id:
        return {"ok": False, "error": "Missing build_id", "code": "MISSING_BUILD_ID"}

    status = payload.get("status", "unknown")
    binary_url = payload.get("binary_url")
    size_bytes = payload.get("size_bytes", 0)
    test_result = payload.get("test_result")
    error_msg = payload.get("error")

    # Find build record (by id or by handoff tool)
    build = await db.prepare(
        "SELECT id, tool_id, handoff_id FROM builds WHERE id = ?"
    ).bind(build_id).first()
    if not build:
        # Fallback: find by handoff (e.g. build_id from GH = "build-..." same as D1)
        log.warn("build_not_found", build_id=build_id)
        return {"ok": False, "error": f"Build {build_id} not found", "code": "BUILD_NOT_FOUND"}

    now = datetime.now(timezone.utc).isoformat()

    try:
        # Update build record
        if status == "success" and binary_url:
            await db.prepare(
                """UPDATE builds
                   SET binary_url = ?, size_bytes = ?, test_result = ?, code_path = ?
                   WHERE id = ?"""
            ).bind(
                binary_url, size_bytes, test_result or "pass",
                f"r2://{build['tool_id']}/{build_id}",
                build_id,
            ).run()

            # Update tool record with latest binary URL
            await db.prepare(
                "UPDATE tools SET binary_url = ?, updated_at = ? WHERE id = ?"
            ).bind(binary_url, now, build["tool_id"]).run()

            # Update handoff status to done
            await db.prepare(
                "UPDATE handoff SET status = ?, done_at = ? WHERE id = ?"
            ).bind("done", now, build["handoff_id"]).run()
        else:
            await db.prepare(
                "UPDATE builds SET test_result = ? WHERE id = ?"
            ).bind(f"failed: {error_msg or 'unknown'}", build_id).run()

            await db.prepare(
                "UPDATE handoff SET status = ? WHERE id = ?"
            ).bind("failed", build["handoff_id"]).run()
    except Exception as e:
        log.error("webhook_update_failed", err=str(e))
        return {"ok": False, "error": f"DB error: {e}", "code": "DB_ERROR"}

    return {
        "ok": True,
        "build_id": build_id,
        "tool_id": build["tool_id"],
        "status": status,
        "binary_url": binary_url,
    }


def webhook_handler_response(result: dict, env: "object") -> "Response":
    """Wrap webhook result in HTTP response."""
    if not result["ok"]:
        code = result.get("code", "WEBHOOK_FAILED")
        status = 500 if code in ("DB_NOT_BOUND", "DB_ERROR") else 400
        return error_response(result.get("error", "unknown"), status=status, code=code)
    return json_response(result)
