"""Forge build orchestrator — trigger Tauri build via GitHub Actions.

Flow:
1. Owner (or Forge agent) calls POST /api/forge/build-binary
2. Worker triggers GitHub Actions workflow_dispatch with build_id, tool_id
3. GH Action checks out repo, builds Tauri (Linux MVP, Windows in P4.5)
4. GH Action uploads binary to R2
5. GH Action POSTs result back to /api/forge/webhook/built
6. Worker updates D1 build record with binary URL
7. Frontend polls /api/forge/get?id=build-... to get download URL
"""
from __future__ import annotations

import os
from typing import Any

from src.lib.log import get_logger

log = get_logger("forge.orchestrator")


async def trigger_github_workflow(
    build_id: str,
    tool_id: str,
    version: str,
    callback_url: str,
    env: "object",
) -> dict[str, Any]:
    """Trigger GitHub Actions workflow_dispatch for Tauri build.

    Required secrets:
    - GITHUB_TOKEN: PAT with workflow scope, OR use GH Actions app token
    - GITHUB_REPO_OWNER: "TungIT98"
    - GITHUB_REPO_NAME: "toolforge"
    - WEBHOOK_SECRET: shared secret with GH Action
    """
    token = getattr(env, "GITHUB_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
    repo_owner = getattr(env, "GITHUB_REPO_OWNER", "") or os.environ.get("GITHUB_REPO_OWNER", "TungIT98")
    repo_name = getattr(env, "GITHUB_REPO_NAME", "") or os.environ.get("GITHUB_REPO_NAME", "toolforge")
    webhook_secret = getattr(env, "WEBHOOK_SECRET", "") or os.environ.get("WEBHOOK_SECRET", "")

    if not token:
        return {
            "ok": False,
            "error": "GITHUB_TOKEN not set. wrangler secret put GITHUB_TOKEN",
            "code": "GITHUB_TOKEN_MISSING",
        }
    if not webhook_secret:
        return {
            "ok": False,
            "error": "WEBHOOK_SECRET not set. wrangler secret put WEBHOOK_SECRET",
            "code": "WEBHOOK_SECRET_MISSING",
        }

    # GH API endpoint
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/workflows/build-tauri.yml/dispatches"
    import httpx
    payload = {
        "ref": "main",  # workflow must be on main
        "inputs": {
            "build_id": build_id,
            "tool_id": tool_id,
            "version": version,
            "callback_url": callback_url,
            "webhook_secret": webhook_secret,
        },
    }
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code == 204:
            log.info("gh_workflow_triggered", build_id=build_id, tool_id=tool_id)
            return {
                "ok": True,
                "build_id": build_id,
                "status": "triggered",
                "workflow_url": f"https://github.com/{repo_owner}/{repo_name}/actions/workflows/build-tauri.yml",
            }
        else:
            log.warn("gh_workflow_failed", status=resp.status_code, body=resp.text[:500])
            return {
                "ok": False,
                "error": f"GH API returned {resp.status_code}: {resp.text[:200]}",
                "code": "GH_API_FAILED",
            }
    except Exception as e:
        log.error("gh_workflow_exception", err=str(e))
        return {
            "ok": False,
            "error": str(e),
            "code": "GH_API_EXCEPTION",
        }
