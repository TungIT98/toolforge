"""Tests for Architect spec generator (mocked LLM)."""
from unittest.mock import AsyncMock, patch

import pytest

from src.architect.spec_generator import (
    _extract_effort_hours,
    _parse_sections,
    generate_spec,
    validate_spec,
)
from src.llm import LLMClient


SAMPLE_SPEC = """## 1. Problem statement
- Pain: Reup TikTok tốn time
- User: MMO reup
- Why now: 2026

## 2. User flow
- Step 1: open tool
- Step 2: paste video URL

## 3. Features (MVP scope)
### Must-have (P0)
- Download video
- Edit watermark
### Nice-to-have (P1)
- Batch mode
### Out of scope
- Live streaming

## 4. Technical architecture
- Stack: Tauri 2.x
- Frontend: React

## 5. Data model
- Table: jobs

## 6. API contract
- POST /api/jobs

## 7. UI/UX wireframe
- Main window

## 8. Test plan
- 10 manual test cases

## 9. Effort estimate
- Forge build time: 16 giờ
- Risk: thấp

## 10. Rollout plan
- Phase 1: internal
"""


@pytest.mark.asyncio
async def test_generate_spec_success():
    """LLM returns valid spec → parsed + sections extracted."""
    fake_response = {
        "text": SAMPLE_SPEC,
        "usage": {"input_tokens": 500, "output_tokens": 2000},
        "model": "minimax/MiniMax-M3",
        "latency_ms": 5000,
    }

    pain_point = {
        "title": "Reup TikTok tốn time",
        "description": "MMO mất 2-3h/ngày",
        "audience": "MMO reup",
        "severity": 9,
        "market_size_vn": "100K+",
    }

    with patch.object(LLMClient, "call", new=AsyncMock(return_value=fake_response)):
        client = LLMClient(api_key="test", agent_name="test")
        result = await generate_spec(pain_point, client)

    assert "spec_markdown" in result
    assert "sections" in result
    assert len(result["sections"]) == 10
    assert result["effort_estimate_hours"] == 16.0
    assert "problem_statement" in result["sections"]
    assert "rollout_plan" in result["sections"]


@pytest.mark.asyncio
async def test_generate_spec_no_10_sections_returns_empty_parse():
    """LLM returns incomplete spec → sections empty for missing."""
    incomplete = "## 1. Problem statement\nSome text only."
    fake_response = {
        "text": incomplete,
        "usage": {"input_tokens": 100, "output_tokens": 50},
        "model": "minimax/MiniMax-M3",
        "latency_ms": 100,
    }

    with patch.object(LLMClient, "call", new=AsyncMock(return_value=fake_response)):
        client = LLMClient(api_key="test", agent_name="test")
        result = await generate_spec({"title": "x"}, client)

    assert len(result["sections"]) == 1  # only section 1 parsed


# === _parse_sections tests ===

def test_parse_sections_full_spec():
    sections = _parse_sections(SAMPLE_SPEC)
    assert len(sections) == 10
    assert "MMO reup" in sections["problem_statement"]
    assert "Tauri" in sections["technical_architecture"]


def test_parse_sections_handles_extra_spaces():
    md = "##  1.  Problem statement\nX\n## 2. User flow\nY"
    sections = _parse_sections(md)
    assert "problem_statement" in sections
    assert "user_flow" in sections


def test_parse_sections_empty():
    sections = _parse_sections("No headers here")
    assert sections == {}


# === _extract_effort_hours tests ===

def test_extract_effort_hours_giờ():
    assert _extract_effort_hours("Effort: 8 giờ") == 8.0
    assert _extract_effort_hours("Effort: 16 hours") == 16.0


def test_extract_effort_hours_ngày():
    assert _extract_effort_hours("Effort: 2 ngày") == 16.0
    assert _extract_effort_hours("Effort: 1 day") == 8.0


def test_extract_effort_hours_none_when_missing():
    assert _extract_effort_hours("No effort mentioned") is None


def test_extract_effort_hours_decimal():
    assert _extract_effort_hours("Effort: 2.5 giờ") == 2.5


# === validate_spec tests ===

def test_validate_spec_complete_passes():
    spec = {
        "sections": {
            "problem_statement": "x", "user_flow": "x", "features_mvp": "x",
            "technical_architecture": "x", "data_model": "x", "api_contract": "x",
            "ui_ux_wireframe": "x", "test_plan": "x", "effort_estimate": "x",
            "rollout_plan": "x",
        }
    }
    is_valid, issues = validate_spec(spec)
    assert is_valid
    assert issues == []


def test_validate_spec_missing_sections():
    spec = {"sections": {"problem_statement": "x"}}
    is_valid, issues = validate_spec(spec)
    assert not is_valid
    assert len(issues) == 9
    assert any("user_flow" in i for i in issues)


def test_validate_spec_stub_sections_flagged():
    spec = {
        "sections": {
            "problem_statement": "N/A",
            "user_flow": "x",
            "features_mvp": "N/A vì ...",
            "technical_architecture": "x",
            "data_model": "x", "api_contract": "x",
            "ui_ux_wireframe": "x", "test_plan": "x",
            "effort_estimate": "x", "rollout_plan": "x",
        }
    }
    is_valid, issues = validate_spec(spec)
    assert not is_valid
    assert len(issues) == 2
