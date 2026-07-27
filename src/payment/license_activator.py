"""License activator — generate + activate license after successful payment.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.forge.license import generate_license_key
from src.lib.log import get_logger

log = get_logger("payment.license_activator")


async def activate_license_for_order(
    db: "object",
    order_id: str,
    tool_id: str,
    customer_email: str | None,
    customer_telegram: str | None,
) -> dict[str, Any]:
    """Generate + save license for a paid order.

    Returns:
        {ok: True, license_key, expires_at} or {ok: False, error}
    """
    license_key = generate_license_key()
    now = datetime.now(timezone.utc).isoformat()
    # License valid 1 year by default
    expires_at = datetime.now(timezone.utc).replace(year=datetime.now().year + 1).isoformat()

    try:
        # 1. Save license
        await db.prepare(
            """INSERT INTO licenses
               (key, tool_id, status, customer_email, customer_telegram, activated_at, expires_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
        ).bind(
            license_key,
            tool_id,
            "active",
            customer_email,
            customer_telegram,
            now,
            expires_at,
            now,
        ).run()

        # 2. Update order with license_key
        await db.prepare(
            "UPDATE orders SET license_key = ?, updated_at = ? WHERE id = ?"
        ).bind(license_key, now, order_id).run()

        # 3. Log event
        await db.prepare(
            """INSERT INTO payment_events (order_id, event_type, source, result)
               VALUES (?, ?, ?, ?)"""
        ).bind(order_id, "license_activated", "sepay", "success").run()

        return {
            "ok": True,
            "license_key": license_key,
            "tool_id": tool_id,
            "customer_email": customer_email,
            "customer_telegram": customer_telegram,
            "activated_at": now,
            "expires_at": expires_at,
        }
    except Exception as e:
        log.error("activate_license_failed", err=str(e), order_id=order_id)
        try:
            await db.prepare(
                """INSERT INTO payment_events (order_id, event_type, source, result, error_message)
                   VALUES (?, ?, ?, ?, ?)"""
            ).bind(order_id, "license_activated", "sepay", "error", str(e)).run()
        except Exception:
            pass
        return {"ok": False, "error": str(e), "code": "DB_ERROR"}


async def log_payment_event(
    db: "object",
    order_id: str | None,
    event_type: str,
    source: str,
    payload: dict | None = None,
    result: str = "success",
    error_message: str | None = None,
) -> None:
    """Log a payment event to audit trail."""
    try:
        payload_json = json.dumps(payload, ensure_ascii=False, default=str)[:2000] if payload else None
        await db.prepare(
            """INSERT INTO payment_events
               (order_id, event_type, source, payload_json, result, error_message)
               VALUES (?, ?, ?, ?, ?, ?)"""
        ).bind(
            order_id, event_type, source, payload_json, result, error_message
        ).run()
    except Exception as e:
        log.warn("log_event_failed", err=str(e))


import json  # noqa: E402  (used in log_payment_event)
