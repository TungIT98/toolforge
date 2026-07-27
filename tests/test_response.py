"""Tests for response helpers.
"""
import json

from src.lib.response import error_response, json_response


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
