"""Hype 📣 — Marketing agent.

Takes a tool (name + spec + pricing) and generates a full marketing campaign:
- Landing page copy (headline, benefits, FAQ, CTA)
- 2 Facebook ad variants (pain focus + result focus)
- 1 TikTok script (15-30s)

All content in Vietnamese, dân giã, sales-aggressive nhưng không spam.

For MVP: returns structured dict. Does NOT actually post to Meta/TikTok
(those need owner's business account tokens, separate setup).
"""
from __future__ import annotations

import json
from typing import Any

from src.lib.log import get_logger

log = get_logger("hype")


# === Prompt for LLM ===

HYPE_SYSTEM_PROMPT = """Bạn là Hype 📣 — Marketing agent cho ToolForge (cửa hàng tool tự động hóa cho MMO community Việt Nam).

Nhiệm vụ: Từ spec tool, viết 1 campaign marketing HOÀN CHỈNH bằng tiếng Việt dân giã.

Tone:
- Dân giã, sales-aggressive nhưng tử tế
- Câu ngắn 5-15 từ
- Có số liệu cụ thể (không "rẻ hơn" mà thiếu con số)
- Pain point đầu, solution giữa, CTA cuối
- Emoji vừa đủ (2-3 cái mỗi post)

Output JSON format (không markdown, không ```json):

{
  "landing": {
    "headline": "<30 từ, pain + solution>",
    "subhead": "<20 từ, giải thích ngắn>",
    "benefits": ["<benefit 1 với số liệu>", "<benefit 2>", "<benefit 3>", "<benefit 4>"],
    "cta": "<CTA ngắn, urgency>",
    "faq": [{"q": "...", "a": "..."}, {"q": "...", "a": "..."}, {"q": "...", "a": "..."}]
  },
  "facebook_ad_a": {
    "name": "Pain focus",
    "hook": "Anh/chị đang <pain point>?",
    "body": "<3 dòng empathy + 1 dòng solution>",
    "cta": "Tải ngay — Free trial 3 ngày"
  },
  "facebook_ad_b": {
    "name": "Result focus",
    "hook": "Tool X giúp <audience> tiết kiệm Y giờ/tuần",
    "body": "<3 case study mini hoặc social proof>",
    "cta": "Xem demo — Tải miễn phí"
  },
  "tiktok_script": {
    "hook_3s": "<3 giây đầu cực mạnh>",
    "body": "<demo tool chạy, 15-25 giây>",
    "caption": "<caption ngắn, kèm 'Link tải trong bio'>"
  }
}

QUAN TRỌNG:
- KHÔNG dùng "Kính gửi quý khách" — quá formal
- KHÔNG dùng "Wow amazing" — quá tây
- KHÔNG spam emoji 📣📣📣📣
- KHÔNG hứa suông "Sẽ giúp anh thành công"
- KHÔNG bịa số liệu — nếu không có thì đừng viết
- Tất cả JSON phải parse được, không lỗi
"""


def _build_user_prompt(tool_name: str, spec: dict, pricing_vnd: int, target_audience: str) -> str:
    """Build the user message for LLM."""
    problem = spec.get("problem", spec.get("description", ""))
    features = spec.get("features", spec.get("key_features", []))
    platform = spec.get("platform", spec.get("target_platform", ""))
    return f"""Tool: {tool_name}
Vấn đề giải quyết: {problem}
Audience chính: {target_audience}
Nền tảng: {platform}
Tính năng chính: {json.dumps(features, ensure_ascii=False) if features else '(chưa có)'}
Giá bán: {pricing_vnd:,} VND

Viết campaign marketing cho tool này. Output JSON thuần (không markdown)."""


def _parse_llm_json(text: str) -> dict:
    """Parse LLM response, handling markdown fences + trailing text."""
    text = text.strip()
    # Strip markdown fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Drop first ```json or ``` line
        if lines[0].startswith("```"):
            lines = lines[1:]
        # Drop last ``` line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    # Find JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(text[start:end + 1])


async def generate_campaign(
    env: Any,
    tool_name: str,
    spec: dict,
    pricing_vnd: int,
    target_audience: str = "MMO TikTok creator Việt Nam",
) -> dict:
    """Generate full marketing campaign via LLM.

    Returns dict with: ok, campaign (full structured copy), usage, latency_ms
    """
    from src.llm import LLMError, get_client

    try:
        client = get_client(agent_name="hype", env=env)
    except LLMError as e:
        return {"ok": False, "error": str(e), "code": "LLM_KEY_MISSING"}

    user_prompt = _build_user_prompt(tool_name, spec, pricing_vnd, target_audience)
    log.info("hype_generate_start", tool=tool_name, audience=target_audience)
    try:
        result = await client.call(
            system=HYPE_SYSTEM_PROMPT,
            user=user_prompt,
            max_tokens=2500,
            temperature=0.8,  # more creative for marketing
        )
    except LLMError as e:
        return {"ok": False, "error": str(e), "code": "LLM_FAILED"}

    text = result.get("text", "")
    try:
        campaign = _parse_llm_json(text)
    except Exception as e:
        log.error("hype_parse_failed", err=str(e), text_preview=text[:200])
        return {
            "ok": False, "error": f"Failed to parse LLM JSON: {e}",
            "code": "LLM_PARSE_FAILED", "raw": text[:500],
        }

    log.info("hype_generate_done", tool=tool_name)
    return {
        "ok": True,
        "tool_name": tool_name,
        "campaign": campaign,
        "llm_usage": result.get("usage", {}),
        "latency_ms": result.get("latency_ms", 0),
    }


async def save_campaign(
    db: Any,
    tool_id: str,
    tool_name: str,
    campaign: dict,
    pricing_vnd: int,
) -> dict:
    """Save generated campaign to D1 for later retrieval."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    campaign_json = json.dumps(campaign, ensure_ascii=False)
    try:
        await db.prepare(
            """INSERT OR REPLACE INTO campaigns
               (tool_id, tool_name, pricing_vnd, content_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)"""
        ).bind(tool_id, tool_name, pricing_vnd, campaign_json, now, now).run()
        return {"ok": True, "tool_id": tool_id, "saved_at": now}
    except Exception as e:
        log.error("hype_save_failed", err=str(e), tool_id=tool_id)
        return {"ok": False, "error": str(e), "code": "DB_ERROR"}


async def get_campaign(db: Any, tool_id: str) -> dict | None:
    """Retrieve saved campaign by tool_id."""
    try:
        row = await db.prepare(
            "SELECT tool_id, tool_name, pricing_vnd, content_json, created_at, updated_at "
            "FROM campaigns WHERE tool_id = ?"
        ).bind(tool_id).first()
        if not row:
            return None
        row["content"] = json.loads(row.get("content_json") or "{}")
        return row
    except Exception as e:
        log.warn("hype_get_failed", err=str(e), tool_id=tool_id)
        return None
