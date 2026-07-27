"""Tests for response helpers — includes CORS configuration.
"""
import json

import pytest

from src.lib import response as resp_mod
from src.lib.response import configure_cors, error_response, json_response


@pytest.fixture(autouse=True)
def reset_cors():
    """Reset CORS state between tests so order doesn't matter."""
    resp_mod._allowed_origins = []
    yield
    resp_mod._allowed_origins = []


class FakeResponse:
    """Mimics Cloudflare Workers Response for unit testing."""
    def __init__(self, body: str, status: int, headers: dict):
        self.body = body
        self.status = status
        self.headers = headers


def test_json_response_default():
    """json_response returns 200 + JSON content-type by default."""
    resp = json_response({"ok": True, "x": 1})
    assert resp.status == 200
    assert "application/json" in resp.headers["Content-Type"]
    data = json.loads(resp.body)
    assert data == {"ok": True, "x": 1}


def test_json_response_custom_status():
    """Custom status code is applied."""
    resp = json_response({"ok": False}, status=404)
    assert resp.status == 404


def test_json_response_unicode():
    """Vietnamese characters are preserved."""
    resp = json_response({"msg": "Tiếng Việt có dấu"})
    data = json.loads(resp.body)
    assert data["msg"] == "Tiếng Việt có dấu"


def test_error_response_format():
    """error_response wraps payload in {ok: false, error: {...}}."""
    resp = error_response("Bad request", status=400, code="INVALID", details={"field": "x"})
    data = json.loads(resp.body)
    assert data["ok"] is False
    assert data["error"]["code"] == "INVALID"
    assert data["error"]["message"] == "Bad request"
    assert data["error"]["details"] == {"field": "x"}
    assert resp.status == 400


def test_error_response_minimal():
    """error_response works with just message."""
    resp = error_response("Boom", status=500)
    data = json.loads(resp.body)
    assert data["error"]["message"] == "Boom"
    assert "code" not in data["error"]


# === CORS tests ===

def test_cors_wildcard_by_default():
    """Empty allowed origins → '*' (dev mode)."""
    resp = json_response({"ok": True})
    assert resp.headers["Access-Control-Allow-Origin"] == "*"


def test_cors_configure_empty_stays_wildcard():
    """configure_cors('') keeps wildcard."""
    configure_cors("")
    resp = json_response({"ok": True})
    assert resp.headers["Access-Control-Allow-Origin"] == "*"


def test_cors_configure_single_origin_matches():
    """Single origin in allowlist, request matches → that origin returned."""
    configure_cors("https://toolforge.vn")
    class Req:
        headers = {"Origin": "https://toolforge.vn"}
    resp = json_response({"ok": True}, request=Req())
    assert resp.headers["Access-Control-Allow-Origin"] == "https://toolforge.vn"


def test_cors_configure_single_origin_no_match_blocks():
    """Origin not in allowlist → empty (browser blocks)."""
    configure_cors("https://toolforge.vn")
    class Req:
        headers = {"Origin": "https://evil.com"}
    resp = json_response({"ok": True}, request=Req())
    assert resp.headers["Access-Control-Allow-Origin"] == ""


def test_cors_configure_multiple_origins():
    """Multiple origins allowed, request matches one → that origin."""
    configure_cors("https://toolforge.vn,https://admin.toolforge.vn,http://localhost:3000")
    class Req1:
        headers = {"Origin": "https://admin.toolforge.vn"}
    class Req2:
        headers = {"Origin": "http://localhost:3000"}
    class Req3:
        headers = {"Origin": "https://attacker.com"}
    assert json_response({"x": 1}, request=Req1()).headers["Access-Control-Allow-Origin"] == "https://admin.toolforge.vn"
    assert json_response({"x": 1}, request=Req2()).headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert json_response({"x": 1}, request=Req3()).headers["Access-Control-Allow-Origin"] == ""


def test_cors_configure_strips_whitespace():
    """Whitespace in CSV is stripped."""
    configure_cors("  https://a.com , https://b.com  ,")
    assert "https://a.com" in resp_mod._allowed_origins
    assert "https://b.com" in resp_mod._allowed_origins
    assert "" not in resp_mod._allowed_origins


def test_cors_preflight_returns_204_with_headers():
    """handle_cors_preflight returns 204 + CORS headers."""
    from src.lib.response import handle_cors_preflight
    resp = handle_cors_preflight()
    assert resp.status == 204
    assert "Access-Control-Allow-Origin" in resp.headers
    assert "Access-Control-Allow-Methods" in resp.headers


def test_cors_preflight_with_specific_origin_adds_vary():
    """When specific origin is set, Vary: Origin is added (cache safety)."""
    from src.lib.response import handle_cors_preflight
    configure_cors("https://toolforge.vn")
    class Req:
        headers = {"Origin": "https://toolforge.vn"}
    resp = handle_cors_preflight(Req())
    assert resp.headers["Access-Control-Allow-Origin"] == "https://toolforge.vn"
    assert resp.headers.get("Vary") == "Origin"


def test_cors_includes_webhook_secret_in_allowed_headers():
    """X-Webhook-Secret is now in the allowed headers list."""
    from src.lib.response import handle_cors_preflight
    resp = handle_cors_preflight()
    assert "X-Webhook-Secret" in resp.headers["Access-Control-Allow-Headers"]


def test_cors_configure_from_env_object():
    """configure_cors can read ALLOWED_ORIGINS from env object."""
    class FakeEnv:
        ALLOWED_ORIGINS = "https://from-env.com"
    configure_cors(env=FakeEnv())
    class Req:
        headers = {"Origin": "https://from-env.com"}
    resp = json_response({"ok": True}, request=Req())
    assert resp.headers["Access-Control-Allow-Origin"] == "https://from-env.com"


def test_cors_no_origin_header_with_allowlist_blocks():
    """No Origin header (e.g. server-to-server) + allowlist → empty."""
    configure_cors("https://toolforge.vn")
    class Req:
        headers = {}
    resp = json_response({"ok": True}, request=Req())
    # No origin in headers → not in allowlist → empty
    assert resp.headers["Access-Control-Allow-Origin"] == ""
