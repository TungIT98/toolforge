"""Scout-related endpoints.

P0 stub:
  POST /api/scout/run — manually trigger daily pain point scan.
  In P0 it just validates LLM + saves a placeholder brief to D1.
  Real implementation in P1.

Cron trigger (in wrangler.jsonc): 0 23 * * * = 06:00 Asia/Saigon daily.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.lib.log import get_logger
from src.lib.response import error_response, json_response
from src.llm import LLMError, get_client
from src.router import route

log = get_logger("scout")


async def run_scout_scan(env: "object", triggered_by: str = "manual") -> dict:
    """Core scout logic. P0 stub: just call LLM to generate 1 sample pain point.

    Real P1 implementation: scan 8 sources (TikTok, YouTube, Telegram, FB, Voz, Trends, 1Touch Pro)
    + save to D1.
    """
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    brief_id = f"brief-{date_str}"

    # 1. Build LLM client
    try:
        client = get_client(agent_name="scout", env=env)
    except LLMError as e:
        log.error("scout_no_llm_key", err=str(e))
        return {"ok": False, "error": str(e)}

    # 2. P0 stub: ask LLM for 1 sample pain point
    system = (
        "Bạn là Scout, research agent cho ToolForge. "
        "Nhiệm vụ: tìm pain point của MMO/creator Việt Nam. "
        "Trả lời bằng tiếng Việt, ngắn gọn, có số liệu."
    )
    user = (
        f"Hôm nay {date_str}. Đây là stub scan P0. "
        "Liệt kê 1 pain point của MMO/creator Việt mà bạn nghĩ ToolForge nên build tool. "
        "Format: <title> | <audience> | <severity 1-10> | <1 câu giải pháp>."
    )

    try:
        result = await client.call(system=system, user=user, max_tokens=200)
    except LLMError as e:
        log.error("scout_llm_failed", err=str(e))
        return {"ok": False, "error": str(e)}

    # 3. Best-effort: save to D1
    saved = False
    try:
        db = getattr(env, "DB", None)
        if db is not None:
            content = f"# Scout Brief — {date_str}\n\n(P0 stub)\n\n{result['text']}\n"
            await db.prepare(
                """INSERT OR REPLACE INTO briefs (id, scout_date, content, top_pain_json, severity_avg, source_count)
                   VALUES (?, ?, ?, ?, ?, ?)"""
            ).bind(
                brief_id,
                date_str,
                content,
                result["text"],
                5.0,  # placeholder severity
                1,    # P0 only 1 source (LLM stub)
            ).run()
            saved = True
    except Exception as e:
        log.warn("scout_save_failed", err=str(e))

    # 4. Log token usage
    try:
        db = getattr(env, "DB", None)
        if db is not None:
            usage = result.get("usage", {})
            await db.prepare(
                """INSERT INTO llm_usage (agent, model, prompt_tokens, completion_tokens, total_tokens, cost_usd, task)
                   VALUES (?, ?, ?, ?, ?, ?, ?)"""
            ).bind(
                "scout",
                result.get("model", "unknown"),
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
                usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                None,
                f"scout_run_{triggered_by}",
            ).run()
    except Exception:
        pass

    return {
        "ok": True,
        "brief_id": brief_id,
        "scout_date": date_str,
        "triggered_by": triggered_by,
        "saved_to_d1": saved,
        "result_text": result["text"],
        "usage": result.get("usage", {}),
        "latency_ms": result.get("latency_ms", 0),
    }


@route("POST", "/api/scout/run")
async def scout_run_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Manually trigger scout scan (P0 stub)."""
    result = await run_scout_scan(env, triggered_by="manual_api")
    if not result["ok"]:
        return error_response(result.get("error", "unknown"), status=500, code="SCOUT_FAILED")
    return json_response(result)
