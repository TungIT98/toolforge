"""Tests for LLM wrapper.

Run: pytest tests/

Note: These are unit tests with mocked HTTP. Integration tests against
real MiniMax M3 should be run manually (require API key).
"""
import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from src.lib.http import _Response as _MockResponse

from src.llm import LLMClient, LLMError, get_client


class FakeResponse:
    """Mimics _MockResponse for testing."""
    def __init__(self, status_code: int, json_data: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self) -> dict:
        return self._json


@pytest.fixture
def fake_env(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key-abc")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.test.example/anthropic")
    monkeypatch.setenv("LLM_MODEL", "minimax/MiniMax-M3-test")
    monkeypatch.setenv("ENVIRONMENT", "test")
    return monkeypatch


@pytest.mark.asyncio
async def test_call_success(fake_env):
    """LLMClient.call() returns parsed text + usage on 200 OK."""
    client = LLMClient(api_key="test-key-abc", agent_name="test")

    fake_json = {
        "id": "msg_123",
        "model": "minimax/MiniMax-M3",
        "content": [{"type": "text", "text": "ToolForge P0 OK"}],
        "usage": {"input_tokens": 20, "output_tokens": 5},
        "stop_reason": "end_turn",
    }

    with patch("src.lib.http.AsyncClient.post", new=AsyncMock(return_value=FakeResponse(200, fake_json))):
        result = await client.call(system="sys", user="user", max_tokens=64)

    assert result["text"] == "ToolForge P0 OK"
    assert result["usage"]["input_tokens"] == 20
    assert result["usage"]["output_tokens"] == 5
    assert result["model"] == "minimax/MiniMax-M3"
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_call_non_200_raises(fake_env):
    """Non-200 response raises LLMError."""
    client = LLMClient(api_key="test-key-abc", agent_name="test")

    with patch("src.lib.http.AsyncClient.post", new=AsyncMock(return_value=FakeResponse(401, text="Unauthorized"))):
        with pytest.raises(LLMError) as exc_info:
            await client.call(system="s", user="u")
        assert "401" in str(exc_info.value)


@pytest.mark.asyncio
async def test_call_timeout_raises(fake_env):
    """Timeout raises LLMError."""
    client = LLMClient(api_key="test-key-abc", agent_name="test")

    with patch("src.lib.http.AsyncClient.post", new=AsyncMock(side_effect=httpx.TimeoutException("timeout"))):
        with pytest.raises(LLMError) as exc_info:
            await client.call(system="s", user="u", timeout_s=5)
        assert "timeout" in str(exc_info.value).lower()


def test_empty_key_raises():
    """Empty API key raises LLMError at construction."""
    with pytest.raises(LLMError) as exc_info:
        LLMClient(api_key="", agent_name="test")
    assert "LLM_API_KEY" in str(exc_info.value)


def test_get_client_from_env(fake_env):
    """get_client() reads from env var when no env binding given."""
    client = get_client(agent_name="test", env=None)
    assert client.api_key == "test-key-abc"
    assert client.base_url == "https://api.test.example/anthropic"
    assert client.model == "minimax/MiniMax-M3-test"


def test_get_client_from_cf_env(fake_env):
    """get_client() reads from CF env binding when provided."""
    class FakeEnv:
        LLM_API_KEY = "cf-secret-key"
        LLM_BASE_URL = "https://api.cf.example/anthropic"
        LLM_MODEL = "minimax/MiniMax-M3"

    client = get_client(agent_name="test", env=FakeEnv())
    assert client.api_key == "cf-secret-key"
    assert client.base_url == "https://api.cf.example/anthropic"
