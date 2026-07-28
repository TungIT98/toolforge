"""Tests for P4 endpoints: /api/forge/build-binary + /api/forge/download/{build_id}.

These complete the P4 Tauri build pipeline:
  POST /api/forge/build          (P1 — generates code, writes build record with test_result=pass)
  POST /api/forge/build-binary   (P4 — triggers GH Action workflow_dispatch)
  POST /api/forge/webhook/built  (P4 — GH Action callback, writes binary_path to D1)
  GET  /api/forge/download/{id}  (P4 — returns fresh R2 signed URL, 7-day expiry)
"""
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.forge.license import generate_license_key


def _body(resp):
    """Parse JSON body from a Response (handles bytes or str)."""
    raw = resp.body
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    return json.loads(raw) if raw else {}


def _code(resp):
    """Extract error code from response (e.g. 'BUILD_NOT_FOUND')."""
    body = _body(resp)
    err = body.get("error") or {}
    if isinstance(err, dict):
        return err.get("code")
    return None


def _make_env(db=None, **extra):
    """Build a minimal env that the handler can read from."""

    class Env:
        pass

    env = Env()
    env.DB = db
    for k, v in extra.items():
        setattr(env, k, v)
    return env


def _make_request(method, path, body=None, headers=None):
    """Build a minimal request object (used by handler signature)."""
    from types import SimpleNamespace

    req = SimpleNamespace()
    req.method = method
    req.path = path
    req.headers = headers or {}
    req.url = path

    async def _json():
        return body or {}

    async def _text():
        return json.dumps(body) if body else ""

    req.json = _json
    req.text = _text
    return req


# === /api/forge/build-binary ===

@pytest.mark.asyncio
async def test_build_binary_missing_build_id():
    from src.handlers.forge import forge_build_binary_handler
    req = _make_request("POST", "/api/forge/build-binary", body={})
    resp = await forge_build_binary_handler(req, _make_env(db=None), None)
    assert resp.status == 400
    assert _code(resp) == "MISSING_BUILD_ID"


@pytest.mark.asyncio
async def test_build_binary_invalid_json():
    from src.handlers.forge import forge_build_binary_handler
    req = _make_request("POST", "/api/forge/build-binary", body=None)

    async def bad_json():
        raise Exception("bad json")

    req.json = bad_json
    resp = await forge_build_binary_handler(req, _make_env(), None)
    assert resp.status == 400
    body = _body(resp)
    assert _code(resp) == "INVALID_JSON"


@pytest.mark.asyncio
async def test_build_binary_no_db():
    from src.handlers.forge import forge_build_binary_handler
    req = _make_request("POST", "/api/forge/build-binary", body={"build_id": "build-x"})
    resp = await forge_build_binary_handler(req, _make_env(db=None), None)
    assert resp.status == 500
    body = _body(resp)
    assert _code(resp) == "DB_NOT_BOUND"


@pytest.mark.asyncio
async def test_build_binary_build_not_found():
    from tests.test_e2e import FakeD1, FakeEnv
    from src.handlers.forge import forge_build_binary_handler
    env = FakeEnv()
    req = _make_request("POST", "/api/forge/build-binary", body={"build_id": "build-ghost"})
    resp = await forge_build_binary_handler(req, env, None)
    assert resp.status == 404
    body = _body(resp)
    assert _code(resp) == "BUILD_NOT_FOUND"


@pytest.mark.asyncio
async def test_build_binary_build_not_ready_test_result_fail():
    from tests.test_e2e import FakeD1, FakeEnv
    from src.handlers.forge import forge_build_binary_handler
    env = FakeEnv()
    env.DB.tables["builds"].append({
        "id": "build-fail-001", "tool_id": "test-tool", "handoff_id": "h-1",
        "version": "0.1.0", "code_path": "d1://...", "test_result": "fail",
        "binary_path": "", "binary_url": "", "size_bytes": 0, "created_at": "2026-07-28",
    })
    req = _make_request("POST", "/api/forge/build-binary", body={"build_id": "build-fail-001"})
    resp = await forge_build_binary_handler(req, env, None)
    assert resp.status == 400
    body = _body(resp)
    assert _code(resp) == "BUILD_NOT_READY"


@pytest.mark.asyncio
async def test_build_binary_missing_github_token():
    from tests.test_e2e import FakeEnv
    from src.handlers.forge import forge_build_binary_handler
    env = FakeEnv()
    env.DB.tables["builds"].append({
        "id": "build-001", "tool_id": "test-tool", "handoff_id": "h-1",
        "version": "0.1.0", "code_path": "d1://...", "test_result": "pass",
        "binary_path": "", "binary_url": "", "size_bytes": 0, "created_at": "2026-07-28",
    })
    req = _make_request("POST", "/api/forge/build-binary", body={"build_id": "build-001"})
    resp = await forge_build_binary_handler(req, env, None)
    assert resp.status == 500
    body = _body(resp)
    assert _code(resp) == "GITHUB_TOKEN_MISSING"


@pytest.mark.asyncio
async def test_build_binary_success():
    from tests.test_e2e import FakeEnv
    from src.handlers.forge import forge_build_binary_handler
    env = FakeEnv()
    env.GITHUB_TOKEN = "ghp-test-123"
    env.WEBHOOK_SECRET = "shared-secret"
    env.WORKER_URL = "https://toolforge-api.tungit98.workers.dev"
    env.DB.tables["builds"].append({
        "id": "build-001", "tool_id": "test-tool", "handoff_id": "h-1",
        "version": "0.1.0", "code_path": "d1://...", "test_result": "pass",
        "binary_path": "", "binary_url": "", "size_bytes": 0, "created_at": "2026-07-28",
    })

    async def fake_post(*args, **kwargs):
        return httpx.Response(204)

    req = _make_request("POST", "/api/forge/build-binary", body={"build_id": "build-001"})
    with patch("httpx.AsyncClient.post", new=fake_post):
        resp = await forge_build_binary_handler(req, env, None)

    assert resp.status == 200
    body = json.loads(resp.body.decode() if isinstance(resp.body, bytes) else resp.body)
    assert body["ok"] is True
    assert body["build_id"] == "build-001"
    assert body["status"] == "building"
    assert "workflow_url" in body
    assert body["callback_url"].endswith("/api/forge/webhook/built")
    assert body["expected_time_minutes"] == "5-10"
    # D1 should be updated to 'building'
    build = next(b for b in env.DB.tables["builds"] if b["id"] == "build-001")
    assert build["test_result"] == "building"


@pytest.mark.asyncio
async def test_build_binary_accepts_partial_test_result():
    """A build with test_result='partial' should still be triggerable (manual override)."""
    from tests.test_e2e import FakeEnv
    from src.handlers.forge import forge_build_binary_handler
    env = FakeEnv()
    env.GITHUB_TOKEN = "ghp-test"
    env.WEBHOOK_SECRET = "secret"
    env.DB.tables["builds"].append({
        "id": "build-partial-001", "tool_id": "test-tool", "handoff_id": "h-1",
        "version": "0.1.0", "code_path": "d1://...", "test_result": "partial",
        "binary_path": "", "binary_url": "", "size_bytes": 0, "created_at": "2026-07-28",
    })

    async def fake_post(*args, **kwargs):
        return httpx.Response(204)

    req = _make_request("POST", "/api/forge/build-binary", body={"build_id": "build-partial-001"})
    with patch("httpx.AsyncClient.post", new=fake_post):
        resp = await forge_build_binary_handler(req, env, None)

    assert resp.status == 200
    body = json.loads(resp.body.decode() if isinstance(resp.body, bytes) else resp.body)
    assert body["ok"] is True


@pytest.mark.asyncio
async def test_build_binary_uses_default_worker_url_when_env_missing():
    """If WORKER_URL is not set, fall back to workers.dev pattern."""
    from tests.test_e2e import FakeEnv
    from src.handlers.forge import forge_build_binary_handler
    env = FakeEnv()
    env.GITHUB_TOKEN = "ghp-test"
    env.WEBHOOK_SECRET = "secret"
    env.ACCOUNT_SUBDOMAIN = "tungit98"
    env.DB.tables["builds"].append({
        "id": "build-002", "tool_id": "test-tool", "handoff_id": "h-1",
        "version": "0.1.0", "code_path": "d1://...", "test_result": "pass",
        "binary_path": "", "binary_url": "", "size_bytes": 0, "created_at": "2026-07-28",
    })

    async def fake_post(*args, **kwargs):
        return httpx.Response(204)

    req = _make_request("POST", "/api/forge/build-binary", body={"build_id": "build-002"})
    with patch("httpx.AsyncClient.post", new=fake_post):
        resp = await forge_build_binary_handler(req, env, None)

    body = json.loads(resp.body.decode() if isinstance(resp.body, bytes) else resp.body)
    assert "tungit98.workers.dev" in body["callback_url"]


# === /api/forge/download/{build_id} ===

@pytest.mark.asyncio
async def test_download_no_db():
    from src.handlers.forge import forge_download_handler
    req = _make_request("GET", "/api/forge/download/build-001")
    req.path_params = {"build_id": "build-001"}
    resp = await forge_download_handler(req, _make_env(db=None), None)
    assert resp.status == 500
    body = _body(resp)
    assert _code(resp) == "DB_NOT_BOUND"


@pytest.mark.asyncio
async def test_download_build_not_found():
    from tests.test_e2e import FakeEnv
    from src.handlers.forge import forge_download_handler
    env = FakeEnv()
    req = _make_request("GET", "/api/forge/download/build-ghost")
    req.path_params = {"build_id": "build-ghost"}
    resp = await forge_download_handler(req, env, None)
    assert resp.status == 404
    body = _body(resp)
    assert _code(resp) == "BUILD_NOT_FOUND"


@pytest.mark.asyncio
async def test_download_no_binary_path():
    """Build exists but no binary yet — webhook hasn't fired."""
    from tests.test_e2e import FakeEnv
    from src.handlers.forge import forge_download_handler
    env = FakeEnv()
    env.R2_ACCOUNT_ID = "test-acct"
    env.R2_ACCESS_KEY_ID = "test-key"
    env.R2_SECRET_ACCESS_KEY = "test-secret"
    env.DB.tables["builds"].append({
        "id": "build-empty-001", "tool_id": "test-tool", "handoff_id": "h-1",
        "version": "0.1.0", "code_path": "d1://...", "test_result": "pass",
        "binary_path": "", "binary_url": "", "size_bytes": 0, "created_at": "2026-07-28",
    })
    req = _make_request("GET", "/api/forge/download/build-empty-001")
    req.path_params = {"build_id": "build-empty-001"}
    resp = await forge_download_handler(req, env, None)
    assert resp.status == 400
    body = _body(resp)
    assert _code(resp) == "NO_BINARY"


@pytest.mark.asyncio
async def test_download_r2_not_configured():
    from tests.test_e2e import FakeEnv
    from src.handlers.forge import forge_download_handler
    env = FakeEnv()
    # Don't set R2_* env vars
    env.DB.tables["builds"].append({
        "id": "build-r2-001", "tool_id": "test-tool", "handoff_id": "h-1",
        "version": "0.1.0", "code_path": "d1://...", "test_result": "pass",
        "binary_path": "test-tool/0.1.0/setup.exe", "binary_url": "",
        "size_bytes": 12345678, "created_at": "2026-07-28",
    })
    req = _make_request("GET", "/api/forge/download/build-r2-001")
    req.path_params = {"build_id": "build-r2-001"}
    resp = await forge_download_handler(req, env, None)
    assert resp.status == 503
    body = _body(resp)
    assert _code(resp) == "R2_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_download_success():
    from tests.test_e2e import FakeEnv
    from src.handlers.forge import forge_download_handler
    env = FakeEnv()
    env.R2_ACCOUNT_ID = "test-acct"
    env.R2_ACCESS_KEY_ID = "test-key"
    env.R2_SECRET_ACCESS_KEY = "test-secret"
    env.DB.tables["builds"].append({
        "id": "build-dl-001", "tool_id": "test-tool", "handoff_id": "h-1",
        "version": "0.1.0", "code_path": "d1://...", "test_result": "pass",
        "binary_path": "test-tool/0.1.0/setup.exe",
        "binary_url": "https://r2.example.com/old-url",  # expired
        "size_bytes": 12345678, "created_at": "2026-07-28",
    })
    req = _make_request("GET", "/api/forge/download/build-dl-001")
    req.path_params = {"build_id": "build-dl-001"}
    resp = await forge_download_handler(req, env, None)
    assert resp.status == 200
    body = json.loads(resp.body.decode() if isinstance(resp.body, bytes) else resp.body)
    assert body["ok"] is True
    assert body["build_id"] == "build-dl-001"
    assert body["tool_id"] == "test-tool"
    assert body["version"] == "0.1.0"
    assert "test-acct.r2.cloudflarestorage.com" in body["binary_url"]
    assert "test-tool/0.1.0/setup.exe" in body["binary_url"]
    assert body["binary_path"] == "test-tool/0.1.0/setup.exe"
    assert body["cached_url"] == "https://r2.example.com/old-url"
    assert body["size_bytes"] == 12345678
    assert body["expires_in_days"] == 7
    assert "T" in body["expires_at"]  # ISO timestamp


@pytest.mark.asyncio
async def test_download_fallback_to_path_parsing():
    """If router didn't attach path_params (e.g. in tests), handler falls back
    to parsing request.path manually. This is the same path builder.py uses."""
    from tests.test_e2e import FakeEnv
    from src.handlers.forge import forge_download_handler
    env = FakeEnv()
    env.R2_ACCOUNT_ID = "test-acct"
    env.R2_ACCESS_KEY_ID = "test-key"
    env.R2_SECRET_ACCESS_KEY = "test-secret"
    env.DB.tables["builds"].append({
        "id": "build-fb-001", "tool_id": "test-tool", "handoff_id": "h-1",
        "version": "0.1.0", "code_path": "d1://...", "test_result": "pass",
        "binary_path": "test-tool/0.1.0/setup.exe", "binary_url": "",
        "size_bytes": 0, "created_at": "2026-07-28",
    })
    req = _make_request("GET", "/api/forge/download/build-fb-001")
    # No path_params set
    resp = await forge_download_handler(req, env, None)
    assert resp.status == 200
    body = json.loads(resp.body.decode() if isinstance(resp.body, bytes) else resp.body)
    assert body["build_id"] == "build-fb-001"
