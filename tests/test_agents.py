"""Tests for /agents roster page."""
import pytest

from tests.test_e2e import FakeD1, FakeEnv


@pytest.mark.asyncio
async def test_agents_returns_html():
    from src.handlers.agents import agents_handler
    class Req:
        method = "GET"
        path = "/agents"
    resp = await agents_handler(Req(), FakeEnv(), None)
    assert resp.status == 200
    assert "text/html" in resp.headers.get("Content-Type", "").lower()
    assert "ToolForge" in resp.body or "Meet the 5 Agents" in resp.body


@pytest.mark.asyncio
async def test_agents_lists_all_5_agents():
    """All 5 agents must appear in the roster."""
    from src.handlers.agents import agents_handler, AGENTS
    class Req:
        method = "GET"
        path = "/agents"
    resp = await agents_handler(Req(), FakeEnv(), None)
    body = resp.body
    # All 5 agent names + 1 helper = 6 total
    assert len(AGENTS) == 6
    for agent in AGENTS:
        assert agent["name"] in body
        assert agent["emoji"] in body


@pytest.mark.asyncio
async def test_agents_shows_quotes():
    """Each agent's personality quote must appear."""
    from src.handlers.agents import agents_handler, AGENTS
    class Req:
        method = "GET"
        path = "/agents"
    resp = await agents_handler(Req(), FakeEnv(), None)
    for agent in AGENTS:
        # Quote contains first 20 chars
        first_20 = agent["quote"][:20]
        assert first_20 in resp.body, f"Quote for {agent['name']} not found"


@pytest.mark.asyncio
async def test_agents_has_pipeline_diagram():
    """Pipeline diagram shows the 5 phases + helper."""
    from src.handlers.agents import agents_handler
    class Req:
        method = "GET"
        path = "/agents"
    resp = await agents_handler(Req(), FakeEnv(), None)
    body = resp.body
    # Pipeline order: Scout → Architect → Forge → Hype → Store → Helper
    assert "Scout" in body
    assert "Architect" in body
    assert "Forge" in body
    assert "Hype" in body
    assert "Store" in body
    assert "Helper" in body
    # Has arrows
    assert "→" in body


@pytest.mark.asyncio
async def test_agents_has_cta_to_showcase():
    """CTA links to /showcase for live demo."""
    from src.handlers.agents import agents_handler
    class Req:
        method = "GET"
        path = "/agents"
    resp = await agents_handler(Req(), FakeEnv(), None)
    body = resp.body
    assert "/showcase" in body
    assert "Run Pipeline" in body or "run pipeline" in body.lower()


@pytest.mark.asyncio
async def test_agents_credits_agency_agents_repo():
    """Footer credits the inspiration source."""
    from src.handlers.agents import agents_handler
    class Req:
        method = "GET"
        path = "/agents"
    resp = await agents_handler(Req(), FakeEnv(), None)
    assert "agency-agents" in resp.body
