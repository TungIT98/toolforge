"""Builder Tool chat — LLM conversation with user to gather requirements.

Flow:
1. User sends initial message ("Tôi cần tool download video TikTok")
2. LLM asks clarifying question(s) (max 5 rounds)
3. When enough info: LLM outputs JSON {ready: true, spec: {...}, tool_name: "..."}
4. Session marked status='ready_to_build' + spec saved
5. User can trigger build via POST /api/builder/session/{id}/build
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from src.lib.log import get_logger
from src.llm import LLMClient, LLMError

log = get_logger("builder.chat")

BUILDER_SYSTEM = """Bạn là ToolForge Builder AI — chuyên gia giúp user mô tả tool họ cần, hỏi đủ thông tin để generate spec kỹ thuật.

NGUYÊN TẮC:
- Hỏi tối đa 5 câu, mỗi câu 1 ý (KHÔNG hỏi list dài)
- Bắt đầu bằng câu xác nhận đã hiểu user, sau đó hỏi câu quan trọng nhất
- Câu hỏi theo thứ tự ưu tiên:
  1. Mục đích chính (user dùng để làm gì)
  2. Input/output cụ thể (lấy data từ đâu, output ra sao)
  3. Platform (Windows/Mac/Web, dạng CLI/GUI/extension)
  4. Tính năng must-have (1-2 cái, không hỏi list)
  5. Edge case (1-2 cái quan trọng)
- Khi đã đủ thông tin (sau 2-5 câu), output JSON DUY NHẤT:
  {"ready": true, "tool_name": "...", "spec": {"problem": "...", "input": "...", "output": "...", "platform": "windows|mac|web|cli", "stack": "...", "features": ["..."], "edge_cases": ["..."]}}

- Nếu user cung cấp đầy đủ thông tin trong 1-2 tin nhắn đầu, output ready: true ngay
- Nếu user nói "OK build đi" hoặc "đủ rồi" → output ready: true với best-guess spec

TONE: Dân giã Việt, ngắn gọn, thân thiện. Dùng "bạn/mình". Tiếng Việt có dấu.
"""


async def create_chat_session(db: "object", user_ip: str | None = None, user_email: str | None = None) -> dict:
    """Create a new chat session."""
    from datetime import datetime, timezone
    session_id = f"sess-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    await db.prepare(
        """INSERT INTO builder_sessions (id, user_email, user_ip, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)"""
    ).bind(session_id, user_email, user_ip, "chatting", now, now).run()
    return {"session_id": session_id, "status": "chatting", "created_at": now}


async def add_message(db: "object", session_id: str, role: str, content: str) -> None:
    """Append a message to the session."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    await db.prepare(
        """INSERT INTO builder_messages (session_id, role, content, ts)
           VALUES (?, ?, ?, ?)"""
    ).bind(session_id, role, content, now).run()
    # Increment counter
    try:
        await db.prepare(
            "UPDATE builder_sessions SET messages_count = messages_count + 1, updated_at = ? WHERE id = ?"
        ).bind(now, session_id).run()
    except Exception:
        pass


async def get_session(db: "object", session_id: str) -> dict | None:
    """Get session + messages."""
    session = await db.prepare(
        "SELECT id, user_email, user_ip, status, tool_name, final_spec, spec_json, messages_count, created_at, updated_at "
        "FROM builder_sessions WHERE id = ?"
    ).bind(session_id).first()
    if not session:
        return None
    messages = await db.prepare(
        "SELECT role, content, ts FROM builder_messages WHERE session_id = ? ORDER BY id ASC"
    ).bind(session_id).all()
    return {**session, "messages": messages or []}


def build_llm_messages(system: str, history: list[dict], new_user_message: str) -> tuple[str, list]:
    """Convert session history to LLM messages format."""
    msgs = []
    for m in history[-20:]:  # keep last 20 messages for context
        role = m.get("role", "user")
        content = m.get("content", "")
        if role in ("user", "assistant", "system"):
            msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": new_user_message})
    return system, msgs


def detect_ready_response(text: str) -> tuple[bool, dict | None]:
    """Detect if LLM output JSON with ready=true.

    Returns (is_ready, parsed_dict_or_none).
    """
    text = text.strip()
    # Strip markdown code fence if present
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    # Try parse JSON
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object (may have nested braces) - balanced match
        idx = text.find('"ready"')
        if idx < 0:
            return False, None
        start = text.rfind("{", 0, idx + 1)
        if start < 0:
            return False, None
        depth = 0
        end = -1
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end < 0:
            return False, None
        candidate = text[start:end+1]
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            return False, None

    if isinstance(data, dict) and data.get("ready") is True:
        return True, data
    return False, data if isinstance(data, dict) else None


async def chat_with_user(
    db: "object",
    session_id: str,
    user_message: str,
    client: LLMClient,
) -> dict[str, Any]:
    """Process a user message in a chat session.

    Returns: {
        ok: True,
        session_id,
        assistant_message,
        status: chatting | ready_to_build,
        tool_name (if ready),
        spec (if ready),
        messages_count
    }
    """
    # 1. Get session + history
    session = await db.prepare(
        "SELECT id, status, messages_count FROM builder_sessions WHERE id = ?"
    ).bind(session_id).first()
    if not session:
        return {"ok": False, "error": "Session not found", "code": "SESSION_NOT_FOUND"}
    if session["status"] not in ("chatting", "ready_to_build"):
        return {"ok": False, "error": f"Session status is {session['status']}", "code": "BAD_STATUS"}

    # 2. Get history
    history = await db.prepare(
        "SELECT role, content FROM builder_messages WHERE session_id = ? ORDER BY id ASC"
    ).bind(session_id).all()
    history = list(history or [])

    # 3. Save user message
    await add_message(db, session_id, "user", user_message)

    # 4. Build LLM call
    msgs = [{"role": m["role"], "content": m["content"]} for m in history[-20:]]
    msgs.append({"role": "user", "content": user_message})

    # 5. Call LLM
    try:
        # Convert to Anthropic format: system separate, messages array
        # LLMClient.call takes (system, user) so we need to flatten or use a different method
        # For now, we'll concatenate the conversation as a single user prompt
        conversation = "\n".join([
            f"{m['role'].upper()}: {m['content']}" for m in msgs
        ])
        result = await client.call(
            system=BUILDER_SYSTEM,
            user=f"Cuộc hội thoại:\n\n{conversation}\n\nASSISTANT:",
            max_tokens=1500,
            temperature=0.7,
            timeout_s=45,
        )
    except LLMError as e:
        return {"ok": False, "error": str(e), "code": "LLM_FAILED"}

    assistant_text = result["text"].strip()

    # 6. Detect if ready (JSON output)
    is_ready, parsed = detect_ready_response(assistant_text)

    if is_ready and parsed:
        # Save spec
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        tool_name = parsed.get("tool_name", "Untitled Tool")
        spec = parsed.get("spec", {})
        spec_json = json.dumps(spec, ensure_ascii=False)
        # Format as markdown
        spec_md = f"""# {tool_name}

## Problem
{spec.get('problem', 'N/A')}

## Input/Output
- **Input:** {spec.get('input', 'N/A')}
- **Output:** {spec.get('output', 'N/A')}

## Platform
{spec.get('platform', 'N/A')}

## Stack
{spec.get('stack', 'N/A')}

## Features (must-have)
{chr(10).join(f"- {f}" for f in spec.get('features', [])) or '- N/A'}

## Edge cases
{chr(10).join(f"- {e}" for e in spec.get('edge_cases', [])) or '- N/A'}
"""
        try:
            await db.prepare(
                """UPDATE builder_sessions
                   SET status = 'ready_to_build', tool_name = ?, final_spec = ?, spec_json = ?, updated_at = ?
                   WHERE id = ?"""
            ).bind(tool_name, spec_md, spec_json, now, session_id).run()
        except Exception as e:
            log.warn("save_spec_failed", err=str(e))
        # Save assistant message
        await add_message(db, session_id, "assistant", assistant_text)

        return {
            "ok": True,
            "session_id": session_id,
            "assistant_message": assistant_text,
            "status": "ready_to_build",
            "tool_name": tool_name,
            "spec": spec,
            "spec_markdown": spec_md,
            "messages_count": session.get("messages_count", 0) + 2,
        }
    else:
        # Just a regular question
        await add_message(db, session_id, "assistant", assistant_text)
        return {
            "ok": True,
            "session_id": session_id,
            "assistant_message": assistant_text,
            "status": "chatting",
            "messages_count": session.get("messages_count", 0) + 2,
        }


def count_user_messages_in_round(history: list) -> int:
    """Count user messages in the last few rounds (for forced ready after 5)."""
    return sum(1 for m in history if m["role"] == "user")
