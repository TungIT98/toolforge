"""Tests for Store catalog + admin + seed."""
import pytest

from tests.test_e2e import FakeD1, FakeEnv
from src.store.admin import add_tool, update_tool
from src.store.catalog import (
    ALLOWED_NICHES,
    ALLOWED_SORT,
    ALLOWED_STATUSES,
    get_catalog_stats,
    get_tool_detail,
    get_tools,
)
from src.store.seed import SEED_TOOLS, seed_to_d1


@pytest.fixture
def fake_db():
    """Fresh FakeD1 per test."""
    return FakeD1()


# === seed tests ===

@pytest.mark.asyncio
async def test_seed_inserts_all_tools(fake_db):
    result = await seed_to_d1(fake_db)
    assert result["inserted"] == len(SEED_TOOLS)
    assert result["skipped"] == 0
    assert len(fake_db.tables["tools"]) == len(SEED_TOOLS)


@pytest.mark.asyncio
async def test_seed_idempotent_skips_existing(fake_db):
    result1 = await seed_to_d1(fake_db)
    assert result1["inserted"] == len(SEED_TOOLS)
    result2 = await seed_to_d1(fake_db)
    assert result2["inserted"] == 0
    assert result2["skipped"] == len(SEED_TOOLS)


@pytest.mark.asyncio
async def test_seed_tools_have_required_fields(fake_db):
    await seed_to_d1(fake_db)
    for tool in fake_db.tables["tools"]:
        assert tool["id"]
        assert tool["name"]
        assert tool["description"]
        assert tool["niche"] in ALLOWED_NICHES
        assert tool["status"] in ALLOWED_STATUSES
        assert tool["pricing_vnd"] >= 0
        assert tool["license_required"] in (0, 1)


@pytest.mark.asyncio
async def test_seed_includes_free_and_paid(fake_db):
    await seed_to_d1(fake_db)
    has_free = any(t["pricing_vnd"] == 0 for t in fake_db.tables["tools"])
    has_paid = any(t["pricing_vnd"] > 0 for t in fake_db.tables["tools"])
    assert has_free
    assert has_paid


# === catalog tests ===

@pytest.mark.asyncio
async def test_get_tools_returns_all(fake_db):
    await seed_to_d1(fake_db)
    tools = await get_tools(fake_db)
    assert len(tools) == len(SEED_TOOLS)


@pytest.mark.asyncio
async def test_get_tools_filter_by_niche(fake_db):
    await seed_to_d1(fake_db)
    tools = await get_tools(fake_db, niche="mmo_reup")
    assert all(t["niche"] == "mmo_reup" for t in tools)
    assert len(tools) >= 1


@pytest.mark.asyncio
async def test_get_tools_filter_by_status(fake_db):
    await seed_to_d1(fake_db)
    tools = await get_tools(fake_db, status="live")
    assert all(t["status"] == "live" for t in tools)


@pytest.mark.asyncio
async def test_get_tools_invalid_niche_returns_all(fake_db):
    """Invalid niche (not in whitelist) → silently ignored → all tools."""
    await seed_to_d1(fake_db)
    tools = await get_tools(fake_db, niche="invalid_niche")
    assert len(tools) == len(SEED_TOOLS)


@pytest.mark.asyncio
async def test_get_tools_search(fake_db):
    await seed_to_d1(fake_db)
    tools = await get_tools(fake_db, q="capcut")
    assert len(tools) >= 1
    for t in tools:
        assert "capcut" in (t["name"] + t["description"]).lower()


@pytest.mark.asyncio
async def test_get_tools_pagination(fake_db):
    await seed_to_d1(fake_db)
    tools = await get_tools(fake_db, limit=2, offset=0)
    assert len(tools) == 2
    tools2 = await get_tools(fake_db, limit=2, offset=2)
    assert len(tools2) == 2
    # Different tools
    assert tools[0]["id"] != tools2[0]["id"]


@pytest.mark.asyncio
async def test_get_tools_sort_by_name(fake_db):
    await seed_to_d1(fake_db)
    tools = await get_tools(fake_db, sort="name", order="ASC")
    names = [t["name"] for t in tools]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_get_tools_invalid_sort_falls_back_to_default(fake_db):
    await seed_to_d1(fake_db)
    tools = await get_tools(fake_db, sort="injection_attempt")
    assert len(tools) == len(SEED_TOOLS)


@pytest.mark.asyncio
async def test_get_tool_detail_found(fake_db):
    await seed_to_d1(fake_db)
    tool = await get_tool_detail(fake_db, "capcut-desktop-reup")
    assert tool is not None
    assert tool["id"] == "capcut-desktop-reup"
    assert "latest_build" in tool
    assert "active_license_count" in tool


@pytest.mark.asyncio
async def test_get_tool_detail_not_found(fake_db):
    await seed_to_d1(fake_db)
    tool = await get_tool_detail(fake_db, "ghost-xxx")
    assert tool is None


@pytest.mark.asyncio
async def test_get_tool_detail_invalid_id(fake_db):
    assert await get_tool_detail(fake_db, "") is None
    assert await get_tool_detail(fake_db, None) is None


@pytest.mark.asyncio
async def test_get_catalog_stats(fake_db):
    await seed_to_d1(fake_db)
    stats = await get_catalog_stats(fake_db)
    assert stats["total_tools"] == len(SEED_TOOLS)
    assert "mmo_reup" in stats["by_niche"]
    assert "content_creator" in stats["by_niche"]
    assert "productivity" in stats["by_niche"]
    assert stats["free_tools"] >= 1
    assert stats["paid_tools"] >= 1


# === admin tests ===

@pytest.mark.asyncio
async def test_add_tool_success(fake_db):
    tool = {
        "id": "new-tool",
        "name": "Test Tool",
        "description": "Test description",
        "niche": "productivity",
        "pricing_vnd": 500_000,
        "license_required": True,
        "tags": ["test", "demo"],
    }
    result = await add_tool(fake_db, tool)
    assert result["ok"]
    assert result["tool_id"] == "new-tool"
    assert any(t["id"] == "new-tool" for t in fake_db.tables["tools"])


@pytest.mark.asyncio
async def test_add_tool_missing_field(fake_db):
    tool = {"id": "x", "name": "X"}  # missing description, niche
    result = await add_tool(fake_db, tool)
    assert not result["ok"]
    assert result["code"] == "MISSING_FIELD"


@pytest.mark.asyncio
async def test_add_tool_invalid_niche(fake_db):
    tool = {
        "id": "x", "name": "X", "description": "Y",
        "niche": "invalid_niche",
    }
    result = await add_tool(fake_db, tool)
    assert not result["ok"]
    assert result["code"] == "INVALID_NICHE"


@pytest.mark.asyncio
async def test_add_tool_invalid_status(fake_db):
    tool = {
        "id": "x", "name": "X", "description": "Y",
        "niche": "mmo_reup",
        "status": "weird_status",
    }
    result = await add_tool(fake_db, tool)
    assert not result["ok"]
    assert result["code"] == "INVALID_STATUS"


@pytest.mark.asyncio
async def test_add_tool_negative_price(fake_db):
    tool = {
        "id": "x", "name": "X", "description": "Y",
        "niche": "mmo_reup",
        "pricing_vnd": -1000,
    }
    result = await add_tool(fake_db, tool)
    assert not result["ok"]
    assert result["code"] == "INVALID_PRICE"


@pytest.mark.asyncio
async def test_update_tool_success(fake_db):
    await seed_to_d1(fake_db)
    result = await update_tool(fake_db, "capcut-desktop-reup", {
        "pricing_vnd": 1_500_000,
        "description": "Updated description",
    })
    assert result["ok"]
    tool = next(t for t in fake_db.tables["tools"] if t["id"] == "capcut-desktop-reup")
    assert tool["pricing_vnd"] == 1_500_000
    assert tool["description"] == "Updated description"


@pytest.mark.asyncio
async def test_update_tool_filters_invalid_fields(fake_db):
    """Fields not in whitelist (like 'id') are silently ignored."""
    await seed_to_d1(fake_db)
    result = await update_tool(fake_db, "capcut-desktop-reup", {
        "id": "hacker",  # invalid field, should be ignored
        "pricing_vnd": 1_500_000,  # valid
    })
    assert result["ok"]
    # ID should NOT change
    assert any(t["id"] == "capcut-desktop-reup" for t in fake_db.tables["tools"])
    assert not any(t["id"] == "hacker" for t in fake_db.tables["tools"])


@pytest.mark.asyncio
async def test_update_tool_no_valid_fields(fake_db):
    await seed_to_d1(fake_db)
    result = await update_tool(fake_db, "capcut-desktop-reup", {
        "hacker_field_1": 1,
        "hacker_field_2": 2,
    })
    assert not result["ok"]
    assert result["code"] == "NO_FIELDS"


# === constants tests ===

def test_allowed_niches_completeness():
    assert "mmo_reup" in ALLOWED_NICHES
    assert "content_creator" in ALLOWED_NICHES
    assert "productivity" in ALLOWED_NICHES
    assert len(ALLOWED_NICHES) == 3


def test_allowed_statuses_completeness():
    assert "draft" in ALLOWED_STATUSES
    assert "approved" in ALLOWED_STATUSES
    assert "live" in ALLOWED_STATUSES
    assert "deprecated" in ALLOWED_STATUSES
    assert len(ALLOWED_STATUSES) == 4


def test_allowed_sort_columns():
    assert "created_at" in ALLOWED_SORT
    assert "name" in ALLOWED_SORT
    assert "pricing_vnd" in ALLOWED_SORT
