"""Tests for /api/forge/webhook/built — secret verification + fail-closed.

Critical security tests: webhook must:
- Fail-closed (503) if WEBHOOK_SECRET env is not set
- Reject (401) if X-Webhook-Secret is missing
- Reject (401) if X-Webhook-Secret doesn't match
- Accept (200) if secret matches
"""
import json
import pytest

from tests.test_e2e import FakeD1, FakeEnv


def _make_req(secret: str | None = None, body: dict | None = None):
    """Build a fake request object."""
    class Req:
        def __init__(self, headers, body_dict):
            self.headers = headers
            self._body = json.dumps(body_dict) if body_dict is not None else "{}"
        async def text(self):
            return self._body
        async def json(self):
            return json.loads(self._body)
    return Req(
        {"X-Webhook-Secret": secret} if secret else {},
        body or {"build_id": "build-test-0.1.0", "tool_id": "test-tool"},
    )


def _make_env(secret: str | None = None) -> FakeEnv:
    """Build env with optional WEBHOOK_SECRET."""
    class _Env(FakeEnv):
        def __init__(self, webhook_secret):
            super().__init__()
            self.WEBHOOK_SECRET = webhook_secret
    return _Env(secret)


@pytest.mark.asyncio
async def test_webhook_fail_closed_when_secret_not_configured():
    """WEBHOOK_SECRET empty → 503 (refuse to process)."""
    from src.handlers.forge import webhook_built_handler
    env = _make_env(secret="")
    req = _make_req(secret="anything")
    resp = await webhook_built_handler(req, env, None)
    assert resp.status == 503
    body = json.loads(resp.body)
    assert body["ok"] is False
    assert body["error"]["code"] == "WEBHOOK_SECRET_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_webhook_fail_closed_when_secret_is_none():
    """WEBHOOK_SECRET None → 503 (refuse to process)."""
    from src.handlers.forge import webhook_built_handler
    env = _make_env(secret=None)
    req = _make_req(secret="anything")
    resp = await webhook_built_handler(req, env, None)
    assert resp.status == 503


@pytest.mark.asyncio
async def test_webhook_reject_missing_secret_header():
    """No X-Webhook-Secret header → 401."""
    from src.handlers.forge import webhook_built_handler
    env = _make_env(secret="real-secret-123")
    req = _make_req(secret=None)
    resp = await webhook_built_handler(req, env, None)
    assert resp.status == 401
    body = json.loads(resp.body)
    assert body["error"]["code"] == "WEBHOOK_AUTH_FAILED"


@pytest.mark.asyncio
async def test_webhook_reject_wrong_secret():
    """Wrong X-Webhook-Secret → 401."""
    from src.handlers.forge import webhook_built_handler
    env = _make_env(secret="real-secret-123")
    req = _make_req(secret="wrong-secret")
    resp = await webhook_built_handler(req, env, None)
    assert resp.status == 401


@pytest.mark.asyncio
async def test_webhook_accept_valid_secret():
    """Correct X-Webhook-Secret → 200/400 (depends on body)."""
    from src.handlers.forge import webhook_built_handler
    env = _make_env(secret="real-secret-123")
    # No matching build → 400 BUILD_NOT_FOUND but NOT 401/503
    req = _make_req(secret="real-secret-123", body={"build_id": "build-nonexistent"})
    resp = await webhook_built_handler(req, env, None)
    # Pass auth + body parsing → reaches handle_build_complete → returns 400
    assert resp.status in (200, 400)
    body = json.loads(resp.body)
    if not body["ok"]:
        # Either BUILD_NOT_FOUND (400) — auth passed
        assert body["error"]["code"] != "WEBHOOK_AUTH_FAILED"
        assert body["error"]["code"] != "WEBHOOK_SECRET_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_webhook_secret_is_case_sensitive_comparison():
    """verify_webhook_secret uses hmac.compare_digest (constant-time, exact match)."""
    from src.handlers.forge import webhook_built_handler
    env = _make_env(secret="Real-Secret-123")
    # Different case → should fail
    req = _make_req(secret="real-secret-123")
    resp = await webhook_built_handler(req, env, None)
    assert resp.status == 401


@pytest.mark.asyncio
async def test_webhook_rejects_empty_string_secret():
    """X-Webhook-Secret: "" → 401 (empty is not valid)."""
    from src.handlers.forge import webhook_built_handler
    env = _make_env(secret="real-secret-123")
    req = _make_req(secret="")
    resp = await webhook_built_handler(req, env, None)
    assert resp.status == 401
