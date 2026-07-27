"""Tests for license verification endpoint."""
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.forge.license_verifier import verify_license
from tests.test_e2e import FakeD1, FakeEnv


@pytest.mark.asyncio
async def test_verify_license_invalid_format():
    """Bad format returns invalid: invalid_format."""
    env = FakeEnv()
    result = await verify_license(env.DB, "not-a-key", "any-tool")
    assert result["ok"]
    assert result["valid"] is False
    assert result["reason"] == "invalid_format"


@pytest.mark.asyncio
async def test_verify_license_not_found():
    """Valid format but not in D1."""
    env = FakeEnv()
    result = await verify_license(env.DB, "AAAA-BBBB-CCCC-DDDD", "any-tool")
    assert result["ok"]
    assert result["valid"] is False
    assert result["reason"] == "not_found"


@pytest.mark.asyncio
async def test_verify_license_active_match():
    """Active license for matching tool → valid."""
    env = FakeEnv()
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    env.DB.tables["licenses"].append({
        "key": "AAAA-1111-BBBB-2222",
        "tool_id": "capcut-reup",
        "status": "active",
        "customer_email": "zui@example.com",
        "customer_telegram": None,
        "activated_at": "2026-07-27",
        "expires_at": future,
    })
    result = await verify_license(env.DB, "AAAA-1111-BBBB-2222", "capcut-reup")
    assert result["ok"]
    assert result["valid"] is True
    assert result["reason"] == "active"
    assert result["license"]["customer_email"] == "zui@example.com"


@pytest.mark.asyncio
async def test_verify_license_expired():
    """Past expiry → invalid: expired."""
    env = FakeEnv()
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    env.DB.tables["licenses"].append({
        "key": "AAAA-1111-BBBB-2222",
        "tool_id": "capcut-reup",
        "status": "active",
        "customer_email": "zui@example.com",
        "expires_at": past,
    })
    result = await verify_license(env.DB, "AAAA-1111-BBBB-2222", "capcut-reup")
    assert result["valid"] is False
    assert result["reason"] == "expired"


@pytest.mark.asyncio
async def test_verify_license_revoked():
    env = FakeEnv()
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    env.DB.tables["licenses"].append({
        "key": "AAAA-1111-BBBB-2222",
        "tool_id": "capcut-reup",
        "status": "revoked",
        "customer_email": "bad@actor.com",
        "expires_at": future,
    })
    result = await verify_license(env.DB, "AAAA-1111-BBBB-2222", "capcut-reup")
    assert result["valid"] is False
    assert result["reason"] == "revoked"


@pytest.mark.asyncio
async def test_verify_license_tool_mismatch():
    env = FakeEnv()
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    env.DB.tables["licenses"].append({
        "key": "AAAA-1111-BBBB-2222",
        "tool_id": "capcut-reup",
        "status": "active",
        "customer_email": "zui@example.com",
        "expires_at": future,
    })
    result = await verify_license(env.DB, "AAAA-1111-BBBB-2222", "voice-clone")
    assert result["valid"] is False
    assert result["reason"] == "tool_mismatch"


@pytest.mark.asyncio
async def test_verify_license_no_expiry_is_perpetual():
    """No expires_at set → always valid (until revoked)."""
    env = FakeEnv()
    env.DB.tables["licenses"].append({
        "key": "AAAA-1111-BBBB-2222",
        "tool_id": "capcut-reup",
        "status": "active",
        "customer_email": "zui@example.com",
        "expires_at": None,
    })
    result = await verify_license(env.DB, "AAAA-1111-BBBB-2222", "capcut-reup")
    assert result["valid"] is True
    assert result["reason"] == "active"


# === handler tests ===

@pytest.mark.asyncio
async def test_license_verify_handler_success():
    from src.handlers.license import license_verify_handler
    env = FakeEnv()
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    env.DB.tables["licenses"].append({
        "key": "AAAA-1111-BBBB-2222",
        "tool_id": "capcut-reup",
        "status": "active",
        "customer_email": "zui@example.com",
        "expires_at": future,
    })

    class Req:
        path = "/api/license/verify"
        method = "POST"
        headers = {"content-type": "application/json"}
        async def json(self):
            return {"key": "AAAA-1111-BBBB-2222", "tool_id": "capcut-reup"}
    resp = await license_verify_handler(Req(), env, None)
    body = json.loads(resp.body)
    assert body["ok"]
    assert body["valid"] is True


@pytest.mark.asyncio
async def test_license_verify_handler_missing_fields():
    from src.handlers.license import license_verify_handler
    env = FakeEnv()

    class Req:
        path = "/api/license/verify"
        method = "POST"
        headers = {"content-type": "application/json"}
        async def json(self):
            return {}
    resp = await license_verify_handler(Req(), env, None)
    body = json.loads(resp.body)
    assert body["ok"] is False
    assert body["error"]["code"] == "MISSING_FIELDS"


@pytest.mark.asyncio
async def test_license_check_handler_get():
    from src.handlers.license import license_check_handler
    env = FakeEnv()
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    env.DB.tables["licenses"].append({
        "key": "ABCD-1234-EF56-7890",
        "tool_id": "voice-clone",
        "status": "active",
        "customer_email": "x@y.com",
        "expires_at": future,
    })

    class Req:
        path = "/api/license/check"
        method = "GET"
        url = "/api/license/check?key=ABCD-1234-EF56-7890&tool_id=voice-clone"
        headers = {}
    resp = await license_check_handler(Req(), env, None)
    body = json.loads(resp.body)
    assert body["ok"]
    assert body["valid"] is True
    assert body["license"]["tool_id"] == "voice-clone"
