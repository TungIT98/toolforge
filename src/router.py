"""Router: match URL path to handler. Kept tiny and explicit.
"""
from __future__ import annotations

from typing import Awaitable, Callable

from src.lib.log import get_logger
from src.lib.response import error_response, handle_cors_preflight, json_response

log = get_logger("router")

# Handler type: (request, env, ctx) -> Response
Handler = Callable[["object", "object", "object"], Awaitable["Response"]]

# Map path -> handler
ROUTES: list[tuple[str, str, Handler]] = []


def route(method: str, path: str) -> Callable[[Handler], Handler]:
    """Decorator to register a route."""
    def decorator(fn: Handler) -> Handler:
        ROUTES.append((method, path, fn))
        return fn
    return decorator


async def dispatch(request: "object", env: "object", ctx: "object") -> "Response":
    """Main router: match method+path to handler, else 404."""
    if request.method == "OPTIONS":
        return handle_cors_preflight()

    # Lazy import handlers to avoid circular deps
    from src.handlers import health, llm, scout, version  # noqa: F401

    url_path = request.path  # type: ignore[attr-defined]
    method = request.method  # type: ignore[attr-defined]

    for m, p, fn in ROUTES:
        if m == method and p == url_path:
            return await fn(request, env, ctx)

    log.warn("route_not_found", method=method, path=url_path)
    return error_response(f"No route for {method} {url_path}", status=404, code="ROUTE_NOT_FOUND")
