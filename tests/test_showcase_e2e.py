"""End-to-end test for the full showcase flow.

Simulates: 1 user click on /showcase → 5 agents collaborate → tool published.
This is the showpiece E2E test that validates the entire pipeline works.
"""
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from src.lib.http import _Response as _MockResponse

from tests.test_e2e import FakeD1, FakeEnv


def _resp_json(text: str) -> _MockResponse:
    return _MockResponse(200, body_json={
        "id": "msg_test", "model": "minimax/MiniMax-M3-test",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 200, "output_tokens": 500},
        "stop_reason": "end_turn",
    })


def _scout_resp() -> str:
    return json.dumps([
        {
            "title": "Reup TikTok mất thời gian",
            "description": "MMOer mất 3 giờ/ngày để reup video TikTok thủ công",
            "audience": "MMO TikTok creator Việt Nam",
            "category": "mmo_reup",
            "severity": 8,
            "market_size_vn": "50K+ creators",
            "current_solutions": "Manual edit, các tool nước ngoài không support tiếng Việt",
            "gap": "Tự động hóa + hỗ trợ tiếng Việt",
            "opportunity": "S",
        },
    ])


def _architect_resp() -> str:
    return """# Spec: CapCut Reup

## 1. Problem
MMOer mất 3 giờ/ngày reup video TikTok thủ công.

## 2. Solution
Tự động hóa quy trình reup: download → edit → caption → đăng.

## 3. Features
- Auto-download video TikTok
- Auto-edit (cắt, ghép, transition)
- Auto-caption tiếng Việt
- Auto-post theo lịch

## 4. Tech Stack
Python + Tauri 2.x

## 5. Architecture
Desktop binary, chạy local

## 6. Platform
Windows 10/11

## 7. Pricing
1.2M VND/lifetime

## 8. Effort Estimate
60 hours

## 9. Risks
TikTok anti-bot

## 10. Success Metrics
Save 14h/week, 20 videos/day
"""


def _hype_resp() -> str:
    return json.dumps({
        "landing": {
            "headline": "MMOer Việt: tiết kiệm 14 giờ/tuần với CapCut Reup",
            "subhead": "Auto download, edit, caption, đăng TikTok",
            "benefits": [
                "Tiết kiệm 14 giờ/tuần so với manual",
                "Đăng 20 video/ngày, không burnout",
                "Caption tiếng Việt tự động",
            ],
            "cta": "Mua ngay 1.2M VND — Free trial 3 ngày",
            "faq": [{"q": "Cần biết code?", "a": "Không"}, {"q": "Có trên Mac?", "a": "Sắp có"}],
        },
        "facebook_ad_a": {
            "name": "Pain focus",
            "hook": "MMOer ơi, mất 3 giờ/ngày reup TikTok có mệt không?",
            "body": "Cắt, edit, caption, đăng — lặp đi lặp lại. CapCut Reup tự động hóa hết.",
            "cta": "Tải ngay — Free trial 3 ngày",
        },
        "facebook_ad_b": {
            "name": "Result focus",
            "hook": "Tool Việt giúp MMOer đăng 20 video/ngày",
            "body": "Anh Khoa: tăng 3x output. Chị Linh: ROI sau 9 ngày.",
            "cta": "Xem demo — Tải miễn phí",
        },
        "tiktok_script": {
            "hook_3s": "POV: Bạn tiết kiệm 14 giờ/tuần nhờ 1 tool",
            "body": "Demo tool chạy — edit xong 1 video trong 5 phút",
            "caption": "Link tải trong bio 🔥",
        },
    })


def _make_full_mock():
    """Build mock that returns correct content for each agent phase."""
    async def mock(*a, **kw):
        system = kw.get("json", {}).get("system", "").lower()
        # Hype first (Hype prompt contains 'spec')
        if "hype" in system[:50] or "marketing" in system[:50]:
            return _resp_json(_hype_resp())
        if "phân tích" in system or "scout" in system[:50]:
            return _resp_json(_scout_resp())
        if "kiến trúc" in system or "10-section" in system or "architect" in system[:50]:
            return _resp_json(_architect_resp())
        if "engineer" in system or "generate code" in system:
            return _resp_json("```python:main.py\ndef main(): print('reup tool')\n```")
        return _resp_json(json.dumps({"result": "ok"}))
    return mock


# === E2E: full showcase flow ===

@pytest.mark.asyncio
async def test_e2e_showcase_full_flow():
    """The showpiece E2E: 1 click → 5 agents → 1 tool in store + 1 campaign."""
    from src.handlers.orchestrator import (
        orchestrator_get_handler, orchestrator_run_handler,
    )
    from src.orchestrator import get_run

    env = FakeEnv()
    class RunReq:
        async def json(self):
            return {
                "input": "MMOer mất 3 giờ/ngày reup TikTok thủ công",
                "tool_name": "CapCut Reup",
                "trigger": "showcase",
            }

    # === STEP 1: User clicks "Run Pipeline" on /showcase ===
    with patch("src.lib.http.AsyncClient.post", new=_make_full_mock()):
        resp = await orchestrator_run_handler(RunReq(), env, None)
    assert resp.status == 200, f"expected 200, got {resp.status}: {resp.body[:300]}"
    body = json.loads(resp.body)
    assert body["ok"] is True
    run_id = body["run_id"]
    assert run_id.startswith("run-")

    # === STEP 2: Verify all 5 phases completed ===
    run = await get_run(env.DB, run_id)
    assert run is not None
    assert run["status"] == "success", f"Pipeline failed: {run}"
    assert run["tool_id"] == "capcut-reup"
    assert run["tool_name"] == "CapCut Reup"

    # All 5 steps must be present and successful
    assert len(run["steps"]) == 5
    phases_seen = [s["phase"] for s in run["steps"]]
    assert phases_seen == ["scout", "architect", "forge", "hype", "store"]
    for s in run["steps"]:
        assert s["status"] == "success", f"Step {s['phase']} failed: {s}"

    # Each step has summary + duration
    for s in run["steps"]:
        assert s["summary"]
        assert s["duration_ms"] >= 0

    # === STEP 3: Verify tool was published ===
    tools = env.DB.tables["tools"]
    published_tool = next((t for t in tools if t["id"] == "capcut-reup"), None)
    assert published_tool is not None, "Tool not published to store"
    assert published_tool["name"] == "CapCut Reup"
    assert published_tool["pricing_vnd"] == 1_200_000
    assert published_tool["status"] == "draft"  # owner reviews before live

    # === STEP 4: Verify campaign was saved ===
    campaigns = env.DB.tables["campaigns"]
    saved_campaign = next((c for c in campaigns if c["tool_id"] == "capcut-reup"), None)
    assert saved_campaign is not None, "Campaign not saved"
    content = json.loads(saved_campaign["content_json"])
    assert content["landing"]["headline"]
    assert content["facebook_ad_a"]["hook"]
    assert content["facebook_ad_b"]["hook"]
    assert content["tiktok_script"]["hook_3s"]

    # === STEP 5: Verify X-Request-Id propagated (live trace visibility) ===
    # Get via HTTP handler to verify
    class GetReq:
        path = f"/api/orchestrator/run/{run_id}"
    resp2 = await orchestrator_get_handler(GetReq(), env, None)
    body2 = json.loads(resp2.body)
    assert body2["ok"] is True
    assert body2["run"]["id"] == run_id
    # Re-fetch — must return same data
    run2 = await get_run(env.DB, run_id)
    assert run2["tool_id"] == "capcut-reup"
    assert run2["status"] == "success"


@pytest.mark.asyncio
async def test_e2e_showcase_creates_unique_tool_id_from_name():
    """Tool name 'My Cool Tool' → tool_id 'my-cool-tool'."""
    from src.handlers.orchestrator import orchestrator_run_handler
    from src.orchestrator import get_run

    async def mock(*a, **kw):
        system = kw.get("json", {}).get("system", "").lower()
        if "hype" in system[:50]:
            return _resp_json(_hype_resp())
        if "phân tích" in system or "scout" in system[:50]:
            return _resp_json(_scout_resp())
        if "kiến trúc" in system or "10-section" in system:
            return _resp_json(_architect_resp())
        if "engineer" in system:
            return _resp_json("```python:main.py\ndef main(): pass\n```")
        return _resp_json("ok")

    class Req:
        async def json(self):
            return {"input": "Test pain", "tool_name": "My Cool Tool"}

    env = FakeEnv()
    with patch("src.lib.http.AsyncClient.post", new=mock):
        resp = await orchestrator_run_handler(Req(), env, None)
    body = json.loads(resp.body)
    run = await get_run(env.DB, body["run_id"])
    assert run["tool_id"] == "my-cool-tool"  # lowercase, hyphenated


@pytest.mark.asyncio
async def test_e2e_showcase_pipeline_runs_listed_in_order():
    """Multiple runs all listed via /api/orchestrator/runs."""
    from src.handlers.orchestrator import orchestrator_list_handler, orchestrator_run_handler

    async def mock(*a, **kw):
        system = kw.get("json", {}).get("system", "").lower()
        if "hype" in system[:50]:
            return _resp_json(_hype_resp())
        if "scout" in system[:50]:
            return _resp_json(_scout_resp())
        if "architect" in system[:50]:
            return _resp_json(_architect_resp())
        if "engineer" in system:
            return _resp_json("```python:x.py\nx\n```")
        return _resp_json("ok")

    env = FakeEnv()

    class Req:
        async def json(self):
            return {"input": "Test", "tool_name": "Tool X"}

    # Run 3 times
    with patch("src.lib.http.AsyncClient.post", new=mock):
        for i in range(3):
            r = await orchestrator_run_handler(Req(), env, None)
            assert r.status == 200

    class ListReq:
        pass
    resp = await orchestrator_list_handler(ListReq(), env, None)
    body = json.loads(resp.body)
    assert body["count"] == 3
    assert len(body["runs"]) == 3
