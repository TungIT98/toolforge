# ToolForge — Project AGENTS.md

> Consumed by orchestrator agents (Mavis primary, mavis, coder, general) when working in this repo.

## Project identity

- **Name**: ToolForge
- **Tagline**: AI agent platform tự động research + build + list software tools cho thị trường MMO/creator Việt Nam.
- **Owner**: Zui (TungIT98, @gnut_22)
- **Repo**: https://github.com/TungIT98/toolforge (private)
- **Created**: 2026-07-27
- **Status**: P0 setup (week 1 of 12)

## What this project does

ToolForge giải quyết 2 vấn đề song song:

1. **Owner Brain (internal)** — Một agent team 5 con tự động vận hành một store bán tool MMO/creator giống aff.1touch.pro nhưng thay vì 1 ông chủ + vài dev làm tay, AI team lo hết từ research → design → build → list → marketing → support.
2. **Builder Tool (external)** — Web app cho user cuối (MMO-er, TikToker, content creator) mô tả "tôi cần tool A" bằng tiếng Việt → AI build trong 1 giờ.

Combo = network effect: user dùng Builder Tool → phát hiện pain point mới → Brain research → list tool mới lên Store → user khác mua.

## Tech stack (locked decisions 2026-07-27)

| Layer | Choice | Reason |
|---|---|---|
| Frontend | Cloudflare Pages + React (Vite) | Free edge CDN, owner quen |
| Backend | Cloudflare Workers (Python via pyodide / Node.js) | Free tier generous, có kinh nghiệm |
| DB | Cloudflare D1 (SQLite) | Free, đủ cho catalog + payment log |
| Storage | Cloudflare R2 | File tool (.exe), 10GB free |
| Cache/Session | Cloudflare KV | Session, rate limit, hot data |
| LLM | MiniMax M3 via `https://api.minimaxi.com/anthropic` | Sẵn credential, 450K context |
| Build runner | GitHub Actions | Free 2000 mins/tháng, build Tauri |
| Desktop tool | Tauri (Rust + WebView) | Nhẹ hơn Electron 10x, file < 10MB |
| Payment | SePay webhook + VietQR | Free, tự động detect ck |
| Notification | Telegram Bot | Free, owner có kinh nghiệm |
| Auth | Email + password + license key | Đơn giản, không cần OAuth |

## File layout

```
toolforge/
├── AGENTS.md                # File này (consumed by orchestrator)
├── PRD.md                   # Tài liệu kỹ thuật đầy đủ
├── README.md                # Overview cho người mới
├── .gitignore
├── docs/                    # Spec, decisions, meeting notes
├── src/                     # Source code (P2+)
└── .mavis/                  # Agent home (NOT .mavis/agents/ global)
    └── agents/
        ├── scout/           # Agent 1: research pain point từ MMO/creator community
        ├── architect/       # Agent 2: viết spec kỹ thuật từ brief
        ├── forge/           # Agent 3: generate code + build .exe
        ├── hype/            # Agent 4: viết copy + post quảng cáo
        └── helper/          # Agent 5: reply khách qua Telegram/Facebook
```

## Agent team (5 agents)

Mỗi agent là một Mavis instance riêng, có PERSONA + context + memory riêng. Agent home = `toolforge/.mavis/agents/<name>/` (KHÔNG `~/.mavis/agents/`).

| Agent | Role | Trigger | Output |
|---|---|---|---|
| `scout` 🔭 | Research | Cron 06:00 daily | Top 10 pain points → `scout/data/briefs/<date>.md` |
| `architect` 📐 | Spec | Manual (owner gọi) | Spec kỹ thuật → `architect/data/specs/<id>.md` |
| `forge` 🔥 | Build | Manual approve spec | Code + test report + R2 URL → `forge/data/builds/<id>/` |
| `hype` 📣 | Market | Trigger khi Forge done | Copy + post + report → `hype/data/campaigns/<id>/` |
| `helper` 🤝 | Support | Telegram webhook | Reply khách → `helper/data/conversations/` |

### Workflow pipeline

```
Scout → Architect → [Owner duyệt] → Forge → [Owner duyệt] → Hype → Store → Helper
   ↓         ↓                          ↓                      ↓        ↓        ↓
 brief     spec                      code+exe             copy+ads  live    reply
```

Owner (Zui) làm checkpoint ở 2 điểm: approve spec (trước khi Forge code) và approve build (trước khi Hype post). Mọi output khác chạy tự động.

## Build & deploy (khi có code)

- **Local dev**: (chưa có ở P0, sẽ setup ở P1)
- **Deploy**: `wrangler deploy` cho Workers, `wrangler pages deploy` cho Pages
- **Build Tauri**: GitHub Action tự động khi tag release

## Phases (12 tuần MVP)

| Phase | Tuần | Output | Checkpoint |
|---|---|---|---|
| **P0: Setup** | 1 | Repo + CI/CD + LLM wrapper + memory layer | Deploy thử 1 endpoint |
| **P1: Owner Brain MVP** | 2-3 | Scout + Architect + 1 tool đầu tiên (copy Capcut Reup) | List + bán được 1 tool |
| **P2: Store** | 4-5 | aff.toolforge.vn hoàn chỉnh, payment, license | 10 sales thật |
| **P3: Builder Tool MVP** | 6-8 | builder.toolforge.vn, user chat + AI build web tool | 5 builds thành công |
| **P4: Build Pipeline** | 9-10 | GitHub Action build Tauri → R2, auto-sign | Tool desktop chạy được |
| **P5: Scale agents** | 11-12 | Hype + Helper + full pipeline, 5 tools auto-gen | Brain chạy 90% tự động |

## Conventions

### Code
- Python 3.11+ cho backend Workers (pyodide)
- TypeScript cho frontend Pages
- Rust cho Tauri desktop
- Lint: ruff (Python), eslint + prettier (TS)
- Format: PEP 8 + Google docstring

### Git
- Branch: `main` (production) + `feat/<scope>` cho features
- Commit message: Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`)
- PR: small, 1 commit = 1 concept, review bởi Mavis (auto) hoặc owner

### Memory
- Project memory: file này (AGENTS.md) + topic files trong `docs/`
- Agent memory: mỗi agent có `memory/MEMORY.md` riêng
- User memory: `~/.mavis/memory/user.md` (global, không ghi project-specific)

### Secrets
- KHÔNG BAO GIỜ echo secret trong chat, log, code
- Tất cả secret: Cloudflare Worker secrets (`wrangler secret put`)
- GitHub Actions secrets: `CF_API_TOKEN`, `R2_ACCESS_KEY`, `MINIMAX_API_KEY`
- Owner set trực tiếp qua `gh secret set` / Cloudflare dashboard

### Vietnamese-first
- Tất cả content (copy, doc, comment) bằng tiếng Việt
- Code/identifier bằng tiếng Anh
- Agent system prompt: tiếng Việt, tone dân giã như marketing agent

## Current status (2026-07-27)

- [x] Repo tạo (private) — https://github.com/TungIT98/toolforge
- [x] Folder structure
- [x] 5 agent folders + subfolders
- [ ] Agent PERSONA + context + RBAC (in progress)
- [ ] P0 setup tasks

## Open questions (cho owner)

1. Domain `toolforge.vn` chưa mua — owner confirm tên domain + mua khi ready
2. SePay account — owner confirm có sẵn chưa
3. Telegram bot — owner tạo + cấp token cho Helper
4. MiniMax API key — owner cấp qua `wrangler secret put`
5. First tool "copy" — confirm chọn **Capcut Desktop Reup** của 1Touch (đề xuất)

## Related docs

- `PRD.md` — Tài liệu kỹ thuật đầy đủ (PRD v0.1)
- `docs/decisions/` — ADRs (Architecture Decision Records)
- `docs/research/` — Market research, competitor analysis
- `.mavis/agents/<name>/PERSONA.md` — Persona từng agent
- `.mavis/agents/<name>/context.md` — Context làm việc từng agent
