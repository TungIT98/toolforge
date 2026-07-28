"""Orchestrator 🎼 — conductor for 5-agent pipeline.

The SHOWPIECE: takes 1 pain point → runs Scout + Architect + Forge + Hype + Store
sequentially, each step recorded in pipeline_steps table for live trace.

For demo: 1 command → 5 agents collaborate → 1 new tool listed in store.

Each step:
- Started_at / ended_at (for duration)
- Status: pending → running → success | failed
- Summary: 1-line human-readable
- Result preview (truncated)
- Error message (if any)

The frontend polls /api/orchestrator/run/{run_id} to show live trace.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from src.lib.log import get_logger

log = get_logger("orchestrator")

# 5 phases of the pipeline
PHASES = ["scout", "architect", "forge", "hype", "store"]


# === DB helpers ===

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


async def _create_run(db: Any, run_id: str, trigger: str, input_text: str) -> None:
    await db.prepare(
        """INSERT INTO pipeline_runs
           (id, trigger, input_text, status, current_step, started_at, total_steps)
           VALUES (?, ?, ?, ?, ?, ?, ?)"""
    ).bind(
        run_id, trigger, input_text, "running", None, _now_iso(), len(PHASES),
    ).run()


async def _update_run(
    db: Any, run_id: str, status: str, current_step: str | None = None,
    tool_id: str | None = None, tool_name: str | None = None, ended: bool = False,
) -> None:
    if ended:
        await db.prepare(
            """UPDATE pipeline_runs
               SET status = ?, current_step = ?, tool_id = ?, tool_name = ?, ended_at = ?
               WHERE id = ?"""
        ).bind(status, current_step, tool_id, tool_name, _now_iso(), run_id).run()
    else:
        await db.prepare(
            """UPDATE pipeline_runs
               SET status = ?, current_step = ?, tool_id = ?, tool_name = ?
               WHERE id = ?"""
        ).bind(status, current_step, tool_id, tool_name, run_id).run()


async def _create_step(db: Any, step_id: str, run_id: str, index: int, phase: str) -> None:
    await db.prepare(
        """INSERT INTO pipeline_steps
           (id, run_id, step_index, phase, status)
           VALUES (?, ?, ?, ?, 'pending')"""
    ).bind(step_id, run_id, index, phase).run()


async def _start_step(db: Any, step_id: str) -> None:
    await db.prepare(
        """UPDATE pipeline_steps
           SET status = 'running', started_at = ?
           WHERE id = ?"""
    ).bind(_now_iso(), step_id).run()


async def _finish_step(
    db: Any, step_id: str, status: str,
    summary: str, result: Any = None, error: str | None = None,
    duration_ms: int = 0,
) -> None:
    result_json = json.dumps(result, ensure_ascii=False, default=str)[:5000] if result else None
    await db.prepare(
        """UPDATE pipeline_steps
           SET status = ?, ended_at = ?, duration_ms = ?, summary = ?, result_json = ?, error = ?
           WHERE id = ?"""
    ).bind(status, _now_iso(), duration_ms, summary, result_json, error, step_id).run()


async def get_run(db: Any, run_id: str) -> dict | None:
    run = await db.prepare(
        "SELECT * FROM pipeline_runs WHERE id = ?"
    ).bind(run_id).first()
    if not run:
        return None
    steps = await db.prepare(
        "SELECT * FROM pipeline_steps WHERE run_id = ? ORDER BY step_index ASC"
    ).bind(run_id).all() or []
    # Parse result_json
    for s in steps:
        if s.get("result_json"):
            try:
                s["result"] = json.loads(s["result_json"])
            except Exception:
                pass
            del s["result_json"]
    run["steps"] = steps
    return run


# === Per-phase execution ===

async def _phase_scout(env: Any, input_text: str) -> dict:
    """Scout: take input as a manual source, extract top pain point.

    For demo: use the input_text as a single source, run through analyzer to
    have a consistent LLM-formatted pain point (with severity, audience, etc).
    """
    from src.llm import LLMError, get_client
    from src.scout.analyzer import analyze_to_pain_points, select_top_3_critical
    try:
        client = get_client(agent_name="scout", env=env)
    except LLMError as e:
        return {"ok": False, "error": str(e), "code": "LLM_KEY_MISSING"}

    # Build raw_data dict (analyzer expects {group: [hits]})
    raw_data = {
        "manual": [
            {"title": "User input", "url": "manual://input", "content": input_text}
        ]
    }
    pain_points = await analyze_to_pain_points(raw_data, client)
    if not pain_points:
        # Fallback: synthesize a pain point from raw input
        pain_points = [{
            "title": input_text[:60],
            "description": input_text,
            "audience": "MMO TikTok creator Việt Nam",
            "category": "mmo_reup",
            "severity": 7,
            "opportunity": "S",
        }]
    top = select_top_3_critical(pain_points) if pain_points else []
    primary = top[0] if top else pain_points[0]
    return {
        "ok": True,
        "pain": primary,
        "total_found": len(pain_points),
        "top_3_critical": [p.get("title", p.get("description", ""))[:80] for p in top],
    }


async def _phase_architect(env: Any, pain: dict) -> dict:
    """Architect: generate 10-section spec from pain point."""
    from src.architect.spec_generator import generate_spec
    from src.llm import LLMError, get_client
    try:
        client = get_client(agent_name="architect", env=env)
    except LLMError as e:
        return {"ok": False, "error": str(e), "code": "LLM_KEY_MISSING"}
    try:
        spec = await generate_spec(pain, client, category="auto")
    except LLMError as e:
        return {"ok": False, "error": str(e), "code": "SPEC_FAILED"}
    if not spec:
        return {"ok": False, "error": "Failed to generate spec", "code": "SPEC_FAILED"}
    # Normalize to have "content" key
    spec["content"] = spec.get("spec_markdown", "")
    return {
        "ok": True,
        "sections_count": len(spec.get("sections", {})),
        "content_preview": spec.get("content", "")[:300],
        "spec": spec,
    }


async def _phase_forge(env: Any, spec: dict, tool_id: str, tool_name: str) -> dict:
    """Forge: generate code from spec (no binary build for demo speed)."""
    from src.llm import LLMError, get_client
    try:
        client = get_client(agent_name="forge", env=env)
    except LLMError as e:
        return {"ok": False, "error": str(e), "code": "LLM_KEY_MISSING"}
    try:
        result = await client.call(
            system=(
                "Bạn là Forge — AI engineer. Từ spec tool, generate code Python hoàn chỉnh. "
                "Output: ```python:filename``` blocks cho mỗi file."
            ),
            user=f"Tool: {tool_name}\n\nSpec:\n{spec.get('content', '')[:3000]}\n\nGenerate code.",
            max_tokens=2500,
            temperature=0.5,
        )
    except LLMError as e:
        return {"ok": False, "error": str(e), "code": "LLM_FAILED"}
    text = result.get("text", "")
    # Quick parse: count code fences
    file_count = text.count("```python:") + text.count("```txt:")
    return {
        "ok": True,
        "file_count": file_count,
        "code_preview": text[:300],
        "llm_usage": result.get("usage", {}),
    }


async def _phase_hype(env: Any, tool_id: str, tool_name: str, spec: dict) -> dict:
    """Hype: generate marketing campaign."""
    from src.hype import generate_campaign, save_campaign
    spec_for_hype = {
        "problem": spec.get("content", "")[:500],
        "features": spec.get("sections", {}).get("features", "").split("\n")[:5] if isinstance(spec.get("sections", {}).get("features"), str) else [],
    }
    # Default pricing
    pricing = 1_200_000
    audience = "MMO TikTok creator Việt Nam"
    result = await generate_campaign(env, tool_name, spec_for_hype, pricing, audience)
    if not result["ok"]:
        return result
    # Save
    db = getattr(env, "DB", None)
    if db is not None:
        await save_campaign(db, tool_id, tool_name, result["campaign"], pricing)
    return {
        "ok": True,
        "has_landing": bool(result["campaign"].get("landing")),
        "has_fb_ad_a": bool(result["campaign"].get("facebook_ad_a")),
        "has_fb_ad_b": bool(result["campaign"].get("facebook_ad_b")),
        "has_tiktok": bool(result["campaign"].get("tiktok_script")),
        "headline": result["campaign"].get("landing", {}).get("headline", ""),
        "llm_usage": result.get("llm_usage", {}),
    }


async def _phase_store(env: Any, tool_id: str, tool_name: str, spec: dict) -> dict:
    """Store: add tool to catalog (status=draft, owner approves later)."""
    from src.store.admin import add_tool
    db = getattr(env, "DB", None)
    if db is None:
        return {"ok": False, "error": "D1 not bound", "code": "DB_NOT_BOUND"}
    # Generate tool_id from tool_name
    if not tool_id:
        tool_id = tool_name.lower().replace(" ", "-").replace("/", "-")[:30]
    tool = {
        "id": tool_id,
        "name": tool_name,
        "description": spec.get("content", "")[:200],
        "niche": "mmo_reup",
        "status": "draft",  # owner review before live
        "pricing_vnd": 1_200_000,
        "tags": "ai-generated,showcase",
    }
    result = await add_tool(db, tool)
    if not result["ok"]:
        return {"ok": False, "error": result.get("error"), "code": "STORE_FAILED"}
    return {"ok": True, "tool_id": tool_id, "tool_name": tool_name, "status": "draft"}


# === Main pipeline runner ===

async def run_pipeline(
    env: Any, input_text: str, trigger: str = "manual",
    tool_name: str | None = None,
) -> dict:
    """Run the 5-phase pipeline. Saves each step to pipeline_steps for live trace.

    Args:
        env: Worker env
        input_text: Pain point description (or starting topic)
        trigger: "manual" | "showcase" | "auto"
        tool_name: Optional override for tool name (default: derived from pain)

    Returns: {ok, run_id, status, steps: [...], final: {tool_id, tool_name}}
    """
    db = getattr(env, "DB", None)
    if db is None:
        return {"ok": False, "error": "D1 not bound", "code": "DB_NOT_BOUND"}

    run_id = f"run-{uuid.uuid4().hex[:12]}"
    await _create_run(db, run_id, trigger, input_text)
    log.info("pipeline_start", run_id=run_id, trigger=trigger, input=input_text[:100])

    # Derive initial tool name from input if not provided
    if not tool_name:
        # Take first 5 words as tool name
        tool_name = " ".join(input_text.split()[:5]).title() or "AI Tool"

    tool_id = ""
    final_status = "success"  # default; only set to "failed" if a phase fails
    steps_summary = []

    for i, phase in enumerate(PHASES):
        step_id = f"step-{uuid.uuid4().hex[:12]}"
        await _create_step(db, step_id, run_id, i, phase)
        await _start_step(db, step_id)
        t0 = time.time()
        log.info(f"phase_{phase}_start", run_id=run_id)

        result: dict = {"ok": False, "error": "phase not run"}
        try:
            if phase == "scout":
                result = await _phase_scout(env, input_text)
            elif phase == "architect":
                # Use scout result as pain
                result = await _phase_architect(env, {"description": input_text, "category": "general"})
                # Store spec for downstream phases
                if result.get("ok"):
                    spec = result.get("spec", {})
            elif phase == "forge":
                result = await _phase_forge(env, spec, tool_id, tool_name)
            elif phase == "hype":
                result = await _phase_hype(env, tool_id, tool_name, spec)
            elif phase == "store":
                result = await _phase_store(env, tool_id, tool_name, spec)
                if result.get("ok"):
                    tool_id = result.get("tool_id", tool_id)
        except Exception as e:
            result = {"ok": False, "error": str(e), "code": "PHASE_EXCEPTION"}
            log.error(f"phase_{phase}_exception", err=str(e), run_id=run_id)

        duration_ms = int((time.time() - t0) * 1000)
        status = "success" if result.get("ok") else "failed"
        summary = _make_summary(phase, result)
        await _finish_step(
            db, step_id, status, summary,
            result=result, error=result.get("error"),
            duration_ms=duration_ms,
        )
        steps_summary.append({"phase": phase, "status": status, "summary": summary, "duration_ms": duration_ms})
        log.info(f"phase_{phase}_done", run_id=run_id, status=status, duration_ms=duration_ms)

        # Update current_step
        await _update_run(db, run_id, "running", current_step=phase, tool_id=tool_id, tool_name=tool_name)

        if not result.get("ok"):
            final_status = "failed"
            break

    # Done
    final_tool_id = tool_id if final_status != "failed" else None
    await _update_run(
        db, run_id, final_status, current_step=PHASES[-1] if final_status == "success" else None,
        tool_id=final_tool_id, tool_name=tool_name, ended=True,
    )
    log.info("pipeline_done", run_id=run_id, status=final_status, tool_id=final_tool_id)

    return {
        "ok": final_status == "success",
        "run_id": run_id,
        "status": final_status,
        "tool_id": final_tool_id,
        "tool_name": tool_name,
        "steps": steps_summary,
    }


def _make_summary(phase: str, result: dict) -> str:
    """Make a 1-line human-readable summary for a phase."""
    if not result.get("ok"):
        err = result.get("error", "unknown")
        return f"❌ Failed: {err[:80]}"
    if phase == "scout":
        return f"🔭 Tìm thấy {result.get('total_found', 0)} pain points"
    if phase == "architect":
        return f"📐 Viết xong spec ({result.get('sections_count', 0)} sections)"
    if phase == "forge":
        return f"⚒️ Generate {result.get('file_count', 0)} file code"
    if phase == "hype":
        return f"📣 Campaign: \"{result.get('headline', '?')[:50]}...\""
    if phase == "store":
        return f"🏪 Published: {result.get('tool_id', '?')} (status: draft)"
    return "Done"
