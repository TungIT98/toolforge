"""Tests for showcase handler — returns inline HTML demo page."""
import pytest

from tests.test_e2e import FakeD1, FakeEnv


@pytest.mark.asyncio
async def test_showcase_returns_html():
    from src.handlers.showcase import showcase_handler
    class Req:
        method = "GET"
        path = "/showcase"
    resp = await showcase_handler(Req(), FakeEnv(), None)
    assert resp.status == 200
    assert "text/html" in resp.headers.get("Content-Type", "").lower()
    assert "ToolForge" in resp.body
    assert "5-Agent Pipeline" in resp.body or "5 agent" in resp.body


@pytest.mark.asyncio
async def test_showcase_html_has_run_button():
    """Page must have a Run button + polling JS."""
    from src.handlers.showcase import showcase_handler
    class Req:
        method = "GET"
        path = "/showcase"
    resp = await showcase_handler(Req(), FakeEnv(), None)
    body = resp.body
    assert "runPipeline" in body
    assert "Run Pipeline" in body or "Run" in body
    assert "orchestrator/run" in body  # API endpoint reference
    assert "phase" in body  # has phase tracking


@pytest.mark.asyncio
async def test_showcase_lists_all_5_phases():
    from src.handlers.showcase import showcase_handler
    class Req:
        method = "GET"
        path = "/showcase"
    resp = await showcase_handler(Req(), FakeEnv(), None)
    for phase in ["scout", "architect", "forge", "hype", "store"]:
        assert phase in resp.body.lower(), f"Phase {phase} not in HTML"
