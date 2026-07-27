"""POST /api/llm/test — verify LLM connection + log token usage.

Request body (optional):
    {
        "prompt": "Custom user prompt",  // default: "ToolForge P0 OK"
        "system": "Custom system prompt" // default Vietnamese assistant
    }

Response:
    {
        "ok": true,
        "result": {
            "text": "...",
            "usage": {"input_tokens": X, "output_tokens": Y},
            "model": "minimax/MiniMax-M3",
            "latency_ms": 1234
        }
    }
"""
from __future__ import annotations

from src.handlers.middleware import apply_rate_limit
from src.lib.log import get_logger
from src.lib.response import error_response, json_response
from src.llm import LLMError, get_client
from src.router import route

log = get_logger("llm.test")


@route("POST", "/api/llm/test")
async def llm_test_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Test LLM connectivity. Logs token usage to D1 if available."""
    # Rate limit (10 req/min for LLM endpoint)
    blocked = await apply_rate_limit(request, env, "/api/llm/test")
    if blocked:
        return blocked

    # Parse body (optional)
    custom_prompt: str | None = None
    custom_system: str | None = None
    try:
        # CF Workers Request has .json() coroutine
        if request.headers.get("content-type", "").startswith("application/json"):  # type: ignore[attr-defined]
            body = await request.json()  # type: ignore[attr-defined]
            if isinstance(body, dict):
                custom_prompt = body.get("prompt")
                custom_system = body.get("system")
    except Exception as e:
        log.warn("llm_test_bad_body", err=str(e))

    # Build client
    try:
        client = get_client(agent_name="llm_test", env=env)
    except LLMError as e:
        log.error("llm_test_no_key", err=str(e))
        return error_response(str(e), status=500, code="LLM_KEY_MISSING")

    # Make a trivial call
    try:
        if custom_prompt and custom_system:
            result = await client.call(system=custom_system, user=custom_prompt, max_tokens=128)
        else:
            result = await client.test_connection()
    except LLMError as e:
        return error_response(str(e), status=502, code="LLM_CALL_FAILED")

    # Best-effort: log token usage to D1
    try:
        db = getattr(env, "DB", None)
        if db is not None:
            usage = result.get("usage", {})
            await db.prepare(
                """INSERT INTO llm_usage (agent, model, prompt_tokens, completion_tokens, total_tokens, cost_usd, task)
                   VALUES (?, ?, ?, ?, ?, ?, ?)"""
            ).bind(
                "llm_test",
                result.get("model", "unknown"),
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
                usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                None,
                "test_connection",
            ).run()
    except Exception as e:
        log.warn("llm_test_log_failed", err=str(e))

    return json_response({"ok": True, "result": result})
