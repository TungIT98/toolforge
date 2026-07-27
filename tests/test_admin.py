"""Tests for Admin overview + auth."""
import pytest

from src.admin.auth import check_admin_key
from src.admin.overview import get_admin_overview
from tests.test_e2e import FakeD1, FakeEnv


def test_check_admin_key_match():
    assert check_admin_key("secret", "secret") is True


def test_check_admin_key_mismatch():
    assert check_admin_key("secret", "other") is False


def test_check_admin_key_empty():
    assert check_admin_key("", "secret") is False
    assert check_admin_key("secret", "") is False
    assert check_admin_key(None, "secret") is False


@pytest.mark.asyncio
async def test_admin_overview_empty():
    """Empty D1 returns zeros, no crash."""
    env = FakeEnv()
    overview = await get_admin_overview(env.DB)
    assert overview["tools"]["total"] == 0
    assert overview["orders"]["total"] == 0
    assert overview["licenses"]["total"] == 0


@pytest.mark.asyncio
async def test_admin_overview_with_data():
    """Populated D1 returns aggregated stats."""
    env = FakeEnv()
    # Tools
    env.DB.tables["tools"].extend([
        {"id": "t1", "name": "T1", "description": "", "niche": "mmo_reup", "status": "live",
         "build_id": None, "pricing_vnd": 1000000, "binary_url": "", "license_required": 1,
         "tags": "", "created_at": "2026-07-27", "updated_at": "2026-07-27"},
        {"id": "t2", "name": "T2", "description": "", "niche": "productivity", "status": "draft",
         "build_id": None, "pricing_vnd": 0, "binary_url": "", "license_required": 0,
         "tags": "", "created_at": "2026-07-27", "updated_at": "2026-07-27"},
    ])
    # Orders
    env.DB.tables["orders"].extend([
        {"id": "o1", "tool_id": "t1", "tool_name": "T1", "customer_email": "a@b.c",
         "amount_vnd": 1000000, "status": "paid", "created_at": "2026-07-27"},
        {"id": "o2", "tool_id": "t1", "tool_name": "T1", "customer_email": "c@d.e",
         "amount_vnd": 1000000, "status": "pending", "created_at": "2026-07-27"},
    ])
    # Licenses
    env.DB.tables["licenses"].extend([
        {"key": "AAAA-1111-BBBB-2222", "tool_id": "t1", "status": "active",
         "customer_email": "a@b.c", "created_at": "2026-07-27"},
    ])

    overview = await get_admin_overview(env.DB)
    assert overview["tools"]["total"] == 2
    assert overview["tools"]["live_count"] == 1
    assert overview["tools"]["draft_count"] == 1
    assert overview["tools"]["by_niche"]["mmo_reup"] == 1
    assert overview["tools"]["by_niche"]["productivity"] == 1

    assert overview["orders"]["total"] == 2
    assert overview["orders"]["paid_count"] == 1
    assert overview["orders"]["pending_count"] == 1
    assert overview["orders"]["total_revenue_vnd"] == 1_000_000  # 1 paid * 1M

    assert overview["licenses"]["total"] == 1
    assert overview["licenses"]["active_count"] == 1
