# ToolForge — Setup Guide (P0)

> Hướng dẫn deploy ToolForge API lên Cloudflare Workers từ đầu.
> Đọc trước khi chạy `wrangler deploy`.

## 1. Prerequisites

- **Cloudflare account** (free tier OK): https://dash.cloudflare.com/sign-up
- **Node.js 20+** + npm
- **Python 3.11+** (cho local dev/test)
- **Git** + GitHub account
- **MiniMax API key** (đã có sẵn)

## 2. Clone & install

```bash
git clone https://github.com/TungIT98/toolforge.git
cd toolforge
npm install -g wrangler
pip install -e ".[dev]"
```

## 3. Cloudflare setup (one-time)

### 3.1. Login Wrangler
```bash
wrangler login
```
Sẽ mở browser để auth. Sau khi xong, wrangler sẽ lưu token.

### 3.2. Tạo D1 database
```bash
wrangler d1 create toolforge-db
```
Output sẽ cho ra `database_id`. Copy id đó vào `wrangler.jsonc`:
```jsonc
"d1_databases": [{
  "binding": "DB",
  "database_name": "toolforge-db",
  "database_id": "<paste-id-here>",   // ← UPDATE
  ...
}]
```

### 3.3. Tạo R2 bucket
```bash
wrangler r2 bucket create toolforge-tools
```

### 3.4. Tạo KV namespace
```bash
wrangler kv namespace create CACHE
```
Output cho ra `id`. Copy vào `wrangler.jsonc`:
```jsonc
"kv_namespaces": [{
  "binding": "CACHE",
  "id": "<paste-id-here>"   // ← UPDATE
}]
```

### 3.5. Set secrets
```bash
# MiniMax API key (BẮT BUỘC)
wrangler secret put LLM_API_KEY
# Nhập: sk-cp-...

# Telegram bot (P5+, optional cho P0)
wrangler secret put OWNER_TELEGRAM_BOT_TOKEN

# Owner chat ID (P5+)
wrangler secret put OWNER_TELEGRAM_CHAT_ID
```

## 4. Local dev

```bash
# Copy env file
cp .env.example .env
# Edit .env, fill LLM_API_KEY

# Run tests (mocked LLM, không cần API key thật)
pytest

# Run local worker (cần wrangler + thư mục .wrangler/)
wrangler dev
# Mở http://localhost:8787/api/health
```

## 5. Apply D1 migrations

```bash
# Local (dùng file SQLite local)
wrangler d1 migrations apply toolforge-db --local

# Remote (production)
wrangler d1 migrations apply toolforge-db --remote
```

## 6. Deploy

```bash
# Manual deploy
wrangler deploy

# Auto deploy: push lên main → GitHub Actions sẽ tự chạy
git push origin main
```

Worker URL sau khi deploy: `https://toolforge-api.<email-prefix>.workers.dev`

## 7. Smoke test

```bash
# Health
curl https://toolforge-api.<email-prefix>.workers.dev/api/health

# Version
curl https://toolforge-api.<email-prefix>.workers.dev/api/version

# LLM test (cần LLM_API_KEY đã set)
curl -X POST https://toolforge-api.<email-prefix>.workers.dev/api/llm/test

# Scout manual trigger
curl -X POST https://toolforge-api.<email-prefix>.workers.dev/api/scout/run
```

## 8. Verify cron triggers

Cron chạy 06:00 Asia/Saigon daily. Để test ngay:
```bash
# Manual trigger qua Cloudflare Dashboard:
# Workers & Pages → toolforge-api → Triggers → Cron Triggers → Run Test

# Hoặc trigger qua API:
curl -X POST "https://api.cloudflare.com/accounts/$CF_ACCOUNT_ID/workers/scripts/$WORKER_NAME/schedules?force=true" \
  -H "Authorization: Bearer $CF_API_TOKEN"
```

## 9. GitHub Secrets (cho CI/CD)

Vào repo → Settings → Secrets and variables → Actions, thêm:

| Secret | Value | Required |
|---|---|---|
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token (tạo tại https://dash.cloudflare.com/profile/api-tokens) với quyền edit Workers + D1 | YES |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID (xem ở dashboard URL) | YES |

## 10. Troubleshooting

### Lỗi "Module not found"
- Kiểm tra `wrangler.jsonc` → `main` đúng path → `src/worker.py`
- Kiểm tra imports dùng `from src.xxx` (KHÔNG dùng relative từ root)

### Lỗi "D1 binding missing"
- Đã chạy `wrangler d1 create` chưa?
- Đã update `database_id` trong `wrangler.jsonc` chưa?

### Lỗi "LLM 401 Unauthorized"
- Check key đúng format: `sk-cp-...`
- Set lại: `wrangler secret put LLM_API_KEY`

### Cron không chạy
- Free plan tối đa 5 cron/worker
- Check timezone: CF Cron dùng UTC. Asia/Saigon = UTC+7.
- Schedule hiện tại:
  - `0 23 * * *` = 06:00 Asia/Saigon daily
  - `0 15 * * *` = 22:00 Asia/Saigon daily
  - `0 14 * * *` = 21:00 Asia/Saigon daily

## 11. Cost estimate (free tier)

- Workers: 100K requests/day free
- D1: 5M row reads/day + 100K writes/day free
- R2: 10GB storage + 10M reads/month free
- KV: 100K reads/day + 1K writes/day free
- Cron: 5 triggers max free

Dùng hết free tier khi:
- > 100K API calls/day
- > 100K Cron runs/month (5 cron × ~30 runs/month = 150 runs, an toàn)
- > 1K D1 writes/day

## 12. Next steps (sau P0)

- P1: Build tool đầu tiên (Capcut Reup clone), test pipeline end-to-end
- P2: aff.toolforge.vn store + SePay + license system
- P3: builder.toolforge.vn cho user tự build
- P4: GitHub Action build Tauri → R2
