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

D1 JsProxy shim: every request wraps `env.DB` via `src.lib.d1.wrap_db`
so `.first()` / `.all()` / `.run()` return native Python dicts instead
of `pyodide.ffi.JsProxy` objects. Without this, handlers raise
`'pyodide.ffi.JsProxy' object is not iterable` on the first D1 read.
"""
from workers import WorkerEntrypoint, Response

from src.lib.d1 import wrap_db
from src.lib.log import get_logger
from src.lib.response import error_response
from src.router import dispatch

log = get_logger("worker")


def _wrap_env_d1(env):
    """Wrap env.DB so .first()/.all() return native Python dicts.

    CF Python Workers (Pyodide) returns D1 prepared statement results as
    `pyodide.ffi.JsProxy` objects. Without unwrapping, handlers see
    `'pyodide.ffi.JsProxy' object is not iterable` errors. See
    `src/lib/d1.py` for the shim.

    This is idempotent and safe to call per-request. The wrapped object
    is lightweight and stateless; the wrap is cheap.
    """
    if env is None:
        return env
    db = getattr(env, "DB", None)
    if db is None:
        return env
    # Mutate env so downstream handlers reading `env.DB` get the wrapper.
    # `wrap_db` is a no-op if db is already wrapped.
    env.DB = wrap_db(db)
    return env


class Default(WorkerEntrypoint):
    """ToolForge Worker — entrypoint for all 49 HTTP routes + 3 cron triggers."""

    async def on_fetch(self, request):
        # In CF Python Workers, bindings are at self.env (NOT in a
        # parameter to on_fetch). The `env` parameter is None.
        env = self.env
        _wrap_env_d1(env)
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

        # on_scheduled receives env as a parameter (NOT self.env). Wrap here too.
        _wrap_env_d1(env)
        return await handle_cron(controller, env, ctx)
