"""Agents roster page — showpiece for the 5 ToolForge agents.

GET /agents → returns self-contained HTML that:
1. Lists all 5 agents with emoji, color, vibe, sample quote
2. Shows the pipeline flow (Scout → Architect → Forge → Hype → Store → Helper)
3. Links to /showcase where users can see them run end-to-end

Inspired by agency-agents (https://github.com/msitarzewski/agency-agents) README
table format — but for our 5 focused agents.

The HTML is INLINE in this handler (no build step needed, deploys instantly).
"""
from __future__ import annotations

from src.lib.log import get_logger
from src.lib.response import Response
from src.router import route

log = get_logger("agents.handler")


# Roster data — mirrors PERSONA.md frontmatter
# Keep in sync with .mavis/agents/*/PERSONA.md when adding/editing agents
AGENTS = [
    {
        "id": "scout",
        "name": "Scout",
        "emoji": "🔭",
        "color": "#06b6d4",
        "vibe": "Pain point hunter — turns MMO community complaints into buildable tools.",
        "quote": "Mình không research cho vui — mình tìm pain point mà tuần này có người sẵn sàng trả tiền.",
        "role": "Research pain points từ MMO community, ưu tiên Việt Nam",
    },
    {
        "id": "architect",
        "name": "Architect",
        "emoji": "📐",
        "color": "#8b5cf6",
        "vibe": "Spec engineer — writes 10-section blueprints Forge builds without asking.",
        "quote": "Spec mơ hồ = Forge đoán = sai. Mình viết đủ 10 mục để Forge build đúng 1 phát.",
        "role": "Viết spec kỹ thuật 10 mục, trade-off matrix, effort estimate",
    },
    {
        "id": "forge",
        "name": "Forge",
        "emoji": "🔥",
        "color": "#f97316",
        "vibe": "Code smith — ships production-ready tools, binary in hand, license in inbox.",
        "quote": "Mình không \"tin là code chạy\" — mình TEST, rồi mới báo done.",
        "role": "Generate code, test đầy đủ, build binary, upload R2",
    },
    {
        "id": "hype",
        "name": "Hype",
        "emoji": "📣",
        "color": "#ec4899",
        "vibe": "Sales copy crafter — Vietnamese landing pages that make MMOers click \"Buy\".",
        "quote": "Không \"wow amazing tool\". Mình viết copy như nói chuyện với 1 MMOer cụ thể.",
        "role": "Viết landing copy, 2 FB ad variants, TikTok script, đo ROAS",
    },
    {
        "id": "store",
        "name": "Store",
        "emoji": "🏪",
        "color": "#22c55e",
        "vibe": "Publisher — adds new tool to catalog with pricing, description, status.",
        "quote": "ToolForge chỉ có 1 quy trình: build xong là list, không có bước trung gian nào.",
        "role": "Publish tool lên catalog với status=draft, chờ owner duyệt",
    },
    {
        "id": "helper",
        "name": "Helper",
        "emoji": "🤝",
        "color": "#10b981",
        "vibe": "Customer whisperer — Telegram reply in 30s, escalation only when needed.",
        "quote": "Khách giận mà mình vẫn mát. Không bao giờ nói \"tôi là AI\".",
        "role": "Reply khách Telegram/Facebook, 80% auto-resolve, 5% escalate owner",
    },
]

# Pipeline order (left to right)
PIPELINE = ["scout", "architect", "forge", "hype", "store"]


def _agent_card(agent: dict) -> str:
    return f"""
      <a href="#{agent['id']}" class="agent-card" style="--accent: {agent['color']}">
        <div class="agent-emoji">{agent['emoji']}</div>
        <div class="agent-content">
          <div class="agent-name">{agent['name']}</div>
          <div class="agent-vibe">{agent['vibe']}</div>
          <div class="agent-role">{agent['role']}</div>
        </div>
      </a>
    """


def _pipeline_arrow() -> str:
    return '<div class="pipeline-arrow">→</div>'


def _pipeline_diagram() -> str:
    """Show the 5-step flow as connected cards."""
    parts = []
    for i, agent_id in enumerate(PIPELINE):
        agent = next(a for a in AGENTS if a["id"] == agent_id)
        parts.append(f'<div class="pipeline-step" style="--accent: {agent["color"]}"><div class="pipeline-emoji">{agent["emoji"]}</div><div class="pipeline-name">{agent["name"]}</div></div>')
        if i < len(PIPELINE) - 1:
            parts.append('<div class="pipeline-arrow">→</div>')
    # Helper comes after (handles customers of all the published tools)
    parts.append('<div class="pipeline-arrow">→</div>')
    helper = next(a for a in AGENTS if a["id"] == "helper")
    parts.append(f'<div class="pipeline-step helper" style="--accent: {helper["color"]}"><div class="pipeline-emoji">{helper["emoji"]}</div><div class="pipeline-name">{helper["name"]}</div></div>')
    return f'<div class="pipeline">{"".join(parts)}</div>'


AGENTS_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ToolForge — Meet the 5 Agents</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", sans-serif;
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      color: #e2e8f0;
      min-height: 100vh;
      padding: 3rem 1.5rem;
    }
    .container { max-width: 1100px; margin: 0 auto; }
    h1 {
      font-size: 2.5rem;
      font-weight: 800;
      background: linear-gradient(90deg, #60a5fa, #a78bfa, #f472b6);
      -webkit-background-clip: text;
      background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 0.5rem;
      text-align: center;
    }
    .subtitle {
      color: #94a3b8;
      font-size: 1.1rem;
      text-align: center;
      margin-bottom: 3rem;
    }
    .section-title {
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: #64748b;
      margin-bottom: 1.5rem;
      font-weight: 600;
    }
    .roster {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 1.25rem;
      margin-bottom: 4rem;
    }
    .agent-card {
      display: flex;
      align-items: flex-start;
      gap: 1rem;
      background: #1e293b;
      border: 1px solid #334155;
      border-left: 4px solid var(--accent);
      border-radius: 12px;
      padding: 1.25rem 1.5rem;
      text-decoration: none;
      color: inherit;
      transition: transform 0.15s, border-color 0.15s;
    }
    .agent-card:hover {
      transform: translateY(-2px);
      border-color: var(--accent);
    }
    .agent-emoji {
      font-size: 2.2rem;
      min-width: 48px;
      text-align: center;
    }
    .agent-content {
      flex: 1;
    }
    .agent-name {
      font-size: 1.15rem;
      font-weight: 700;
      color: var(--accent);
      margin-bottom: 0.4rem;
    }
    .agent-vibe {
      font-size: 0.9rem;
      color: #cbd5e1;
      font-style: italic;
      margin-bottom: 0.5rem;
      line-height: 1.4;
    }
    .agent-role {
      font-size: 0.8rem;
      color: #94a3b8;
      line-height: 1.4;
    }
    .pipeline {
      display: flex;
      align-items: center;
      justify-content: center;
      flex-wrap: wrap;
      gap: 0.5rem;
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 16px;
      padding: 1.5rem;
      margin-bottom: 2rem;
      overflow-x: auto;
    }
    .pipeline-step {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.4rem;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--accent);
      min-width: 80px;
    }
    .pipeline-step.helper { background: rgba(16, 185, 129, 0.15); }
    .pipeline-emoji { font-size: 1.5rem; }
    .pipeline-name {
      font-size: 0.75rem;
      font-weight: 600;
      color: #cbd5e1;
    }
    .pipeline-arrow {
      color: #475569;
      font-size: 1.2rem;
      font-weight: 600;
    }
    .quote-section {
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 2rem;
      margin-bottom: 3rem;
    }
    .quote-section h2 {
      color: #cbd5e1;
      margin-bottom: 1.5rem;
      font-size: 1.1rem;
    }
    .quote-block {
      border-left: 3px solid var(--accent);
      padding: 0.75rem 1rem;
      margin-bottom: 1rem;
      background: rgba(255,255,255,0.02);
      border-radius: 4px;
      color: #e2e8f0;
      font-style: italic;
      line-height: 1.5;
    }
    .quote-block .quote-name {
      color: var(--accent);
      font-weight: 600;
      font-style: normal;
      margin-bottom: 0.3rem;
      font-size: 0.85rem;
    }
    .cta {
      text-align: center;
      background: linear-gradient(135deg, #1e293b, #0f172a);
      border: 1px solid #334155;
      border-radius: 16px;
      padding: 2.5rem 2rem;
    }
    .cta h2 {
      color: #f1f5f9;
      font-size: 1.5rem;
      margin-bottom: 0.75rem;
    }
    .cta p { color: #94a3b8; margin-bottom: 1.5rem; }
    .cta-btn {
      display: inline-block;
      background: #2563eb;
      color: white;
      padding: 0.85rem 2rem;
      border-radius: 8px;
      text-decoration: none;
      font-weight: 600;
      transition: background 0.15s;
    }
    .cta-btn:hover { background: #1d4ed8; }
    .footer {
      margin-top: 2.5rem;
      text-align: center;
      color: #64748b;
      font-size: 0.85rem;
    }
    .footer a { color: #60a5fa; text-decoration: none; }
    @media (max-width: 700px) {
      h1 { font-size: 1.8rem; }
      .pipeline { flex-direction: column; }
      .pipeline-arrow { transform: rotate(90deg); }
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>🎼 Meet the 5 Agents</h1>
    <p class="subtitle">Mỗi agent là 1 chuyên gia. Mỗi agent có personality, voice, success metrics.<br>Cùng nhau, họ tự vận hành: từ "có vấn đề" → "có tool + landing + marketing + support".</p>

    <div class="section-title">📋 Roster</div>
    <div class="roster">
""" + "".join(_agent_card(a) for a in AGENTS) + """
    </div>

    <div class="section-title">🔄 Pipeline (5 pha tự vận hành)</div>
""" + _pipeline_diagram() + """

    <div class="section-title">💬 Personality Highlights (1 quote per agent)</div>
    <div class="quote-section">
""" + "".join(f'''<div class="quote-block" style="--accent: {a["color"]}">
        <div class="quote-name">{a["emoji"]} {a["name"]}</div>
        "{a["quote"]}"
      </div>''' for a in AGENTS) + """
    </div>

    <div class="cta">
      <h2>🚀 Xem họ chạy thật</h2>
      <p>1 click. 5 agents collaborate. 1 tool mới trong ~30 giây.</p>
      <a href="/showcase" class="cta-btn">▶ Run Pipeline Now</a>
    </div>

    <p class="footer">
      Inspired by <a href="https://github.com/msitarzewski/agency-agents">agency-agents</a> · Built with ❤️ by Mavis
    </p>
  </div>
</body>
</html>
"""


@route("GET", "/agents")
async def agents_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Serve the agents roster page (inline HTML)."""
    return Response(
        AGENTS_HTML,
        status=200,
        headers={"Content-Type": "text/html; charset=utf-8"},
    )
