"""ToolForge Worker entry point.

Cloudflare Workers Python runtime — uses pyodide.

Routes (see src/router.py):
  GET  /                       Landing
  GET  /api/health             Liveness + D1 ping
  GET  /api/version            Build + runtime info
  POST /api/llm/test           LLM connectivity test
  POST /api/scout/run          Manually trigger Scout

Cron Triggers (3 active in wrangler.jsonc):
  0 23 * * *  → 06:00 Asia/Saigon daily — Scout scan
  0 15 * * *  → 22:00 Asia/Saigon daily — Helper report
  0 14 * * *  → 21:00 Asia/Saigon daily — Hype report
"""
from __future__ import annotations

from src.lib.log import get_logger
from src.lib.response import error_response
from src.router import dispatch

log = get_logger("worker")


# Required export: WorkerEntrypoint subclass named "Default"
class Default:
    """Cloudflare Workers Python entrypoint.

    Required by CF Python Workers runtime — class name MUST be `Default`
    (or override via main_export in wrangler.jsonc).
    """

    async def fetch(self, request, env, ctx):
        try:
            return await dispatch(request, env, ctx)
        except Exception as e:
            log.error("worker_unhandled", err=str(e), path=getattr(request, "path", "?"))
            return error_response(
                f"Internal error: {e}",
                status=500,
                code="INTERNAL_ERROR",
            )

    async def scheduled(self, controller, env, ctx):
        """Handle cron triggers."""
        from src.handlers.scheduled import handle_cron

        return await handle_cron(controller, env, ctx)
