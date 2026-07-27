"""Tests for SePay webhook + license activator."""
import asyncio
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest

from src.forge.license import generate_license_key, is_valid_license_key
from src.payment.license_activator import activate_license_for_order
from src.payment.sepay import (
    extract_order_info,
    is_incoming_transfer,
    parse_webhook,
    verify_api_key,
    verify_signature,
)
from tests.test_e2e import FakeD1, FakeEnv


# === verify_api_key tests ===

def test_verify_api_key_match():
    assert verify_api_key("secret-abc", "secret-abc") is True


def test_verify_api_key_mismatch():
    assert verify_api_key("secret-abc", "secret-xyz") is False


def test_verify_api_key_empty_inputs():
    assert verify_api_key("", "secret-xyz") is False
    assert verify_api_key("secret-abc", "") is False
    assert verify_api_key(None, "secret-xyz") is False
    assert verify_api_key("secret-abc", None) is False


# === verify_signature tests ===

def test_verify_signature_valid():
    payload = b'{"test": "data"}'
    secret = "my-secret"
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert verify_signature(payload, expected, secret) is True


def test_verify_signature_invalid():
    assert verify_signature(b"payload", "wrong-sig", "secret") is False


def test_verify_signature_missing_inputs():
    assert verify_signature(b"data", None, "secret") is False
    assert verify_signature(b"data", "sig", "") is False


# === parse_webhook tests ===

def test_parse_webhook_valid():
    body = {
        "id": 12345,
        "gateway": "Vietcombank",
        "transactionDate": "2026-07-27 10:30:45",
        "accountNumber": "0123456789",
        "amount": 500000,
        "transferType": "in",
        "description": "TOOLFORGE capcut-reup zui@example.com",
        "referenceCode": "VCB.1234567",
    }
    parsed = parse_webhook(body)
    assert parsed["sepay_id"] == 12345
    assert parsed["amount_vnd"] == 500000
    assert parsed["transfer_type"] == "in"
    assert parsed["description"] == "TOOLFORGE capcut-reup zui@example.com"


def test_parse_webhook_from_string():
    body_str = '{"id": 1, "amount": 100, "transferType": "in", "description": "x"}'
    parsed = parse_webhook(body_str)
    assert parsed["amount_vnd"] == 100


def test_parse_webhook_invalid_json_raises():
    with pytest.raises(ValueError):
        parse_webhook("not json {")


def test_parse_webhook_non_object_raises():
    with pytest.raises(ValueError):
        parse_webhook([1, 2, 3])


# === is_incoming_transfer tests ===

def test_is_incoming_transfer_true():
    parsed = {"transfer_type": "in", "amount_vnd": 100}
    assert is_incoming_transfer(parsed) is True


def test_is_incoming_transfer_false_type():
    parsed = {"transfer_type": "out", "amount_vnd": 100}
    assert is_incoming_transfer(parsed) is False


def test_is_incoming_transfer_false_amount():
    parsed = {"transfer_type": "in", "amount_vnd": 0}
    assert is_incoming_transfer(parsed) is False


# === extract_order_info tests ===

def test_extract_order_info_full():
    info = extract_order_info("TOOLFORGE capcut-reup zui@example.com")
    assert info["tool_id"] == "capcut-reup"
    assert info["customer"] == "zui@example.com"


def test_extract_order_info_no_customer():
    info = extract_order_info("TOOLFORGE capcut-reup")
    assert info["tool_id"] == "capcut-reup"
    assert info["customer"] == ""


def test_extract_order_info_lowercase_prefix():
    """Case-insensitive prefix matching."""
    info = extract_order_info("toolforge voice-clone @zui")
    assert info["tool_id"] == "voice-clone"
    assert info["customer"] == "@zui"


def test_extract_order_info_no_prefix():
    info = extract_order_info("random text here")
    assert info["tool_id"] == ""


def test_extract_order_info_empty():
    info = extract_order_info("")
    assert info["tool_id"] == ""


# === activate_license_for_order tests ===

@pytest.mark.asyncio
async def test_activate_license_success():
    env = FakeEnv()
    env.DB.tables["tools"].append({
        "id": "capcut-reup", "name": "Capcut", "description": "x",
        "niche": "mmo_reup", "status": "live", "build_id": None,
        "pricing_vnd": 1000000, "binary_url": "", "license_required": 1,
        "tags": "", "created_at": "2026-07-27", "updated_at": "2026-07-27",
    })

    result = await activate_license_for_order(
        env.DB, "order-test123", "capcut-reup", "zui@example.com", "@zui"
    )
    assert result["ok"]
    assert is_valid_license_key(result["license_key"])
    # Verify license saved in D1
    assert any(l["key"] == result["license_key"] for l in env.DB.tables["licenses"])
    assert any(l["tool_id"] == "capcut-reup" for l in env.DB.tables["licenses"])


@pytest.mark.asyncio
async def test_activate_license_no_customer():
    env = FakeEnv()
    result = await activate_license_for_order(
        env.DB, "order-test456", "voice-clone", None, None
    )
    assert result["ok"]
    # License should still be created (customer info optional)


# === end-to-end payment flow test ===

@pytest.mark.asyncio
async def test_payment_flow_complete():
    """Full flow: create order → simulate SePay webhook → license activated."""
    from src.handlers.payment import create_order_handler, test_payment_handler

    env = FakeEnv()
    # Pre-populate tool
    env.DB.tables["tools"].append({
        "id": "capcut-reup", "name": "Capcut Reup", "description": "Tool MMO",
        "niche": "mmo_reup", "status": "live", "build_id": None,
        "pricing_vnd": 1000000, "binary_url": "", "license_required": 1,
        "tags": "mmo,capcut", "created_at": "2026-07-27", "updated_at": "2026-07-27",
    })

    # 1. Create order
    class Req:
        url = "/api/payment/orders"
        method = "POST"
        headers = {"content-type": "application/json"}
        async def json(self):
            return {"tool_id": "capcut-reup", "customer_email": "zui@example.com"}

    resp = await create_order_handler(Req(), env, None)
    body = json.loads(resp.body)
    assert body["ok"]
    order_id = body["order_id"]
    assert body["amount_vnd"] == 1000000
    assert "TOOLFORGE" in body["description"]

    # 2. Simulate payment via test endpoint
    class Req2:
        url = "/api/payment/test"
        method = "POST"
        headers = {"content-type": "application/json"}
        async def json(self):
            return {"order_id": order_id}

    resp2 = await test_payment_handler(Req2(), env, None)
    body2 = json.loads(resp2.body)
    assert body2["ok"]
    assert body2["test_mode"] is True
    assert is_valid_license_key(body2["license_key"])

    # 3. Verify order updated
    orders = env.DB.tables["orders"]
    order = next((o for o in orders if o["id"] == order_id), None)
    assert order is not None
    assert order["status"] == "paid"
    assert order["license_key"] == body2["license_key"]

    # 4. Verify license saved
    licenses = env.DB.tables["licenses"]
    license_row = next((l for l in licenses if l["key"] == body2["license_key"]), None)
    assert license_row is not None
    assert license_row["tool_id"] == "capcut-reup"
    assert license_row["customer_email"] == "zui@example.com"
    assert license_row["status"] == "active"

    # 5. Verify event logged
    events = env.DB.tables["payment_events"]
    assert len(events) >= 3  # order_created, test_payment, license_activated
