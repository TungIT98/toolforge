"""Telegram Bot API client — minimal wrapper for Helper agent.

Endpoints used:
- sendMessage: POST /bot{token}/sendMessage
- setWebhook: POST /bot{token}/setWebhook
- deleteWebhook: POST /bot{token}/deleteWebhook
- getMe: GET /bot{token}/getMe

Required env (set via `wrangler secret put`):
- OWNER_TELEGRAM_BOT_TOKEN: Bot token from @BotFather
- OWNER_TELEGRAM_CHAT_ID: Owner's chat_id for daily reports (numeric, e.g. "123456789")

Helper agent functionality:
1. Receive messages via webhook → auto-reply (look up order/license)
2. Send license key to customer after SePay webhook
3. Daily report to owner (cron)
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from src.lib.log import get_logger

log = get_logger("telegram")

TELEGRAM_API_BASE = "https://api.telegram.org"


def get_bot_token(env: Any | None = None) -> str:
    """Get bot token from env or os.environ."""
    if env is not None:
        token = getattr(env, "OWNER_TELEGRAM_BOT_TOKEN", "")
        if token:
            return token
    return os.environ.get("OWNER_TELEGRAM_BOT_TOKEN", "")


def get_owner_chat_id(env: Any | None = None) -> str:
    """Get owner's chat_id from env or os.environ (for daily reports)."""
    if env is not None:
        cid = getattr(env, "OWNER_TELEGRAM_CHAT_ID", "")
        if cid:
            return cid
    return os.environ.get("OWNER_TELEGRAM_CHAT_ID", "")


def is_configured(env: Any | None = None) -> bool:
    """True if bot token is configured."""
    return bool(get_bot_token(env))


async def send_message(
    chat_id: str | int,
    text: str,
    env: Any | None = None,
    parse_mode: str = "HTML",
    reply_to_message_id: int | None = None,
    timeout: float = 10.0,
) -> dict:
    """Send a message via Telegram Bot API.

    Args:
        chat_id: Telegram chat_id (numeric or @channelusername)
        text: Message text. Use HTML by default; can switch to Markdown.
        env: Worker env (for bot token)
        parse_mode: "HTML" (default) | "Markdown" | "MarkdownV2"
        reply_to_message_id: Optional message to reply to
        timeout: HTTP timeout in seconds

    Returns:
        {"ok": True, "message_id": ..., "chat": {...}} on success
        {"ok": False, "error": "...", "code": "..."} on failure
    """
    token = get_bot_token(env)
    if not token:
        return {"ok": False, "error": "OWNER_TELEGRAM_BOT_TOKEN not configured", "code": "TELEGRAM_NOT_CONFIGURED"}

    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=payload)
            data = r.json()
            if r.status_code == 200 and data.get("ok"):
                return {
                    "ok": True,
                    "message_id": data["result"]["message_id"],
                    "chat_id": data["result"]["chat"]["id"],
                }
            # API-level error
            err_msg = data.get("description", "Unknown Telegram API error")
            log.warn("telegram_api_error", err=err_msg, status=r.status_code)
            return {"ok": False, "error": err_msg, "code": "TELEGRAM_API_ERROR", "status": r.status_code}
    except httpx.TimeoutException:
        log.warn("telegram_timeout", chat_id=str(chat_id))
        return {"ok": False, "error": "Telegram API timeout", "code": "TELEGRAM_TIMEOUT"}
    except Exception as e:
        log.error("telegram_send_failed", err=str(e))
        return {"ok": False, "error": str(e), "code": "TELEGRAM_EXCEPTION"}


async def send_to_owner(text: str, env: Any | None = None) -> dict:
    """Send message to owner (uses OWNER_TELEGRAM_CHAT_ID)."""
    chat_id = get_owner_chat_id(env)
    if not chat_id:
        return {"ok": False, "error": "OWNER_TELEGRAM_CHAT_ID not configured", "code": "OWNER_CHAT_NOT_CONFIGURED"}
    return await send_message(chat_id, text, env=env)


async def set_webhook(webhook_url: str, env: Any | None = None, secret_token: str | None = None) -> dict:
    """Register webhook URL with Telegram.

    Args:
        webhook_url: Public HTTPS URL to receive updates (e.g., https://toolforge-api.x.workers.dev/api/telegram/webhook)
        env: Worker env
        secret_token: Optional secret to validate incoming webhooks (Telegram sends as X-Telegram-Bot-Api-Secret-Token)

    Returns: dict with ok / error
    """
    token = get_bot_token(env)
    if not token:
        return {"ok": False, "error": "Bot token not configured", "code": "TELEGRAM_NOT_CONFIGURED"}
    url = f"{TELEGRAM_API_BASE}/bot{token}/setWebhook"
    payload: dict[str, Any] = {"url": webhook_url}
    if secret_token:
        payload["secret_token"] = secret_token
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, json=payload)
            data = r.json()
            if data.get("ok"):
                return {"ok": True, "description": data.get("description", "")}
            return {"ok": False, "error": data.get("description", "Unknown error"), "code": "TELEGRAM_API_ERROR"}
    except Exception as e:
        return {"ok": False, "error": str(e), "code": "TELEGRAM_EXCEPTION"}


async def get_me(env: Any | None = None) -> dict:
    """Verify bot token is valid. Returns bot info on success."""
    token = get_bot_token(env)
    if not token:
        return {"ok": False, "error": "Bot token not configured", "code": "TELEGRAM_NOT_CONFIGURED"}
    url = f"{TELEGRAM_API_BASE}/bot{token}/getMe"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
            data = r.json()
            if data.get("ok"):
                return {"ok": True, "bot": data["result"]}
            return {"ok": False, "error": data.get("description", "Unknown"), "code": "TELEGRAM_API_ERROR"}
    except Exception as e:
        return {"ok": False, "error": str(e), "code": "TELEGRAM_EXCEPTION"}


def parse_update(update: dict) -> dict | None:
    """Extract useful fields from a Telegram Update object.

    Returns dict with: update_id, message_id, chat_id, from_id, from_username,
                       from_first_name, text, is_command, command, args
    Returns None if update doesn't have a message.
    """
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return None
    chat = msg.get("chat", {})
    user = msg.get("from", {})
    text = msg.get("text", "")

    parsed = {
        "update_id": update.get("update_id"),
        "message_id": msg.get("message_id"),
        "chat_id": chat.get("id"),
        "from_id": user.get("id"),
        "from_username": user.get("username"),
        "from_first_name": user.get("first_name", "bạn"),
        "text": text,
        "is_command": text.startswith("/"),
        "command": None,
        "args": "",
    }
    if parsed["is_command"]:
        parts = text.split(maxsplit=1)
        parsed["command"] = parts[0][1:].split("@")[0]  # strip @botname
        parsed["args"] = parts[1] if len(parts) > 1 else ""
    return parsed
