# Context cho Forge 🔥

## Build pipeline tổng thể

```
[Architect spec] → [Forge build local] → [GitHub Actions] → [R2 binary] → [Owner test] → [Hype launch]
   approved       code + test            CI/CD              signed URL     manual        ads
```

Forge chạy 2 bước đầu (build local + commit code). GitHub Actions chạy 2 bước sau (CI/CD + R2 upload) — có thể manual trigger hoặc auto khi tag.

## Local build env (Windows PC của owner)
- Node.js 20+ (cho Tauri frontend)
- Rust 1.75+ (cho Tauri backend)
- Python 3.11+ (cho Python tool, web tool)
- pnpm 8+ (cho JS deps)
- Tauri CLI 2.x
- pyinstaller 6+ (cho Python exe)
- Git + GitHub CLI + Wrangler CLI

## Tauri build gotcha
- Tauri 2.x cần WebView2 runtime trên Windows (đã có sẵn trên Win 10+)
- Bundle size: ~5-8 MB cho app đơn giản, ~15-20 MB nếu có video processing
- Cross-compile Linux từ Windows: cần WSL, dùng GitHub Actions thay vì local
- Code signing: chưa cần cho MVP (Windows SmartScreen warning OK)
- Auto-update: dùng `tauri-plugin-updater`, nhưng chưa cần ở P1

## Python build gotcha
- pyinstaller `--onefile` chậm khởi động (~3-5s) nhưng dễ distribute
- pyinstaller `--onedir` khởi động nhanh nhưng distribute cả folder
- Hidden import: thường cần cho `playwright`, `opencv`, `pydub`
- UPX compression: giảm 30% size nhưng tăng false-positive antivirus
- Build trên Windows cho ra `.exe`, trên Mac cho `.app`, cross-compile KHÔNG work

## Cloudflare Workers gotcha
- Python runtime = pyodide, KHÔNG phải CPython → một số stdlib không có (subprocess, multiprocessing, distutils)
- Workers free plan: 10ms CPU, 30s wall time → không chạy được ML inference lớn
- Cron Trigger: tối đa 5 cron/account → share giữa tất cả Worker
- D1: tối đa 10GB database, 5M row reads/day free
- R2: 10GB storage + 10M requests/month free
- KV: 100K reads/day + 1K writes/day free (writes đắt, dùng cache in-memory)

## GitHub Actions pattern
- Workflow file: `.github/workflows/build-<tool-id>.yml`
- Trigger: `workflow_dispatch` (manual) hoặc `push tag: v*`
- Runner: `ubuntu-latest` (free) — cross-compile Tauri Windows từ Linux CẦN hack, dùng Windows runner
- Cache: `actions/cache` cho `node_modules`, `target/`, `__pycache__`
- Artifact: upload `.exe`/`.dmg` lên GitHub Release

## R2 + license pattern
- Bucket: `toolforge-tools`
- Path: `<tool-id>/<version>/<binary>`
- Metadata: `tool-id`, `version`, `license-key`, `created-at`
- Signed URL: TTL 7 ngày (cho download page), 1 giờ (cho API call)
- License check: client gửi key + tool-id, server verify trong D1, return challenge

## Owner (Zui) preferences
- Code phải chạy được trên Windows 10/11 (64-bit) — đa số khách ToolForge dùng Windows
- Binary size < 50MB (ưu tiên < 20MB)
- Cold start < 5s
- KHÔNG dùng Docker (khách không cài Docker)
- License key dạng `XXXX-XXXX-XXXX-XXXX` (dễ đọc, dễ nhập)
- Auto-update qua R2 manifest (P5+)

## Anti-patterns
- ❌ Không dùng Electron (file 100MB+)
- ❌ Không dùng Docker
- ❌ Không hardcode license key trong binary (decompile là lộ)
- ❌ Không push binary lên git (dùng R2 + Release)
- ❌ Không dùng SSH/RDP để deploy (dùng CF CLI)
- ❌ Không test trên Mac (chưa cần ở MVP, owner dùng Windows)
