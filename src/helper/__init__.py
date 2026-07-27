"""Helper agent — auto-reply Telegram users, send daily report.

Functions:
- handle_message(update, env) -> dict: process a Telegram message, return reply info
- daily_report(env) -> dict: generate + send daily stats to owner

Auto-reply logic:
- /start: greeting
- /help: list commands
- /order <order_id>: look up order status + license
- /license <key>: look up license details
- /tools: list available tools
- /contact: how to contact human

For non-command messages: friendly fallback + suggest /help
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Any

from src.lib.log import get_logger
from src.lib.telegram import send_message

log = get_logger("helper")


WELCOME = (
    "👋 Chào {name}! Mình là Helper của ToolForge.\n\n"
    "Mình có thể giúp:\n"
    "• /order <id> — Tra cứu đơn hàng\n"
    "• /license <key> — Tra cứu license\n"
    "• /tools — Danh sách tool hiện có\n"
    "• /help — Hướng dẫn chi tiết\n\n"
    "Gõ /help để xem tất cả lệnh nhé!"
)

HELP_TEXT = (
    "📖 <b>ToolForge Helper — Hướng dẫn</b>\n\n"
    "<b>/start</b> — Lời chào\n"
    "<b>/help</b> — Hướng dẫn này\n"
    "<b>/order &lt;order_id&gt;</b> — Tra cứu đơn hàng (vd: /order order-abc123)\n"
    "<b>/license &lt;key&gt;</b> — Tra cứu license key\n"
    "<b>/tools</b> — Danh sách tool đang bán\n"
    "<b>/contact</b> — Liên hệ support\n\n"
    "💬 Ngoài lệnh: mình sẽ không trả lời (tránh spam). Dùng /help nếu cần."
)

CONTACT_TEXT = (
    "📞 <b>Liên hệ support</b>\n\n"
    "Telegram: @zui (anh Zui)\n"
    "Email: support@toolforge.vn\n\n"
    "Giờ làm việc: 9:00 - 21:00 (GMT+7)\n"
    "Trả lời trong vòng 4 giờ làm việc."
)


async def _lookup_order(db: Any, order_id: str) -> dict | None:
    """Look up order by ID. Returns order dict or None."""
    try:
        order = await db.prepare(
            "SELECT id, tool_id, tool_name, amount_vnd, status, "
            "customer_email, customer_telegram, license_key, paid_at, created_at "
            "FROM orders WHERE id = ?"
        ).bind(order_id).first()
        return order
    except Exception as e:
        log.warn("order_lookup_failed", err=str(e), order_id=order_id)
        return None


async def _lookup_license(db: Any, license_key: str) -> dict | None:
    """Look up license by key. Returns license dict or None."""
    try:
        lic = await db.prepare(
            "SELECT key, tool_id, status, customer_email, customer_telegram, "
            "activated_at, expires_at, created_at "
            "FROM licenses WHERE key = ?"
        ).bind(license_key).first()
        return lic
    except Exception as e:
        log.warn("license_lookup_failed", err=str(e), key=license_key[:8])
        return None


async def _list_tools(db: Any, limit: int = 10) -> list[dict]:
    """List active tools."""
    try:
        rows = await db.prepare(
            "SELECT id, name, niche, pricing_vnd, description "
            "FROM tools WHERE status = 'live' ORDER BY created_at DESC LIMIT ?"
        ).bind(limit).all()
        return rows or []
    except Exception as e:
        log.warn("tools_list_failed", err=str(e))
        return []


def _format_order(order: dict) -> str:
    """Format order info as Telegram message."""
    status_emoji = {
        "pending": "⏳",
        "paid": "✅",
        "failed": "❌",
        "refunded": "↩️",
    }.get(order.get("status", ""), "❓")

    text = (
        f"📦 <b>Đơn hàng {order['id']}</b>\n\n"
        f"{status_emoji} Trạng thái: <b>{order.get('status', 'unknown')}</b>\n"
        f"🛠 Tool: {order.get('tool_name', order.get('tool_id', '?'))}\n"
        f"💰 Số tiền: {int(order.get('amount_vnd', 0)):,} VND\n"
        f"📅 Tạo: {order.get('created_at', '?')}\n"
    )
    if order.get("paid_at"):
        text += f"💳 Thanh toán: {order['paid_at']}\n"
    if order.get("license_key"):
        text += f"\n🔑 <b>License key:</b>\n<code>{order['license_key']}</code>\n"
        text += "\nDùng lệnh /license &lt;key&gt; để xem chi tiết."
    elif order.get("status") == "pending":
        text += "\n⏳ Đơn đang chờ thanh toán. Vui lòng quét QR SePay trong email."
    return text


def _format_license(lic: dict) -> str:
    """Format license info as Telegram message."""
    status_emoji = {
        "active": "✅",
        "expired": "⏰",
        "revoked": "🚫",
    }.get(lic.get("status", ""), "❓")
    return (
        f"🔑 <b>License {lic['key'][:12]}...</b>\n\n"
        f"{status_emoji} Trạng thái: <b>{lic.get('status', 'unknown')}</b>\n"
        f"🛠 Tool: {lic.get('tool_id', '?')}\n"
        f"📅 Kích hoạt: {lic.get('activated_at') or 'Chưa kích hoạt'}\n"
        f"⏰ Hết hạn: {lic.get('expires_at') or 'Vĩnh viễn'}\n"
    )


async def handle_message(update: dict, env: Any) -> dict:
    """Process a Telegram message and send a reply.

    Returns dict with: ok, replied, reply_text, action
    """
    from src.lib.telegram import parse_update, send_message
    parsed = parse_update(update)
    if not parsed:
        return {"ok": True, "replied": False, "reason": "no_message"}

    chat_id = parsed["chat_id"]
    db = getattr(env, "DB", None)
    if db is None:
        # Without DB, can only handle simple commands
        db = None

    # Build reply based on command or text
    reply_text = ""
    if parsed["is_command"]:
        cmd = parsed["command"]
        args = parsed["args"].strip()

        if cmd == "start":
            reply_text = WELCOME.format(name=parsed.get("from_first_name") or "bạn")
        elif cmd == "help":
            reply_text = HELP_TEXT
        elif cmd == "contact":
            reply_text = CONTACT_TEXT
        elif cmd == "order":
            if not args:
                reply_text = "⚠️ Bạn chưa nhập order_id.\n\nVD: /order order-abc123"
            elif not db:
                reply_text = "❌ Lỗi hệ thống: D1 chưa kết nối."
            else:
                order = await _lookup_order(db, args)
                if order:
                    reply_text = _format_order(order)
                else:
                    reply_text = f"❌ Không tìm thấy đơn hàng <code>{args}</code>.\n\nKiểm tra lại ID (bắt đầu bằng 'order-')."
        elif cmd == "license":
            if not args:
                reply_text = "⚠️ Bạn chưa nhập license key.\n\nVD: /license ABCD-1234-EFGH-5678"
            elif not db:
                reply_text = "❌ Lỗi hệ thống: D1 chưa kết nối."
            else:
                lic = await _lookup_license(db, args)
                if lic:
                    reply_text = _format_license(lic)
                else:
                    reply_text = f"❌ Không tìm thấy license <code>{args[:12]}...</code>"
        elif cmd == "tools":
            if not db:
                reply_text = "❌ Lỗi hệ thống: D1 chưa kết nối."
            else:
                tools = await _list_tools(db)
                if tools:
                    lines = ["🛠 <b>ToolForge Store</b>\n"]
                    for t in tools[:10]:
                        price = f"{int(t.get('pricing_vnd', 0)):,} VND" if t.get('pricing_vnd') else "Miễn phí"
                        desc = (t.get("description") or "")[:80]
                        lines.append(f"• <b>{t['name']}</b> — {price}\n  {desc}...")
                    reply_text = "\n".join(lines)
                    reply_text += "\n\n👉 Mua tại: https://toolforge.vn/store"
                else:
                    reply_text = "Hiện chưa có tool nào. Quay lại sau nhé!"
        else:
            reply_text = f"❓ Lệnh /{cmd} chưa hỗ trợ. Gõ /help để xem danh sách."
    else:
        # Non-command: friendly fallback
        reply_text = (
            f"👋 Mình chỉ hiểu lệnh (bắt đầu bằng /). "
            f"Ví dụ: /order, /license, /tools.\n\n"
            f"Gõ /help để xem tất cả lệnh nhé!"
        )

    # Send reply
    if not reply_text:
        return {"ok": True, "replied": False, "reason": "no_reply_text"}

    result = await send_message(
        chat_id=chat_id, text=reply_text, env=env,
        reply_to_message_id=parsed.get("message_id"),
    )
    return {
        "ok": result.get("ok", False),
        "replied": result.get("ok", False),
        "reply_text_len": len(reply_text),
        "message_id": result.get("message_id"),
        "error": result.get("error") if not result.get("ok") else None,
    }


async def send_license_to_customer(
    db: Any, env: Any, order: dict, license_key: str
) -> dict:
    """Send license to customer via Telegram after successful payment.

    Called from SePay webhook handler when an order is paid and has
    customer_telegram. Returns send result.
    """
    from src.lib.telegram import send_message
    customer_tg = order.get("customer_telegram", "")
    if not customer_tg:
        return {"ok": False, "skipped": "no_telegram", "code": "NO_TELEGRAM"}

    # If customer_tg is a username like "@zui", we can't send (need numeric chat_id)
    if customer_tg.startswith("@"):
        log.info("telegram_username_not_resolvable", username=customer_tg)
        return {"ok": False, "skipped": "username_not_supported", "code": "USERNAME_NOT_SUPPORTED"}

    try:
        chat_id = int(customer_tg)
    except (ValueError, TypeError):
        return {"ok": False, "skipped": "invalid_chat_id", "code": "INVALID_CHAT_ID"}

    text = (
        f"🎉 <b>Thanh toán thành công!</b>\n\n"
        f"Đơn: <code>{order['id']}</code>\n"
        f"Tool: <b>{order.get('tool_name', order.get('tool_id', '?'))}</b>\n"
        f"Số tiền: {int(order.get('amount_vnd', 0)):,} VND\n\n"
        f"🔑 <b>License key của bạn:</b>\n"
        f"<code>{license_key}</code>\n\n"
        f"📥 Dùng key này để active tool. Lưu lại để dùng sau nhé!\n"
        f"Gõ /license {license_key} để kiểm tra trạng thái."
    )

    result = await send_message(chat_id=chat_id, text=text, env=env)
    if result.get("ok"):
        log.info("license_sent_to_customer", order_id=order["id"], chat_id=chat_id)
    return result


async def daily_report(env: Any) -> dict:
    """Generate + send daily stats to owner. Called by cron at 22:00 Saigon."""
    from src.lib.telegram import send_to_owner
    db = getattr(env, "DB", None)
    if db is None:
        return {"ok": False, "error": "D1 not bound", "code": "DB_NOT_BOUND"}

    try:
        # Today in Saigon timezone
        tz = timezone(timedelta(hours=7))
        today_sg = datetime.now(tz).strftime("%Y-%m-%d")

        # Fetch all rows, aggregate in Python (works with FakeD1 + real D1)
        all_orders = await db.prepare(
            "SELECT id, amount_vnd, status, created_at, paid_at FROM orders"
        ).bind().all() or []
        all_licenses = await db.prepare(
            "SELECT key, created_at FROM licenses"
        ).bind().all() or []

        # Aggregate for today
        orders_today = [o for o in all_orders if (o.get("created_at") or "").startswith(today_sg)]
        paid_today = [o for o in all_orders if o.get("status") == "paid" and (o.get("paid_at") or "").startswith(today_sg)]
        licenses_today = [lic for lic in all_licenses if (lic.get("created_at") or "").startswith(today_sg)]
        revenue_today = sum(int(o.get("amount_vnd", 0) or 0) for o in paid_today)

        # Recent errors (from KV monitoring log)
        from src.lib.monitoring import list_recent_errors
        recent_errors = await list_recent_errors(env, limit=50)
        err_count = sum(1 for e in recent_errors if e.get("severity") == "error")
        warn_count = sum(1 for e in recent_errors if e.get("severity") == "warn")

        text = (
            f"📊 <b>ToolForge — Báo cáo ngày {today_sg}</b>\n\n"
            f"💰 <b>Doanh thu hôm nay</b>\n"
            f"  Đơn mới: {len(orders_today)}\n"
            f"  Đã thanh toán: {len(paid_today)}\n"
            f"  Doanh thu: {revenue_today:,} VND\n\n"
            f"🔑 <b>License mới:</b> {len(licenses_today)}\n\n"
            f"⚠️ <b>Lỗi 24h qua</b>\n"
            f"  Error: {err_count}\n"
            f"  Warn: {warn_count}\n"
            f"\nXem chi tiết: /api/admin/errors"
        )

        result = await send_to_owner(text, env=env)
        return {
            "ok": result.get("ok", False),
            "sent": result.get("ok", False),
            "orders": len(orders_today),
            "paid": len(paid_today),
            "revenue_vnd": revenue_today,
            "licenses": len(licenses_today),
            "errors_24h": err_count,
        }
    except Exception as e:
        log.error("daily_report_failed", err=str(e))
        return {"ok": False, "error": str(e), "code": "DAILY_REPORT_EXCEPTION"}
