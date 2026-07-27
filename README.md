# ToolForge 🛠️

> AI agent platform tự động research, build và list software tools cho thị trường MMO/creator Việt Nam.

## Tại sao tồn tại

Thị trường tool MMO/creator Việt (reup TikTok, voice clone, content AI, antidetect browser...) đang bị **1Touch Pro** thống trị bằng 1 ông chủ + vài dev làm tay. ToolForge thay thế workflow đó bằng 1 agent team AI, scale được 10-100× số tool mà không cần thuê thêm người.

## Hai sản phẩm

### 1. Owner Brain (internal)
Agent team 5 con tự động:
- **Scout** 🔭 — research pain point từ MMO/creator community
- **Architect** 📐 — viết spec kỹ thuật
- **Forge** 🔥 — generate code + build tool
- **Hype** 📣 — viết copy + chạy quảng cáo
- **Helper** 🤝 — reply khách qua Telegram/Facebook

### 2. Builder Tool (external)
Web app cho user cuối. Mô tả "tôi cần tool A" bằng tiếng Việt → AI build trong 1 giờ.

## Tech stack

- **Cloudflare Workers + D1 + R2 + KV** — full free tier
- **MiniMax M3** (LLM) — 450K context, đã có kinh nghiệm
- **Tauri** (desktop tool) — nhẹ, < 10MB
- **SePay + VietQR** — payment
- **Telegram Bot** — customer support

Cost MVP: **~$65-165/tháng**.

## Status

🟡 P0 — Setup (week 1 of 12).

Xem chi tiết trong [AGENTS.md](./AGENTS.md) và [PRD.md](./PRD.md).

## Liên hệ

- Owner: Zui (TungIT98, @gnut_22)
- Repo: https://github.com/TungIT98/toolforge (private)
