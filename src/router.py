"""Router: match URL path to handler. Kept tiny and explicit.

Supports path parameters via `{name}` syntax. Example:

    @route("GET", "/api/forge/download/{id}")
    async def handler(request, env, ctx):
        build_id = request.path_params["id"]   # "build-abc-123"
        ...

At runtime, `dispatch()` compiles each registered path to a regex
(`/api/forge/download/{id}` -> `^/api/forge/download/(?P<id>[^/]+)$`)
and matches the path extracted from `request.url` against it. On a
hit, the captured groups are attached to the request object as
`request.path_params`.

CF Python Workers note: the `Request` object does NOT have a `.path`
attribute (unlike the older Workers Python SDK). Path must be extracted
from `request.url` via `urllib.parse.urlparse`.
"""
from __future__ import annotations

import re
from typing import Awaitable, Callable
from urllib.parse import urlparse

from src.lib.log import get_logger
from src.lib.response import error_response, handle_cors_preflight, json_response

log = get_logger("router")

# Handler type: (request, env, ctx) -> Response
Handler = Callable[["object", "object", "object"], Awaitable["Response"]]

# Pattern to convert {name} -> (?P<name>[^/]+)
_PARAM_RE = re.compile(r"\{(\w+)\}")

# (method, path_pattern, compiled_regex, handler)
ROUTES: list[tuple[str, str, "re.Pattern[str]", Handler]] = []


def _compile_path(path: str) -> "re.Pattern[str]":
    """Convert /api/foo/{id}/bar -> ^/api/foo/(?P<id>[^/]+)/bar$"""
    pattern = _PARAM_RE.sub(r"(?P<\1>[^/]+)", path)
    return re.compile(f"^{pattern}$")


def route(method: str, path: str) -> Callable[[Handler], Handler]:
    """Decorator to register a route. Supports {name} path params.

    Examples:
        @route("GET", "/api/health")
        @route("POST", "/api/forge/download/{id}")
    """
    def decorator(fn: Handler) -> Handler:
        ROUTES.append((method, path, _compile_path(path), fn))
        return fn
    return decorator


def _add_request_id_header(response, request_id: str):
    """Add X-Request-Id to response headers if not already there."""
    try:
        if response is None:
            return response
        if hasattr(response, "headers") and isinstance(response.headers, dict):
            if "X-Request-Id" not in response.headers:
                response.headers["X-Request-Id"] = request_id
    except Exception:
        # Never let monitoring break responses
        pass
    return response


async def dispatch(request: "object", env: "object", ctx: "object") -> "Response":
    """Main router: match method+path to handler, else 404.

    Per-request setup:
    1. Configure CORS from env.ALLOWED_ORIGINS
    2. Generate X-Request-Id (or use client-provided)
    3. Inject X-Request-Id into all response headers
    """
    # 1. Configure CORS at request start so all response helpers use the right policy
    from src.lib.response import configure_cors
    configure_cors(env=env)

    # 2. Generate / propagate request_id
    from src.lib.monitoring import generate_request_id, set_request_id
    # Honor client-provided X-Request-Id for tracing across services (with safety cap)
    client_rid = None
    try:
        client_rid = request.headers.get("X-Request-Id") or request.headers.get("X-Request-ID")  # type: ignore[attr-defined]
    except Exception:
        client_rid = None
    rid = (client_rid[:64] if client_rid else generate_request_id())
    set_request_id(rid)

    if request.method == "OPTIONS":
        return _add_request_id_header(handle_cors_preflight(request), rid)

    # Lazy import handlers to avoid circular deps.
    # CRITICAL: must import ALL handler modules so their @route decorators
    # run and register routes. Missing one = endpoint 404 in production.
    from src.handlers import (  # noqa: F401
        admin, agents, architect, builder, forge, health, hype, license, llm,
        orchestrator, payment, scout, showcase, store, telegram, version,
    )

    # CF Python Workers Request has no `.path` attr; parse from `.url`.
    # Fall back to `.path` for tests that build a SimpleNamespace mock.
    if hasattr(request, "url") and isinstance(getattr(request, "url", None), str):
        url_path = urlparse(request.url).path
    else:
        url_path = getattr(request, "path", "/")
    method = request.method

    for m, p, regex, fn in ROUTES:
        if m == method:
            match = regex.match(url_path)
            if match:
                # Attach path params to request (best-effort: read-only
                # request types in some runtimes will raise on setattr,
                # but tests + CF Workers Python both allow it)
                try:
                    request.path_params = match.groupdict()
                except Exception:
                    pass
                response = await fn(request, env, ctx)
                return _add_request_id_header(response, rid)

    # 404 — log to stdout only
    log.warn("route_not_found", method=method, path=url_path, request_id=rid)
    response = error_response(f"No route for {method} {url_path}", status=404, code="ROUTE_NOT_FOUND")
    return _add_request_id_header(response, rid)
