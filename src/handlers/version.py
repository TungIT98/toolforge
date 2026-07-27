"""GET /api/version — return build + env version info.
"""
from __future__ import annotations

import os
import platform

from src.lib.response import json_response
from src.router import route


@route("GET", "/api/version")
async def version_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Return build + runtime info (no secrets)."""
    return json_response(
        {
            "ok": True,
            "service": "toolforge-api",
            "version": os.environ.get("TOOLFORGE_VERSION", "unknown"),
            "environment": os.environ.get("ENVIRONMENT", "development"),
            "llm_provider": os.environ.get("LLM_PROVIDER", "minimax"),
            "llm_model": os.environ.get("LLM_MODEL", "minimax/MiniMax-M3"),
            "runtime": "cloudflare-workers-python",
            "python_version": platform.python_version(),
            "phase": "P0-setup",
        }
    )


@route("GET", "/")
async def root_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Landing info for humans visiting the worker URL."""
    return json_response(
        {
            "ok": True,
            "service": "ToolForge API",
            "tagline": "AI agent platform tự động research + build + list software tools cho MMO/creator Việt",
            "version": os.environ.get("TOOLFORGE_VERSION", "unknown"),
            "phase": "P0-setup (week 1 of 12)",
            "endpoints": {
                "GET /": "This page",
                "GET /api/health": "Liveness check (D1 ping)",
                "GET /api/version": "Build + runtime info",
                "POST /api/llm/test": "Test LLM connection (MiniMax M3)",
                "POST /api/scout/run": "Manually trigger Scout pain point scan (P0 stub)",
            },
            "docs": "https://github.com/TungIT98/toolforge",
        }
    )
