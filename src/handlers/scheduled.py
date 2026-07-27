"""Scheduled (cron) handler — invoked by Cloudflare Triggers.

3 crons registered in wrangler.jsonc:
  1. 0 23 * * *  → 06:00 Asia/Saigon daily — Scout pain point scan
  2. 0 15 * * *  → 22:00 Asia/Saigon daily — Helper daily report (P5+)
  3. 0 14 * * *  → 21:00 Asia/Saigon daily — Hype daily ads report (P2+)
"""
from __future__ import annotations

from src.lib.log import get_logger
from src.lib.response import json_response

log = get_logger("scheduled")


async def handle_cron(controller: "object", env: "object", ctx: "object") -> "Response":
    """Dispatch cron trigger to the right agent.

    CF CronTrigger pattern: schedule = "* / 6 * * *"
    We get the cron string from controller.cron (or parse controller itself).
    """
    # controller.cron is a string like "0 23 * * *"
    cron_str = getattr(controller, "cron", "unknown")
    log.info("cron_trigger", cron=cron_str)

    if cron_str == "0 23 * * *":
        # Scout daily 06:00
        from src.handlers.scout import run_scout_scan

        result = await run_scout_scan(env, triggered_by="cron_daily")
        log.info("cron_scout_done", ok=result.get("ok"), brief_id=result.get("brief_id"))
        return json_response({"ok": True, "cron": cron_str, "agent": "scout", "result": result})

    elif cron_str == "0 15 * * *":
        # Helper daily 22:00 (P5+ — stub now)
        log.info("cron_helper_daily_stub")
        return json_response({"ok": True, "cron": cron_str, "agent": "helper", "result": {"stub": True}})

    elif cron_str == "0 14 * * *":
        # Hype daily 21:00 (P2+ — stub now)
        log.info("cron_hype_daily_stub")
        return json_response({"ok": True, "cron": cron_str, "agent": "hype", "result": {"stub": True}})

    else:
        log.warn("cron_unknown", cron=cron_str)
        return json_response({"ok": False, "error": f"unknown cron: {cron_str}"}, status=400)
