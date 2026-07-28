"""Tests for Hype agent — campaign generation + storage."""
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from src.lib.http import _Response as _MockResponse

from tests.test_e2e import FakeD1, FakeEnv


def _fake_campaign_json() -> str:
    return json.dumps({
        "landing": {
            "headline": "Reup TikTok không còn mất 3 giờ mỗi ngày",
            "subhead": "CapCut Desktop Reup tự động cắt, edit, đăng — chỉ 5 phút/ngày",
            "benefits": [
                "Tiết kiệm 14 giờ/tuần so với manual",
                "Đăng 20 video/ngày, không burnout",
                "Không bị TikTok flag bản quyền nhờ auto-rotate",
            ],
            "cta": "Mua ngay 1.2 triệu — free trial 3 ngày",
            "faq": [
                {"q": "Có cần biết code không?", "a": "Không. Click là chạy."},
                {"q": "Hoạt động trên Mac không?", "a": "Có, Windows + Mac."},
                {"q": "Bao lâu thì có ROI?", "a": "Trung bình 2 tuần."},
            ],
        },
        "facebook_ad_a": {
            "name": "Pain focus",
            "hook": "Anh/chị đang mất 3 giờ/ngày để reup TikTok?",
            "body": "Cắt, edit, caption, đăng — lặp đi lặp lại. Mệt mỏi. CapCut Reup tự động hóa tất cả. Anh chỉ cần click.",
            "cta": "Tải ngay — Free trial 3 ngày",
        },
        "facebook_ad_b": {
            "name": "Result focus",
            "hook": "Tool X giúp MMOer tiết kiệm 14 giờ/tuần",
            "body": "Anh Khoa: \"Tăng 3x output, vẫn ngủ đủ giấc\". Chị Linh: \"ROI sau 9 ngày\". Bạn: ???",
            "cta": "Xem demo — Tải miễn phí",
        },
        "tiktok_script": {
            "hook_3s": "POV: Bạn vừa tiết kiệm 14 giờ/tuần nhờ 1 tool",
            "body": "Demo tool chạy, edit xong 1 video trong 5 phút. Trước đây mất 30 phút.",
            "caption": "Link tải trong bio 🔥",
        },
    })


def _make_llm_response(text: str) -> _MockResponse:
    return _MockResponse(200, body_json={
        "id": "msg_test", "model": "minimax/MiniMax-M3",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 200, "output_tokens": 500},
        "stop_reason": "end_turn",
    })


def _make_env_with_llm() -> FakeEnv:
    class E(FakeEnv):
        LLM_API_KEY = "test-key"
    return E()


# === _parse_llm_json tests ===

def test_parse_llm_json_pure_json():
    from src.hype import _parse_llm_json
    raw = _fake_campaign_json()
    result = _parse_llm_json(raw)
    assert "landing" in result
    assert result["landing"]["headline"]


def test_parse_llm_json_with_markdown_fence():
    from src.hype import _parse_llm_json
    raw = "```json\n" + _fake_campaign_json() + "\n```"
    result = _parse_llm_json(raw)
    assert "landing" in result


def test_parse_llm_json_with_surrounding_text():
    from src.hype import _parse_llm_json
    raw = "Đây là campaign:\n" + _fake_campaign_json() + "\nHết."
    result = _parse_llm_json(raw)
    assert "landing" in result


def test_parse_llm_json_invalid_raises():
    from src.hype import _parse_llm_json
    with pytest.raises(ValueError):
        _parse_llm_json("No JSON here at all")


# === generate_campaign tests ===

@pytest.mark.asyncio
async def test_generate_campaign_success():
    from src.hype import generate_campaign
    spec = {
        "problem": "MMOer mất 3 giờ/ngày reup TikTok",
        "features": ["auto-cut", "auto-caption", "auto-post"],
        "platform": "Windows + Mac",
    }
    with patch("src.lib.http.AsyncClient.post", new=AsyncMock(return_value=_make_llm_response(_fake_campaign_json()))):
        result = await generate_campaign(
            _make_env_with_llm(), "CapCut Reup", spec, 1_200_000, "MMO TikTok creator"
        )
    assert result["ok"] is True
    assert "landing" in result["campaign"]
    assert "facebook_ad_a" in result["campaign"]
    assert "tiktok_script" in result["campaign"]
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_generate_campaign_no_llm_key():
    from src.hype import generate_campaign
    env = FakeEnv()
    env.LLM_API_KEY = ""  # override the FakeEnv default
    result = await generate_campaign(env, "X", {}, 1000)
    assert result["ok"] is False
    assert result["code"] == "LLM_KEY_MISSING"


@pytest.mark.asyncio
async def test_generate_campaign_handles_markdown_fence():
    """LLM sometimes wraps in ```json ... ``` — parser must handle."""
    from src.hype import generate_campaign
    raw = "```json\n" + _fake_campaign_json() + "\n```"
    spec = {"problem": "test"}
    with patch("src.lib.http.AsyncClient.post", new=AsyncMock(return_value=_make_llm_response(raw))):
        result = await generate_campaign(
            _make_env_with_llm(), "ToolX", spec, 500_000
        )
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_generate_campaign_handles_invalid_json():
    from src.hype import generate_campaign
    spec = {"problem": "test"}
    with patch("src.lib.http.AsyncClient.post", new=AsyncMock(return_value=_make_llm_response("No JSON at all"))):
        result = await generate_campaign(
            _make_env_with_llm(), "ToolX", spec, 500_000
        )
    assert result["ok"] is False
    assert result["code"] == "LLM_PARSE_FAILED"


@pytest.mark.asyncio
async def test_generate_campaign_returns_vietnamese_content():
    """Hype must generate Vietnamese content (target audience)."""
    from src.hype import generate_campaign
    spec = {"problem": "MMO cần tự động hóa"}
    with patch("src.lib.http.AsyncClient.post", new=AsyncMock(return_value=_make_llm_response(_fake_campaign_json()))):
        result = await generate_campaign(
            _make_env_with_llm(), "Test Tool", spec, 1_000_000
        )
    assert result["ok"] is True
    # Check for Vietnamese diacritics in output
    headline = result["campaign"]["landing"]["headline"]
    assert any(c in headline for c in "ăâđêôơưĂÂĐÊÔƠƯ"), f"No Vietnamese diacritics: {headline}"


# === save_campaign + get_campaign tests ===

@pytest.mark.asyncio
async def test_save_and_get_campaign():
    from src.hype import get_campaign, save_campaign
    env = _make_env_with_llm()
    campaign = {"landing": {"headline": "test"}, "facebook_ad_a": {}, "tiktok_script": {}}
    save_result = await save_campaign(env.DB, "tool-1", "Tool 1", campaign, 1_000_000)
    assert save_result["ok"] is True
    fetched = await get_campaign(env.DB, "tool-1")
    assert fetched is not None
    assert fetched["tool_id"] == "tool-1"
    assert fetched["content"]["landing"]["headline"] == "test"


@pytest.mark.asyncio
async def test_save_campaign_overwrites_existing():
    from src.hype import get_campaign, save_campaign
    env = _make_env_with_llm()
    await save_campaign(env.DB, "tool-1", "Tool 1", {"landing": {"v": 1}}, 1000)
    await save_campaign(env.DB, "tool-1", "Tool 1", {"landing": {"v": 2}}, 2000)
    fetched = await get_campaign(env.DB, "tool-1")
    assert fetched["content"]["landing"]["v"] == 2
    assert fetched["pricing_vnd"] == 2000


@pytest.mark.asyncio
async def test_get_campaign_not_found():
    from src.hype import get_campaign
    env = _make_env_with_llm()
    result = await get_campaign(env.DB, "nonexistent")
    assert result is None


# === HTTP handler tests ===

@pytest.mark.asyncio
async def test_hype_generate_handler_missing_tool_id():
    from src.handlers.hype import hype_generate_handler
    class Req:
        async def json(self):
            return {}
    resp = await hype_generate_handler(Req(), _make_env_with_llm(), None)
    assert resp.status == 400


@pytest.mark.asyncio
async def test_hype_generate_handler_success():
    from src.handlers.hype import hype_generate_handler
    class Req:
        async def json(self):
            return {
                "tool_id": "test-tool",
                "tool_name": "Test Tool",
                "pricing_vnd": 1_000_000,
                "spec": {"problem": "test"},
            }
    with patch("src.lib.http.AsyncClient.post", new=AsyncMock(return_value=_make_llm_response(_fake_campaign_json()))):
        resp = await hype_generate_handler(Req(), _make_env_with_llm(), None)
    assert resp.status == 200
    body = json.loads(resp.body)
    assert body["ok"] is True
    assert "campaign" in body
    assert body["saved"] is True


@pytest.mark.asyncio
async def test_hype_generate_handler_no_llm_key():
    from src.handlers.hype import hype_generate_handler
    class Req:
        async def json(self):
            return {"tool_id": "x"}
    env = FakeEnv()
    env.LLM_API_KEY = ""
    resp = await hype_generate_handler(Req(), env, None)
    assert resp.status == 500


@pytest.mark.asyncio
async def test_hype_list_handler():
    from src.hype import save_campaign
    from src.handlers.hype import hype_list_handler
    env = _make_env_with_llm()
    await save_campaign(env.DB, "t1", "T1", {"landing": {}}, 1000)
    class Req:
        method = "GET"
    resp = await hype_list_handler(Req(), env, None)
    body = json.loads(resp.body)
    assert body["ok"] is True
    assert body["count"] == 1


@pytest.mark.asyncio
async def test_hype_get_handler_not_found():
    from src.handlers.hype import hype_get_handler
    class Req:
        path = "/api/hype/campaign/nonexistent"
    resp = await hype_get_handler(Req(), _make_env_with_llm(), None)
    assert resp.status == 404
