"""License key generator.

Format: XXXX-XXXX-XXXX-XXXX (16 chars, 4 groups of 4, easy to read + type).
Uses uuid4 for collision-safe randomness.
"""
from __future__ import annotations

import uuid


def generate_license_key() -> str:
    """Generate a license key in XXXX-XXXX-XXXX-XXXX format.

    Uses uuid4 (16 hex chars without dashes) → split into 4 groups.
    """
    raw = uuid.uuid4().hex.upper()  # 32 hex chars
    # Take first 16 chars, group into 4
    chars = raw[:16]
    return f"{chars[0:4]}-{chars[4:8]}-{chars[8:12]}-{chars[12:16]}"


def is_valid_license_key(key: str) -> bool:
    """Check if key matches XXXX-XXXX-XXXX-XXXX format (hex chars)."""
    if not isinstance(key, str):
        return False
    parts = key.split("-")
    if len(parts) != 4:
        return False
    for p in parts:
        if len(p) != 4:
            return False
        try:
            int(p, 16)
        except ValueError:
            return False
    return True
