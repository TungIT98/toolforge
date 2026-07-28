"""Tests for monitoring module — just request_id (lean)."""
import pytest

from src.lib import monitoring as mon_mod
from src.lib.monitoring import generate_request_id, get_request_id, set_request_id


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
    assert len(rid) == 36
    assert rid.count("-") == 4


def test_generate_request_id_unique():
    """Each call returns a unique ID."""
    ids = {generate_request_id() for _ in range(100)}
    assert len(ids) == 100


# === set/get request_id tests ===

def test_set_and_get_request_id():
    set_request_id("req-test-123")
    assert get_request_id() == "req-test-123"


def test_get_request_id_empty_when_unset():
    assert get_request_id() == ""


# === dispatch X-Request-Id integration ===

@pytest.mark.asyncio
async def test_dispatch_adds_request_id_to_response():
    from src.router import dispatch
    from tests.test_e2e import FakeEnv

    class Req:
        method = "GET"
        path = "/api/health"
        headers = {}

    env = FakeEnv()
    resp = await dispatch(Req(), env, None)
    assert "X-Request-Id" in resp.headers
    rid = resp.headers["X-Request-Id"]
    assert len(rid) > 0


@pytest.mark.asyncio
async def test_dispatch_honors_client_request_id_header():
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
    from src.router import dispatch
    from tests.test_e2e import FakeEnv

    class Req:
        method = "GET"
        path = "/api/health"
        headers = {"X-Request-Id": "x" * 200}

    env = FakeEnv()
    resp = await dispatch(Req(), env, None)
    assert len(resp.headers["X-Request-Id"]) == 64
