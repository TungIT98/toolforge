# ToolForge — PRD v0.1 (Draft)

> **Status**: Draft, chờ owner (Zui) duyệt.
> **Date**: 2026-07-27
> **Author**: Mavis (orchestrator agent)

---

## 1. Vision

Một **cỗ máy tự động** vận hành cả 2 đầu của thị trường tool MMO/creator Việt:

- **Owner Brain (internal)**: AI agent team tự research pain point → design tool → code → list lên store → viết quảng cáo → support khách. Owner chỉ cần duyệt & approve tại 2 checkpoint.
- **Builder Tool (external)**: User cuối (MMO-er, TikToker, Reuper, người làm content) mô tả "tôi cần tool A" bằng tiếng Việt → AI build tool desktop/web trong 1 giờ → dùng ngay hoặc mua license.

**Network effect**: user dùng Builder Tool → phát hiện pain point mới → Brain research → list tool mới lên Store → user khác mua. Càng nhiều user, càng nhiều data, Brain càng thông minh.

## 2. Value Proposition

| Đối tượng | Pain hiện tại | ToolForge giải quyết |
|---|---|---|
| **Owner (Zui)** | Tự research + dev + marketing mỗi tool, tốn tuần | Brain team tự làm, owner chỉ duyệt |
| **MMO-er / creator** | Cần tool nhỏ, không ai làm, phải tự code hoặc thuê | Mô tả bằng tiếng Việt → có tool trong 1h |
| **Affiliate / shop khác** | Muốn bán tool nhưng không biết dev | Resell tool từ marketplace ToolForge (P6+) |

## 3. Competitor analysis (snapshot 2026-07-27)

### aff.1touch.pro (Aff Store)
- Owner: Nguyễn Thái (Facebook: nqthaivl.1982)
- Stack: PHP thuần + Bootstrap 4 + jQuery, KHÔNG dùng WordPress (khác với 1touch.pro chính)
- 20+ tool đang list, tất cả cho MMO/creator Việt
- Giá: "Miễn phí" đến 1.000.000 VNĐ
- Pattern: 1 tool = 1 bài toán nhỏ, giao ngay, support qua Facebook
- **Weakness**: hoàn toàn manual, không scale, không có AI

### ToolForge differentiation
- AI auto-research → suggest tool nên build tiếp theo
- AI auto-build + test → giảm 80% effort
- AI auto-marketing → A/B test copy, đo conversion
- AI auto-support → reply 30s qua Telegram
- Builder Tool cho user tự phục vụ → giảm ticket support

## 4. Two products

### 4.1. Owner Brain (Internal)

5 agents work theo pipeline:

```
Scout → Architect → [Owner duyệt] → Forge → [Owner duyệt] → Hype → Store → Helper
```

| Agent | Mô tả | Output |
|---|---|---|
| **Scout** 🔭 | Scan MMO/creator community (TikTok comments, Telegram groups, YouTube reup channels, diễn đàn MMO VN) → trích xuất top pain point/tuần | Brief markdown: pain point + audience + estimated market size |
| **Architect** 📐 | Nhận brief từ Scout → viết spec kỹ thuật (features, stack, MVP scope, effort estimate) | Spec markdown: features + user flow + API contract + data model |
| **Forge** 🔥 | Nhận spec → generate code (Tauri/Python) → build .exe → test cơ bản → upload lên R2 | Code repo + binary R2 URL + test report |
| **Hype** 📣 | Nhận tool → viết copy landing page, post Facebook/TikTok, A/B 2 version, report conversion | Landing page + 2 ad variants + campaign report |
| **Helper** 🤝 | Reply khách qua Telegram/Facebook (cùng pattern 1Touch đang làm thủ công) | Auto-reply 30s, escalate phức tạp lên owner |

Owner duyệt tại 2 checkpoint:
1. Sau Architect, trước Forge (đảm bảo spec đúng)
2. Sau Forge, trước Hype (đảm bảo tool chạy được)

Mọi output khác chạy tự động.

### 4.2. Builder Tool (External)

Web app tại `builder.toolforge.vn` (hoặc domain tương tự):

- User đăng ký (email + password)
- Chọn "Tôi cần tool..." → chat với AI bằng tiếng Việt
- AI hỏi lại cho rõ (input/output, workflow, edge case) — max 5 câu hỏi
- AI generate code (Python + Flask/FastAPI cho web tool, hoặc Tauri shell cho desktop)
- Preview demo trong browser + cho tải .exe/.zip
- **Pricing**:
  - Free tier: 3 builds/tháng, chỉ web tool, watermark
  - Pro: $5/tháng, unlimited builds, desktop tool, no watermark

## 5. Kiến trúc tổng thể

```
┌─────────────────────────────────────────────────────┐
│                TOOLFORGE PLATFORM                    │
├─────────────────────────────────────────────────────┤
│  Frontend (Cloudflare Pages)                         │
│  • aff.toolforge.vn       → Store (giống aff.1touch) │
│  • builder.toolforge.vn  → Builder Tool              │
│  • admin.toolforge.vn    → Dashboard cho owner       │
├─────────────────────────────────────────────────────┤
│  Backend (Cloudflare Workers + D1 + R2 + KV)         │
│  • /api/store/*         → catalog, search, payment  │
│  • /api/builder/*       → chat, code-gen, build job │
│  • /api/admin/*         → approve, stats, agents    │
│  • /api/license/*       → activate, verify           │
├─────────────────────────────────────────────────────┤
│  Agent Layer (Cloudflare Workers + Cron Triggers)    │
│  • scout-agent          → 06:00 daily scan           │
│  • forge-agent          → triggered by Architect     │
│  • hype-agent           → triggered by Forge done    │
│  • helper-agent         → Telegram webhook           │
├─────────────────────────────────────────────────────┤
│  Build Pipeline (R2 + GitHub Actions)                │
│  • forge-runner         → Build Tauri → upload R2    │
│    Return signed URL                                  │
├─────────────────────────────────────────────────────┤
│  LLM (MiniMax M3 via api.minimaxi.com/anthropic)     │
│  Brain for tất cả agents                             │
├─────────────────────────────────────────────────────┤
│  External: SePay webhook, Telegram Bot, FB Page      │
└─────────────────────────────────────────────────────┘
```

## 6. Tech stack (locked)

| Layer | Choice | Reason |
|---|---|---|
| Frontend | Cloudflare Pages + React (Vite) | Free, edge CDN, owner quen |
| Backend | Cloudflare Workers (Python pyodide) | Free tier generous |
| DB | Cloudflare D1 (SQLite) | Free, đủ cho catalog, payment log |
| Storage | Cloudflare R2 | File tool (.exe), 10GB free |
| Cache/Session | Cloudflare KV | Session, rate limit, hot data |
| LLM | MiniMax M3 (`minimax/MiniMax-M3`, 450K context) | Sẵn credential |
| Build runner | GitHub Actions | Free 2000 mins/tháng, build Tauri |
| Desktop tool | Tauri (Rust + WebView) | Nhẹ hơn Electron 10×, file < 10MB |
| Payment | SePay webhook + VietQR | Free, auto-detect ck |
| Notification | Telegram Bot | Free, owner quen |
| Auth | Email + password + license key | Đơn giản, không cần OAuth |

## 7. Phases (12 tuần MVP)

| Phase | Tuần | Output | Checkpoint |
|---|---|---|---|
| **P0: Setup** | 1 | Repo + CI/CD + LLM wrapper + memory layer | Deploy thử 1 endpoint |
| **P1: Owner Brain MVP** | 2-3 | Scout + Architect + 1 tool đầu tiên (copy Capcut Reup) | List + bán được 1 tool |
| **P2: Store** | 4-5 | aff.toolforge.vn hoàn chỉnh, payment, license | 10 sales thật |
| **P3: Builder Tool MVP** | 6-8 | builder.toolforge.vn, user chat + AI build web tool | 5 builds thành công |
| **P4: Build Pipeline** | 9-10 | GitHub Action build Tauri → R2, auto-sign | Tool desktop chạy được |
| **P5: Scale agents** | 11-12 | Hype + Helper + full pipeline, 5 tools auto-gen | Brain chạy 90% tự động |
| **P6: Marketplace** | 13+ | User khác upload tool, revenue share 70/30 | 1 user upload thành công |

## 8. Cost estimate

| Hạng mục | MVP/tháng | Scale (100+ user)/tháng |
|---|---|---|
| Cloudflare Workers/Pages/D1/R2/KV | $0 | $0 (vẫn free tier) |
| GitHub Actions | $0 | $0 (2000 min/tháng) |
| Domain `toolforge.vn` | ~$1.25 ($15/năm) | $1.25 |
| MiniMax LLM | $50-150 | $200-400 |
| SePay | $0 (chỉ phí ck ngân hàng) | $0 |
| **Tổng** | **$51-151** | **$201-401** |

**Break-even**: ~50 sales tool/tháng × 500K VNĐ = 25M VNĐ/tháng (~$1000 USD).

## 9. Risks & Mitigations

| Risk | Mức độ | Mitigation |
|---|---|---|
| AI generate code desktop chất lượng kém | Cao | Bắt đầu với web tool (P3), sau mới Tauri (P4). Manual test trước khi list. |
| Legal/TOS (antidetect, captcha) | Trung bình | Tránh niche vi phạm ở MVP, focus tool productivity hợp lệ. Có disclaimer. |
| Vietnam market niche nhỏ | Trung bình | Mở rộng sang Indo, Brazil sau khi prove concept (post-MVP). |
| LLM hallucination trong spec/code | Trung bình | Bắt buộc Architect review + Forge có test gate. |
| Anthropic/MiniMax API limit | Thấp | Có fallback Gemini/Claude direct. |
| Owner không duyệt kịp (bottleneck) | Trung bình | Auto-approve nếu confidence > 0.9 (sau P5). |

## 10. Agent Team — chi tiết

Xem PERSONA từng agent trong `.mavis/agents/<name>/PERSONA.md`. Tóm tắt:

| Agent | Home | Trigger | Output | Owner duyệt? |
|---|---|---|---|---|
| `scout` | `.mavis/agents/scout/` | Cron 06:00 daily | Brief markdown | Không (info only) |
| `architect` | `.mavis/agents/architect/` | Manual (owner gọi) | Spec markdown | **Có** (checkpoint 1) |
| `forge` | `.mavis/agents/forge/` | Sau khi architect approved | Code + binary | **Có** (checkpoint 2) |
| `hype` | `.mavis/agents/hype/` | Sau khi forge approved | Copy + ads | Không (auto-post) |
| `helper` | `.mavis/agents/helper/` | Telegram webhook | Reply khách | Không (auto-reply) |

## 11. Open questions (chờ owner)

1. **Domain `toolforge.vn`**: owner mua chưa? Nếu chưa, mua ở P0.
2. **SePay account**: owner có sẵn chưa? Cần để integrate payment.
3. **Telegram bot token**: owner tạo qua @BotFather, cấp token cho Helper.
4. **MiniMax API key**: owner cấp qua `wrangler secret put MINIMAX_API_KEY`.
5. **First tool copy**: confirm chọn **Capcut Desktop Reup** của 1Touch (đề xuất).
6. **Builder Tool pricing**: confirm freemium (3 free, $5/mo pro) — đã chọn default.
7. **Marketplace phase**: confirm P6+ — đề xuất.

## 12. Success metrics

### MVP (sau 12 tuần)
- ≥ 5 tool auto-gen + list trên store
- ≥ 50 sales thật / tháng
- ≥ 10 user Builder Tool / tháng
- ≥ 1 tool từ Builder Tool được user submit lên marketplace
- Brain chạy ≥ 80% tự động (owner chỉ duyệt, không sửa tay)

### 6 tháng
- 20+ tool active trên store
- 200+ sales / tháng
- 100+ Builder Tool user
- $1000+ MRR

## 13. Changelog

- **v0.1 (2026-07-27)**: Initial draft, chờ owner duyệt.
