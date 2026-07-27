"""Scout handlers — P1 real implementation.

Endpoints:
  POST /api/scout/run     Manually trigger Scout pain point scan
  GET  /api/scout/latest  Return latest brief from D1

Cron: 0 23 * * * = 06:00 Asia/Saigon daily (configured in wrangler.jsonc)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from src.lib.log import get_logger
from src.lib.response import error_response, json_response
from src.llm import LLMError, get_client
from src.router import route
from src.scout.analyzer import analyze_to_pain_points, select_top_3_critical
from src.scout.sources import fetch_all_sources, parse_manual_input
from src.scout.writer import format_brief_markdown, format_top_pain_json

log = get_logger("scout.handler")


async def run_scout_scan(
    env: "object",
    triggered_by: str = "manual",
    manual_data: dict | None = None,
) -> dict:
    """Core Scout logic — P1 real implementation.

    Flow:
    1. Fetch raw data from sources (Tavily API) OR use manual_data
    2. LLM analyze → top 10 pain points
    3. Format brief markdown
    4. Save to D1
    5. Log token usage
    """
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    brief_id = f"brief-{date_str}"

    # 1. Get LLM client
    try:
        client = get_client(agent_name="scout", env=env)
    except LLMError as e:
        log.error("scout_no_llm_key", err=str(e))
        return {"ok": False, "error": str(e), "code": "LLM_KEY_MISSING"}

    # 2. Get raw data
    tavily_key = getattr(env, "TAVILY_API_KEY", "") or os.environ.get("TAVILY_API_KEY", "")
    if manual_data:
        raw_data = parse_manual_input(manual_data)
        log.info("scout_manual_data", sources=list(raw_data.keys()))
    else:
        raw_data = await fetch_all_sources(tavily_key)
        log.info("scout_auto_data", sources={k: len(v) for k, v in raw_data.items()})

    raw_summary = {k: len(v) for k, v in raw_data.items()}
    total_hits = sum(raw_summary.values())
    if total_hits == 0:
        log.warn("scout_no_hits", tavily_key_set=bool(tavily_key))
        return {
            "ok": False,
            "error": "No data fetched. Set TAVILY_API_KEY or provide manual_data.",
            "code": "NO_DATA",
            "tavily_key_set": bool(tavily_key),
        }

    # 3. LLM analyze
    pain_points = await analyze_to_pain_points(raw_data, client, max_pain_points=10)
    if not pain_points:
        return {
            "ok": False,
            "error": "LLM did not extract any valid pain points. Check logs.",
            "code": "NO_PAIN_POINTS",
        }

    # 4. Format brief
    # Re-fetch LLM usage from last call (analyzer uses client.call but doesn't return)
    # We approximate via the last call; for now, use totals
    severity_avg = sum(pp["severity"] for pp in pain_points) / len(pain_points)
    brief_md = format_brief_markdown(
        date_str=date_str,
        pain_points=pain_points,
        raw_data_summary=raw_summary,
    )
    top_pain_json = format_top_pain_json(pain_points)
    top3 = select_top_3_critical(pain_points)

    # 5. Save to D1
    saved = False
    try:
        db = getattr(env, "DB", None)
        if db is not None:
            await db.prepare(
                """INSERT OR REPLACE INTO briefs (id, scout_date, content, top_pain_json, severity_avg, source_count)
                   VALUES (?, ?, ?, ?, ?, ?)"""
            ).bind(
                brief_id,
                date_str,
                brief_md,
                top_pain_json,
                severity_avg,
                total_hits,
            ).run()
            saved = True
    except Exception as e:
        log.warn("scout_save_failed", err=str(e))

    # 6. Log token usage (best-effort)
    try:
        db = getattr(env, "DB", None)
        if db is not None:
            # We don't have exact token count from analyze (returned list, not dict)
            # Estimate: 1 call ~ 2K in + 1K out (rough)
            await db.prepare(
                """INSERT INTO llm_usage (agent, model, prompt_tokens, completion_tokens, total_tokens, cost_usd, task)
                   VALUES (?, ?, ?, ?, ?, ?, ?)"""
            ).bind(
                "scout",
                os.environ.get("LLM_MODEL", "minimax/MiniMax-M3"),
                2000, 1000, 3000, None,
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
        "total_pain_points": len(pain_points),
        "top3_critical": [
            {"title": pp["title"], "severity": pp["severity"], "audience": pp.get("audience", "")}
            for pp in top3
        ],
        "source_coverage": raw_summary,
        "severity_avg": round(severity_avg, 2),
        "tavily_key_used": bool(tavily_key),
        "brief_markdown_preview": brief_md[:1000] + "..." if len(brief_md) > 1000 else brief_md,
    }


@route("POST", "/api/scout/run")
async def scout_run_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Manually trigger Scout scan.

    Request body (optional):
    {
        "manual_data": {
            "google_trends": [...],
            "competitor_1touch": [...],
            "mmo_forums": [...],
            "creator_buzz": [...]
        }
    }
    If no manual_data, Scout will use Tavily API (if TAVILY_API_KEY set).
    """
    manual_data: dict | None = None
    try:
        if request.headers.get("content-type", "").startswith("application/json"):  # type: ignore[attr-defined]
            body = await request.json()  # type: ignore[attr-defined]
            if isinstance(body, dict):
                manual_data = body.get("manual_data")
    except Exception as e:
        log.warn("scout_bad_body", err=str(e))

    result = await run_scout_scan(env, triggered_by="manual_api", manual_data=manual_data)
    if not result["ok"]:
        code = result.get("code", "SCOUT_FAILED")
        status = 500 if code in ("LLM_KEY_MISSING", "NO_PAIN_POINTS") else 400
        return error_response(result.get("error", "unknown"), status=status, code=code)
    return json_response(result)


@route("GET", "/api/scout/latest")
async def scout_latest_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Return the latest brief from D1."""
    try:
        db = getattr(env, "DB", None)
        if db is None:
            return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
        result = await db.prepare(
            "SELECT id, scout_date, content, top_pain_json, severity_avg, source_count, created_at "
            "FROM briefs ORDER BY created_at DESC LIMIT 1"
        ).first()
        if not result:
            return json_response({"ok": True, "brief": None, "message": "No brief yet. Run /api/scout/run first."})
        return json_response({"ok": True, "brief": result})
    except Exception as e:
        return error_response(str(e), status=500, code="DB_QUERY_FAILED")
