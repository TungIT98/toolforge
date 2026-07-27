"""Tests for Helper agent + Telegram integration.

Mock httpx.AsyncClient.post to test Telegram interactions without real API calls.
"""
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from tests.test_e2e import FakeD1, FakeEnv


def _mock_telegram_ok():
    """Mock httpx response for successful Telegram sendMessage."""
    return httpx.Response(200, json={
        "ok": True,
        "result": {
            "message_id": 12345,
            "date": 1722100000,
            "chat": {"id": 111, "type": "private"},
            "text": "ok",
        },
    })


def _mock_telegram_error(description: str = "Bad Request: chat not found"):
    return httpx.Response(400, json={"ok": False, "description": description})


def _make_env(token: str = "test-bot-token", chat_id: str = "111") -> FakeEnv:
    """Build env with Telegram secrets set."""
    class _Env(FakeEnv):
        OWNER_TELEGRAM_BOT_TOKEN = token
        OWNER_TELEGRAM_CHAT_ID = chat_id
    return _Env()


def _make_update(text: str, chat_id: int = 111, from_first_name: str = "Anh") -> dict:
    return {
        "update_id": 99999,
        "message": {
            "message_id": 100,
            "date": 1722100000,
            "chat": {"id": chat_id, "type": "private", "first_name": from_first_name},
            "from": {"id": chat_id, "is_bot": False, "first_name": from_first_name, "username": "tester"},
            "text": text,
        },
    }


# === parse_update tests ===

def test_parse_update_basic():
    from src.lib.telegram import parse_update
    u = _make_update("/start")
    parsed = parse_update(u)
    assert parsed["chat_id"] == 111
    assert parsed["is_command"] is True
    assert parsed["command"] == "start"
    assert parsed["args"] == ""


def test_parse_update_with_args():
    from src.lib.telegram import parse_update
    u = _make_update("/order order-abc-123")
    parsed = parse_update(u)
    assert parsed["command"] == "order"
    assert parsed["args"] == "order-abc-123"


def test_parse_update_command_with_bot_suffix():
    """Command like /help@ToolForgeBot should normalize to 'help'."""
    from src.lib.telegram import parse_update
    u = _make_update("/help@ToolForgeBot")
    parsed = parse_update(u)
    assert parsed["command"] == "help"


def test_parse_update_no_message():
    from src.lib.telegram import parse_update
    parsed = parse_update({"update_id": 1})  # no message
    assert parsed is None


def test_parse_update_non_command():
    from src.lib.telegram import parse_update
    u = _make_update("hello there")
    parsed = parse_update(u)
    assert parsed["is_command"] is False
    assert parsed["command"] is None


# === is_configured / get_bot_token tests ===

def test_telegram_not_configured():
    from src.lib import telegram
    telegram._state_reset_for_test() if hasattr(telegram, "_state_reset_for_test") else None
    import os
    old = os.environ.pop("OWNER_TELEGRAM_BOT_TOKEN", None)
    try:
        from src.lib.telegram import is_configured
        assert is_configured() is False
    finally:
        if old:
            os.environ["OWNER_TELEGRAM_BOT_TOKEN"] = old


def test_telegram_configured_from_env_object():
    from src.lib.telegram import is_configured
    env = _make_env(token="real-token")
    assert is_configured(env) is True


# === send_message tests ===

@pytest.mark.asyncio
async def test_send_message_success():
    from src.lib.telegram import send_message
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_mock_telegram_ok())):
        result = await send_message(chat_id=111, text="hello", env=_make_env())
    assert result["ok"] is True
    assert result["message_id"] == 12345


@pytest.mark.asyncio
async def test_send_message_not_configured():
    from src.lib.telegram import send_message
    class EmptyEnv(FakeEnv):
        OWNER_TELEGRAM_BOT_TOKEN = ""
    env = EmptyEnv()
    result = await send_message(chat_id=111, text="hello", env=env)
    assert result["ok"] is False
    assert result["code"] == "TELEGRAM_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_send_message_api_error():
    from src.lib.telegram import send_message
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_mock_telegram_error())):
        result = await send_message(chat_id=999, text="hi", env=_make_env())
    assert result["ok"] is False
    assert result["code"] == "TELEGRAM_API_ERROR"
    assert "chat not found" in result["error"]


@pytest.mark.asyncio
async def test_send_message_timeout():
    from src.lib.telegram import send_message
    async def timeout_post(*a, **kw):
        raise httpx.TimeoutException("timeout")
    with patch("httpx.AsyncClient.post", new=timeout_post):
        result = await send_message(chat_id=111, text="hi", env=_make_env())
    assert result["ok"] is False
    assert result["code"] == "TELEGRAM_TIMEOUT"


# === handle_message tests ===

@pytest.mark.asyncio
async def test_handle_message_start():
    """Send /start → welcome message with name."""
    from src.helper import handle_message
    update = _make_update("/start", from_first_name="Anh")
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_mock_telegram_ok())):
        result = await handle_message(update, _make_env())
    assert result["replied"] is True
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_handle_message_help():
    """Send /help → help text."""
    from src.helper import handle_message
    update = _make_update("/help")
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_mock_telegram_ok())):
        result = await handle_message(update, _make_env())
    assert result["replied"] is True


@pytest.mark.asyncio
async def test_handle_message_order_found():
    """Send /order <existing> → order details."""
    from src.helper import handle_message
    env = _make_env()
    env.DB.tables["orders"].append({
        "id": "order-test123", "tool_id": "t1", "tool_name": "CapCut Reup",
        "amount_vnd": 1000000, "status": "paid", "customer_email": "a@b.c",
        "customer_telegram": "111", "license_key": "LIC-1234-5678",
        "paid_at": "2026-07-27", "created_at": "2026-07-27",
    })
    update = _make_update("/order order-test123")
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_mock_telegram_ok())):
        result = await handle_message(update, env)
    assert result["replied"] is True


@pytest.mark.asyncio
async def test_handle_message_order_not_found():
    """Send /order <missing> → not found message."""
    from src.helper import handle_message
    update = _make_update("/order order-nonexistent")
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_mock_telegram_ok())):
        result = await handle_message(update, _make_env())
    assert result["replied"] is True


@pytest.mark.asyncio
async def test_handle_message_order_no_args():
    """Send /order without args → asks for ID."""
    from src.helper import handle_message
    update = _make_update("/order")
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_mock_telegram_ok())):
        result = await handle_message(update, _make_env())
    assert result["replied"] is True


@pytest.mark.asyncio
async def test_handle_message_unknown_command():
    """Unknown command → suggests /help."""
    from src.helper import handle_message
    update = _make_update("/foo bar")
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_mock_telegram_ok())):
        result = await handle_message(update, _make_env())
    assert result["replied"] is True


@pytest.mark.asyncio
async def test_handle_message_non_command_friendly_fallback():
    """Plain text (not command) → friendly fallback."""
    from src.helper import handle_message
    update = _make_update("hello bot")
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_mock_telegram_ok())):
        result = await handle_message(update, _make_env())
    assert result["replied"] is True


# === send_license_to_customer tests ===

@pytest.mark.asyncio
async def test_send_license_to_customer_no_telegram():
    """No customer_telegram → skip."""
    from src.helper import send_license_to_customer
    order = {"id": "o1", "tool_name": "T1", "amount_vnd": 1000000, "customer_telegram": ""}
    result = await send_license_to_customer(None, _make_env(), order, "LIC-1234")
    assert result["ok"] is False
    assert result["code"] == "NO_TELEGRAM"


@pytest.mark.asyncio
async def test_send_license_to_customer_username_skipped():
    """Username like @zui can't be sent to (need numeric chat_id)."""
    from src.helper import send_license_to_customer
    order = {"id": "o1", "tool_name": "T1", "amount_vnd": 1000000, "customer_telegram": "@zui"}
    result = await send_license_to_customer(None, _make_env(), order, "LIC-1234")
    assert result["ok"] is False
    assert result["code"] == "USERNAME_NOT_SUPPORTED"


@pytest.mark.asyncio
async def test_send_license_to_customer_success():
    """Numeric chat_id → send license via Telegram."""
    from src.helper import send_license_to_customer
    order = {"id": "o1", "tool_name": "CapCut Reup", "amount_vnd": 1000000, "customer_telegram": "111"}
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_mock_telegram_ok())):
        result = await send_license_to_customer(None, _make_env(), order, "LIC-1234-5678")
    assert result["ok"] is True
    assert result["message_id"] == 12345


# === daily_report tests ===

@pytest.mark.asyncio
async def test_daily_report_no_db():
    """No D1 → error."""
    from src.helper import daily_report
    class _NoDB(FakeEnv):
        def __init__(self):
            super().__init__()
            self.DB = None
    result = await daily_report(_NoDB())
    assert result["ok"] is False
    assert result["code"] == "DB_NOT_BOUND"


@pytest.mark.asyncio
async def test_daily_report_empty():
    """Empty D1 → report with zeros."""
    from src.helper import daily_report
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_mock_telegram_ok())):
        result = await daily_report(_make_env())
    assert result["ok"] is True
    assert result["orders"] == 0
    assert result["paid"] == 0
    assert result["revenue_vnd"] == 0
    assert result["licenses"] == 0


@pytest.mark.asyncio
async def test_daily_report_with_data():
    """Populated D1 → report with real numbers."""
    from src.helper import daily_report
    from datetime import datetime, timezone, timedelta
    env = _make_env()
    tz = timezone(timedelta(hours=7))
    today = datetime.now(tz).strftime("%Y-%m-%d")
    env.DB.tables["orders"].extend([
        {"id": "o1", "amount_vnd": 1000000, "status": "paid", "paid_at": today, "created_at": today},
        {"id": "o2", "amount_vnd": 2000000, "status": "paid", "paid_at": today, "created_at": today},
        {"id": "o3", "amount_vnd": 500000, "status": "pending", "created_at": today},
    ])
    env.DB.tables["licenses"].append({"key": "L-1", "created_at": today})
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_mock_telegram_ok())):
        result = await daily_report(env)
    assert result["ok"] is True
    assert result["orders"] == 3
    assert result["paid"] == 2
    assert result["revenue_vnd"] == 3000000  # 2 paid * sum
    assert result["licenses"] == 1


# === Telegram webhook handler tests ===

@pytest.mark.asyncio
async def test_telegram_webhook_not_configured_returns_503():
    """Bot not configured → 503."""
    from src.handlers.telegram import telegram_webhook_handler
    class EmptyEnv(FakeEnv):
        OWNER_TELEGRAM_BOT_TOKEN = ""

    class Req:
        method = "POST"
        path = "/api/telegram/webhook"
        headers = {}
        async def text(self):
            return json.dumps(_make_update("/start"))

    resp = await telegram_webhook_handler(Req(), EmptyEnv(), None)
    assert resp.status == 503


@pytest.mark.asyncio
async def test_telegram_webhook_auth_failed_with_secret():
    """When TELEGRAM_WEBHOOK_SECRET is set, must match header."""
    from src.handlers.telegram import telegram_webhook_handler
    class SecEnv(FakeEnv):
        OWNER_TELEGRAM_BOT_TOKEN = "t"
        TELEGRAM_WEBHOOK_SECRET = "expected"

    class Req:
        method = "POST"
        path = "/api/telegram/webhook"
        headers = {}  # no secret header
        async def text(self):
            return json.dumps(_make_update("/start"))

    resp = await telegram_webhook_handler(Req(), SecEnv(), None)
    assert resp.status == 401


@pytest.mark.asyncio
async def test_telegram_webhook_processes_update():
    """Valid update → 200 + processed."""
    from src.handlers.telegram import telegram_webhook_handler
    class CfgEnv(FakeEnv):
        OWNER_TELEGRAM_BOT_TOKEN = "t"

    class Req:
        method = "POST"
        path = "/api/telegram/webhook"
        headers = {}
        async def text(self):
            return json.dumps(_make_update("/start"))

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_mock_telegram_ok())):
        resp = await telegram_webhook_handler(Req(), CfgEnv(), None)
    assert resp.status == 200


@pytest.mark.asyncio
async def test_telegram_status_requires_admin_auth():
    """Status endpoint requires X-Admin-Key."""
    from src.handlers.telegram import telegram_status_handler
    class Req:
        method = "GET"
        path = "/api/telegram/status"
        headers = {}

    class CfgEnv(FakeEnv):
        OWNER_TELEGRAM_BOT_TOKEN = "t"

    resp = await telegram_status_handler(Req(), CfgEnv(), None)
    assert resp.status == 401


@pytest.mark.asyncio
async def test_telegram_status_returns_config_state():
    """Status endpoint returns bot + owner config state."""
    from src.handlers.telegram import telegram_status_handler
    class Req:
        method = "GET"
        path = "/api/telegram/status"
        headers = {"X-Admin-Key": "admin-key-123"}

    class CfgEnv(FakeEnv):
        OWNER_TELEGRAM_BOT_TOKEN = "t"
        OWNER_TELEGRAM_CHAT_ID = "111"
        ADMIN_API_KEY = "admin-key-123"

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=httpx.Response(200, json={
        "ok": True, "result": {"id": 123, "is_bot": True, "first_name": "ToolForge", "username": "toolforge_bot"}
    }))):
        resp = await telegram_status_handler(Req(), CfgEnv(), None)
    assert resp.status == 200
    body = json.loads(resp.body)
    assert body["bot_configured"] is True
    assert body["owner_chat_configured"] is True
    assert body["bot_info"]["username"] == "toolforge_bot"
