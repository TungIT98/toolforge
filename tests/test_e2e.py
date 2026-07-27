"""End-to-end test for Scout → Architect → Forge pipeline.

Mocks httpx (HTTP layer) and D1 (in-memory dict).
Verifies data flow + handoff state transitions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.forge.license import generate_license_key
from src.handlers.architect import _update_handoff_status, create_spec_from_pain_point
from src.handlers.forge import run_forge_build
from src.llm import LLMClient
from src.scout.analyzer import analyze_to_pain_points


# === In-memory D1 fake ===

class FakeD1Statement:
    def __init__(self, sql: str, db: "FakeD1"):
        self.sql = sql
        self.db = db

    def bind(self, *args):
        self.bound = args
        return self

    async def run(self):
        return await self.db._execute_write(self.sql, self.bound)

    async def first(self):
        return await self.db._execute_read(self.sql, self.bound, single=True)

    async def all(self):
        return await self.db._execute_read(self.sql, self.bound, single=False)


class FakeD1:
    """Minimal in-memory D1 stand-in."""

    def __init__(self):
        self.tables: dict[str, list[dict]] = {
            "briefs": [], "specs": [], "handoff": [], "builds": [],
            "licenses": [], "llm_usage": [], "tools": [],
            "orders": [], "payment_events": [],
        }

    def prepare(self, sql: str) -> FakeD1Statement:
        return FakeD1Statement(sql, self)

    async def _execute_write(self, sql: str, params: tuple) -> dict:
        sql_l = sql.lower().strip()
        if sql_l.startswith("insert into orders") or sql_l.startswith("insert or replace into orders"):
            try:
                cols_part = sql_l.split("(", 1)[1].split(")")[0]
                cols = [c.strip() for c in cols_part.split(",")]
            except Exception:
                cols = []
            row = {}
            for i, col in enumerate(cols):
                if i < len(params):
                    row[col] = params[i]
            row.setdefault("status", "pending")
            row.setdefault("created_at", datetime.now(timezone.utc).isoformat())
            row.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
            self.tables["orders"] = [r for r in self.tables["orders"] if r["id"] != row["id"]]
            self.tables["orders"].append(row)
        elif sql_l.startswith("update orders"):
            order_id = params[-1]
            for o in self.tables["orders"]:
                if o["id"] == order_id:
                    set_part = sql_l.split("set")[1].split("where")[0]
                    clauses = [c.strip() for c in set_part.split(",") if "=" in c]
                    param_idx = 0
                    for clause in clauses:
                        if "?" not in clause:
                            # Literal value
                            k, v = clause.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'").strip('"')
                            o[k] = v
                        else:
                            k = clause.split("=")[0].strip()
                            if param_idx < len(params) - 1:
                                o[k] = params[param_idx]
                            param_idx += 1
        elif sql_l.startswith("insert into payment_events") or sql_l.startswith("insert or replace into payment_events"):
            try:
                cols_part = sql_l.split("(", 1)[1].split(")")[0]
                cols = [c.strip() for c in cols_part.split(",")]
            except Exception:
                cols = []
            row = {}
            for i, col in enumerate(cols):
                if i < len(params):
                    row[col] = params[i]
            self.tables["payment_events"].append(row)
        elif sql_l.startswith("insert into licenses") or sql_l.startswith("insert or replace into licenses"):
            try:
                cols_part = sql_l.split("(", 1)[1].split(")")[0]
                cols = [c.strip() for c in cols_part.split(",")]
            except Exception:
                cols = []
            row = {}
            for i, col in enumerate(cols):
                if i < len(params):
                    row[col] = params[i]
            row.setdefault("status", "active")
            self.tables["licenses"] = [r for r in self.tables["licenses"] if r["key"] != row["key"]]
            self.tables["licenses"].append(row)
        elif sql_l.startswith("insert or replace into tools") or sql_l.startswith("insert into tools"):
            # Detect column order by parsing INSERT column list
            try:
                cols_part = sql_l.split("(", 1)[1].split(")")[0]
                cols = [c.strip() for c in cols_part.split(",")]
            except Exception:
                cols = []
            row = {}
            for i, col in enumerate(cols):
                if i < len(params):
                    row[col] = params[i]
            # Defaults
            row.setdefault("build_id", None)
            row.setdefault("pricing_vnd", 0)
            row.setdefault("binary_url", "")
            row.setdefault("license_required", 0)
            row.setdefault("tags", "")
            row.setdefault("created_at", datetime.now(timezone.utc).isoformat())
            row.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
            self.tables["tools"] = [r for r in self.tables["tools"] if r["id"] != row["id"]]
            self.tables["tools"].append(row)
        elif sql_l.startswith("update tools"):
            tool_id = params[-1]
            for t in self.tables["tools"]:
                if t["id"] == tool_id:
                    set_part = sql_l.split("set")[1].split("where")[0]
                    clauses = [c.strip() for c in set_part.split(",") if "=" in c]
                    param_idx = 0
                    for clause in clauses:
                        if "?" not in clause:
                            k, v = clause.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'").strip('"')
                            t[k] = v
                        else:
                            k = clause.split("=")[0].strip()
                            if param_idx < len(params) - 1:
                                t[k] = params[param_idx]
                            param_idx += 1
        elif sql_l.startswith("insert or replace into briefs"):
            row = {
                "id": params[0], "scout_date": params[1], "content": params[2],
                "top_pain_json": params[3], "severity_avg": params[4],
                "source_count": params[5], "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self.tables["briefs"] = [r for r in self.tables["briefs"] if r["id"] != row["id"]]
            self.tables["briefs"].append(row)
        elif sql_l.startswith("insert or replace into specs"):
            row = {
                "id": params[0], "tool_id": params[1], "brief_id": params[2],
                "content": params[3], "status": params[4],
                "owner_feedback": None, "effort_estimate_hours": params[5],
                "created_at": params[6], "approved_at": None,
            }
            self.tables["specs"] = [r for r in self.tables["specs"] if r["id"] != row["id"]]
            self.tables["specs"].append(row)
        elif sql_l.startswith("insert or replace into handoff"):
            row = {
                "id": params[0], "tool_id": params[1], "spec_id": params[2],
                "status": params[3], "priority": params[4],
                "owner_feedback": None, "created_at": params[5],
                "approved_at": None, "forge_handoff_at": None, "done_at": None,
            }
            self.tables["handoff"] = [r for r in self.tables["handoff"] if r["id"] != row["id"]]
            self.tables["handoff"].append(row)
        elif sql_l.startswith("insert or replace into builds"):
            row = {
                "id": params[0], "tool_id": params[1], "handoff_id": params[2],
                "version": params[3], "code_path": params[4], "test_result": params[5],
                "test_report": params[6], "effort_actual_hours": params[7],
                "size_bytes": params[8], "created_at": params[9],
            }
            self.tables["builds"] = [r for r in self.tables["builds"] if r["id"] != row["id"]]
            self.tables["builds"].append(row)
        elif sql_l.startswith("update handoff"):
            status = params[0]
            spec_id = params[-1]
            for h in self.tables["handoff"]:
                if h["spec_id"] == spec_id:
                    h["status"] = status
                    if len(params) >= 2 and params[1] is not None:
                        h["owner_feedback"] = params[1]
                    if len(params) >= 3 and params[2] is not None:
                        h["approved_at"] = params[2]
                    if len(params) >= 4 and params[3] is not None:
                        h["forge_handoff_at"] = params[3]
                    if len(params) >= 5 and params[4] is not None:
                        h["done_at"] = params[4]
        elif sql_l.startswith("update specs"):
            status = params[0]
            spec_id = params[-1]
            for s in self.tables["specs"]:
                if s["id"] == spec_id:
                    s["status"] = status
        elif sql_l.startswith("insert into llm_usage"):
            pass
        return {"ok": True}

    async def _execute_read(self, sql: str, params: tuple, single: bool) -> Any:
        import re as _re
        sql_l = sql.lower().strip()
        if "from handoff where spec_id" in sql_l:
            matches = [h for h in self.tables["handoff"] if h["spec_id"] == params[0]]
        elif "from specs where id" in sql_l:
            matches = [s for s in self.tables["specs"] if s["id"] == params[0]]
        elif "from orders" in sql_l:
            if "where id = ?" in sql_l:
                matches = [o for o in self.tables["orders"] if o["id"] == params[0]]
            elif "where status = ?" in sql_l:
                matches = [o for o in self.tables["orders"] if o.get("status") == params[0]]
            elif "where tool_id = ? and status = ?" in sql_l and "amount_vnd" in sql_l:
                matches = [
                    o for o in self.tables["orders"]
                    if o.get("tool_id") == params[0]
                    and o.get("status") == params[1]
                    and o.get("amount_vnd") == params[2]
                ]
            else:
                matches = list(self.tables["orders"])
        elif "from licenses where key" in sql_l:
            matches = [l for l in self.tables["licenses"] if l["key"] == params[0]]
        elif "from tools" in sql_l and "group by" not in sql_l:
            # Parse WHERE clauses (support AND + OR + LIKE)
            where_match = _re.search(r"where\s+(.*?)(?:\s+order by|\s+limit|$)", sql_l, _re.DOTALL)
            matches = list(self.tables["tools"])
            if where_match:
                where_expr = where_match.group(1).strip()
                # Strip outer parens if any
                if where_expr.startswith("(") and where_expr.endswith(")"):
                    where_expr = where_expr[1:-1].strip()
                # Split by OR (top-level)
                or_groups = _re.split(r"\s+or\s+", where_expr)
                # For each OR group, split by AND and collect param indices
                matched = []
                for or_group in or_groups:
                    and_clauses = [c.strip() for c in or_group.split(" and ")]
                    or_matches = list(self.tables["tools"])
                    group_matched_any = False
                    for clause in and_clauses:
                        col = None
                        right = None
                        if "=" in clause:
                            left, right = clause.split("=", 1)
                            col_expr = left.strip().strip("()").strip()
                            col_expr_l = col_expr.lower()
                            if col_expr_l.endswith(" like") or col_expr_l.endswith(" like") or " like " in col_expr_l:
                                col = col_expr_l.replace(" like", "").strip()
                            else:
                                col = col_expr
                            right = right.strip()
                        elif " like " in clause:
                            # LIKE without `=` (e.g. "name LIKE ?")
                            left, right = clause.split(" like ", 1)
                            col = left.strip().strip("()").strip()
                            right = right.strip()
                        if col is None or right != "?":
                            continue
                        where_before = where_expr.split(clause)[0]
                        q_count = where_before.count("?")
                        val = params[q_count] if q_count < len(params) else None
                        if " like " in clause:
                            if val and isinstance(val, str) and val.startswith("%") and val.endswith("%"):
                                sub = val[1:-1].lower()
                                or_matches = [m for m in or_matches if sub in (m.get(col, "") or "").lower()]
                            else:
                                or_matches = [m for m in or_matches if m.get(col) == val]
                        else:
                            or_matches = [m for m in or_matches if m.get(col) == val]
                        group_matched_any = True
                    if group_matched_any:
                        matched.extend(or_matches)
                # Deduplicate while preserving order
                seen = set()
                matches = []
                for m in matched:
                    mid = id(m)
                    if mid not in seen:
                        seen.add(mid)
                        matches.append(m)
            # ORDER BY
            order_match = _re.search(r"order by\s+(\w+)\s*(asc|desc)?", sql_l)
            if order_match:
                col = order_match.group(1)
                direction = (order_match.group(2) or "asc").lower()
                reverse = direction == "desc"
                matches = sorted(matches, key=lambda m: m.get(col) or "", reverse=reverse)
            # LIMIT
            limit_match = _re.search(r"limit\s+\?\s+offset\s+\?", sql_l)
            if limit_match:
                limit = params[-2] if len(params) >= 2 else 50
                offset = params[-1] if len(params) >= 1 else 0
                matches = matches[offset:offset + limit]
        elif "from builds" in sql_l:
            if "where tool_id = ?" in sql_l:
                matches = [b for b in self.tables["builds"] if b.get("tool_id") == params[0]]
            else:
                matches = list(self.tables["builds"])
        elif "from licenses" in sql_l:
            if "where tool_id = ?" in sql_l and "count(*)" in sql_l:
                n = sum(1 for l in self.tables["licenses"]
                       if l.get("tool_id") == params[0] and l.get("status") == "active")
                return {"n": n} if single else [{"n": n}]
            matches = list(self.tables["licenses"])
        elif "from tools group by" in sql_l:
            # Real groupby on tools table
            from collections import Counter
            groups = Counter()
            for t in self.tables["tools"]:
                key = (t.get("niche", ""), t.get("status", ""), t.get("pricing_vnd", 0))
                groups[key] += 1
            return [
                {"niche": k[0], "status": k[1], "pricing_vnd": k[2], "n": v}
                for k, v in groups.items()
            ]
        else:
            return None if single else []
        if not matches:
            return None if single else []
        if single:
            return matches[0]
        return matches


class FakeEnv:
    def __init__(self):
        self.DB = FakeD1()
        self.LLM_API_KEY = "test-key"
        self.LLM_BASE_URL = "https://api.test.example/anthropic"
        self.LLM_MODEL = "minimax/MiniMax-M3-test"
        self.TAVILY_API_KEY = ""


# === Fake HTTP responses ===

FAKE_PAIN_POINTS_JSON = """[
    {
        "title": "Reup TikTok tốn time",
        "description": "MMO mất 2-3h/ngày reup thủ công",
        "audience": "MMO reup Việt",
        "severity": 9,
        "market_size_vn": "100K+",
        "current_solutions": "Capcut thủ công",
        "gap": "Không có tool Việt tự động",
        "opportunity": "M",
        "estimated_monthly_revenue_vnd": 50000000,
        "source_signals": ["voz.vn/thread-1"],
        "avoid": false
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
        "source_signals": ["reddit.com/r/MMO_vietnam"],
        "avoid": false
    }
]"""

FAKE_SPEC_MD = """## 1. Problem statement
- Pain: Reup TikTok tốn time
- User: MMO reup Việt
- Why now: 2026

## 2. User flow
- Step 1: Paste video URL
- Step 2: Tool downloads, edits, exports

## 3. Features (MVP scope)
### Must-have (P0)
- Download TikTok video
- Auto remove watermark
- Re-encode to MP4
### Nice-to-have (P1)
- Batch mode
### Out of scope
- Live streaming

## 4. Technical architecture
- Stack: Tauri 2.x + React + yt-dlp
- Frontend: React + Vite

## 5. Data model
- Table: jobs (id, url, status, output_path, created_at)

## 6. API contract
- POST /api/jobs (start new job)

## 7. UI/UX wireframe
- Main window with URL input + status

## 8. Test plan
- 10 manual test cases

## 9. Effort estimate
- Forge build time: 16 giờ
- Risk: thấp

## 10. Rollout plan
- Phase 1: internal test
- Phase 2: beta 5 user
- Phase 3: public trên aff.toolforge.vn, giá 1.000.000 VNĐ
"""

FAKE_CODE_BLOCKS = """```python:src-tauri/src/main.py
def main():
    print("Capcut Reup Tool")
    return 0

if __name__ == "__main__":
    main()
```

```typescript:src/App.tsx
import React from 'react';

export default function App() {
    return <div>Capcut Reup</div>;
}
```

```toml:src-tauri/Cargo.toml
[package]
name = "capcut-reup"
version = "0.1.0"
```
"""


def make_fake_response(text: str) -> "httpx.Response":
    """Build a fake httpx.Response with the given text in Anthropic API format."""
    import json
    body = {
        "id": "msg_test",
        "model": "minimax/MiniMax-M3-test",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 100, "output_tokens": len(text.split())},
        "stop_reason": "end_turn",
    }
    return httpx.Response(200, json=body)


def make_fake_post_side_effect(responses: list):
    """Build side_effect function that returns responses in order."""
    iter_responses = iter(responses)
    counter = {"i": 0}

    async def fake_post(*args, **kwargs):
        counter["i"] += 1
        try:
            return next(iter_responses)
        except StopIteration:
            # If more calls than responses, return last one
            return responses[-1] if responses else make_fake_response("OK")
    return fake_post


# === Tests ===

@pytest.mark.asyncio
async def test_e2e_happy_path():
    """Full pipeline: Scout → Architect → Approve → Forge → Build."""
    env = FakeEnv()

    # Mock httpx.post to return: pain_points → spec → code
    responses = [
        make_fake_response(FAKE_PAIN_POINTS_JSON),  # Scout analyze
        make_fake_response(FAKE_SPEC_MD),            # Architect generate
        make_fake_response(FAKE_CODE_BLOCKS),         # Forge generate code
    ]
    fake_post = make_fake_post_side_effect(responses)

    with patch("httpx.AsyncClient.post", new=fake_post):
        # Step 1: Scout analyze
        client = LLMClient(api_key="test", agent_name="scout_e2e")
        raw_data = {
            "mmo_forums": [
                {"title": "t", "url": "u", "content": "MMO-er kêu ca reup TikTok tốn time"}
            ],
        }
        pain_points = await analyze_to_pain_points(raw_data, client)
        assert len(pain_points) == 2
        top1 = pain_points[0]
        assert top1["severity"] == 9
        assert top1["title"] == "Reup TikTok tốn time"

        # Step 2: Architect create spec from top pain point
        spec_result = await create_spec_from_pain_point(top1, env, category="desktop")
        assert spec_result["ok"] is True
        assert spec_result["is_valid"] is True
        spec_id = spec_result["spec_id"]
        tool_id = spec_result["tool_id"]
        assert spec_result["saved_to_d1"] is True

        # Verify D1 state
        assert len(env.DB.tables["specs"]) == 1
        assert env.DB.tables["specs"][0]["status"] == "pending_owner_review"
        assert len(env.DB.tables["handoff"]) == 1
        assert env.DB.tables["handoff"][0]["status"] == "pending"

        # Step 3: Owner approves
        approve_result = await _update_handoff_status(spec_id, "approved", "Looks good", env)
        assert approve_result["ok"] is True
        assert approve_result["ready_for_forge"] is True
        assert env.DB.tables["handoff"][0]["status"] == "approved"
        assert env.DB.tables["specs"][0]["status"] == "approved"

        # Step 4: Forge build
        build_result = await run_forge_build(spec_id, env, triggered_by="e2e_test")
        assert build_result["ok"] is True
        assert build_result["test_result"] == "pass"
        assert build_result["file_count"] >= 2
        assert "src-tauri/src/main.py" in build_result["files_preview"]
        assert build_result["saved_to_d1"] is True

        # Verify final D1 state
        assert len(env.DB.tables["builds"]) == 1
        build_record = env.DB.tables["builds"][0]
        assert build_record["tool_id"] == tool_id
        assert build_record["test_result"] == "pass"
        assert env.DB.tables["handoff"][0]["status"] == "done"


@pytest.mark.asyncio
async def test_forge_rejects_non_approved_spec():
    """Forge must reject if handoff status != 'approved'."""
    env = FakeEnv()
    env.DB.tables["specs"].append({
        "id": "spec-test-pending", "tool_id": "tool-test-pending",
        "brief_id": None, "content": "spec", "status": "pending_owner_review",
        "owner_feedback": None, "effort_estimate_hours": None,
        "created_at": "2026-07-27", "approved_at": None,
    })
    env.DB.tables["handoff"].append({
        "id": "handoff-test", "tool_id": "tool-test-pending",
        "spec_id": "spec-test-pending", "status": "pending", "priority": "medium",
        "owner_feedback": None, "created_at": "2026-07-27",
        "approved_at": None, "forge_handoff_at": None, "done_at": None,
    })

    with patch("httpx.AsyncClient.post", new=AsyncMock()):
        result = await run_forge_build("spec-test-pending", env, triggered_by="e2e_test")
    # Spec status is 'pending_owner_review' (not 'approved') → SPEC_NOT_APPROVED fires first
    assert result["ok"] is False
    assert result["code"] == "SPEC_NOT_APPROVED"


@pytest.mark.asyncio
async def test_forge_rejects_when_handoff_pending_but_spec_approved():
    """Edge case: spec is approved but handoff still pending (owner forgot to click approve on handoff)."""
    env = FakeEnv()
    env.DB.tables["specs"].append({
        "id": "spec-test-approved", "tool_id": "tool-test",
        "brief_id": None, "content": "spec", "status": "approved",
        "owner_feedback": None, "effort_estimate_hours": None,
        "created_at": "2026-07-27", "approved_at": "2026-07-27",
    })
    env.DB.tables["handoff"].append({
        "id": "handoff-test", "tool_id": "tool-test",
        "spec_id": "spec-test-approved", "status": "pending", "priority": "medium",
        "owner_feedback": None, "created_at": "2026-07-27",
        "approved_at": None, "forge_handoff_at": None, "done_at": None,
    })

    with patch("httpx.AsyncClient.post", new=AsyncMock()):
        result = await run_forge_build("spec-test-approved", env, triggered_by="e2e_test")
    assert result["ok"] is False
    assert result["code"] == "HANDOFF_NOT_APPROVED"


@pytest.mark.asyncio
async def test_forge_rejects_nonexistent_spec():
    """Forge returns clean error if spec not found."""
    env = FakeEnv()
    with patch("httpx.AsyncClient.post", new=AsyncMock()):
        result = await run_forge_build("spec-ghost-xxx", env, triggered_by="e2e_test")
    assert result["ok"] is False
    assert result["code"] == "SPEC_NOT_FOUND"


@pytest.mark.asyncio
async def test_architect_priority_by_severity():
    """High severity pain point → high priority handoff."""
    env = FakeEnv()
    with patch("httpx.AsyncClient.post", new=make_fake_post_side_effect([make_fake_response(FAKE_SPEC_MD)])):
        result = await create_spec_from_pain_point(
            {"title": "x", "severity": 9}, env, category="desktop"
        )
        assert result["ok"]
        assert env.DB.tables["handoff"][0]["priority"] == "high"

    env2 = FakeEnv()
    with patch("httpx.AsyncClient.post", new=make_fake_post_side_effect([make_fake_response(FAKE_SPEC_MD)])):
        result2 = await create_spec_from_pain_point(
            {"title": "y", "severity": 5}, env2, category="desktop"
        )
        assert result2["ok"]
        assert env2.DB.tables["handoff"][0]["priority"] == "medium"


@pytest.mark.asyncio
async def test_scout_filters_avoid_true_pain_points():
    """Pain points with avoid=true must be filtered out (TOS)."""
    env = FakeEnv()
    fake_with_avoid = """[
        {"title": "Spam tool", "severity": 10, "audience": "x", "avoid": true, "description": "spam"},
        {"title": "Reup legit", "severity": 8, "audience": "x", "avoid": false, "description": "ok"}
    ]"""
    with patch("httpx.AsyncClient.post", new=make_fake_post_side_effect([make_fake_response(fake_with_avoid)])):
        client = LLMClient(api_key="test", agent_name="scout")
        raw_data = {"mmo_forums": [{"title": "x", "url": "u", "content": "y"}]}
        pain_points = await analyze_to_pain_points(raw_data, client)
    # Only 1 valid (avoid=true filtered)
    assert len(pain_points) == 1
    assert pain_points[0]["title"] == "Reup legit"


def test_license_key_format():
    """License key format XXXX-XXXX-XXXX-XXXX with hex chars."""
    key = generate_license_key()
    parts = key.split("-")
    assert len(parts) == 4
    assert all(len(p) == 4 for p in parts)
    int(key.replace("-", ""), 16)
