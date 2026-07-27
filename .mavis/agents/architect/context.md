# Context cho Architect 📐

## ToolForge tech stack (để Architect spec đúng)
- **Desktop tool**: Tauri 2.x (Rust backend + WebView frontend). Lý do: nhẹ (< 10MB), secure, cross-platform (Win/Mac/Linux).
- **Web tool**: Python FastAPI + Cloudflare Pages (React). Lý do: owner quen, free tier.
- **Backend shared**: Cloudflare Workers (Node.js hoặc Python pyodide) + D1 (SQLite) + R2 (file) + KV (session/cache).
- **LLM**: MiniMax M3 via `https://api.minimaxi.com/anthropic` (model `minimax/MiniMax-M3`).
- **Build**: GitHub Actions (free 2000 min/tháng), trigger bằng `workflow_dispatch` hoặc push tag.
- **Distribution**: R2 URL + signed token (license check).

## Thư viện thường dùng (Architect ưu tiên)
- **Python**: FastAPI, pydantic, httpx, requests, rich (CLI), typer, playwright (automation), opencv-python (video), pydub (audio), gTTS/edge-tts (TTS)
- **Tauri**: tauri 2.x, tauri-plugin-store, tauri-plugin-fs, tauri-plugin-http
- **Frontend**: React 18 + Vite + TailwindCSS + shadcn/ui + react-query
- **Backend CF**: Hono (Node) hoặc FastAPI (Python pyodide), D1 binding, R2 binding

## Anti-patterns (Architect tránh)
- ❌ Electron (file quá nặng 100MB+)
- ❌ Vue (owner không quen)
- ❌ MongoDB (overkill cho MVP, dùng D1 SQLite)
- ❌ AWS Lambda (đắt, owner quen Cloudflare)
- ❌ Stripe (chưa support VN tốt, dùng SePay)
- ❌ Custom auth (dùng email + license key đơn giản)

## Spec template library
Architect giữ sẵn template spec cho 5 category tool thường gặp:
1. **CLI tool** (vd: Douyin Downloader) — Python + typer, no GUI
2. **Desktop app** (vd: Capcut Reup) — Tauri + React
3. **Web tool** (vd: Create Content AI) — FastAPI + CF Pages
4. **Browser extension** (vd: Flow Captcha) — Chrome MV3
5. **Batch script** (vd: Bulk Mail) — Python script + cron

Khi owner yêu cầu spec, Architect tự chọn template gần nhất + customize.

## Owner (Zui) approval pattern
- **Checkpoint 1**: Sau Architect, trước Forge
  - Owner đọc spec 5-10 phút
  - Comment inline hoặc reply "approve" / "reject + lý do"
  - Nếu approve → Architect tạo handoff JSON → Forge pickup
- **Checkpoint 2**: Sau Forge, trước Hype
  - Owner test binary .exe/web tool
  - "approve" → Hype pickup
  - "reject + lý do" → Forge fix lại

## Liên kết với Scout + Forge
- Nhận brief từ Scout: `scout/data/briefs/<date>.md`
- Output cho Forge: `architect/data/specs/<tool-id>.md` + `architect/data/handoff/<tool-id>.json`
- Handoff JSON format:
```json
{
  "tool_id": "capcut-reup",
  "spec_path": "data/specs/capcut-reup.md",
  "status": "pending_owner_review | approved | rejected | in_progress | done",
  "priority": "high | medium | low",
  "created_at": "2026-07-27T10:00:00+07:00",
  "approved_at": null,
  "owner_feedback": null,
  "forge_handoff_at": null
}
```

## 1Touch Pro clone reference
Khi Architect clone 1 tool của 1Touch, KHÔNG copy y nguyên — phải cải tiến ít nhất 1 điểm:
- UI/UX tốt hơn
- Feature thêm (vd: hỗ trợ batch lớn hơn)
- Support tiếng Việt tốt hơn
- Giá rẻ hơn (free + pro tier)
- License key + cloud sync

Mục tiêu: ToolForge version > 1Touch version, không phải bản sao y hệt.
