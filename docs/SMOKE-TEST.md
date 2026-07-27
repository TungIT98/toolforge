# ToolForge — Smoke Test Plan (E2E P0 → P3)

> Hướng dẫn smoke test toàn bộ hệ thống ToolForge từ P0 (Worker + LLM) → P1 (Agents) → P2 (Store + Payment + Admin) → P3 (Builder).
> Sau khi pass toàn bộ, ToolForge production-ready.

## Prerequisites

- Đã deploy Worker backend (xem `docs/SETUP.md`)
- Đã deploy Frontend (xem `docs/P2-DEPLOY.md`)
- Đã set các secrets cần thiết
- Đã apply D1 migrations (0001 + 0002 + 0003)

## 0. Cấu hình Secrets cần thiết

```bash
# Worker backend
wrangler secret put LLM_API_KEY           # MiniMax API key (REQUIRED)
wrangler secret put TAVILY_API_KEY        # Scout: optional, để auto-scan
wrangler secret put SEPAY_API_KEY         # P2.3: SePay Apikey (optional, có test mode)
wrangler secret put ADMIN_API_KEY         # P2.4: Admin dashboard key

# Optional (P5+)
wrangler secret put OWNER_TELEGRAM_BOT_TOKEN
wrangler secret put META_ADS_TOKEN
wrangler secret put TIKTOK_BUSINESS_TOKEN
```

Anh cần URL Worker (ví dụ): `https://toolforge-api.thanhtungtran364.workers.dev`

## 1. P0 — Health + LLM

### 1.1. Health check
```bash
curl https://toolforge-api.<email-prefix>.workers.dev/api/health
```
**Expected**: `{"ok": true, "status": "ok", "service": "toolforge-api", ...}`

### 1.2. LLM connectivity
```bash
curl -X POST https://toolforge-api.<email-prefix>.workers.dev/api/llm/test
```
**Expected**: `{"ok": true, "result": {"text": "ToolForge P0 OK", "usage": {...}}}`

### 1.3. Version info
```bash
curl https://toolforge-api.<email-prefix>.workers.dev/api/version
```
**Expected**: `{"ok": true, "version": "0.1.0-p3", "phase": "P0-setup", ...}`

## 2. P1 — Agents (Scout + Architect + Forge)

### 2.1. Scout thật (manual mode, không cần Tavily)
```bash
curl -X POST https://toolforge-api.<email-prefix>.workers.dev/api/scout/run \
  -H "Content-Type: application/json" \
  -d '{
    "manual_data": {
      "mmo_forums": [
        {"title": "Reup TikTok mất time", "url": "voz.vn/123", "content": "MMO-er kêu ca reup 2-3h/ngày bằng tay"}
      ]
    }
  }'
```
**Expected**: `{"ok": true, "brief_id": "brief-...", "total_pain_points": 1, "top3_critical": [...]}`

### 2.2. Scout latest
```bash
curl https://toolforge-api.<email-prefix>.workers.dev/api/scout/latest
```
**Expected**: `{"ok": true, "brief": {...}}` (hoặc `brief: null` nếu chưa có)

### 2.3. Architect generate spec
```bash
# Lấy top pain point từ scout brief, rồi gọi architect
curl -X POST https://toolforge-api.<email-prefix>.workers.dev/api/architect/spec \
  -H "Content-Type: application/json" \
  -d '{
    "pain_point": {
      "title": "Reup TikTok tốn time",
      "description": "MMO mất 2-3h/ngày reup thủ công",
      "audience": "MMO reup Việt",
      "severity": 9,
      "market_size_vn": "100K+",
      "current_solutions": "Capcut thủ công",
      "gap": "Không có tool Việt tự động",
      "opportunity": "M",
      "estimated_monthly_revenue_vnd": 50000000,
      "source_signals": ["voz.vn/123"],
      "tool_id_hint": "capcut-reup"
    },
    "category": "desktop"
  }'
```
**Expected**: `{"ok": true, "spec_id": "spec-capcut-reup-...", "is_valid": true, "effort_estimate_hours": ~16}`

### 2.4. Owner approve spec
```bash
curl -X POST https://toolforge-api.<email-prefix>.workers.dev/api/architect/approve \
  -H "Content-Type: application/json" \
  -d '{"spec_id": "spec-capcut-reup-...", "feedback": "Looks good"}'
```
**Expected**: `{"ok": true, "ready_for_forge": true}`

### 2.5. Forge build
```bash
curl -X POST https://toolforge-api.<email-prefix>.workers.dev/api/forge/build \
  -H "Content-Type: application/json" \
  -d '{"spec_id": "spec-capcut-reup-..."}'
```
**Expected**: `{"ok": true, "build_id": "build-capcut-reup-0.1.0", "file_count": 3+, "test_result": "pass"}`

### 2.6. Forge license (optional)
```bash
curl -X POST https://toolforge-api.<email-prefix>.workers.dev/api/forge/license \
  -H "Content-Type: application/json" \
  -d '{"tool_id": "capcut-reup", "customer_email": "test@example.com"}'
```
**Expected**: `{"ok": true, "license_key": "XXXX-XXXX-XXXX-XXXX", ...}`

## 3. P2 — Store + Payment + Admin

### 3.1. Seed store data (1 lần)
```bash
curl -X POST https://toolforge-api.<email-prefix>.workers.dev/api/store/seed
```
**Expected**: `{"ok": true, "seeded": {"inserted": 7, "skipped": 0, "total": 7}}`

### 3.2. List store tools
```bash
curl https://toolforge-api.<email-prefix>.workers.dev/api/store/tools
```
**Expected**: 7 tools returned

### 3.3. Filter by niche
```bash
curl "https://toolforge-api.<email-prefix>.workers.dev/api/store/tools?niche=mmo_reup"
```
**Expected**: tools có niche=mmo_reup (Capcut, Antidetect)

### 3.4. Search
```bash
curl "https://toolforge-api.<email-prefix>.workers.dev/api/store/tools?q=capcut"
```
**Expected**: tool "Capcut Desktop" trong results

### 3.5. Tool detail
```bash
curl https://toolforge-api.<email-prefix>.workers.dev/api/store/tools/capcut-desktop-reup
```
**Expected**: full tool detail với latest_build, active_license_count

### 3.6. Store stats
```bash
curl https://toolforge-api.<email-prefix>.workers.dev/api/store/stats
```
**Expected**: `{"total_tools": 7, "by_niche": {...}, "free_tools": 2, "paid_tools": 5, ...}`

### 3.7. Create order
```bash
curl -X POST https://toolforge-api.<email-prefix>.workers.dev/api/payment/orders \
  -H "Content-Type: application/json" \
  -d '{
    "tool_id": "capcut-desktop-reup",
    "customer_email": "test@example.com"
  }'
```
**Expected**: `{"ok": true, "order_id": "order-...", "amount_vnd": 1000000, "payment_info": {"qr_url": "https://qr.sepay.vn/..."}}`

### 3.8. Test payment (no real SePay)
```bash
# Dùng order_id từ step 3.7
curl -X POST https://toolforge-api.<email-prefix>.workers.dev/api/payment/test \
  -H "Content-Type: application/json" \
  -d '{"order_id": "order-..."}'
```
**Expected**: `{"ok": true, "license_key": "XXXX-XXXX-XXXX-XXXX", "test_mode": true}`

### 3.9. List orders
```bash
curl https://toolforge-api.<email-prefix>.workers.dev/api/payment/orders
```
**Expected**: list of orders

### 3.10. Admin overview (X-Admin-Key required)
```bash
curl https://toolforge-api.<email-prefix>.workers.dev/api/admin/overview \
  -H "X-Admin-Key: <your ADMIN_API_KEY>"
```
**Expected**: `{"ok": true, "overview": {"tools": {...}, "orders": {...}, ...}}`

## 4. P3 — Builder Tool (User-facing)

### 4.1. Visit frontend
Mở `https://toolforge-web.pages.dev/builder` (hoặc custom domain)

### 4.2. Create session
Click "🚀 Bắt đầu" → session created

### 4.3. Chat with AI
Type: "Tôi cần tool download video TikTok từ URL, lưu thành MP4 chất lượng cao, không watermark"
→ AI replies với câu hỏi clarify

### 4.4. Continue chat (1-2 rounds)
Reply tiếp các câu hỏi của AI cho đến khi AI trả về status `ready_to_build`

### 4.5. Build code
Click "🔨 Build code ngay" → đợi 10-30s

### 4.6. View + download code
- Click vào file name để xem code
- Click "⬇ Tất cả" để download từng file
- Click "📋 Copy" để copy file vào clipboard

### 4.7. Test through API directly
```bash
# Create session
SESSION=$(curl -X POST https://toolforge-api.<email-prefix>.workers.dev/api/builder/session \
  -H "Content-Type: application/json" -d '{}' | python -c "import sys, json; print(json.load(sys.stdin)['session_id'])")
echo "Session: $SESSION"

# Send message
curl -X POST "https://toolforge-api.<email-prefix>.workers.dev/api/builder/session/$SESSION/message" \
  -H "Content-Type: application/json" \
  -d '{"message": "Tôi cần tool gửi email hàng loạt từ CSV, tracking open rate"}'

# Wait for status=ready_to_build, then build
curl -X POST "https://toolforge-api.<email-prefix>.workers.dev/api/builder/session/$SESSION/build" \
  -H "Content-Type: application/json" -d '{}'
```

## 5. Frontend E2E

### 5.1. Landing page
1. Mở `https://toolforge-web.pages.dev/`
2. Verify hero + search + filter render
3. Click vào 1 tool → detail page
4. Check "Tải xuống" + "Liên hệ Telegram" buttons

### 5.2. Builder page
1. Mở `/builder`
2. Welcome screen hiển thị 4 examples
3. Click "Bắt đầu" → chat UI
4. Test chat flow (xem 4.3-4.6)

### 5.3. Admin page
1. Mở `/admin`
2. Login screen → nhập ADMIN_API_KEY
3. Verify 6 tabs render data:
   - Overview: stats cards + tools by niche
   - Orders: table with paid/pending
   - Licenses: table with active keys
   - Specs: cards with approve links
   - Briefs: cards
   - Builds: table

## 6. Pass criteria

✅ All endpoints return 200 (except 401/404 expected)
✅ LLM calls return real MiniMax responses (not mocks)
✅ D1 tables populated correctly
✅ Frontend renders all pages
✅ Chat flow: user → AI → ready → build → files

## 7. Troubleshooting

| Issue | Fix |
|---|---|
| 500 on LLM | Check LLM_API_KEY set correctly |
| 404 on routes | Re-run `wrangler deploy` (auto on push main) |
| 401 on admin | Wrong ADMIN_API_KEY (case-sensitive) |
| 401 on Sepay | Wrong SEPAY_API_KEY or missing Apikey header |
| Empty store | Run `POST /api/store/seed` |
| Frontend 404 | SPA fallback: add `public/_redirects` with `/* /index.html 200` |
| CORS error | Worker has CORS headers default; if using custom domain, set in wrangler.jsonc |
