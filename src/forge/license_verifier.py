"""Server-side license verification.

Tauri app calls POST /api/license/verify with {key, tool_id} to check if
license is valid, active, not expired, and matches the tool.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.forge.license import is_valid_license_key
from src.lib.log import get_logger

log = get_logger("forge.license_verifier")


async def verify_license(db: "object", license_key: str, tool_id: str) -> dict[str, Any]:
    """Verify a license key against D1.

    Returns:
        {
            ok: True,
            valid: bool,
            reason: "active" | "expired" | "revoked" | "tool_mismatch" | "not_found" | "invalid_format",
            license: {key, tool_id, status, customer_email, expires_at} (if found)
        }
    """
    # 1. Format check
    if not is_valid_license_key(license_key):
        return {
            "ok": True,
            "valid": False,
            "reason": "invalid_format",
            "license": None,
        }

    # 2. Lookup in D1
    try:
        license_row = await db.prepare(
            "SELECT key, tool_id, status, customer_email, customer_telegram, activated_at, expires_at "
            "FROM licenses WHERE key = ?"
        ).bind(license_key).first()
    except Exception as e:
        log.error("license_lookup_failed", err=str(e), key=license_key[:8])
        return {"ok": False, "error": str(e), "code": "DB_ERROR"}

    if not license_row:
        return {
            "ok": True,
            "valid": False,
            "reason": "not_found",
            "license": None,
        }

    # 3. Tool mismatch
    if license_row.get("tool_id") != tool_id:
        return {
            "ok": True,
            "valid": False,
            "reason": "tool_mismatch",
            "license": license_row,
        }

    # 4. Status check
    status = license_row.get("status")
    if status == "revoked":
        return {
            "ok": True,
            "valid": False,
            "reason": "revoked",
            "license": license_row,
        }

    # 5. Expiry check
    expires_at = license_row.get("expires_at")
    if expires_at:
        try:
            # expires_at is ISO format
            expiry_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if expiry_dt < now:
                return {
                    "ok": True,
                    "valid": False,
                    "reason": "expired",
                    "license": license_row,
                }
        except (ValueError, TypeError) as e:
            log.warn("expiry_parse_failed", err=str(e), expires_at=expires_at)

    # 6. Active and valid
    return {
        "ok": True,
        "valid": True,
        "reason": "active",
        "license": license_row,
    }
