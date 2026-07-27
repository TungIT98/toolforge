"""Tests for Scout writer + analyzer (mocked LLM)."""
import json
from unittest.mock import AsyncMock, patch

import pytest

from src.scout.analyzer import analyze_to_pain_points, select_top_3_critical
from src.scout.sources import parse_manual_input
from src.scout.writer import format_brief_markdown, format_top_pain_json


# === sources tests ===

def test_parse_manual_input_valid():
    data = {
        "google_trends": [{"title": "x", "url": "y", "content": "z"}],
        "competitor_1touch": [],
        "mmo_forums": [],
        "creator_buzz": [],
        "unknown_field": "ignored",
    }
    out = parse_manual_input(data)
    assert "unknown_field" not in out
    assert len(out["google_trends"]) == 1


def test_parse_manual_input_empty():
    out = parse_manual_input({})
    assert out == {}


def test_parse_manual_input_filters_non_list():
    data = {"google_trends": "not a list"}
    out = parse_manual_input(data)
    assert "google_trends" not in out


# === analyzer tests ===

def _make_fake_pain_points():
    return [
        {
            "title": "Reup TikTok tốn time",
            "description": "MMO-er mất 2-3h/ngày reup",
            "audience": "MMO reup",
            "severity": 9,
            "market_size_vn": "100K+",
            "current_solutions": "Tự làm",
            "gap": "Tool Việt kém",
            "opportunity": "M",
            "estimated_monthly_revenue_vnd": 50000000,
            "source_signals": ["url1"],
            "avoid": False,
        },
        {
            "title": "Voice clone đắt",
            "description": "Tool nước ngoài $20+/mo",
            "audience": "Content creator",
            "severity": 7,
            "market_size_vn": "10K",
            "current_solutions": "ElevenLabs",
            "gap": "Giá cao, Việt hóa kém",
            "opportunity": "M",
            "estimated_monthly_revenue_vnd": 30000000,
            "source_signals": ["url2"],
            "avoid": False,
        },
        {
            "title": "Tool này vi phạm TOS",
            "description": "spam",
            "audience": "bad",
            "severity": 10,
            "market_size_vn": "1M",
            "current_solutions": "x",
            "gap": "x",
            "opportunity": "S",
            "estimated_monthly_revenue_vnd": 100,
            "source_signals": ["url3"],
            "avoid": True,  # should be filtered
        },
    ]


@pytest.mark.asyncio
async def test_analyze_to_pain_points_parses_valid_json():
    """LLM returns valid JSON array → parsed correctly."""
    from src.llm import LLMClient

    fake_response = {
        "text": json.dumps(_make_fake_pain_points()),
        "usage": {"input_tokens": 100, "output_tokens": 200},
        "model": "minimax/MiniMax-M3",
        "latency_ms": 1000,
    }

    with patch.object(LLMClient, "call", new=AsyncMock(return_value=fake_response)):
        client = LLMClient(api_key="test", agent_name="test")
        raw_data = {"mmo_forums": [{"title": "x", "url": "y", "content": "z"}]}
        result = await analyze_to_pain_points(raw_data, client, max_pain_points=10)

    # 3 input → 2 valid (avoid=True filtered)
    assert len(result) == 2
    # Sorted by severity DESC
    assert result[0]["severity"] == 9
    assert result[1]["severity"] == 7


@pytest.mark.asyncio
async def test_analyze_to_pain_points_handles_markdown_fence():
    """LLM returns ```json ... ``` → should strip fence."""
    from src.llm import LLMClient

    pps = _make_fake_pain_points()
    fake_response = {
        "text": f"```json\n{json.dumps(pps)}\n```",
        "usage": {"input_tokens": 100, "output_tokens": 200},
        "model": "minimax/MiniMax-M3",
        "latency_ms": 1000,
    }

    with patch.object(LLMClient, "call", new=AsyncMock(return_value=fake_response)):
        client = LLMClient(api_key="test", agent_name="test")
        raw_data = {"creator_buzz": [{"title": "a", "url": "b", "content": "c"}]}
        result = await analyze_to_pain_points(raw_data, client)

    assert len(result) == 2


@pytest.mark.asyncio
async def test_analyze_to_pain_points_invalid_json_returns_empty():
    """LLM returns garbage → empty list, no crash."""
    from src.llm import LLMClient

    fake_response = {
        "text": "this is not JSON, sorry",
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "model": "minimax/MiniMax-M3",
        "latency_ms": 0,
    }

    with patch.object(LLMClient, "call", new=AsyncMock(return_value=fake_response)):
        client = LLMClient(api_key="test", agent_name="test")
        raw_data = {"mmo_forums": [{"title": "x"}]}
        result = await analyze_to_pain_points(raw_data, client)

    assert result == []


@pytest.mark.asyncio
async def test_analyze_to_pain_points_empty_data_returns_empty():
    """No raw data → empty list, LLM not called."""
    from src.llm import LLMClient

    with patch.object(LLMClient, "call", new=AsyncMock()) as mock_call:
        client = LLMClient(api_key="test", agent_name="test")
        result = await analyze_to_pain_points({}, client)
        mock_call.assert_not_called()

    assert result == []


# === select_top_3 tests ===

def test_select_top_3_critical_picks_severity_7plus():
    pps = _make_fake_pain_points()
    top3 = select_top_3_critical(pps)
    # After filtering avoid=True, we have 2 left: severity 9 and 7
    assert len(top3) == 2
    assert all(pp["severity"] >= 7 for pp in top3)


def test_select_top_3_critical_fills_with_5plus_if_needed():
    pps = [
        {"title": "a", "severity": 8, "audience": "x"},
        {"title": "b", "severity": 6, "audience": "x"},
        {"title": "c", "severity": 5, "audience": "x"},
        {"title": "d", "severity": 4, "audience": "x"},
        {"title": "e", "severity": 3, "audience": "x"},
    ]
    top3 = select_top_3_critical(pps)
    assert len(top3) == 3
    severities = sorted([pp["severity"] for pp in top3], reverse=True)
    assert severities == [8, 6, 5]


# === writer tests ===

def test_format_brief_markdown_contains_sections():
    pps = _make_fake_pain_points()
    md = format_brief_markdown(
        date_str="2026-07-27",
        pain_points=pps,
        raw_data_summary={"mmo_forums": 5, "creator_buzz": 3},
    )
    assert "# Scout Brief — 2026-07-27" in md
    assert "Top 3 — Critical" in md
    assert "Reup TikTok tốn time" in md
    assert "Source coverage" in md
    assert "mmo_forums | 5" in md
    assert "Recommendation" in md


def test_format_brief_markdown_handles_empty_pain_points():
    md = format_brief_markdown(
        date_str="2026-07-27",
        pain_points=[],
        raw_data_summary={"mmo_forums": 0},
    )
    assert "Top 3 — Critical" in md
    assert "không có pain point" in md.lower() or "no pain" in md.lower()


def test_format_top_pain_json_compact():
    pps = _make_fake_pain_points()
    out = format_top_pain_json(pps)
    parsed = json.loads(out)
    assert isinstance(parsed, list)
    # Only compact fields, no "description" / "gap"
    if parsed:
        first = parsed[0]
        assert "title" in first
        assert "description" not in first
