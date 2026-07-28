# P4 — Tauri build pipeline

This document covers the **end-to-end flow** for turning generated code into a signed desktop binary that customers can download.

The flow has 4 steps and lives across **two systems** (Cloudflare Workers + GitHub Actions) sharing one D1 record (`builds` table) and one R2 bucket.

```text
   Customer/Owner                        Worker (CF)                  GH Actions runner           R2
        │                                    │                              │                     │
        │  POST /api/forge/build-binary      │                              │                     │
        │  { "build_id": "build-...-v0.1.0"} │                              │                     │
        │ ─────────────────────────────────► │                              │                     │
        │                                    │  POST .../actions/workflows/  │                     │
        │                                    │       build-tauri.yml/dispatches                  │
        │                                    │ ───────────────────────────► │                     │
        │                                    │  204 No Content (triggered)  │                     │
        │                                    │ ◄─────────────────────────── │                     │
        │   { status: "building",            │                              │                     │
        │     workflow_url, poll_url }       │   build job runs 5-10 min    │                     │
        │ ◄───────────────────────────────── │ ───────────────────────────► │                     │
        │                                    │                              │   aws s3 cp .exe     │
        │                                    │                              │ ───────────────────►│
        │                                    │                              │                     │
        │                                    │   POST /api/forge/webhook/built                    │
        │                                    │ ◄─────────────────────────── │                     │
        │                                    │   writes binary_path,        │                     │
        │                                    │   binary_url, size_bytes     │                     │
        │                                    │   to builds table            │                     │
        │  GET /api/forge/download/{id}      │                              │                     │
        │  (poll after a few min)            │                              │                     │
        │ ─────────────────────────────────► │                              │                     │
        │                                    │   generate fresh R2 signed   │                     │
        │                                    │   URL (7-day TTL)            │                     │
        │   { binary_url: "https://...r2...  │                              │                     │
        │     expires_in_days: 7 }           │                              │                     │
        │ ◄───────────────────────────────── │                              │                     │
```

## Why two systems?

- **Worker (Python on pyodide)** is great for HTTP, LLM orchestration, and serving signed URLs. It cannot run a 5–10 minute `cargo tauri build` — CF Workers have a 30 s wall-time per request.
- **GH Actions (`windows-latest` runner)** is great for long builds, with free 2 000 min/month for private repos. The build pushes the `.msi`/`.exe` to R2, then POSTs back to the Worker.
- **R2** stores the binaries. The Worker signs fresh URLs on every download request so the customer never sees an expired link.

## What you need to set

Before the pipeline will work, the owner must set **8 secrets** (most are R2 + GH):

```bash
# R2 (Cloudflare dashboard → R2 → Manage R2 API Tokens → Create token
#      with Object Read & Write on bucket `toolforge-tools`)
wrangler secret put R2_ACCOUNT_ID
wrangler secret put R2_ACCESS_KEY_ID
wrangler secret put R2_SECRET_ACCESS_KEY
wrangler secret put R2_BUCKET               # optional, defaults to "toolforge-tools"

# GitHub (Personal Access Token with `workflow` scope on TungIT98/toolforge)
wrangler secret put GITHUB_TOKEN
wrangler secret put GITHUB_REPO_OWNER       # optional, defaults to "TungIT98"
wrangler secret put GITHUB_REPO_NAME        # optional, defaults to "toolforge"
wrangler secret put WORKER_URL              # optional, falls back to workers.dev URL

# Webhook (shared with the GH Action; also used by /api/forge/webhook/built)
wrangler secret put WEBHOOK_SECRET
```

You can also set `ACCOUNT_SUBDOMAIN` (e.g. `tungit98`) as a `wrangler secret` if your Worker URL isn't `https://toolforge-api.<sub>.workers.dev`. The default is `tungit98`.

## Endpoints (P4)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/forge/build` | POST | P1 — generate code from an approved spec, write `test_result="pass"` to `builds` |
| `/api/forge/build-binary` | POST | **P4** — trigger GH Action `workflow_dispatch` to compile code → upload R2 |
| `/api/forge/webhook/built` | POST | **P4** — GH Action callback. Writes `binary_path` + `binary_url` + `size_bytes` to `builds` |
| `/api/forge/download/{build_id}` | GET | **P4** — return a fresh R2 signed URL (7-day expiry, re-signed every call) |
| `/api/forge/license` | POST | Generate a license key for a tool (called after payment) |
| `/api/forge/list` | GET | List recent builds |
| `/api/forge/get` | GET | Get one build by id (`?id=build-...`) |

## What the GH Action does

The workflow at `.github/workflows/build-tauri.yml` is invoked via `workflow_dispatch` with 5 inputs (`build_id`, `tool_id`, `version`, `callback_url`, `webhook_secret`).

Steps:
1. Check out the repo (so the workflow can find `src-tauri/`).
2. Set up Rust toolchain (`stable`, `x86_64-pc-windows-msvc`).
3. Patch `src-tauri/tauri.conf.json` with the new version.
4. Run `cargo tauri build --target x86_64-pc-windows-msvc` (this is the 5–10 min step).
5. Find the generated `.msi` (preferred) or `*setup*.exe`.
6. `aws s3 cp` to R2 at `s3://toolforge-tools/{tool_id}/{version}/setup.{ext}`.
7. `aws s3 presign` a 7-day URL.
8. POST to the callback URL with `X-Webhook-Secret` and the result JSON.
9. If the build fails, POST a failure payload so D1 records the error.

## Why a fresh signed URL on every download

`binary_url` written by the webhook is the URL the GH Action generated at build time — that signature is valid for 7 days. After that, downloads would 403.

Instead of trying to track expiry client-side, we **re-sign on every request** to `/api/forge/download/{build_id}`. The R2 SDK call is fast (sub-millisecond) and there's no client state to manage. The `cached_url` field in the response carries the old (potentially expired) URL for clients that want to see the difference during testing.

## Security

- **Webhook fail-closed.** If `WEBHOOK_SECRET` is not set in the Worker's env, `/api/forge/webhook/built` returns 503 and refuses to process. This is the right default — running with the secret unset would let anyone with the URL poison your build records.
- **HMAC compare.** `verify_webhook_secret()` uses `hmac.compare_digest` to avoid timing attacks. The test suite covers match, mismatch, empty, and `None` cases.
- **R2 signed URLs are read-only by construction.** The signing in `generate_signed_url()` builds a `GET` request signature. The same code path cannot be used to upload.

## Why no streaming / no queues

We considered pushing build events to a queue (Cloudflare Queues or SQS) and having a separate worker consume them. We cut it because:

- One HTTP request, one build, one callback. There's no fan-out.
- The GH Action already calls back when it finishes — the Worker doesn't need to poll.
- A queue adds an integration surface (IAM, DLQ, retries) that has to be tested, monitored, and paid for. The current design is "one round trip, one D1 row".
- The pipeline finishes in 5–10 min, well within the lifetime of a customer waiting for a download link.

## Open items for v2

- **Multi-platform build matrix** (macOS + Linux). Currently `windows-latest` only. Adding `macos-latest` would let the same build emit a `.dmg` for Apple Silicon.
- **Build artifact retention policy.** R2 has no built-in lifecycle rules. Old builds pile up. Plan: nightly cron that deletes `builds/` older than 90 days.
- **Re-build on spec change.** Today the owner has to manually call `/api/forge/build-binary` after editing a spec. A trigger from `/api/architect/spec` (status flip to `approved`) would close the loop.
- **Progress streaming.** Right now the customer has to poll `/api/forge/get`. A webhook subscription model (push to owner's Telegram via Helper) would be friendlier.

## Related

- `src/forge/build_orchestrator.py` — `trigger_github_workflow()`
- `src/forge/r2_uploader.py` — `generate_signed_url()`, `build_r2_path()`
- `src/forge/webhook.py` — `handle_build_complete()`, `verify_webhook_secret()`
- `src/handlers/forge.py` — HTTP entry points
- `.github/workflows/build-tauri.yml` — the GH Action
- `tests/test_forge_p4_endpoints.py` — 14 P4 endpoint tests
- `tests/test_forge_build.py` — 9 P4 internals tests (R2 signing, webhook, orchestrator)
- `tests/test_router.py` — router path-param tests
