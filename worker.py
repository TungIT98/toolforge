"""ToolForge Worker entry point (root).

CF Python Workers runtime contract (verified working 2026-07-28):
- Entry module must define a `Default` class extending `WorkerEntrypoint`
- Method `on_fetch(self, request)` is the event-handler convention
- Bindings are at `self.env.DB`, `self.env.CACHE`, etc. (NOT in a
  parameter to on_fetch). The `env` parameter is `None` in the
  current CF Python runtime.
- `on_scheduled(self, controller, env, ctx)` for cron — env IS a
  parameter here.
- The runtime sets `cwd=/` and exposes bundled Python modules via
  `/workspace` in sys.path. After ~60s rollout, `from src.X import Y`
  resolves correctly.
- `httpx` is NOT pre-installed — use `src.lib.http` (urllib shim).
- `Request` has no `.path` — extract via `urllib.parse.urlparse(request.url).path`

Why this file lives at the project root (not inside `src/`):
The CF Python runtime does NOT use the entrypoint's directory as cwd
(it uses `/` always). The `from src.X` pattern works because wrangler
bundles the project tree and the runtime exposes them as importable
modules. The project structure on disk is purely for the bundler; the
runtime has no `/src/` directory.
"""
from workers import WorkerEntrypoint, Response

from src.lib.log import get_logger
from src.lib.response import error_response
from src.router import dispatch

log = get_logger("worker")


class Default(WorkerEntrypoint):
    """ToolForge Worker — entrypoint for all 49 HTTP routes + 3 cron triggers."""

    async def on_fetch(self, request):
        # In CF Python Workers, bindings are at self.env (NOT in a
        # parameter to on_fetch). The `env` parameter is None.
        env = self.env
        try:
            return await dispatch(request, env, None)
        except Exception as e:
            log.error("worker_unhandled", err=str(e), path=getattr(request, "path", "?"))
            return error_response(
                f"Internal error: {e}",
                status=500,
                code="INTERNAL_ERROR",
            )

    async def on_scheduled(self, controller, env, ctx):
        from src.handlers.scheduled import handle_cron

        return await handle_cron(controller, env, ctx)
