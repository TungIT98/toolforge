"""Tests for rate limiting."""
import time
from unittest.mock import AsyncMock

import pytest

from src.lib.rate_limit import (
    DEFAULT_LIMITS,
    get_client_ip,
    get_endpoint_limit,
    rate_limit_response,
    check_rate_limit,
)


# === get_endpoint_limit tests ===

def test_get_endpoint_limit_exact_match():
    assert get_endpoint_limit("/api/health") == 300
    assert get_endpoint_limit("/api/scout/run") == 5


def test_get_endpoint_limit_parameterized():
    """Match /api/admin/specs/123/approve via {id} pattern."""
    assert get_endpoint_limit("/api/admin/specs/abc-123/approve") == 30
    assert get_endpoint_limit("/api/store/tools/capcut-reup") == 120
    assert get_endpoint_limit("/api/builder/session/sess-xxx/message") == 60


def test_get_endpoint_limit_default_fallback():
    """Unknown endpoint → 60 req/min default."""
    assert get_endpoint_limit("/api/unknown/endpoint") == 60


def test_get_endpoint_limit_priority():
    """Exact match wins over pattern match."""
    # /api/health has exact limit 300
    assert get_endpoint_limit("/api/health") == 300


# === get_client_ip tests ===

def test_get_client_ip_cloudflare_header():
    class Req:
        headers = {"CF-Connecting-IP": "203.0.113.42", "X-Forwarded-For": "10.0.0.1"}
    assert get_client_ip(Req()) == "203.0.113.42"


def test_get_client_ip_x_forwarded_for_fallback():
    class Req:
        headers = {"X-Forwarded-For": "192.0.2.1, 10.0.0.1, 172.16.0.1"}
    assert get_client_ip(Req()) == "192.0.2.1"


def test_get_client_ip_unknown():
    class Req:
        headers = {}
    assert get_client_ip(Req()) == "unknown"


# === rate_limit_response tests ===

def test_rate_limit_response_format():
    resp = rate_limit_response(retry_after=60)
    assert resp.status == 429
    assert "Rate limit" in resp.body
    assert "RATE_LIMITED" in resp.body


# === check_rate_limit tests ===

class FakeKV:
    def __init__(self, fail=False):
        self.store: dict = {}
        self.fail = fail
        self.get_count = 0
        self.put_count = 0

    async def get(self, key, type=None):
        self.get_count += 1
        if self.fail:
            raise Exception("KV fail")
        val = self.store.get(key)
        if val is None:
            return None
        if type == "json":
            return int(val) if val.isdigit() else val
        return val

    async def put(self, key, value, **kwargs):
        self.put_count += 1
        if self.fail:
            raise Exception("KV fail")
        self.store[key] = value


class FakeEnv:
    def __init__(self, kv=None):
        self.CACHE = kv


@pytest.mark.asyncio
async def test_check_rate_limit_under_threshold():
    """First request: allowed, count=1."""
    kv = FakeKV()
    env = FakeEnv(kv=kv)
    class Req:
        headers = {"CF-Connecting-IP": "1.2.3.4"}
    allowed, count, limit = await check_rate_limit(Req(), env, "/api/scout/run", limit=5)
    assert allowed is True
    assert count == 1
    assert limit == 5
    assert kv.put_count == 1


@pytest.mark.asyncio
async def test_check_rate_limit_over_threshold():
    """6th request with limit=5 → blocked. count stays at 5 (function returns BEFORE incrementing when over)."""
    kv = FakeKV()
    env = FakeEnv(kv=kv)
    class Req:
        headers = {"CF-Connecting-IP": "1.2.3.4"}
    # 5 requests pass
    for i in range(5):
        allowed, _, _ = await check_rate_limit(Req(), env, "/api/test", limit=5)
        assert allowed is True
    # 6th fails (count is still 5 — we don't increment past limit)
    allowed, count, limit = await check_rate_limit(Req(), env, "/api/test", limit=5)
    assert allowed is False
    assert count == 5
    assert limit == 5


@pytest.mark.asyncio
async def test_check_rate_limit_per_ip_separate():
    """Different IPs have separate counters."""
    kv = FakeKV()
    env = FakeEnv(kv=kv)
    class ReqA:
        headers = {"CF-Connecting-IP": "1.1.1.1"}
    class ReqB:
        headers = {"CF-Connecting-IP": "2.2.2.2"}
    # IP A hits limit
    for _ in range(3):
        allowed, _, _ = await check_rate_limit(ReqA(), env, "/api/test", limit=3)
        assert allowed is True
    allowed_a, _, _ = await check_rate_limit(ReqA(), env, "/api/test", limit=3)
    assert allowed_a is False
    # IP B still has full quota
    allowed_b, _, _ = await check_rate_limit(ReqB(), env, "/api/test", limit=3)
    assert allowed_b is True


@pytest.mark.asyncio
async def test_check_rate_limit_kv_failure_fails_open():
    """KV error → fail open (allow) so legit users not blocked."""
    kv = FakeKV(fail=True)
    env = FakeEnv(kv=kv)
    class Req:
        headers = {"CF-Connecting-IP": "1.2.3.4"}
    allowed, count, limit = await check_rate_limit(Req(), env, "/api/test", limit=1)
    assert allowed is True  # fail open
    assert count == 0


@pytest.mark.asyncio
async def test_check_rate_limit_no_kv_fails_open():
    """No KV bound → fail open (allow)."""
    env = FakeEnv(kv=None)
    class Req:
        headers = {"CF-Connecting-IP": "1.2.3.4"}
    allowed, count, limit = await check_rate_limit(Req(), env, "/api/test", limit=1)
    assert allowed is True
    assert count == 0


@pytest.mark.asyncio
async def test_check_rate_limit_zero_disabled():
    """Limit=0 → disabled (always allowed)."""
    kv = FakeKV()
    env = FakeEnv(kv=kv)
    class Req:
        headers = {"CF-Connecting-IP": "1.2.3.4"}
    for _ in range(100):
        allowed, _, _ = await check_rate_limit(Req(), env, "/api/test", limit=0)
        assert allowed is True
    # Should not hit KV at all (early return)
    assert kv.put_count == 0


def test_default_limits_have_all_critical_endpoints():
    """Sanity check: all public endpoints in DEFAULT_LIMITS."""
    expected = {
        "/api/health", "/api/version", "/api/store/tools", "/api/store/stats",
        "/api/builder/session", "/api/license/verify", "/api/llm/test",
        "/api/scout/run", "/api/architect/spec", "/api/forge/build",
        "/api/payment/orders", "/api/admin/overview",
    }
    assert expected.issubset(set(DEFAULT_LIMITS.keys()))
