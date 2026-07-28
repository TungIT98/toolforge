"""Request monitoring — X-Request-Id generation and propagation.

Minimal: just request_id for tracing + live demo traces.
No KV error log, no admin endpoints — keep it lean.

Usage:
    from src.lib.monitoring import generate_request_id, get_request_id

    rid = generate_request_id()
    set_request_id(rid)
    ...
    log.info("event", request_id=get_request_id())
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Any

# === Module-level state for request_id ===
# CF Workers: module persists across requests in same isolate
# Always set fresh on every request via set_request_id() in dispatch
_current_request_id: str = ""


def generate_request_id() -> str:
    """Generate a unique request ID (UUID v4)."""
    try:
        return str(uuid.uuid4())
    except Exception:
        # Fallback if uuid not available
        return f"req-{int(time.time() * 1000000)}-{os.urandom(4).hex()}"


def set_request_id(request_id: str) -> None:
    """Set the current request ID. Call at the start of every request."""
    global _current_request_id
    _current_request_id = request_id


def get_request_id() -> str:
    """Get the current request ID. Returns empty string if not set."""
    return _current_request_id
