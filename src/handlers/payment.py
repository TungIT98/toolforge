"""Payment handlers — SePay webhook + order management.

Endpoints:
  POST /api/payment/sepay-webhook     Receive SePay payment event (verifies Apikey)
  POST /api/payment/orders            Create pending order (called from frontend checkout)
  GET  /api/payment/orders            List orders (admin)
  GET  /api/payment/orders/{id}       1 order detail
  POST /api/payment/test              Test mode: simulate payment (no real SePay needed)

Flow:
  1. User clicks "Buy" on frontend → POST /api/payment/orders (creates pending order)
  2. Frontend shows SePay QR / bank info
  3. User pays via SePay
  4. SePay → POST /api/payment/sepay-webhook
  5. Webhook validates auth + parses + activates license
  6. User gets license via Telegram or email (P5+ Helper integration)
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from src.lib.log import get_logger
from src.lib.response import error_response, json_response
from src.payment.license_activator import activate_license_for_order, log_payment_event
from src.payment.sepay import (
    extract_order_info,
    is_incoming_transfer,
    parse_webhook,
    verify_api_key,
)
from src.router import route

log = get_logger("payment.handler")


@route("POST", "/api/payment/orders")
async def create_order_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Create a pending order.

    Request body:
    {
        "tool_id": "capcut-desktop-reup",
        "customer_email": "zui@example.com",  // optional
        "customer_telegram": "@zui",          // optional
        "amount_vnd": 1000000,                 // optional (default from tool pricing)
        "description": "optional note"          // optional
    }
    """
    try:
        body = await request.json()  # type: ignore[attr-defined]
    except Exception as e:
        return error_response(f"Invalid JSON: {e}", status=400, code="INVALID_JSON")
    if not isinstance(body, dict):
        return error_response("Body must be JSON object", status=400, code="INVALID_JSON")

    tool_id = body.get("tool_id")
    if not tool_id:
        return error_response("Missing tool_id", status=400, code="MISSING_TOOL_ID")

    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")

    # Look up tool to get price
    tool = await db.prepare(
        "SELECT id, name, pricing_vnd FROM tools WHERE id = ?"
    ).bind(tool_id).first()
    if not tool:
        return error_response(f"Tool {tool_id} not found", status=404, code="TOOL_NOT_FOUND")

    amount = int(body.get("amount_vnd") or tool.get("pricing_vnd", 0))
    customer_email = body.get("customer_email")
    customer_telegram = body.get("customer_telegram")
    customer_name = body.get("customer_name")
    custom_desc = body.get("description")

    # Build description in SePay format: "TOOLFORGE <tool_id> <customer>"
    parts = ["TOOLFORGE", tool_id]
    if customer_telegram:
        parts.append(customer_telegram)
    elif customer_email:
        parts.append(customer_email)
    if custom_desc:
        parts.append(custom_desc)
    description = " ".join(parts)

    order_id = f"order-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.prepare(
            """INSERT INTO orders
               (id, tool_id, tool_name, customer_email, customer_telegram, customer_name,
                amount_vnd, description, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        ).bind(
            order_id, tool_id, tool["name"], customer_email, customer_telegram, customer_name,
            amount, description, "pending", now, now,
        ).run()
        await log_payment_event(db, order_id, "order_created", "admin")
    except Exception as e:
        return error_response(f"DB error: {e}", status=500, code="DB_ERROR")

    return json_response({
        "ok": True,
        "order_id": order_id,
        "tool_id": tool_id,
        "tool_name": tool["name"],
        "amount_vnd": amount,
        "description": description,
        "status": "pending",
        "payment_info": {
            "bank": os.environ.get("SEPAY_BANK_NAME", "Vietcombank"),
            "account_number": os.environ.get("SEPAY_ACCOUNT_NUMBER", ""),
            "account_holder": os.environ.get("SEPAY_ACCOUNT_HOLDER", "TOOLFORGE"),
            "content": description,
            "amount_vnd": amount,
            "qr_url": f"https://qr.sepay.vn/img?bank={os.environ.get('SEPAY_BANK_CODE', 'VCB')}&acc={os.environ.get('SEPAY_ACCOUNT_NUMBER', '')}&template=compact&amount={amount}&des={description}",
        },
    })


@route("POST", "/api/payment/sepay-webhook")
async def sepay_webhook_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Receive SePay payment webhook.

    SePay sends POST with:
    - Header: "Apikey: <merchant_apikey>" (or Authorization: Bearer)
    - Header: "X-Sepay-Signature: <hmac>" (if HMAC mode)
    - Body: JSON (see parse_webhook)

    On valid incoming payment matching a pending order:
    - Update order.status = 'paid', save sepay_transaction_id
    - Generate license + save
    - Return 200 to acknowledge
    """
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")

    # 1. Verify auth
    expected_key = getattr(env, "SEPAY_API_KEY", "") or os.environ.get("SEPAY_API_KEY", "")
    provided_key = (
        request.headers.get("Apikey")  # type: ignore[attr-defined]
        or request.headers.get("apikey")  # type: ignore[attr-defined]
    )
    if not verify_api_key(provided_key, expected_key):
        log.warn("sepay_auth_failed", provided=bool(provided_key))
        await log_payment_event(db, None, "webhook_received", "sepay", result="error", error_message="auth_failed")
        return error_response("Invalid Apikey", status=401, code="AUTH_FAILED")

    # 2. Parse body
    try:
        body_text = await request.text()  # type: ignore[attr-defined]
        body = json.loads(body_text) if body_text else {}
    except Exception as e:
        await log_payment_event(db, None, "webhook_received", "sepay", result="error", error_message=f"json_parse: {e}")
        return error_response(f"Invalid JSON: {e}", status=400, code="INVALID_JSON")

    try:
        parsed = parse_webhook(body)
    except ValueError as e:
        await log_payment_event(db, None, "webhook_received", "sepay", result="error", error_message=str(e))
        return error_response(str(e), status=400, code="PARSE_FAILED")

    await log_payment_event(db, None, "webhook_received", "sepay", payload=parsed)

    # 3. Filter: only incoming transfers
    if not is_incoming_transfer(parsed):
        log.info("sepay_skipped_not_incoming", transfer_type=parsed["transfer_type"])
        return json_response({"ok": True, "skipped": "not_incoming"})

    # 4. Extract order info from description
    order_info = extract_order_info(parsed["description"])
    tool_id = order_info["tool_id"]
    customer = order_info["customer"]
    if not tool_id:
        log.warn("sepay_no_tool_id_in_description", description=parsed["description"][:100])
        return json_response({"ok": True, "skipped": "no_tool_id"})

    # 5. Find matching pending order
    order = await db.prepare(
        """SELECT id, amount_vnd, status, tool_id, customer_email, customer_telegram
           FROM orders
           WHERE tool_id = ? AND status = 'pending' AND amount_vnd = ?
           ORDER BY created_at DESC LIMIT 1"""
    ).bind(tool_id, parsed["amount_vnd"]).first()

    if not order:
        log.warn("sepay_no_matching_order", tool_id=tool_id, amount=parsed["amount_vnd"])
        return json_response({"ok": True, "skipped": "no_matching_order"})

    # 6. Update order to paid
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.prepare(
            """UPDATE orders
               SET status = 'paid', paid_at = ?, sepay_transaction_id = ?, sepay_reference_code = ?,
                   sepay_account = ?, sepay_transfer_type = ?, updated_at = ?
               WHERE id = ?"""
        ).bind(
            now, str(parsed["sepay_id"]), parsed["reference_code"],
            parsed["account_number"], parsed["transfer_type"], now,
            order["id"],
        ).run()
        await log_payment_event(db, order["id"], "payment_received", "sepay", payload=parsed)
    except Exception as e:
        await log_payment_event(db, order["id"], "payment_received", "sepay", result="error", error_message=str(e))
        return error_response(f"DB error: {e}", status=500, code="DB_ERROR")

    # 7. Activate license
    customer_email = order.get("customer_email")
    customer_telegram = order.get("customer_telegram")
    # If description has customer info but order doesn't, parse from description
    if not customer_email and not customer_telegram and customer:
        if customer.startswith("@"):
            customer_telegram = customer
        elif "@" in customer:
            customer_email = customer

    license_result = await activate_license_for_order(
        db, order["id"], tool_id, customer_email, customer_telegram,
    )

    if not license_result["ok"]:
        return error_response(
            f"License activation failed: {license_result.get('error')}",
            status=500, code="LICENSE_ACTIVATION_FAILED"
        )

    # 8. Return success to SePay
    return json_response({
        "ok": True,
        "order_id": order["id"],
        "tool_id": tool_id,
        "license_key": license_result["license_key"],
        "expires_at": license_result["expires_at"],
    })


@route("POST", "/api/payment/test")
async def test_payment_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Test mode: simulate successful payment (no real SePay needed).

    Request body:
    {
        "order_id": "order-..."
    }
    """
    try:
        body = await request.json()  # type: ignore[attr-defined]
    except Exception as e:
        return error_response(f"Invalid JSON: {e}", status=400, code="INVALID_JSON")
    if not isinstance(body, dict):
        return error_response("Body must be JSON object", status=400, code="INVALID_JSON")

    order_id = body.get("order_id")
    if not order_id:
        return error_response("Missing order_id", status=400, code="MISSING_ORDER_ID")

    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")

    order = await db.prepare(
        "SELECT id, tool_id, customer_email, customer_telegram, amount_vnd, status FROM orders WHERE id = ?"
    ).bind(order_id).first()
    if not order:
        return error_response(f"Order {order_id} not found", status=404, code="ORDER_NOT_FOUND")
    if order["status"] == "paid":
        return error_response("Order already paid", status=400, code="ORDER_ALREADY_PAID")

    # Simulate webhook
    now = datetime.now(timezone.utc).isoformat()
    await db.prepare(
        """UPDATE orders
           SET status = 'paid', paid_at = ?, sepay_transaction_id = 'TEST-12345',
               sepay_reference_code = 'TEST', sepay_account = 'TEST_ACC',
               sepay_transfer_type = 'in', updated_at = ?
           WHERE id = ?"""
    ).bind(now, now, order_id).run()
    await log_payment_event(db, order_id, "test_payment", "test")

    # Activate license
    license_result = await activate_license_for_order(
        db, order_id, order["tool_id"],
        order.get("customer_email"), order.get("customer_telegram"),
    )
    if not license_result["ok"]:
        return error_response(f"License activation failed: {license_result.get('error')}", status=500)

    return json_response({
        "ok": True,
        "order_id": order_id,
        "tool_id": order["tool_id"],
        "license_key": license_result["license_key"],
        "expires_at": license_result["expires_at"],
        "test_mode": True,
    })


@route("GET", "/api/payment/orders")
async def list_orders_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """List orders (admin). Optional ?status=pending|paid|failed|refunded."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    url = getattr(request, "url", "") or ""
    status_filter = None
    if "?" in url:
        qs = url.split("?", 1)[1]
        for pair in qs.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                if k == "status":
                    status_filter = v

    if status_filter:
        rows = await db.prepare(
            "SELECT id, tool_id, tool_name, customer_email, amount_vnd, status, paid_at, created_at, license_key "
            "FROM orders WHERE status = ? ORDER BY created_at DESC LIMIT 100"
        ).bind(status_filter).all()
    else:
        rows = await db.prepare(
            "SELECT id, tool_id, tool_name, customer_email, amount_vnd, status, paid_at, created_at, license_key "
            "FROM orders ORDER BY created_at DESC LIMIT 100"
        ).all()
    return json_response({"ok": True, "count": len(rows or []), "orders": rows or []})


@route("GET", "/api/payment/orders/{order_id}")
async def get_order_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Get 1 order detail."""
    db = getattr(env, "DB", None)
    if db is None:
        return error_response("D1 not bound", status=500, code="DB_NOT_BOUND")
    path = getattr(request, "path", "")
    order_id = path.split("/api/payment/orders/")[-1].strip("/")
    if not order_id:
        return error_response("Missing order_id", status=400, code="MISSING_ORDER_ID")
    order = await db.prepare(
        "SELECT id, tool_id, tool_name, customer_email, customer_telegram, customer_name, "
        "amount_vnd, description, status, payment_method, sepay_transaction_id, sepay_reference_code, "
        "sepay_account, paid_at, created_at, updated_at, license_key "
        "FROM orders WHERE id = ?"
    ).bind(order_id).first()
    if not order:
        return error_response(f"Order {order_id} not found", status=404, code="ORDER_NOT_FOUND")
    return json_response({"ok": True, "order": order})
