"""Architect spec generator — use LLM to produce 10-section technical spec.

Spec structure (from .mavis/agents/architect/PERSONA.md):
1. Problem statement
2. User flow
3. Features (MVP scope) — must-have / nice-to-have / out-of-scope
4. Technical architecture
5. Data model
6. API contract
7. UI/UX wireframe
8. Test plan
9. Effort estimate
10. Rollout plan
"""
from __future__ import annotations

import re
from typing import Any

from src.lib.log import get_logger
from src.llm import LLMClient, LLMError

log = get_logger("architect.spec")

ARCHITECT_SYSTEM = """Bạn là Architect, spec engineer cho ToolForge. Nhiệm vụ: viết SPEC KỸ THUẬT ĐẦY ĐỦ 10 MỤC để team dev (Forge) build được, không cần hỏi lại.

FORMAT BẮT BUỘC: Markdown với đúng 10 section sau (DÙNG ĐÚNG TÊN):

## 1. Problem statement
- Pain point (1 câu)
- Target user (audience cụ thể)
- Why now (urgency)

## 2. User flow
- Happy path (step by step)
- 3-5 edge cases
- Error states

## 3. Features (MVP scope)
### Must-have (P0)
- ...

### Nice-to-have (P1, sau MVP)
- ...

### Out of scope (KHÔNG làm)
- ...

## 4. Technical architecture
- Stack: Tauri 2.x (desktop) / Python FastAPI (web) / Cloudflare Worker (backend)
- Frontend: React + Vite + Tailwind
- Backend: FastAPI / Hono
- Storage: D1 / R2 / local file
- External APIs: gì, cost

## 5. Data model
- Schema SQLite/D1 nếu cần
- File structure nếu local
- Config format

## 6. API contract
- REST endpoints (nếu có)
- Input/output JSON examples

## 7. UI/UX wireframe
- ASCII wireframe cho mỗi screen
- Key interactions
- Empty/loading/error states

## 8. Test plan
- Unit test scope
- Integration test scope
- Manual test checklist (10 case)
- Acceptance criteria (đo được)

## 9. Effort estimate
- Forge build time: X giờ
- LLM token estimate: ~$Y
- Risk: thấp/trung bình/cao
- Dependency: gì cần có sẵn

## 10. Rollout plan
- Phase 1: internal test
- Phase 2: beta (5 user)
- Phase 3: public trên aff.toolforge.vn
- Pricing: ... VNĐ
- Distribution: ...

QUY TẮC:
- Tiếng Việt cho mô tả, tiếng Anh cho technical terms
- PHẢI có đủ 10 mục — nếu mục nào không áp dụng được, ghi "N/A vì <lý do>" thay vì bỏ
- Effort estimate phải THỰC TẾ (đừng fake "2 giờ" cho cái cần 2 ngày)
- Nếu clone từ competitor (1Touch Pro), phải CẢI TIẾN ít nhất 1 điểm (UI, feature, giá, support)
- Output CHỈ markdown spec, không text thừa
"""


async def generate_spec(
    pain_point: dict[str, Any],
    client: LLMClient,
    category: str = "auto",
) -> dict[str, Any]:
    """Generate 10-section spec from a pain point.

    Args:
        pain_point: dict with title, description, audience, severity, market_size_vn, etc.
        client: LLMClient instance
        category: tool category hint — "cli" | "desktop" | "web" | "extension" | "batch" | "auto"
                  ("auto" = LLM decides from pain point description)

    Returns:
        dict with: spec_markdown, sections_parsed (dict of 10 sections), effort_hours, llm_usage
    """
    # Build user prompt with all pain point context
    user = _build_user_prompt(pain_point, category)

    try:
        result = await client.call(
            system=ARCHITECT_SYSTEM,
            user=user,
            max_tokens=6000,  # specs can be long
            temperature=0.3,  # lower temp = more deterministic
            timeout_s=90,
        )
    except LLMError as e:
        log.error("spec_llm_failed", err=str(e), title=pain_point.get("title", "?"))
        raise

    spec_md = result["text"].strip()

    # Parse into 10 sections
    sections = _parse_sections(spec_md)

    # Extract effort estimate
    effort_hours = _extract_effort_hours(spec_md)

    return {
        "spec_markdown": spec_md,
        "sections": sections,
        "effort_estimate_hours": effort_hours,
        "llm_usage": {
            "input_tokens": result.get("usage", {}).get("input_tokens", 0),
            "output_tokens": result.get("usage", {}).get("output_tokens", 0),
            "model": result.get("model", ""),
            "latency_ms": result.get("latency_ms", 0),
        },
    }


def _build_user_prompt(pain_point: dict[str, Any], category: str) -> str:
    """Build user prompt from pain point dict."""
    lines = [
        f"# Pain Point",
        f"- **Title:** {pain_point.get('title', 'N/A')}",
        f"- **Description:** {pain_point.get('description', 'N/A')}",
        f"- **Audience:** {pain_point.get('audience', 'N/A')}",
        f"- **Severity:** {pain_point.get('severity', 'N/A')}/10",
        f"- **Market size (VN):** {pain_point.get('market_size_vn', 'N/A')}",
        f"- **Current solutions:** {pain_point.get('current_solutions', 'N/A')}",
        f"- **Gap:** {pain_point.get('gap', 'N/A')}",
        f"- **Opportunity size:** {pain_point.get('opportunity', 'N/A')}",
        f"- **Estimated monthly revenue:** {pain_point.get('estimated_monthly_revenue_vnd', 0):,} VNĐ",
    ]
    sources = pain_point.get("source_signals", [])
    if sources:
        lines.append(f"- **Source signals:**")
        for s in sources[:3]:
            lines.append(f"  - {s}")
    lines.append("")
    lines.append(f"# Category hint: {category}")
    lines.append("")
    lines.append(
        "Viết spec kỹ thuật đầy đủ 10 mục cho tool giải quyết pain point trên. "
        "ToolForge tech stack: Tauri 2.x cho desktop, Python FastAPI cho web, "
        "Cloudflare Workers + D1 + R2 cho backend. "
        "Target user Việt Nam, trả tiền qua SePay/VietQR. "
        "Bắt đầu output bằng `## 1. Problem statement`."
    )
    return "\n".join(lines)


def _parse_sections(spec_md: str) -> dict[str, str]:
    """Parse spec markdown into 10 sections.

    Uses regex to find `## N. <name>` headers. Sections split until next header.
    """
    sections: dict[str, str] = {}
    section_names = [
        "problem_statement",
        "user_flow",
        "features_mvp",
        "technical_architecture",
        "data_model",
        "api_contract",
        "ui_ux_wireframe",
        "test_plan",
        "effort_estimate",
        "rollout_plan",
    ]
    # Pattern: ## 1. <title> ... ## 2. <title> ...
    pattern = re.compile(r"^##\s+(\d+)\.\s+([^\n]+)$", re.MULTILINE)
    matches = list(pattern.finditer(spec_md))

    if not matches:
        log.warn("spec_no_sections_found", preview=spec_md[:300])
        return {}

    for i, m in enumerate(matches):
        idx = int(m.group(1)) - 1
        if idx < 0 or idx >= 10:
            continue
        key = section_names[idx]
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(spec_md)
        sections[key] = spec_md[start:end].strip()

    return sections


def _extract_effort_hours(spec_md: str) -> float | None:
    """Extract effort estimate from section 9 of spec.

    Looks for patterns like "X giờ", "X hours", "X days", "X ngày".
    """
    m = re.search(
        r"(?:Forge build time|Effort|Build time)[:\s]+(\d+(?:\.\d+)?)\s*(giờ|hours?|h|ngày|days?|d)",
        spec_md,
        re.IGNORECASE,
    )
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("ngày") or unit.startswith("day") or unit == "d":
        return val * 8  # 1 day = 8 hours
    return val


def validate_spec(spec: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate that spec has all 10 sections + non-empty content.

    Returns: (is_valid, list_of_issues)
    """
    issues = []
    required = [
        "problem_statement", "user_flow", "features_mvp", "technical_architecture",
        "data_model", "api_contract", "ui_ux_wireframe", "test_plan",
        "effort_estimate", "rollout_plan",
    ]
    for key in required:
        if key not in spec.get("sections", {}):
            issues.append(f"missing section: {key}")
        elif not spec["sections"][key].strip() or spec["sections"][key].strip() in ("N/A", "N/A vì ..."):
            issues.append(f"empty/stub section: {key}")
    return (len(issues) == 0, issues)
