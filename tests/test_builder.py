"""Tests for Builder Tool (chat + generator)."""
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.builder.chat import (
    build_llm_messages,
    chat_with_user,
    create_chat_session,
    detect_ready_response,
    get_session,
)
from src.builder.generator import generate_code_from_spec
from src.llm import LLMClient
from tests.test_e2e import FakeD1, FakeEnv


# === detect_ready_response tests ===

def test_detect_ready_clean_json():
    text = '{"ready": true, "tool_name": "X", "spec": {}}'
    is_ready, parsed = detect_ready_response(text)
    assert is_ready is True
    assert parsed["tool_name"] == "X"


def test_detect_ready_markdown_fence():
    text = '```json\n{"ready": true, "tool_name": "Y", "spec": {}}\n```'
    is_ready, parsed = detect_ready_response(text)
    assert is_ready is True
    assert parsed["tool_name"] == "Y"


def test_detect_ready_with_explanation():
    """LLM can include text before JSON."""
    text = 'OK mình hiểu rồi. Đây là spec:\n\n{"ready": true, "tool_name": "Z", "spec": {}}'
    is_ready, parsed = detect_ready_response(text)
    assert is_ready is True
    assert parsed["tool_name"] == "Z"


def test_detect_ready_false_for_question():
    text = "Bạn muốn build tool gì? MP3 hay MP4?"
    is_ready, parsed = detect_ready_response(text)
    assert is_ready is False


def test_detect_ready_invalid_json_returns_false():
    text = "Đây là response không phải JSON"
    is_ready, parsed = detect_ready_response(text)
    assert is_ready is False


def test_detect_ready_false_for_non_dict():
    text = '[1, 2, 3]'
    is_ready, parsed = detect_ready_response(text)
    assert is_ready is False


# === build_llm_messages tests ===

def test_build_llm_messages_empty_history():
    system, msgs = build_llm_messages("sys", [], "hello")
    assert system == "sys"
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "hello"


def test_build_llm_messages_caps_at_20():
    history = [{"role": "user", "content": f"msg {i}"} for i in range(50)]
    system, msgs = build_llm_messages("sys", history, "new")
    assert len(msgs) == 21  # 20 from history + 1 new
    assert msgs[0]["content"] == "msg 30"  # last 20 of 50
    assert msgs[-1]["content"] == "new"


# === session CRUD tests ===

@pytest.mark.asyncio
async def test_create_chat_session():
    env = FakeEnv()
    result = await create_chat_session(env.DB, user_ip="1.2.3.4")
    assert result["session_id"].startswith("sess-")
    assert result["status"] == "chatting"
    assert any(s["user_ip"] == "1.2.3.4" for s in env.DB.tables["builder_sessions"])


@pytest.mark.asyncio
async def test_get_session_with_messages():
    env = FakeEnv()
    sess = await create_chat_session(env.DB)
    # Add some messages
    env.DB.tables["builder_messages"].append({
        "session_id": sess["session_id"], "role": "user", "content": "hello",
        "ts": "2026-07-27T10:00:00",
    })
    env.DB.tables["builder_messages"].append({
        "session_id": sess["session_id"], "role": "assistant", "content": "hi",
        "ts": "2026-07-27T10:00:01",
    })
    s = await get_session(env.DB, sess["session_id"])
    assert s is not None
    assert s["status"] == "chatting"
    assert len(s["messages"]) == 2


# === chat_with_user tests ===

@pytest.mark.asyncio
async def test_chat_with_user_first_message():
    """First user message → LLM asks clarifying question."""
    env = FakeEnv()
    sess = await create_chat_session(env.DB)
    client = LLMClient(api_key="test", agent_name="builder")

    fake_response = {
        "text": "Bạn muốn tool này chạy trên Windows hay Mac?",
        "usage": {"input_tokens": 100, "output_tokens": 30},
        "model": "minimax/MiniMax-M3", "latency_ms": 1000,
    }

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_make_fake_resp(fake_response))):
        result = await chat_with_user(env.DB, sess["session_id"], "Tôi cần tool download video TikTok", client)

    assert result["ok"]
    assert result["status"] == "chatting"
    assert "Windows" in result["assistant_message"] or "Mac" in result["assistant_message"]
    assert result["messages_count"] == 2


@pytest.mark.asyncio
async def test_chat_with_user_triggers_ready():
    """When LLM outputs JSON ready=true → session marked ready_to_build."""
    env = FakeEnv()
    sess = await create_chat_session(env.DB)
    client = LLMClient(api_key="test", agent_name="builder")

    fake_response = {
        "text": json.dumps({
            "ready": True,
            "tool_name": "TikTok Downloader",
            "spec": {
                "problem": "User cần download video TikTok không watermark",
                "input": "TikTok video URL",
                "output": "MP4 file",
                "platform": "windows",
                "stack": "Python CLI",
                "features": ["Download single video", "No watermark"],
                "edge_cases": ["Private video", "Invalid URL"],
            },
        }),
        "usage": {"input_tokens": 200, "output_tokens": 150},
        "model": "minimax/MiniMax-M3", "latency_ms": 2000,
    }

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_make_fake_resp(fake_response))):
        result = await chat_with_user(env.DB, sess["session_id"], "Build đi", client)

    assert result["ok"]
    assert result["status"] == "ready_to_build"
    assert result["tool_name"] == "TikTok Downloader"
    assert "spec" in result
    # Verify DB updated
    s = next(s for s in env.DB.tables["builder_sessions"] if s["id"] == sess["session_id"])
    assert s["status"] == "ready_to_build"
    assert s["tool_name"] == "TikTok Downloader"


@pytest.mark.asyncio
async def test_chat_with_user_session_not_found():
    env = FakeEnv()
    client = LLMClient(api_key="test", agent_name="builder")
    result = await chat_with_user(env.DB, "sess-ghost", "hi", client)
    assert not result["ok"]
    assert result["code"] == "SESSION_NOT_FOUND"


# === generate_code_from_spec tests ===

@pytest.mark.asyncio
async def test_generate_code_from_spec():
    """Spec → LLM → code files."""
    client = LLMClient(api_key="test", agent_name="builder_generator")

    fake_response = {
        "text": (
            "Here's the code:\n\n"
            "```python:main.py\n"
            "def hello():\n    print('hi')\n\nif __name__ == '__main__':\n    hello()\n"
            "```\n\n"
            "```txt:requirements.txt\n"
            "typer>=0.9\n"
            "```\n"
        ),
        "usage": {"input_tokens": 500, "output_tokens": 200},
        "model": "minimax/MiniMax-M3", "latency_ms": 3000,
    }

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_make_fake_resp(fake_response))):
        result = await generate_code_from_spec(
            "# Spec\n## Problem\nTest",
            client,
            tool_name="TestTool",
        )

    assert result["file_count"] == 2
    assert "main.py" in result["files"]
    assert result["total_lines"] > 0


# === end-to-end builder flow ===

@pytest.mark.asyncio
async def test_builder_full_flow_chat_then_build():
    """Full E2E: create session → chat → spec ready → build code."""
    from src.handlers.builder import (
        build_session_handler,
        create_session_handler,
        session_message_handler,
    )

    env = FakeEnv()

    # 1. Create session
    class Req1:
        url = "/api/builder/session"
        method = "POST"
        headers = {"content-type": "application/json"}
        async def json(self):
            return {}
    resp1 = await create_session_handler(Req1(), env, None)
    body1 = json.loads(resp1.body)
    session_id = body1["session_id"]
    assert body1["ok"]

    # 2. Chat (user says "Build it" → LLM outputs ready=true)
    class Req2:
        path = f"/api/builder/session/{session_id}/message"
        url = path
        method = "POST"
        headers = {"content-type": "application/json"}
        async def json(self):
            return {"message": "Build nó đi"}

    ready_json = json.dumps({
        "ready": True,
        "tool_name": "My Tool",
        "spec": {
            "problem": "test",
            "input": "url",
            "output": "file",
            "platform": "cli",
            "stack": "Python",
            "features": ["f1"],
            "edge_cases": ["e1"],
        },
    })
    fake_chat = {
        "text": ready_json,
        "usage": {"input_tokens": 100, "output_tokens": 100},
        "model": "minimax/MiniMax-M3", "latency_ms": 1000,
    }
    fake_build = {
        "text": "```python:main.py\ndef main():\n    pass\n```",
        "usage": {"input_tokens": 200, "output_tokens": 50},
        "model": "minimax/MiniMax-M3", "latency_ms": 2000,
    }
    import httpx
    call_count = {"i": 0}
    async def fake_post(*args, **kwargs):
        call_count["i"] += 1
        if call_count["i"] == 1:
            return _make_fake_resp(fake_chat)
        return _make_fake_resp(fake_build)
    with patch("httpx.AsyncClient.post", new=fake_post):
        resp2 = await session_message_handler(Req2(), env, None)
        body2 = json.loads(resp2.body)
        assert body2["ok"]
        assert body2["status"] == "ready_to_build"
        assert body2["tool_name"] == "My Tool"

        # 3. Build code
        class Req3:
            path = f"/api/builder/session/{session_id}/build"
            url = path
            method = "POST"
            headers = {"content-type": "application/json"}
            async def json(self):
                return {}
        resp3 = await build_session_handler(Req3(), env, None)
        body3 = json.loads(resp3.body)
        assert body3["ok"]
        assert body3["job_id"].startswith("job-")
        assert body3["file_count"] >= 1
        assert "main.py" in body3["files"]

    # 4. Verify D1
    sessions = env.DB.tables["builder_sessions"]
    s = next(x for x in sessions if x["id"] == session_id)
    assert s["status"] == "done"
    jobs = env.DB.tables["builder_jobs"]
    assert any(j["session_id"] == session_id for j in jobs)


# === helpers ===

def _make_fake_resp(payload: dict):
    """Build fake httpx.Response with Anthropic API format."""
    return httpx.Response(200, json={
        "id": "msg_test", "model": payload.get("model", "minimax/MiniMax-M3"),
        "content": [{"type": "text", "text": payload["text"]}],
        "usage": payload.get("usage", {}),
        "stop_reason": "end_turn",
    })
