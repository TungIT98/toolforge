"""Scout sources — fetch raw data from MMO/creator community channels.

P1 implementation strategy:
- Use Tavily API (https://tavily.com) for web_search — free 1000 calls/month
- Fallback to manual input (owner pastes comments/posts) if no Tavily key
- Sources covered:
  1. Google Trends (search query)
  2. aff.1touch.pro catalog (1Touch Pro competitors)
  3. 1touch.pro catalog (design resources)
  4. MMO forums (Voz, TinhTe, Reddit r/MMO_vietnam)
  5. TikTok/YouTube creator channels (via web search)
  6. Facebook groups (public posts via web search)
  7. Telegram public channels (via web search)
  8. SEO competitor research

P2+: integrate Apify / Bright Data for deeper scraping.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from src.lib.log import get_logger

log = get_logger("scout.sources")

TAVILY_BASE_URL = "https://api.tavily.com/search"
DEFAULT_TIMEOUT_S = 20


# === Search queries for each source ===
# These are the queries Scout runs daily. Tune for quality vs cost.
SOURCE_QUERIES: dict[str, list[str]] = {
    "google_trends": [
        "MMO Việt Nam 2026",
        "TikTok reup tool Việt",
        "voice clone tiếng Việt",
        "content creator AI tool Việt Nam",
    ],
    "mmo_forums": [
        "tool MMO Việt 2026 site:voz.vn",
        "tool reup TikTok tốt nhất site:tinh te.com",
        "MMO earn money Vietnam site:reddit.com",
        "phần mềm làm content TikTok site:voz.vn",
    ],
    "tiktok_creators": [
        "tool edit video TikTok hay nhất 2026",
        "phần mềm reup TikTok Việt",
        "voice clone tiếng Việt offline",
        "capcut auto project Việt Nam",
    ],
    "youtube_creators": [
        "best MMO tools Vietnam 2026",
        "tự động reup phim hay nhất",
        "voice cloning vietnamese free",
        "bulk upload youtube tool",
    ],
    "facebook_groups": [
        "MMO Việt Nam group facebook",
        "kiếm tiền online TikTok group",
        "content creator tools group việt",
    ],
    "competitor_intel": [
        "1touch pro aff store",
        "Nguyễn Thái aff.1touch.pro",
        "phần mềm MMO nào tốt 2026",
        "tool creator việt nam giá rẻ",
    ],
}


async def _tavily_search(
    api_key: str,
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
) -> list[dict[str, Any]]:
    """Make 1 Tavily search call. Returns list of result dicts.

    Each result: {title, url, content, score, raw_content (optional)}
    """
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,  # "basic" (cheap) | "advanced" (expensive)
        "include_answer": False,
        "include_raw_content": False,
    }
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_S) as client:
            resp = await client.post(TAVILY_BASE_URL, json=payload)
        if resp.status_code != 200:
            log.warn("tavily_non_200", err=f"status {resp.status_code}", body=resp.text[:200])
            return []
        data = resp.json()
        return data.get("results", [])
    except Exception as e:
        log.warn("tavily_failed", err=str(e), query=query[:60])
        return []


async def fetch_google_trends(api_key: str | None) -> list[dict[str, Any]]:
    """Search Google Trends data for MMO/creator keywords."""
    if not api_key:
        return []
    log.info("fetch_google_trends_start", queries=len(SOURCE_QUERIES["google_trends"]))
    results = []
    for q in SOURCE_QUERIES["google_trends"]:
        hits = await _tavily_search(api_key, f"Google Trends search interest: {q}", max_results=3)
        for h in hits:
            results.append({**h, "source": "google_trends", "query": q})
    log.info("fetch_google_trends_done", hits=len(results))
    return results


async def fetch_competitor_1touch(api_key: str | None) -> list[dict[str, Any]]:
    """Fetch aff.1touch.pro + 1touch.pro catalogs for competitor intel."""
    if not api_key:
        return []
    log.info("fetch_competitor_1touch_start")
    results = []
    # 1Touch Pro product list (from earlier research, ~20+ products)
    catalog_query = (
        "site:aff.1touch.pro phần mềm MMO creator"
    )
    hits = await _tavily_search(api_key, catalog_query, max_results=10, search_depth="advanced")
    for h in hits:
        results.append({**h, "source": "1touch_pro", "category": "competitor_catalog"})
    log.info("fetch_competitor_1touch_done", hits=len(results))
    return results


async def fetch_mmo_forums(api_key: str | None) -> list[dict[str, Any]]:
    """Fetch recent MMO/creator forum posts (Voz, TinhTe, Reddit)."""
    if not api_key:
        return []
    log.info("fetch_mmo_forums_start", queries=len(SOURCE_QUERIES["mmo_forums"]))
    results = []
    for q in SOURCE_QUERIES["mmo_forums"]:
        hits = await _tavily_search(api_key, q, max_results=5)
        for h in hits:
            results.append({**h, "source": "mmo_forum", "query": q})
    log.info("fetch_mmo_forums_done", hits=len(results))
    return results


async def fetch_creator_buzz(api_key: str | None) -> list[dict[str, Any]]:
    """Fetch TikTok/YouTube/Facebook creator complaints about tools."""
    if not api_key:
        return []
    log.info("fetch_creator_buzz_start")
    results = []
    all_queries = (
        SOURCE_QUERIES["tiktok_creators"]
        + SOURCE_QUERIES["youtube_creators"]
        + SOURCE_QUERIES["facebook_groups"]
    )
    for q in all_queries:
        hits = await _tavily_search(api_key, q, max_results=4)
        for h in hits:
            results.append({**h, "source": "creator_buzz", "query": q})
    log.info("fetch_creator_buzz_done", hits=len(results))
    return results


async def fetch_all_sources(api_key: str | None) -> dict[str, list[dict[str, Any]]]:
    """Fetch from all 4 source groups in parallel.

    Returns dict: {source_group: [hits]}
    """
    import asyncio

    log.info("fetch_all_sources_start", has_api_key=bool(api_key))
    if not api_key:
        log.warn("fetch_all_sources_no_key")
        return {
            "google_trends": [],
            "competitor_1touch": [],
            "mmo_forums": [],
            "creator_buzz": [],
        }

    results = await asyncio.gather(
        fetch_google_trends(api_key),
        fetch_competitor_1touch(api_key),
        fetch_mmo_forums(api_key),
        fetch_creator_buzz(api_key),
        return_exceptions=True,
    )
    out: dict[str, list[dict[str, Any]]] = {
        "google_trends": results[0] if not isinstance(results[0], Exception) else [],
        "competitor_1touch": results[1] if not isinstance(results[1], Exception) else [],
        "mmo_forums": results[2] if not isinstance(results[2], Exception) else [],
        "creator_buzz": results[3] if not isinstance(results[3], Exception) else [],
    }
    total = sum(len(v) for v in out.values())
    log.info("fetch_all_sources_done", total=total, by_source={k: len(v) for k, v in out.items()})
    return out


def parse_manual_input(manual_data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Parse owner-provided raw data into the same shape as fetch_all_sources().

    Owner can POST raw data to /api/scout/run when:
    - No Tavily API key
    - Wants to feed specific posts/comments
    - Wants to test with known data

    Schema:
    {
        "google_trends": [{"title": "...", "url": "...", "content": "..."}],
        "competitor_1touch": [...],
        "mmo_forums": [...],
        "creator_buzz": [...]
    }
    """
    return {
        k: v for k, v in manual_data.items()
        if k in ("google_trends", "competitor_1touch", "mmo_forums", "creator_buzz")
        and isinstance(v, list)
    }
