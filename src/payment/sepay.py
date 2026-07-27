"""SePay webhook handler — verify signature + parse payment events.

SePay docs: https://docs.sepay.vn/
Webhook format: POST with JSON body, signature in X-Sepay-Signature header
(Apikey, HMAC-SHA256, or Bearer depending on merchant config).

P2.3 P1: Support Apikey header (simplest, sufficient for our use case).
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from src.lib.log import get_logger

log = get_logger("payment.sepay")

# SePay IP whitelist (for production, check against this list)
# Reference: https://docs.sepay.vn/#ip-allowlist
SEPAY_IPS = [
    "103.110.84.0/24",
    "103.110.85.0/24",
    "13.213.13.13",
    # Add more as needed
]


def verify_api_key(api_key_from_header: str | None, expected_api_key: str) -> bool:
    """Verify SePay Apikey authentication.

    Owner configures Apikey in SePay dashboard, sets same value as SEPAY_API_KEY
    Cloudflare Worker secret.

    Args:
        api_key_from_header: value of "Apikey" header from SePay request
        expected_api_key: SEPAY_API_KEY from env (Worker secret)

    Returns:
        True if match (constant-time), False otherwise
    """
    if not api_key_from_header or not expected_api_key:
        return False
    return hmac.compare_digest(api_key_from_header, expected_api_key)


def verify_signature(payload_bytes: bytes, signature_header: str | None, secret: str) -> bool:
    """Verify HMAC-SHA256 signature from SePay.

    Used when SePay is configured with HMAC instead of Apikey.
    """
    if not signature_header or not secret:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature_header, expected)


def parse_webhook(body: dict | str) -> dict[str, Any]:
    """Parse SePay webhook payload into normalized dict.

    Input (per SePay docs):
    {
        "id": 12345,
        "gateway": "Vietcombank",
        "transactionDate": "2026-07-27 10:30:45",
        "accountNumber": "0123456789",
        "subAccount": null,
        "amount": 500000,
        "transferType": "in",  // "in" = customer paid us, "out" = we sent
        "description": "TOOLFORGE capcut-desktop-reup user@example.com",
        "referenceCode": "VCB.1234567",
        "content": null
    }
    """
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
    if not isinstance(body, dict):
        raise ValueError("Webhook body must be object")

    return {
        "sepay_id": body.get("id"),
        "gateway": body.get("gateway", ""),
        "transaction_date": body.get("transactionDate", ""),
        "account_number": body.get("accountNumber", ""),
        "sub_account": body.get("subAccount"),
        "amount_vnd": int(body.get("amount", 0)),
        "transfer_type": body.get("transferType", "in"),  # "in" = paid us
        "description": body.get("description", ""),
        "reference_code": body.get("referenceCode", ""),
        "content": body.get("content"),
    }


def is_incoming_transfer(parsed: dict) -> bool:
    """Check if this webhook is an incoming payment (not outgoing)."""
    return parsed.get("transfer_type") == "in" and parsed.get("amount_vnd", 0) > 0


def extract_order_info(description: str) -> dict[str, str]:
    """Parse our custom order description format.

    Format: "TOOLFORGE <tool_id> <customer_email|telegram>"

    Examples:
    - "TOOLFORGE capcut-desktop-reup zui@example.com"
    - "TOOLFORGE voice-clone-desktop @zui_telegram"
    - "TOOLFORGE flow-captcha-veo3"
    """
    info: dict[str, str] = {"tool_id": "", "customer": "", "raw": description}
    if not description:
        return info
    parts = description.strip().split()
    if not parts:
        return info
    # Find TOOLFORGE prefix
    prefix_idx = -1
    for i, p in enumerate(parts):
        if p.upper() == "TOOLFORGE":
            prefix_idx = i
            break
    if prefix_idx < 0 or prefix_idx + 1 >= len(parts):
        return info
    info["tool_id"] = parts[prefix_idx + 1]
    if prefix_idx + 2 < len(parts):
        info["customer"] = parts[prefix_idx + 2]
    return info
