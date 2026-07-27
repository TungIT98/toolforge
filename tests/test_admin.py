"""Tests for Admin overview + auth + monitoring endpoints."""
import json

import pytest

from src.admin.auth import check_admin_key
from src.admin.overview import get_admin_overview
from tests.test_e2e import FakeD1, FakeEnv


def test_check_admin_key_match():
    assert check_admin_key("secret", "secret") is True


def test_check_admin_key_mismatch():
    assert check_admin_key("secret", "other") is False


def test_check_admin_key_empty():
    assert check_admin_key("", "secret") is False
    assert check_admin_key("secret", "") is False
    assert check_admin_key(None, "secret") is False


@pytest.mark.asyncio
async def test_admin_overview_empty():
    """Empty D1 returns zeros, no crash."""
    env = FakeEnv()
    overview = await get_admin_overview(env.DB)
    assert overview["tools"]["total"] == 0
    assert overview["orders"]["total"] == 0
    assert overview["licenses"]["total"] == 0


@pytest.mark.asyncio
async def test_admin_overview_with_data():
    """Populated D1 returns aggregated stats."""
    env = FakeEnv()
    # Tools
    env.DB.tables["tools"].extend([
        {"id": "t1", "name": "T1", "description": "", "niche": "mmo_reup", "status": "live",
         "build_id": None, "pricing_vnd": 1000000, "binary_url": "", "license_required": 1,
         "tags": "", "created_at": "2026-07-27", "updated_at": "2026-07-27"},
        {"id": "t2", "name": "T2", "description": "", "niche": "productivity", "status": "draft",
         "build_id": None, "pricing_vnd": 0, "binary_url": "", "license_required": 0,
         "tags": "", "created_at": "2026-07-27", "updated_at": "2026-07-27"},
    ])
    # Orders
    env.DB.tables["orders"].extend([
        {"id": "o1", "tool_id": "t1", "tool_name": "T1", "customer_email": "a@b.c",
         "amount_vnd": 1000000, "status": "paid", "created_at": "2026-07-27"},
        {"id": "o2", "tool_id": "t1", "tool_name": "T1", "customer_email": "c@d.e",
         "amount_vnd": 1000000, "status": "pending", "created_at": "2026-07-27"},
    ])
    # Licenses
    env.DB.tables["licenses"].extend([
        {"key": "AAAA-1111-BBBB-2222", "tool_id": "t1", "status": "active",
         "customer_email": "a@b.c", "created_at": "2026-07-27"},
    ])

    overview = await get_admin_overview(env.DB)
    assert overview["tools"]["total"] == 2
    assert overview["tools"]["live_count"] == 1
    assert overview["tools"]["draft_count"] == 1
    assert overview["tools"]["by_niche"]["mmo_reup"] == 1
    assert overview["tools"]["by_niche"]["productivity"] == 1

    assert overview["orders"]["total"] == 2
    assert overview["orders"]["paid_count"] == 1
    assert overview["orders"]["pending_count"] == 1
    assert overview["orders"]["total_revenue_vnd"] == 1_000_000  # 1 paid * 1M

    assert overview["licenses"]["total"] == 1
    assert overview["licenses"]["active_count"] == 1


# === /api/admin/errors endpoint tests ===

class _Req:
    def __init__(self, headers=None, url=""):
        self.headers = headers or {}
        self.url = url


class _KV:
    """Minimal KV for admin errors test."""
    def __init__(self):
        self.store = {}

    async def get(self, key, type=None):
        v = self.store.get(key)
        if v is None:
            return None
        if type == "text":
            return v
        try:
            return json.loads(v)
        except Exception:
            return v

    async def put(self, key, value, **kwargs):
        self.store[key] = value

    async def list(self, prefix="", limit=100):
        keys = [{"name": k} for k in sorted(self.store.keys()) if k.startswith(prefix)]
        return {"keys": keys[:limit]}


@pytest.mark.asyncio
async def test_admin_errors_requires_auth():
    """No X-Admin-Key → 401."""
    from src.handlers.admin import admin_errors_handler
    env = FakeEnv()
    env.CACHE = _KV()
    req = _Req(headers={})
    resp = await admin_errors_handler(req, env, None)
    assert resp.status == 401


@pytest.mark.asyncio
async def test_admin_errors_returns_logged_errors():
    """Logged errors are returned by /api/admin/errors."""
    from src.handlers.admin import admin_errors_handler
    from src.lib.monitoring import log_error_to_kv

    class AdminEnv(FakeEnv):
        ADMIN_API_KEY = "secret-key"

    env = AdminEnv()
    env.CACHE = _KV()
    # Pre-populate KV
    await log_error_to_kv(env, severity="error", endpoint="/api/x", error="boom", code="X", request_id="r1")
    await log_error_to_kv(env, severity="warn", endpoint="/api/y", error="meh", code="Y", request_id="r2")

    req = _Req(headers={"X-Admin-Key": "secret-key"}, url="/api/admin/errors?limit=10")
    resp = await admin_errors_handler(req, env, None)
    assert resp.status == 200
    body = json.loads(resp.body)
    assert body["ok"] is True
    assert body["count"] == 2
    assert {e["code"] for e in body["errors"]} == {"X", "Y"}


@pytest.mark.asyncio
async def test_admin_errors_severity_filter():
    """?severity=error filters out warns."""
    from src.handlers.admin import admin_errors_handler
    from src.lib.monitoring import log_error_to_kv

    class AdminEnv(FakeEnv):
        ADMIN_API_KEY = "k"

    env = AdminEnv()
    env.CACHE = _KV()
    await log_error_to_kv(env, severity="error", endpoint="/a", error="e", code="E", request_id="r1")
    await log_error_to_kv(env, severity="warn", endpoint="/b", error="w", code="W", request_id="r2")

    req = _Req(headers={"X-Admin-Key": "k"}, url="/api/admin/errors?severity=error")
    resp = await admin_errors_handler(req, env, None)
    body = json.loads(resp.body)
    assert body["count"] == 1
    assert body["errors"][0]["severity"] == "error"


@pytest.mark.asyncio
async def test_admin_error_stats_aggregates():
    """/api/admin/error-stats returns counts by severity."""
    from src.handlers.admin import admin_error_stats_handler
    from src.lib.monitoring import log_error_to_kv

    class AdminEnv(FakeEnv):
        ADMIN_API_KEY = "k"

    env = AdminEnv()
    env.CACHE = _KV()
    await log_error_to_kv(env, severity="error", endpoint="/a", error="e", request_id="r1")
    await log_error_to_kv(env, severity="error", endpoint="/b", error="e", request_id="r2")
    await log_error_to_kv(env, severity="warn", endpoint="/c", error="w", request_id="r3")

    req = _Req(headers={"X-Admin-Key": "k"})
    resp = await admin_error_stats_handler(req, env, None)
    assert resp.status == 200
    body = json.loads(resp.body)
    assert body["stats"]["error"] == 2
    assert body["stats"]["warn"] == 1
    assert body["total_recent"] == 3
