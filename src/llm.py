"""MiniMax M3 LLM wrapper for ToolForge.

Provider: MiniMax (minimaxi.com / anthropic-compatible endpoint)
Model: minimax/MiniMax-M3 (450K context)
API: Anthropic Messages format

Reference: memory MEMORY.md line 40-45 (HubFlow MVP uses same provider).
"""
from __future__ import annotations

import os
import time
from typing import Any

from src.lib.http import AsyncClient, HTTPError, TimeoutException as HTTPTimeout

from src.lib.log import get_logger

log = get_logger("llm")

PROVIDER_DEFAULT = "minimax"
BASE_URL_DEFAULT = "https://api.minimaxi.com/anthropic"
MODEL_DEFAULT = "minimax/MiniMax-M3"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TIMEOUT_S = 30


class LLMError(Exception):
    """Raised when LLM call fails."""


class LLMClient:
    """Async client for MiniMax M3 (Anthropic-compatible API)."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str | None = None,
        agent_name: str = "unknown",
    ) -> None:
        if not api_key:
            raise LLMError("LLM_API_KEY is empty; set via `wrangler secret put LLM_API_KEY`")
        self.api_key = api_key
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL") or BASE_URL_DEFAULT).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL") or MODEL_DEFAULT
        self.agent_name = agent_name

    async def call(
        self,
        system: str,
        user: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = 0.7,
        timeout_s: int = DEFAULT_TIMEOUT_S,
    ) -> dict[str, Any]:
        """Make 1 LLM call. Returns dict with: text, usage, model, latency_ms.

        Raises LLMError on failure.
        """
        url = f"{self.base_url}/v1/messages"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }

        log.info(
            "llm_call_start",
            agent=self.agent_name,
            model=self.model,
            prompt_len=len(user) + len(system),
            max_tokens=max_tokens,
        )
        t0 = time.time()
        try:
            async with AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(url, headers=headers, json=payload)
        except HTTPTimeout as e:
            log.error("llm_call_timeout", err=str(e), timeout_s=timeout_s, agent=self.agent_name)
            raise LLMError(f"LLM timeout after {timeout_s}s") from e
        except Exception as e:
            log.error("llm_call_failed", err=str(e), agent=self.agent_name)
            raise LLMError(f"LLM call failed: {e}") from e

        latency_ms = int((time.time() - t0) * 1000)

        if resp.status_code != 200:
            err_body = resp.text[:500]
            log.error(
                "llm_call_non_200",
                err=f"status {resp.status_code}",
                body=err_body,
                agent=self.agent_name,
            )
            raise LLMError(f"LLM returned {resp.status_code}: {err_body}")

        data = resp.json()
        text_blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        text = "\n".join(text_blocks).strip()
        usage = data.get("usage", {})

        log.info(
            "llm_call_ok",
            agent=self.agent_name,
            model=self.model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            latency_ms=latency_ms,
        )
        return {
            "text": text,
            "usage": usage,
            "model": data.get("model", self.model),
            "latency_ms": latency_ms,
            "stop_reason": data.get("stop_reason"),
        }

    async def test_connection(self) -> dict[str, Any]:
        """Make a trivial LLM call to verify auth + network. Used by /api/llm/test."""
        system = "Bạn là một AI assistant. Trả lời ngắn gọn bằng tiếng Việt."
        user = "Nói 'ToolForge P0 OK' bằng tiếng Việt. Một dòng duy nhất."
        result = await self.call(system=system, user=user, max_tokens=64, temperature=0.0, timeout_s=15)
        return result


def get_client(agent_name: str, env: Any | None = None) -> LLMClient:
    """Factory: build LLMClient from environment bindings.

    Args:
        agent_name: Agent identifier for logging (e.g., "scout", "forge")
        env: Cloudflare env binding (has .LLM_API_KEY, .LLM_BASE_URL, .LLM_MODEL)

    Returns:
        LLMClient instance
    """
    api_key = ""
    base_url: str | None = None
    model: str | None = None

    if env is not None:
        # CF Workers: secrets + vars are accessed as attributes on env
        api_key = getattr(env, "LLM_API_KEY", "") or ""
        base_url = getattr(env, "LLM_BASE_URL", None)
        model = getattr(env, "LLM_MODEL", None)
    else:
        # Local dev / tests
        api_key = os.environ.get("LLM_API_KEY", "")

    return LLMClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
        agent_name=agent_name,
    )
