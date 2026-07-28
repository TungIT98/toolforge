"""Tests for router — verify all critical endpoints are registered.

CRITICAL: this test catches the bug where someone adds a new handler module
but forgets to import it in src/router.py dispatch() — which would make
the endpoint 404 in production.

Approach: call dispatch() once (which triggers the lazy import that registers
all routes), then check ROUTES.
"""
import pytest

from src.router import ROUTES, dispatch, route


def _trigger_handler_loading():
    """Call dispatch() so all handler modules get imported and routes registered."""
    import asyncio

    class Req:
        method = "GET"
        path = "/__test__/route-loading-trigger"

    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("no loop")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(dispatch(Req(), None, None))


def test_router_registers_critical_endpoints():
    """All public/critical endpoints MUST be registered. If this fails, a
    new handler module was added but not imported in src/router.py dispatch().
    """
    _trigger_handler_loading()
    registered = {(m, p) for m, p, _, _ in ROUTES}

    # Each entry: (method, path). Path must match exactly what @route() registers.
    critical = [
        ("GET", "/api/health"),
        ("GET", "/api/version"),
        ("POST", "/api/llm/test"),
        ("POST", "/api/scout/run"),
        ("POST", "/api/architect/spec"),
        ("POST", "/api/forge/build"),
        ("POST", "/api/forge/build-binary"),
        ("GET", "/api/forge/download/{build_id}"),
        ("POST", "/api/forge/license"),
        ("POST", "/api/forge/webhook/built"),
        ("POST", "/api/payment/orders"),
        ("POST", "/api/payment/sepay-webhook"),
        ("POST", "/api/payment/test"),
        ("GET", "/api/store/tools"),
        ("POST", "/api/store/seed"),
        ("POST", "/api/builder/session"),
        ("POST", "/api/builder/session/{session_id}/message"),
        ("POST", "/api/builder/session/{session_id}/build"),
        ("GET", "/api/admin/overview"),
        ("GET", "/api/admin/orders"),
        ("GET", "/api/admin/licenses"),
        ("GET", "/api/admin/pending-specs"),
        ("GET", "/api/admin/briefs"),
        ("GET", "/api/admin/builds"),
        ("POST", "/api/telegram/webhook"),
        ("POST", "/api/telegram/setup"),
        ("GET", "/api/telegram/status"),
        ("POST", "/api/orchestrator/run"),
        ("GET", "/api/orchestrator/runs"),
        ("GET", "/showcase"),
        ("GET", "/agents"),
    ]
    missing = [(m, p) for m, p in critical if (m, p) not in registered]
    assert not missing, (
        f"Missing routes (add `from src.handlers import <module>` to src/router.py dispatch()):\n"
        + "\n".join(f"  {m} {p}" for m, p in missing)
    )


@pytest.mark.asyncio
async def test_router_dispatch_loads_handlers_and_404s_unknown():
    """dispatch() on unknown path returns 404, and triggers handler loading."""
    class Req:
        method = "GET"
        path = "/this/does/not/exist"

    resp = await dispatch(Req(), None, None)
    assert resp.status == 404
    # After dispatch, the lazy import has registered all routes
    registered = {(m, p) for m, p, _, _ in ROUTES}
    assert ("GET", "/api/health") in registered
    assert ("POST", "/api/forge/build") in registered
    assert ("POST", "/api/payment/orders") in registered
    assert ("POST", "/api/builder/session") in registered


# === path-param routing tests (P4 fix) ===

def test_route_decorator_compiles_path_param_to_regex():
    """`/api/foo/{id}` should match `/api/foo/abc-123` but not `/api/foo/`."""
    captured = {}

    @route("GET", "/api/test/{id}")
    async def handler(request, env, ctx):
        captured["params"] = getattr(request, "path_params", None)
        return None

    # Find compiled regex
    regex = next(r for m, p, r, fn in ROUTES if (m, p) == ("GET", "/api/test/{id}"))
    assert regex.match("/api/test/abc-123").groupdict() == {"id": "abc-123"}
    assert regex.match("/api/test/build-12345").groupdict() == {"id": "build-12345"}
    # No match for trailing slash (empty param)
    assert regex.match("/api/test/") is None
    # No match for wrong prefix
    assert regex.match("/api/other/abc-123") is None


@pytest.mark.asyncio
async def test_router_dispatch_extracts_path_params():
    """dispatch() attaches `path_params` to request when path has placeholders."""
    from src.lib.response import json_response

    captured = {}

    @route("GET", "/api/__test__/param/{name}")
    async def handler(request, env, ctx):
        captured["path_params"] = getattr(request, "path_params", None)
        return json_response({"ok": True, "name": request.path_params.get("name")})

    class Req:
        method = "GET"
        path = "/api/__test__/param/zui"
        headers = {}

    resp = await dispatch(Req(), None, None)
    assert captured["path_params"] == {"name": "zui"}
    # Response body should also reflect the captured param
    import json as _json
    body_raw = resp.body
    if isinstance(body_raw, bytes):
        body_raw = body_raw.decode("utf-8", errors="ignore")
    parsed = _json.loads(body_raw) if body_raw else {}
    assert parsed.get("name") == "zui"

    # Cleanup: remove the test route to avoid polluting other tests
    ROUTES[:] = [(m, p, r, fn) for (m, p, r, fn) in ROUTES if (m, p) != ("GET", "/api/__test__/param/{name}")]


@pytest.mark.asyncio
async def test_router_dispatch_no_match_returns_404():
    """Even with path-param routes registered, an unrelated path 404s."""

    class Req:
        method = "GET"
        path = "/totally/unknown/path"
        headers = {}

    resp = await dispatch(Req(), None, None)
    assert resp.status == 404
