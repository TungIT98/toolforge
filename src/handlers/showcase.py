"""Showcase page — the showpiece demo UI.

GET /showcase → returns self-contained HTML that:
1. Shows a button "Run full pipeline"
2. On click: POSTs to /api/orchestrator/run
3. Polls /api/orchestrator/run/{id} every 1.5s
4. Renders live trace: each agent's status, duration, summary
5. Final result: tool_id + headline preview

The HTML is INLINE in this handler (no build step needed, deploys instantly).
"""
from __future__ import annotations

from src.lib.log import get_logger
from src.lib.response import Response
from src.router import route

log = get_logger("showcase")


SHOWCASE_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ToolForge — 5-Agent Pipeline Showcase</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", sans-serif;
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      color: #e2e8f0;
      min-height: 100vh;
      padding: 2rem 1rem;
    }
    .container { max-width: 900px; margin: 0 auto; }
    h1 {
      font-size: 2.2rem;
      font-weight: 800;
      background: linear-gradient(90deg, #60a5fa, #a78bfa, #f472b6);
      -webkit-background-clip: text;
      background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 0.5rem;
    }
    .subtitle { color: #94a3b8; font-size: 1.05rem; margin-bottom: 2rem; }
    .input-row {
      display: flex; gap: 0.75rem; margin-bottom: 1.5rem;
      background: #1e293b; padding: 1rem; border-radius: 12px;
      border: 1px solid #334155;
    }
    .input-row input {
      flex: 1; padding: 0.7rem 1rem; background: #0f172a; border: 1px solid #334155;
      border-radius: 8px; color: #e2e8f0; font-size: 0.95rem;
    }
    .input-row input:focus { outline: none; border-color: #60a5fa; }
    .btn {
      padding: 0.7rem 1.5rem; background: #2563eb; color: white; border: none;
      border-radius: 8px; font-size: 0.95rem; font-weight: 600; cursor: pointer;
      transition: background 0.15s;
    }
    .btn:hover { background: #1d4ed8; }
    .btn:disabled { background: #475569; cursor: not-allowed; }
    .phases { display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 1.5rem; }
    .phase {
      background: #1e293b; border: 1px solid #334155; border-radius: 10px;
      padding: 1rem 1.25rem; display: flex; align-items: center; gap: 1rem;
      transition: all 0.2s;
    }
    .phase.running { border-color: #fbbf24; background: #422006; }
    .phase.success { border-color: #10b981; background: #064e3b; }
    .phase.failed { border-color: #ef4444; background: #7f1d1d; }
    .phase-icon { font-size: 1.5rem; min-width: 32px; text-align: center; }
    .phase-content { flex: 1; }
    .phase-name { font-weight: 600; font-size: 1rem; }
    .phase-summary { color: #94a3b8; font-size: 0.85rem; margin-top: 0.2rem; }
    .phase-duration { color: #64748b; font-size: 0.8rem; min-width: 70px; text-align: right; }
    .result {
      background: #1e293b; border: 1px solid #10b981; border-radius: 12px;
      padding: 1.5rem; margin-top: 1rem;
    }
    .result h2 { color: #10b981; margin-bottom: 1rem; }
    .result .label { color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; }
    .result .value { color: #e2e8f0; font-size: 1.1rem; font-weight: 600; }
    .spinner {
      width: 16px; height: 16px; border: 2px solid #475569; border-top-color: #60a5fa;
      border-radius: 50%; animation: spin 0.8s linear infinite; display: inline-block;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .pending { opacity: 0.5; }
    .error { background: #7f1d1d; border: 1px solid #ef4444; border-radius: 10px; padding: 1rem; color: #fee2e2; }
    .footer { margin-top: 2rem; text-align: center; color: #64748b; font-size: 0.85rem; }
  </style>
</head>
<body>
  <div class="container">
    <h1>🎼 ToolForge — 5-Agent Pipeline</h1>
    <p class="subtitle">Một cú click. Năm AI agent collaborate. Một tool mới ra đời.</p>

    <div class="input-row">
      <input
        id="inputText"
        type="text"
        placeholder="Mô tả pain point (vd: MMOer mất 3 giờ/ngày reup TikTok)"
        value="MMOer mất 3 giờ/ngày reup TikTok thủ công"
      />
      <button id="runBtn" class="btn" onclick="runPipeline()">▶ Run Pipeline</button>
    </div>

    <div id="trace" class="phases" style="display:none">
      <div class="phase pending" data-phase="scout">
        <div class="phase-icon">🔭</div>
        <div class="phase-content">
          <div class="phase-name">Scout</div>
          <div class="phase-summary">Research pain points từ MMO community</div>
        </div>
        <div class="phase-duration">—</div>
      </div>
      <div class="phase pending" data-phase="architect">
        <div class="phase-icon">📐</div>
        <div class="phase-content">
          <div class="phase-name">Architect</div>
          <div class="phase-summary">Viết 10-section spec kỹ thuật</div>
        </div>
        <div class="phase-duration">—</div>
      </div>
      <div class="phase pending" data-phase="forge">
        <div class="phase-icon">⚒️</div>
        <div class="phase-content">
          <div class="phase-name">Forge</div>
          <div class="phase-summary">Generate code từ spec</div>
        </div>
        <div class="phase-duration">—</div>
      </div>
      <div class="phase pending" data-phase="hype">
        <div class="phase-icon">📣</div>
        <div class="phase-content">
          <div class="phase-name">Hype</div>
          <div class="phase-summary">Viết landing copy + ads + TikTok script</div>
        </div>
        <div class="phase-duration">—</div>
      </div>
      <div class="phase pending" data-phase="store">
        <div class="phase-icon">🏪</div>
        <div class="phase-content">
          <div class="phase-name">Store</div>
          <div class="phase-summary">Publish tool lên catalog</div>
        </div>
        <div class="phase-duration">—</div>
      </div>
    </div>

    <div id="result"></div>
    <div id="error"></div>

    <p class="footer">5 agents. ~30 giây. 1 pain point → 1 tool mới.</p>
  </div>

  <script>
    const API = window.location.origin;
    const PHASES = ["scout", "architect", "forge", "hype", "store"];

    async function runPipeline() {
      const input = document.getElementById("inputText").value.trim();
      if (!input) return alert("Nhập pain point trước nhé!");

      const btn = document.getElementById("runBtn");
      btn.disabled = true;
      btn.textContent = "⏳ Running...";
      document.getElementById("trace").style.display = "flex";
      document.getElementById("result").innerHTML = "";
      document.getElementById("error").innerHTML = "";
      resetPhases();

      try {
        const resp = await fetch(API + "/api/orchestrator/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ input, trigger: "showcase" }),
        });
        const data = await resp.json();
        if (!data.ok) {
          showError("Pipeline failed: " + (data.error || "unknown"));
          btn.disabled = false;
          btn.textContent = "▶ Run Pipeline";
          return;
        }
        pollRun(data.run_id, btn);
      } catch (e) {
        showError("Network error: " + e.message);
        btn.disabled = false;
        btn.textContent = "▶ Run Pipeline";
      }
    }

    async function pollRun(runId, btn) {
      const interval = setInterval(async () => {
        try {
          const resp = await fetch(API + "/api/orchestrator/run/" + runId);
          const data = await resp.json();
          if (data.ok) updateTrace(data.run);
          if (data.run.status === "success" || data.run.status === "failed") {
            clearInterval(interval);
            btn.disabled = false;
            btn.textContent = "▶ Run Pipeline";
            if (data.run.status === "success") showResult(data.run);
            else showError("Pipeline failed at phase: " + (data.run.current_step || "?"));
          }
        } catch (e) {
          console.error("poll failed:", e);
        }
      }, 1500);
    }

    function resetPhases() {
      for (const p of PHASES) {
        const el = document.querySelector(`[data-phase="${p}"]`);
        el.className = "phase pending";
        el.querySelector(".phase-duration").textContent = "—";
        el.querySelector(".phase-summary").textContent = defaultSummary(p);
      }
    }

    function defaultSummary(p) {
      return {
        scout: "Research pain points từ MMO community",
        architect: "Viết 10-section spec kỹ thuật",
        forge: "Generate code từ spec",
        hype: "Viết landing copy + ads + TikTok script",
        store: "Publish tool lên catalog",
      }[p];
    }

    function updateTrace(run) {
      for (const step of run.steps || []) {
        const el = document.querySelector(`[data-phase="${step.phase}"]`);
        if (!el) continue;
        if (step.status === "running") el.className = "phase running";
        else if (step.status === "success") el.className = "phase success";
        else if (step.status === "failed") el.className = "phase failed";
        el.querySelector(".phase-duration").textContent = step.duration_ms + "ms";
        el.querySelector(".phase-summary").textContent = step.summary;
      }
    }

    function showResult(run) {
      const html = `
        <div class="result">
          <h2>✅ Tool mới đã publish!</h2>
          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:1rem; margin-bottom:1rem">
            <div><div class="label">Tool ID</div><div class="value">${run.tool_id || "?"}</div></div>
            <div><div class="label">Tool Name</div><div class="value">${run.tool_name || "?"}</div></div>
            <div><div class="label">Run ID</div><div class="value" style="font-family:monospace;font-size:0.9rem">${run.id}</div></div>
            <div><div class="label">Total time</div><div class="value">${totalDuration(run.steps)}ms</div></div>
          </div>
          <a href="/store/tools/${run.tool_id}" style="color:#60a5fa">Xem trong store →</a>
        </div>
      `;
      document.getElementById("result").innerHTML = html;
    }

    function totalDuration(steps) {
      return (steps || []).reduce((sum, s) => sum + (s.duration_ms || 0), 0);
    }

    function showError(msg) {
      document.getElementById("error").innerHTML = `<div class="error">❌ ${msg}</div>`;
    }
  </script>
</body>
</html>
"""


@route("GET", "/showcase")
async def showcase_handler(request: "object", env: "object", ctx: "object") -> "Response":
    """Serve the showcase demo page (inline HTML)."""
    return Response(
        SHOWCASE_HTML,
        status=200,
        headers={"Content-Type": "text/html; charset=utf-8"},
    )
