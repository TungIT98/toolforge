"""Scout analyzer — use LLM to extract ranked pain points from raw data.

Takes raw search results (from sources.py) and produces structured
top-10 pain points with severity, audience, market size, current solutions, gap.
"""
from __future__ import annotations

import json
from typing import Any

from src.lib.log import get_logger
from src.llm import LLMClient, LLMError

log = get_logger("scout.analyzer")

ANALYZER_SYSTEM = """Bạn là Scout, research agent chuyên săn pain point thị trường tool MMO/creator Việt Nam cho ToolForge.

Nhiệm vụ: Phân tích raw data (search results, forum posts, social media) → trích xuất top 10 pain point MÀ ToolForge có thể build tool giải quyết.

Mỗi pain point cần:
- title: tóm tắt 1 câu (< 80 ký tự)
- description: mô tả chi tiết 2-3 câu
- audience: ai gặp (MMO reup, TikToker, freelancer, content creator, indie hacker)
- severity: 1-10 (10 = đau nhất, sẵn sàng trả tiền ngay)
- market_size_vn: ước tính số người VN gặp pain này (order of magnitude: 100 / 1K / 10K / 100K+)
- current_solutions: họ đang dùng gì (tool nước ngoài, tự code, thuê dev, chịu khổ, ...)
- gap: tại sao giải pháp hiện tại chưa đủ (giá, Việt hóa kém, phức tạp, không support)
- opportunity: S/M/L (effort ToolForge build) + estimated_monthly_revenue_vnd
- source_signals: [list các URL/search query cho thấy pain này tồn tại]
- avoid: bool — true nếu tool này vi phạm TOS nặng (antidetect, captcha, hack) → SKIP

QUAN TRỌNG:
- Output JSON array, không text khác
- Chỉ pain point CÓ DATA hỗ trợ (từ raw data) — không bịa
- Ưu tiên pain point MMO Việt + content creator Việt (KHÔNG phải nông nghiệp, enterprise)
- Top 3 phải severity >= 7 (sẵn sàng trả tiền)
- Top 4-10 có thể severity 4-6 (worth tracking)

Output format: JSON array of objects với đúng fields trên.
"""


async def analyze_to_pain_points(
    raw_data: dict[str, list[dict[str, Any]]],
    client: LLMClient,
    max_pain_points: int = 10,
) -> list[dict[str, Any]]:
    """Use LLM to extract top N pain points from raw data.

    Args:
        raw_data: dict {source_group: [hits]} from sources.fetch_all_sources()
        client: LLMClient instance
        max_pain_points: max pain points to return (default 10)

    Returns:
        list of pain point dicts, sorted by severity DESC
    """
    # Compact raw data for LLM (truncate long content to save tokens)
    compact_data = _compact_for_llm(raw_data)
    if not compact_data:
        log.warn("analyze_no_data")
        return []

    user = (
        f"Phân tích raw data sau và trích xuất top {max_pain_points} pain point cho ToolForge:\n\n"
        f"```json\n{json.dumps(compact_data, ensure_ascii=False, indent=2)[:30000]}\n```\n\n"
        f"Trả về JSON array (không text khác, không markdown fence):\n"
        f'[{{"title": "...", "description": "...", "audience": "...", "severity": N, '
        f'"market_size_vn": "...", "current_solutions": "...", "gap": "...", '
        f'"opportunity": "S", "estimated_monthly_revenue_vnd": N, '
        f'"source_signals": ["url1"], "avoid": false}}]'
    )

    try:
        result = await client.call(
            system=ANALYZER_SYSTEM,
            user=user,
            max_tokens=4096,
            temperature=0.4,
            timeout_s=60,
        )
    except LLMError as e:
        log.error("analyze_llm_failed", err=str(e))
        return []

    # Parse JSON response (may have markdown fence despite instruction)
    text = result["text"].strip()
    if text.startswith("```"):
        # strip ```json ... ```
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        pain_points = json.loads(text)
    except json.JSONDecodeError as e:
        log.error("analyze_json_parse_failed", err=str(e), raw_preview=text[:500])
        return []

    if not isinstance(pain_points, list):
        log.error("analyze_not_array", got_type=type(pain_points).__name__)
        return []

    # Validate + filter avoid=true
    valid = []
    for pp in pain_points:
        if not isinstance(pp, dict):
            continue
        if pp.get("avoid"):
            continue
        if "title" not in pp or "severity" not in pp:
            continue
        # Clamp severity to 1-10
        try:
            pp["severity"] = max(1, min(10, int(pp["severity"])))
        except (ValueError, TypeError):
            continue
        valid.append(pp)

    # Sort by severity DESC
    valid.sort(key=lambda x: x["severity"], reverse=True)
    log.info(
        "analyze_done",
        raw_total=len(pain_points),
        valid=len(valid),
        top_severity=valid[0]["severity"] if valid else 0,
    )
    return valid[:max_pain_points]


def _compact_for_llm(raw_data: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Compact raw data: keep only title, url, content (truncated)."""
    out: dict[str, list[dict[str, Any]]] = {}
    for group, hits in raw_data.items():
        compact = []
        for h in hits[:20]:  # cap at 20 per group
            compact.append({
                "title": str(h.get("title", ""))[:200],
                "url": str(h.get("url", ""))[:200],
                "content": str(h.get("content", ""))[:500],
            })
        if compact:
            out[group] = compact
    return out


def select_top_3_critical(pain_points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pick top 3 critical pain points (severity >= 7) for Architect to spec.

    If < 3 with severity >= 7, fill with next best (severity 5-6).
    Filters out avoid=True pain points (TOS violation).
    """
    # Defensive: filter avoid=True even if caller didn't
    valid = [pp for pp in pain_points if not pp.get("avoid")]
    critical = [pp for pp in valid if pp["severity"] >= 7][:3]
    if len(critical) < 3:
        fillers = [pp for pp in valid if pp["severity"] >= 5 and pp not in critical]
        critical.extend(fillers[: 3 - len(critical)])
    return critical[:3]
