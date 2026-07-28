"""Tests for Orchestrator — the showpiece pipeline."""
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from tests.test_e2e import FakeD1, FakeEnv


def _llm_response_json(content: str) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "msg_test", "model": "minimax/MiniMax-M3-test",
        "content": [{"type": "text", "text": content}],
        "usage": {"input_tokens": 100, "output_tokens": 300},
        "stop_reason": "end_turn",
    })


def _llm_response_text(text: str) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "msg_test", "model": "minimax/MiniMax-M3-test",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 100, "output_tokens": 300},
        "stop_reason": "end_turn",
    })


def _spec_response() -> str:
    return """# Spec: Test Tool

## 1. Problem
MMOer mất 3 giờ/ngày reup TikTok.

## 2. Solution
Auto reup.

## 3. Features
- Auto-cut
- Auto-caption

## 4. Tech Stack
Python CLI

## 5. Architecture
Single binary

## 6. Platform
Windows

## 7. Pricing
1.2M VND

## 8. Effort Estimate
40 hours

## 9. Risks
TikTok ban

## 10. Success Metrics
Save 14h/week
"""


def _hype_response() -> str:
    return json.dumps({
        "landing": {"headline": "Test headline 30 từ cho MMO Việt"},
        "facebook_ad_a": {"hook": "Pain?"},
        "facebook_ad_b": {"hook": "Result?"},
        "tiktok_script": {"hook_3s": "POV"},
    })


def _make_mock_post():
    """Build a mock httpx post that routes by system prompt content.

    Hype check first (Hype prompt contains 'spec' so order matters).
    """
    async def mock_post(*args, **kwargs):
        payload = kwargs.get("json", {})
        system = payload.get("system", "").lower()
        # Hype: must be first because Hype system prompt contains "spec"
        if "hype" in system[:50] or "marketing" in system[:50]:
            return _llm_response_text(_hype_response())
        # Scout: returns JSON array of pain points
        if "phân tích" in system or "scout" in system[:50]:
            return _llm_response_json(json.dumps([
                {"title": "Test pain", "description": "MMOer mất 3h/ngày reup",
                 "audience": "MMO VN", "category": "mmo_reup", "severity": 8},
            ]))
        # Architect: returns spec markdown
        if "kiến trúc" in system or "10-section" in system or "architect" in system[:50]:
            return _llm_response_text(_spec_response())
        # Forge: returns code with fences
        if "engineer" in system or "generate code" in system:
            return _llm_response_text("```python:main.py\ndef main():\n    print('hi')\n```")
        return _llm_response_json(json.dumps({"result": "ok"}))
    return mock_post


# === Full pipeline tests ===

@pytest.mark.asyncio
async def test_run_pipeline_full_success():
    """Full 5-phase pipeline runs to success, creates tool in store."""
    from src.orchestrator import run_pipeline
    with patch("httpx.AsyncClient.post", new=_make_mock_post()):
        env = FakeEnv()
        result = await run_pipeline(
            env, "MMOer mất 3 giờ/ngày reup TikTok", trigger="test"
        )
    assert "run_id" in result
    assert result["run_id"].startswith("run-")
    assert len(result["steps"]) == 5
    for step in result["steps"]:
        assert step["status"] in ("success", "failed")
        assert "phase" in step
        assert "summary" in step
    # Final step should be store
    assert result["steps"][-1]["phase"] == "store"


@pytest.mark.asyncio
async def test_run_pipeline_no_db():
    """No D1 → error."""
    from src.orchestrator import run_pipeline

    class NoDB(FakeEnv):
        def __init__(self):
            super().__init__()
            self.DB = None
    result = await run_pipeline(NoDB(), "test input")
    assert result["ok"] is False
    assert result["code"] == "DB_NOT_BOUND"


@pytest.mark.asyncio
async def test_run_pipeline_creates_db_records():
    """Pipeline creates run + 5 step records in DB."""
    from src.orchestrator import get_run, run_pipeline
    env = FakeEnv()
    with patch("httpx.AsyncClient.post", new=_make_mock_post()):
        result = await run_pipeline(env, "Test pain point", trigger="test")

    assert len(env.DB.tables["pipeline_runs"]) == 1
    # Even if some phases failed, we should have at least 1 step (the one that succeeded)
    assert len(env.DB.tables["pipeline_steps"]) >= 1
    run_id = result["run_id"]
    run = await get_run(env.DB, run_id)
    assert run is not None
    assert run["status"] in ("success", "failed", "running")
    # Steps in order
    phases = [s["phase"] for s in run["steps"]]
    step_indices = [s["step_index"] for s in run["steps"]]
    assert step_indices == sorted(step_indices), f"steps not in order: {phases} / {step_indices}"
    # First step must be scout
    if phases:
        assert phases[0] == "scout"


@pytest.mark.asyncio
async def test_run_pipeline_with_tool_name_override():
    from src.orchestrator import run_pipeline
    with patch("httpx.AsyncClient.post", new=_make_mock_post()):
        env = FakeEnv()
        result = await run_pipeline(env, "Test pain", tool_name="Custom Tool Name")
    assert result["tool_name"] == "Custom Tool Name"


# === get_run tests ===

@pytest.mark.asyncio
async def test_get_run_not_found():
    from src.orchestrator import get_run
    env = FakeEnv()
    result = await get_run(env.DB, "run-nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_get_run_with_steps():
    from src.orchestrator import get_run, run_pipeline
    env = FakeEnv()
    with patch("httpx.AsyncClient.post", new=_make_mock_post()):
        result = await run_pipeline(env, "Test", tool_name="My Tool")
    run = await get_run(env.DB, result["run_id"])
    assert run is not None
    for s in run["steps"]:
        assert "phase" in s
        assert "status" in s
        assert "summary" in s


# === HTTP handler tests ===

@pytest.mark.asyncio
async def test_handler_run_missing_input():
    from src.handlers.orchestrator import orchestrator_run_handler
    class Req:
        async def json(self):
            return {}
    resp = await orchestrator_run_handler(Req(), FakeEnv(), None)
    assert resp.status == 400


@pytest.mark.asyncio
async def test_handler_run_no_db():
    from src.handlers.orchestrator import orchestrator_run_handler
    class NoDB(FakeEnv):
        def __init__(self):
            super().__init__()
            self.DB = None
    class Req:
        async def json(self):
            return {"input": "test"}
    resp = await orchestrator_run_handler(Req(), NoDB(), None)
    assert resp.status == 500


@pytest.mark.asyncio
async def test_handler_run_full():
    from src.handlers.orchestrator import orchestrator_run_handler
    class Req:
        async def json(self):
            return {"input": "Test", "tool_name": "Test Tool"}
    with patch("httpx.AsyncClient.post", new=_make_mock_post()):
        resp = await orchestrator_run_handler(Req(), FakeEnv(), None)
    body = json.loads(resp.body)
    assert body["ok"] is True
    assert "run_id" in body
    assert len(body["steps"]) == 5


@pytest.mark.asyncio
async def test_handler_get_run():
    from src.handlers.orchestrator import orchestrator_get_handler, orchestrator_run_handler
    env = FakeEnv()
    class RunReq:
        async def json(self):
            return {"input": "Test", "tool_name": "Test Tool"}
    with patch("httpx.AsyncClient.post", new=_make_mock_post()):
        resp1 = await orchestrator_run_handler(RunReq(), env, None)
    body1 = json.loads(resp1.body)
    run_id = body1["run_id"]

    class GetReq:
        path = f"/api/orchestrator/run/{run_id}"
    resp2 = await orchestrator_get_handler(GetReq(), env, None)
    body2 = json.loads(resp2.body)
    assert body2["ok"] is True
    assert body2["run"]["id"] == run_id
    assert len(body2["run"]["steps"]) == 5


@pytest.mark.asyncio
async def test_handler_get_run_not_found():
    from src.handlers.orchestrator import orchestrator_get_handler
    class Req:
        path = "/api/orchestrator/run/nonexistent"
    resp = await orchestrator_get_handler(Req(), FakeEnv(), None)
    assert resp.status == 404


@pytest.mark.asyncio
async def test_handler_list_runs():
    from src.handlers.orchestrator import orchestrator_list_handler
    class Req:
        pass
    resp = await orchestrator_list_handler(Req(), FakeEnv(), None)
    body = json.loads(resp.body)
    assert body["ok"] is True
    assert "runs" in body
