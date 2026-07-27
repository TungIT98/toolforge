"""Store catalog — query tools from D1 with filters.
"""
from __future__ import annotations

from typing import Any


# Whitelist of allowed filter values (security: prevent SQL injection via enum check)
ALLOWED_NICHES = {"mmo_reup", "content_creator", "productivity"}
ALLOWED_STATUSES = {"draft", "approved", "live", "deprecated"}
ALLOWED_SORT = {"created_at", "name", "pricing_vnd"}


async def get_tools(
    db: "object",
    niche: str | None = None,
    status: str | None = None,
    q: str | None = None,
    sort: str = "created_at",
    order: str = "DESC",
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Get list of tools with filters.

    Args:
        db: D1 binding
        niche: filter by niche (mmo_reup | content_creator | productivity)
        status: filter by status (draft | approved | live | deprecated)
        q: full-text search in name + description
        sort: sort column (created_at | name | pricing_vnd)
        order: ASC | DESC
        limit: max results (1-200)
        offset: pagination offset

    Returns:
        list of tool dicts
    """
    # Whitelist validation
    if niche and niche not in ALLOWED_NICHES:
        niche = None
    if status and status not in ALLOWED_STATUSES:
        status = None
    if sort not in ALLOWED_SORT:
        sort = "created_at"
    if order.upper() not in ("ASC", "DESC"):
        order = "DESC"
    limit = max(1, min(200, int(limit)))
    offset = max(0, int(offset))

    # Build query dynamically (safe — we use bound parameters)
    where_clauses: list[str] = []
    params: list[Any] = []

    if niche:
        where_clauses.append("niche = ?")
        params.append(niche)
    if status:
        where_clauses.append("status = ?")
        params.append(status)
    if q:
        # Search in name + description (LIKE is case-insensitive in SQLite)
        where_clauses.append("(name LIKE ? OR description LIKE ?)")
        q_pattern = f"%{q}%"
        params.append(q_pattern)
        params.append(q_pattern)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # Note: sort + order cannot be bound params in SQLite; whitelisted above
    sql = (
        f"SELECT id, name, description, niche, status, pricing_vnd, binary_url, "
        f"license_required, tags, created_at, updated_at "
        f"FROM tools {where_sql} ORDER BY {sort} {order} LIMIT ? OFFSET ?"
    )
    params.extend([limit, offset])

    try:
        rows = await db.prepare(sql).bind(*params).all()
    except Exception:
        return []
    return list(rows or [])


async def get_tool_detail(db: "object", tool_id: str) -> dict[str, Any] | None:
    """Get 1 tool with extra info (build, license count).

    Returns:
        tool dict + build (latest) + license_count, or None if not found
    """
    if not tool_id or not isinstance(tool_id, str):
        return None

    tool = await db.prepare(
        "SELECT id, name, description, niche, status, build_id, pricing_vnd, binary_url, "
        "license_required, tags, created_at, updated_at "
        "FROM tools WHERE id = ?"
    ).bind(tool_id).first()
    if not tool:
        return None

    # Get latest build (if any)
    build = None
    try:
        build = await db.prepare(
            "SELECT id, version, test_result, created_at FROM builds "
            "WHERE tool_id = ? ORDER BY created_at DESC LIMIT 1"
        ).bind(tool_id).first()
    except Exception:
        pass

    # Count active licenses
    license_count = 0
    try:
        result = await db.prepare(
            "SELECT COUNT(*) AS n FROM licenses WHERE tool_id = ? AND status = 'active'"
        ).bind(tool_id).first()
        if result:
            license_count = result.get("n", 0)
    except Exception:
        pass

    return {
        **tool,
        "latest_build": build,
        "active_license_count": license_count,
    }


async def get_catalog_stats(db: "object") -> dict[str, Any]:
    """Get catalog overview stats: total tools, by niche, by status, free vs paid."""
    stats: dict[str, Any] = {
        "total_tools": 0,
        "by_niche": {},
        "by_status": {},
        "free_tools": 0,
        "paid_tools": 0,
        "total_active_licenses": 0,
        "estimated_total_revenue_vnd": 0,
    }
    try:
        # Total + by niche
        rows = await db.prepare(
            "SELECT niche, status, pricing_vnd, COUNT(*) AS n FROM tools GROUP BY niche, status, pricing_vnd"
        ).bind().all()
        for r in (rows or []):
            n = r.get("n", 0)
            stats["total_tools"] += n
            stats["by_niche"][r.get("niche", "unknown")] = stats["by_niche"].get(r.get("niche", "unknown"), 0) + n
            stats["by_status"][r.get("status", "unknown")] = stats["by_status"].get(r.get("status", "unknown"), 0) + n
            if r.get("pricing_vnd", 0) == 0:
                stats["free_tools"] += n
            else:
                stats["paid_tools"] += n
        # Active licenses
        result = await db.prepare(
            "SELECT COUNT(*) AS n FROM licenses WHERE status = 'active'"
        ).bind().first()
        if result:
            stats["total_active_licenses"] = result.get("n", 0)
        # Rough revenue estimate (paid tools * 10 estimated sales each)
        stats["estimated_total_revenue_vnd"] = stats["paid_tools"] * 10 * 500_000
    except Exception:
        pass
    return stats
