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

🟡 P0 — Setup code ready, chờ deploy (week 1 of 12).

### P0 deliverables (done 2026-07-27)
- ✅ `wrangler.jsonc` — config Cloudflare Worker + D1 + R2 + KV + 3 cron triggers
- ✅ `migrations/0001_init.sql` — 8 tables: tools, briefs, specs, handoff, builds, licenses, conversations, campaigns, llm_usage
- ✅ `src/worker.py` — Worker entry point (Default class)
- ✅ `src/router.py` — simple decorator-based router
- ✅ `src/llm.py` — MiniMax M3 wrapper (Anthropic API format)
- ✅ `src/handlers/` — health, version, llm (test), scout (manual + cron), scheduled
- ✅ `src/lib/{log,response}.py` — structured JSON logger + JSON response helpers
- ✅ `tests/` — pytest với mocked LLM (9 tests)
- ✅ `pyproject.toml` — deps + ruff + mypy + pytest config
- ✅ `.github/workflows/ci.yml` — lint + test on push/PR
- ✅ `.github/workflows/deploy.yml` — auto-deploy + D1 migrations on push main
- ✅ `.env.example` — local dev env template
- ✅ `docs/SETUP.md` — chi tiết deploy guide

### Endpoints (sau khi deploy)
- `GET /` — landing
- `GET /api/health` — liveness + D1 ping
- `GET /api/version` — build info
- `POST /api/llm/test` — LLM connectivity test
- `POST /api/scout/run` — manual Scout trigger
- Cron `0 23 * * *` — Scout daily 06:00 Asia/Saigon

## Setup & Deploy

Xem chi tiết trong [docs/SETUP.md](./docs/SETUP.md) — hướng dẫn từng bước từ clone → wrangler login → D1/R2/KV create → secret put → deploy.

Tóm tắt nhanh:
```bash
git clone https://github.com/TungIT98/toolforge.git
cd toolforge
wrangler login
wrangler d1 create toolforge-db       # copy id vào wrangler.jsonc
wrangler r2 bucket create toolforge-tools
wrangler kv namespace create CACHE    # copy id vào wrangler.jsonc
wrangler secret put LLM_API_KEY       # MiniMax key
wrangler d1 migrations apply toolforge-db --remote
wrangler deploy
```

Xem thêm [AGENTS.md](./AGENTS.md) và [PRD.md](./PRD.md).

## Liên hệ

- Owner: Zui (TungIT98, @gnut_22)
- Repo: https://github.com/TungIT98/toolforge (private)
