"""Admin overview — aggregated stats for owner dashboard.
"""
from __future__ import annotations

from typing import Any


async def get_admin_overview(db: "object") -> dict[str, Any]:
    """Get aggregated stats for admin dashboard."""
    overview: dict[str, Any] = {
        "tools": {
            "total": 0,
            "by_niche": {},
            "by_status": {},
            "live_count": 0,
            "draft_count": 0,
        },
        "orders": {
            "total": 0,
            "pending_count": 0,
            "paid_count": 0,
            "failed_count": 0,
            "refunded_count": 0,
            "total_revenue_vnd": 0,
        },
        "licenses": {
            "total": 0,
            "active_count": 0,
            "revoked_count": 0,
            "expired_count": 0,
        },
        "pipeline": {
            "pending_specs": 0,
            "pending_handoffs": 0,
            "in_progress_builds": 0,
            "done_builds": 0,
        },
        "scout": {
            "briefs_count": 0,
            "latest_brief_date": None,
        },
        "llm": {
            "total_calls": 0,
            "total_tokens": 0,
        },
    }
    try:
        # Tools
        rows = await db.prepare(
            "SELECT niche, status, COUNT(*) AS n FROM tools GROUP BY niche, status"
        ).bind().all()
        for r in (rows or []):
            n = r.get("n", 0)
            overview["tools"]["total"] += n
            overview["tools"]["by_niche"][r.get("niche", "unknown")] = (
                overview["tools"]["by_niche"].get(r.get("niche", "unknown"), 0) + n
            )
            overview["tools"]["by_status"][r.get("status", "unknown")] = (
                overview["tools"]["by_status"].get(r.get("status", "unknown"), 0) + n
            )
            if r.get("status") == "live":
                overview["tools"]["live_count"] += n
            elif r.get("status") == "draft":
                overview["tools"]["draft_count"] += n

        # Orders
        rows = await db.prepare(
            "SELECT status, amount_vnd, COUNT(*) AS n FROM orders GROUP BY status, amount_vnd"
        ).bind().all()
        for r in (rows or []):
            n = r.get("n", 0)
            amount = r.get("amount_vnd", 0)
            overview["orders"]["total"] += n
            status = r.get("status", "unknown")
            if status == "pending":
                overview["orders"]["pending_count"] += n
            elif status == "paid":
                overview["orders"]["paid_count"] += n
                overview["orders"]["total_revenue_vnd"] += amount * n
            elif status == "failed":
                overview["orders"]["failed_count"] += n
            elif status == "refunded":
                overview["orders"]["refunded_count"] += n

        # Licenses
        rows = await db.prepare(
            "SELECT status, COUNT(*) AS n FROM licenses GROUP BY status"
        ).bind().all()
        for r in (rows or []):
            n = r.get("n", 0)
            overview["licenses"]["total"] += n
            status = r.get("status", "unknown")
            if status == "active":
                overview["licenses"]["active_count"] += n
            elif status == "revoked":
                overview["licenses"]["revoked_count"] += n
            elif status == "expired":
                overview["licenses"]["expired_count"] += n

        # Pipeline
        for status_key, field in [
            ("pending_owner_review", "pending_specs"),
            ("pending", "pending_handoffs"),
            ("in_progress", "in_progress_builds"),
            ("done", "done_builds"),
        ]:
            try:
                if field in ("pending_specs", "done_builds"):
                    table = "specs" if field == "pending_specs" else "builds"
                else:
                    table = "handoff" if field == "pending_handoffs" else "handoff"
                result = await db.prepare(
                    f"SELECT COUNT(*) AS n FROM {table} WHERE status = ?"
                ).bind(status_key).first()
                if result:
                    overview["pipeline"][field] = result.get("n", 0)
            except Exception:
                pass

        # Scout briefs
        result = await db.prepare("SELECT COUNT(*) AS n FROM briefs").bind().first()
        if result:
            overview["scout"]["briefs_count"] = result.get("n", 0)
        latest = await db.prepare(
            "SELECT scout_date FROM briefs ORDER BY created_at DESC LIMIT 1"
        ).bind().first()
        if latest:
            overview["scout"]["latest_brief_date"] = latest.get("scout_date")

        # LLM usage
        result = await db.prepare(
            "SELECT COUNT(*) AS n, COALESCE(SUM(total_tokens), 0) AS tokens FROM llm_usage"
        ).bind().first()
        if result:
            overview["llm"]["total_calls"] = result.get("n", 0)
            overview["llm"]["total_tokens"] = result.get("tokens", 0)
    except Exception as e:
        overview["error"] = str(e)
    return overview
