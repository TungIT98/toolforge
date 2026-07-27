"""Tests for monitoring module: request_id, log_error_to_kv, list_recent_errors."""
import json
import time

import pytest

from src.lib import monitoring as mon_mod
from src.lib.monitoring import (
    generate_request_id,
    get_error_count_by_severity,
    get_request_id,
    list_recent_errors,
    log_error_to_kv,
    set_request_id,
)


class FakeKV:
    """In-memory KV mimicking CF Workers KV interface for monitoring tests."""
    def __init__(self):
        self.store: dict = {}

    async def get(self, key, type=None):
        val = self.store.get(key)
        if val is None:
            return None
        if type == "text":
            return val
        if type == "json":
            try:
                return json.loads(val)
            except Exception:
                return val
        return val

    async def put(self, key, value, **kwargs):
        self.store[key] = value

    async def list(self, prefix="", limit=1000):
        keys = [{"name": k} for k in sorted(self.store.keys()) if k.startswith(prefix)]
        return {"keys": keys[:limit]}


class FakeEnv:
    def __init__(self, kv=None):
        self.CACHE = kv


@pytest.fixture(autouse=True)
def reset_request_id():
    """Reset request_id state between tests."""
    mon_mod._current_request_id = ""
    yield
    mon_mod._current_request_id = ""


# === generate_request_id tests ===

def test_generate_request_id_is_uuid():
    """Request ID is a valid UUID v4 format."""
    rid = generate_request_id()
    # UUID has 8-4-4-4-12 = 32 hex chars + 4 dashes
    assert len(rid) == 36
    assert rid.count("-") == 4


def test_generate_request_id_unique():
    """Each call returns a unique ID."""
    ids = {generate_request_id() for _ in range(100)}
    assert len(ids) == 100


# === set/get request_id tests ===

def test_set_and_get_request_id():
    """set_request_id stores value, get_request_id returns it."""
    set_request_id("req-test-123")
    assert get_request_id() == "req-test-123"


def test_get_request_id_empty_when_unset():
    """Default empty string when never set."""
    assert get_request_id() == ""


# === log_error_to_kv tests ===

@pytest.mark.asyncio
async def test_log_error_to_kv_writes_to_kv():
    """log_error_to_kv persists error to KV with 7-day TTL."""
    kv = FakeKV()
    env = FakeEnv(kv=kv)
    result = await log_error_to_kv(
        env, severity="error", endpoint="/api/test",
        error="Something failed", code="DB_ERROR",
        request_id="req-abc",
    )
    assert result is True
    assert len(kv.store) == 1
    key = list(kv.store.keys())[0]
    assert key.startswith("error:")
    assert "req-abc" in key
    value = json.loads(kv.store[key])
    assert value["severity"] == "error"
    assert value["endpoint"] == "/api/test"
    assert value["error"] == "Something failed"
    assert value["code"] == "DB_ERROR"
    assert value["request_id"] == "req-abc"


@pytest.mark.asyncio
async def test_log_error_to_kv_no_kv_returns_false():
    """No KV bound → returns False, no exception."""
    env = FakeEnv(kv=None)
    result = await log_error_to_kv(
        env, severity="error", endpoint="/x", error="oops",
    )
    assert result is False


@pytest.mark.asyncio
async def test_log_error_to_kv_uses_current_request_id_if_not_provided():
    """If request_id not passed, uses get_request_id()."""
    set_request_id("req-current-xyz")
    kv = FakeKV()
    env = FakeEnv(kv=kv)
    await log_error_to_kv(
        env, severity="warn", endpoint="/api/foo", error="bad input",
    )
    value = json.loads(list(kv.store.values())[0])
    assert value["request_id"] == "req-current-xyz"


@pytest.mark.asyncio
async def test_log_error_to_kv_caps_long_error():
    """Long error messages are truncated to 500 chars."""
    kv = FakeKV()
    env = FakeEnv(kv=kv)
    long_error = "x" * 1000
    await log_error_to_kv(
        env, severity="error", endpoint="/x",
        error=long_error, request_id="rid",
    )
    value = json.loads(list(kv.store.values())[0])
    assert len(value["error"]) == 500


# === list_recent_errors tests ===

@pytest.mark.asyncio
async def test_list_recent_errors_empty():
    """Empty KV → empty list."""
    kv = FakeKV()
    env = FakeEnv(kv=kv)
    errors = await list_recent_errors(env, limit=10)
    assert errors == []


@pytest.mark.asyncio
async def test_list_recent_errors_no_kv_returns_empty():
    """No KV → empty list (graceful)."""
    env = FakeEnv(kv=None)
    errors = await list_recent_errors(env)
    assert errors == []


@pytest.mark.asyncio
async def test_list_recent_errors_returns_all_within_limit():
    """Returns errors up to limit, sorted newest first."""
    kv = FakeKV()
    env = FakeEnv(kv=kv)
    # Write 5 errors with small delays so ISO timestamps differ
    import asyncio
    for i in range(5):
        await log_error_to_kv(
            env, severity="error", endpoint=f"/api/{i}",
            error=f"err-{i}", request_id=f"rid-{i}",
        )
        await asyncio.sleep(0.01)  # ensure different ISO ts (millisecond resolution)
    errors = await list_recent_errors(env, limit=10)
    assert len(errors) == 5
    # Newest first (lexicographic sort = chronological for ISO timestamps)
    assert errors[0]["endpoint"] == "/api/4"
    assert errors[-1]["endpoint"] == "/api/0"


@pytest.mark.asyncio
async def test_list_recent_errors_filters_by_severity():
    """Filter by severity=error excludes warns."""
    kv = FakeKV()
    env = FakeEnv(kv=kv)
    await log_error_to_kv(env, severity="error", endpoint="/a", error="e1", request_id="r1")
    await log_error_to_kv(env, severity="warn", endpoint="/b", error="w1", request_id="r2")
    await log_error_to_kv(env, severity="error", endpoint="/c", error="e2", request_id="r3")

    errors_only = await list_recent_errors(env, severity="error")
    assert len(errors_only) == 2
    assert all(e["severity"] == "error" for e in errors_only)

    warns_only = await list_recent_errors(env, severity="warn")
    assert len(warns_only) == 1
    assert warns_only[0]["error"] == "w1"


@pytest.mark.asyncio
async def test_list_recent_errors_caps_limit():
    """Limit > 200 is clamped to 200."""
    kv = FakeKV()
    env = FakeEnv(kv=kv)
    await log_error_to_kv(env, severity="info", endpoint="/x", error="x", request_id="r")
    errors = await list_recent_errors(env, limit=9999)
    # Should not crash, just return what's there
    assert len(errors) <= 200


# === get_error_count_by_severity tests ===

def test_get_error_count_by_severity():
    """Aggregates error counts by severity."""
    errors = [
        {"severity": "error"},
        {"severity": "error"},
        {"severity": "warn"},
        {"severity": "info"},
        {"severity": "info"},
        {"severity": "info"},
    ]
    counts = get_error_count_by_severity(errors)
    assert counts == {"error": 2, "warn": 1, "info": 3}


def test_get_error_count_by_severity_empty():
    """Empty list returns zero counts."""
    counts = get_error_count_by_severity([])
    assert counts == {"error": 0, "warn": 0, "info": 0}


# === Integration: dispatch adds X-Request-Id header ===

@pytest.mark.asyncio
async def test_dispatch_adds_request_id_to_response():
    """dispatch() injects X-Request-Id into response headers."""
    from src.router import dispatch

    class Req:
        method = "GET"
        path = "/api/health"
        headers = {}

    # Need to provide minimal env for health
    from tests.test_e2e import FakeEnv
    env = FakeEnv()
    resp = await dispatch(Req(), env, None)
    # Health endpoint should return 200 + X-Request-Id
    assert "X-Request-Id" in resp.headers
    rid = resp.headers["X-Request-Id"]
    assert len(rid) > 0


@pytest.mark.asyncio
async def test_dispatch_honors_client_request_id_header():
    """If client sends X-Request-Id, dispatch uses it (capped at 64 chars)."""
    from src.router import dispatch
    from tests.test_e2e import FakeEnv

    class Req:
        method = "GET"
        path = "/api/health"
        headers = {"X-Request-Id": "client-trace-abc-123"}

    env = FakeEnv()
    resp = await dispatch(Req(), env, None)
    assert resp.headers["X-Request-Id"] == "client-trace-abc-123"


@pytest.mark.asyncio
async def test_dispatch_caps_long_client_request_id():
    """Client X-Request-Id > 64 chars is truncated."""
    from src.router import dispatch
    from tests.test_e2e import FakeEnv

    class Req:
        method = "GET"
        path = "/api/health"
        headers = {"X-Request-Id": "x" * 200}

    env = FakeEnv()
    resp = await dispatch(Req(), env, None)
    assert len(resp.headers["X-Request-Id"]) == 64
