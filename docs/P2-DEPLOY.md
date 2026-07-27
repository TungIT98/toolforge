# P2 Deploy Guide — Store Frontend

> Hướng dẫn deploy `web/` (React + Vite) lên Cloudflare Pages, kết nối tới Worker backend.

## Prerequisites

- P0 đã deploy + smoke test OK
- P2.1 (Store API) đã deploy + seed data OK
- Node.js 20+ + npm

## 1. Install + build local

```bash
cd web
npm install
npm run build
# Output: dist/
npm run preview
# Mở http://localhost:4173 để xem
```

Test local với Worker dev (cần Worker chạy port 8787):
```bash
# Terminal 1: Worker
cd ../
wrangler dev

# Terminal 2: Frontend
cd web
npm run dev
# Mở http://localhost:3000
# Vite proxy tự route /api/* → http://localhost:8787
```

## 2. Deploy lên Cloudflare Pages

### Option A: Qua Dashboard
1. Vào https://dash.cloudflare.com → Workers & Pages → Create application → Pages → Connect to Git
2. Chọn repo `TungIT98/toolforge`
3. **Build settings:**
   - Framework preset: Vite
   - Build command: `npm run build`
   - Build output directory: `dist`
   - Root directory: `web`
4. **Environment variables:**
   - `VITE_API_BASE` = `https://toolforge-api.<email-prefix>.workers.dev` (URL Worker của anh)
5. Save and Deploy

### Option B: Qua CLI
```bash
cd web
npm install -g wrangler
wrangler pages deploy dist --project-name toolforge-web
```

## 3. Sau khi deploy

Cloudflare Pages sẽ cho URL dạng `https://toolforge-web.pages.dev`. Custom domain:
1. Vào Pages project → Custom domains
2. Thêm `aff.toolforge.vn` (anh cần mua domain trước)
3. Cloudflare tự động issue SSL + DNS

## 4. Test E2E

1. Mở https://toolforge-web.pages.dev/
2. Check hero + search + filter render
3. Click 1 tool → xem detail page
4. Network tab: request `/api/store/tools` phải trả 200 + JSON

## 5. First-time seed

Nếu Worker backend chưa có data, gọi:
```bash
curl -X POST https://toolforge-api.<email-prefix>.workers.dev/api/store/seed
# → { ok: true, seeded: { inserted: 7, ... } }
```

## 6. Custom domain (optional)

Sau khi deploy Pages + có URL, custom domain:
- DNS: CNAME `aff.toolforge.vn` → `toolforge-web.pages.dev`
- Hoặc dùng Cloudflare DNS (nếu domain đã add vào Cloudflare)

## 7. Troubleshooting

### Lỗi CORS
Nếu frontend và backend khác domain, cần enable CORS trong Worker. Hiện tại Worker đã có CORS headers default — kiểm tra Network tab nếu request bị block.

### Lỗi "API_BASE not set"
Set biến `VITE_API_BASE` trong Cloudflare Pages dashboard (Settings → Environment variables).

### Lỗi 404 trên `/tools/:id`
Pages cần config SPA fallback. Trong Pages dashboard → Settings → Builds → Build output: tạo file `_redirects` trong `public/` với content `/* /index.html 200`.
