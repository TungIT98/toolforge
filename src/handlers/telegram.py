"""Telegram webhook handler — receives updates from Telegram, runs Helper.

Endpoints:
  POST /api/telegram/webhook   Receive Telegram Update
  POST /api/telegram/setup     Register webhook URL (owner only)
  GET  /api/telegram/status    Check bot config status (owner only)

Setup:
1. Create bot via @BotFather, get OWNER_TELEGRAM_BOT_TOKEN
2. Set in Cloudflare: `wrangler secret put OWNER_TELEGRAM_BOT_TOKEN`
3. POST /api/telegram/setup with body { "webhook_url": "https://..." }
   → Registers the webhook with Telegram
4. Optional: set OWNER_TELEGRAM_CHAT_ID for daily reports

For security: optionally set TELEGRAM_WEBHOOK_SECRET in env to validate
X-Telegram-Bot-Api-Secret-Token header from Telegram.
"""
from __future__ import annotations

import os
from typing import Any

from src.helper import handle_message
from src.lib.log import get_logger
from src.lib.response import error_response, json_response
from src.lib.telegram import get_me, is_configured, set_webhook
from src.router import route

log = get_logger("telegram.handler")


@route("POST", "/api/telegram/webhook")
async def telegram_webhook_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Receive a Telegram Update and process it.

    Telegram POSTs Update object as JSON. We parse + auto-reply.
    Returns 200 OK quickly (Telegram doesn't care about response body).
    """
    # Optional: verify Telegram's secret_token header
    expected_secret = (
        getattr(env, "TELEGRAM_WEBHOOK_SECRET", "")
        or os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    )
    if expected_secret:
        provided = (
            request.headers.get("X-Telegram-Bot-Api-Secret-Token")  # type: ignore[attr-defined]
            or ""
        )
        import hmac
        if not hmac.compare_digest(provided, expected_secret):
            log.warn("telegram_webhook_auth_failed")
            return error_response("Invalid secret", status=401, code="TELEGRAM_AUTH_FAILED")

    if not is_configured(env):
        # Bot token not set — log and 503 so owner knows to configure
        log.error("telegram_webhook_called_but_not_configured")
        return error_response("Bot not configured", status=503, code="TELEGRAM_NOT_CONFIGURED")

    try:
        body_text = await request.text()  # type: ignore[attr-defined]
        import json
        update = json.loads(body_text) if body_text else {}
    except Exception as e:
        return error_response(f"Invalid JSON: {e}", status=400, code="INVALID_JSON")

    # Process async — Telegram doesn't wait for our response anyway
    try:
        result = await handle_message(update, env)
        log.info("telegram_update_processed", ok=result.get("ok"), replied=result.get("replied"))
    except Exception as e:
        # Never let helper errors break the webhook (Telegram will retry)
        log.error("telegram_handle_failed", err=str(e))

    # Always return 200 to Telegram so it doesn't retry
    return json_response({"ok": True})


@route("POST", "/api/telegram/setup")
async def telegram_setup_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Register the Worker URL as Telegram webhook (owner only).

    Body: { "webhook_url": "https://..." }
    """
    # Admin auth
    from src.handlers.admin import _check
    err = _check(request, env)
    if err:
        return err

    try:
        body = await request.json()  # type: ignore[attr-defined]
    except Exception as e:
        return error_response(f"Invalid JSON: {e}", status=400, code="INVALID_JSON")
    if not isinstance(body, dict):
        return error_response("Body must be JSON object", status=400, code="INVALID_JSON")

    webhook_url = body.get("webhook_url", "").strip()
    if not webhook_url:
        return error_response("Missing webhook_url", status=400, code="MISSING_WEBHOOK_URL")
    if not webhook_url.startswith("https://"):
        return error_response("webhook_url must be HTTPS", status=400, code="WEBHOOK_NOT_HTTPS")

    # Get secret_token to use (re-use TELEGRAM_WEBHOOK_SECRET if set)
    secret = (
        getattr(env, "TELEGRAM_WEBHOOK_SECRET", "")
        or os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
        or None
    )

    result = await set_webhook(webhook_url, env=env, secret_token=secret)
    if not result.get("ok"):
        return error_response(
            result.get("error", "Failed to set webhook"),
            status=502, code=result.get("code", "TELEGRAM_SET_WEBHOOK_FAILED"),
        )
    return json_response({
        "ok": True,
        "webhook_url": webhook_url,
        "secret_configured": bool(secret),
        "telegram_response": result.get("description", ""),
    })


@route("GET", "/api/telegram/status")
async def telegram_status_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Check Telegram bot config status (owner only)."""
    from src.handlers.admin import _check
    from src.lib.telegram import get_owner_chat_id
    err = _check(request, env)
    if err:
        return err

    configured = is_configured(env)
    owner_chat = get_owner_chat_id(env)
    response = {
        "ok": True,
        "bot_configured": configured,
        "owner_chat_configured": bool(owner_chat),
    }
    if configured:
        me_result = await get_me(env)
        if me_result.get("ok"):
            response["bot_info"] = me_result["bot"]
    return json_response(response)
