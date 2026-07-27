"""Structured logging for ToolForge Workers.

CF Workers Python runtime uses stdout; logs are aggregated by Cloudflare
Observability. Format: JSON line per log event for easy parsing.

Usage:
    from src.lib.log import get_logger
    log = get_logger("scout")
    log.info("daily_scan_started", sources=8)
    log.error("llm_call_failed", err="timeout")
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any


def _get_env() -> str:
    return os.environ.get("ENVIRONMENT", "development")


def _now_iso() -> str:
    """ISO 8601 UTC timestamp."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Logger:
    """Minimal structured logger. Writes JSON line to stdout."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.env = _get_env()

    def _emit(self, level: str, event: str, **fields: Any) -> None:
        payload = {
            "ts": _now_iso(),
            "level": level,
            "env": self.env,
            "logger": self.name,
            "event": event,
            **fields,
        }
        try:
            sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except Exception:
            # Logger must never raise
            pass

    def debug(self, event: str, **fields: Any) -> None:
        self._emit("debug", event, **fields)

    def info(self, event: str, **fields: Any) -> None:
        self._emit("info", event, **fields)

    def warn(self, event: str, **fields: Any) -> None:
        self._emit("warn", event, **fields)

    def error(self, event: str, err: str | None = None, **fields: Any) -> None:
        if err is not None:
            fields["err"] = err
        self._emit("error", event, **fields)


def get_logger(name: str) -> Logger:
    """Get a logger instance for the given component name.

    Examples:
        log = get_logger("scout")
        log = get_logger("forge.worker")
    """
    return Logger(name)
