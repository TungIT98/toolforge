# ToolForge 🛠️🎼

> **Six AI agents that collaborate end-to-end on Cloudflare Workers.**
> One pain point in → one published tool with landing page, ads, and customer-support bot out. ~30 seconds.

[**▶ Live demo · /showcase**](https://toolforge-api.tungit98.workers.dev/showcase) · [**👥 Meet the team · /agents**](https://toolforge-api.tungit98.workers.dev/agents) · [API · /api/health](https://toolforge-api.tungit98.workers.dev/api/health)

---

## What this is

ToolForge is a working **multi-agent orchestration system** that runs entirely on Cloudflare's free tier. Six small LLM agents (Scout, Architect, Forge, Hype, Store, Helper) each own a single concern — research, spec, code, marketing, listings, support — and a thin `orchestrator` runs them in sequence, persisting every step to D1 for a live trace.

Hit one button on `/showcase` and watch the pipeline light up: each agent reports its own status, duration, and one-line summary. When the run finishes, the new tool is sitting in the catalog, the campaign is in the `campaigns` table, and the Telegram bot is ready to take orders.

```text
           ┌──────────────────────────────────────────┐
           │  POST /api/orchestrator/run             │
           │  { "input": "MMOers reup TikTok by hand" }│
           └──────────────────┬───────────────────────┘
                              │
              ┌───────────────▼────────────────┐
              │     Orchestrator (conductor)   │
              │   runs phases, records steps   │
              └───────────────┬────────────────┘
                              │
       ┌──────────┬───────────┼───────────┬──────────┐
       ▼          ▼           ▼           ▼          ▼
   ┌──────┐  ┌────────┐  ┌──────┐  ┌──────┐  ┌──────┐
   │Scout │→ │Architect│→ │Forge │→ │ Hype │→ │Store │
   │🔭    │  │📐       │  │⚒️    │  │📣    │  │🏪    │
   └──────┘  └────────┘  └──────┘  └──────┘  └──────┘
       │          │           │          │          │
       └──────────┴───────────┴──────────┴──────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Helper 🤝       │  (independent, runs on cron)
                    │  Telegram bot    │  replies to customers, sends daily
                    └──────────────────┘  report, delivers license keys
```

---

## Why I built this

I wanted to learn multi-agent orchestration by actually shipping it, not by reading papers. The hypothesis was boring but worth testing: a handful of *small, specialised* agents with explicit handoffs beats a single mega-prompt on real work, even when the total context is smaller. ToolForge is the experiment — the agents are real, the pipeline is real, the output is real (a tool record, a campaign, a Telegram bot reply).

Two things surprised me along the way, and they are now baked into the design:

1. **Modules over monoliths.** Each agent is one file (`src/<agent>/__init__.py`) with a tiny public surface. The orchestrator never reaches into agent internals — it calls `generate_spec()`, `generate_campaign()`, `add_tool()`. This kept the test surface honest: 263 tests, almost all unit, no flaky integration.
2. **Persistence is the product.** Every phase writes a row to `pipeline_steps` *before* it starts and *after* it finishes. The showcase page just polls that table. No event bus, no Redis, no streaming. D1 + `setInterval(1500)` is enough.

If you want to see what the agents actually do, [open `/showcase`](https://toolforge-api.tungit98.workers.dev/showcase) and click *Run Pipeline*. The full trace is persisted in the repo at `src/orchestrator/__init__.py`.

---

## Quick start

You need `wrangler` (≥ 3.80) and a Cloudflare account. The whole thing runs on the free tier.

```bash
git clone https://github.com/TungIT98/toolforge.git
cd toolforge

# 1. Login
wrangler login

# 2. Provision infra
wrangler d1 create toolforge-db           # paste id into wrangler.jsonc
wrangler r2 bucket create toolforge-tools
wrangler kv namespace create CACHE        # paste id into wrangler.jsonc

# 3. Set secrets (the only required one for the showcase)
wrangler secret put LLM_API_KEY           # any Anthropic-format key
# optional: TAVILY_API_KEY, ADMIN_API_KEY, OWNER_TELEGRAM_*, SEPAY_*

# 4. Apply migrations and deploy
wrangler d1 migrations apply toolforge-db --remote
wrangler deploy
```

Visit `https://toolforge-api.<your-subdomain>.workers.dev/showcase` and run the pipeline.

> **Local dev:** `pip install -e . && pytest` runs the full 263-test suite with mocked LLM. No Cloudflare account needed for tests.

---

## The six agents

| Agent | Role | Output | Module |
|---|---|---|---|
| **Scout** 🔭 | Find the pain | ranked pain points (severity, audience, opportunity) | `src/scout/analyzer.py` |
| **Architect** 📐 | Design the tool | 10-section markdown spec | `src/architect/spec_generator.py` |
| **Forge** ⚒️ | Build the code | Python/Tauri source + test + R2 binary | `src/forge/webhook.py` + `src/forge/build.py` |
| **Hype** 📣 | Sell the tool | landing copy, 2 FB ad variants, TikTok script (Vietnamese) | `src/hype/__init__.py` |
| **Store** 🏪 | Publish the catalog | tool record (status=`draft`, owner approves) | `src/store/admin.py` |
| **Helper** 🤝 | Talk to customers | Telegram auto-reply, license delivery, daily report | `src/helper/__init__.py` |

Each agent has its own **PERSONA.md** in `.mavis/agents/<name>/` with a system prompt, a colour, and a one-liner vibe. They are also rendered on the live [`/agents`](https://toolforge-api.tungit98.workers.dev/agents) roster page. The orchestrator doesn't know or care what's inside those prompts — it just calls functions.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| **Runtime** | Cloudflare Workers (Python / pyodide) | Free tier, 30s CPU/request, edge deploys |
| **Database** | D1 (SQLite at the edge) | Same free tier, transactional, JOIN-friendly |
| **Storage** | R2 (S3-compatible) | Free egress for tool binaries |
| **Cache** | Workers KV | Session/rate-limit counters |
| **Frontend** | Pages (React/Vite) + inline HTML for `/showcase` | One repo, no build step for the demo |
| **LLM** | MiniMax M3 (`https://api.minimaxi.com/anthropic`) via Anthropic API format | 450K context, generous limits, sub-second p50 |
| **Desktop tools** | Tauri 2.x binaries built on GitHub Actions (`windows-latest`) | < 10 MB, signs on CI |
| **Payments** | SePay + VietQR | VietQR deep-link, webhook → license |
| **Support** | Telegram Bot API via direct `httpx` (no library) | One file, ~150 LOC |
| **Auth** | API-key header (`X-Admin-Key`) for admin endpoints | YAGNI until v2 |

Cost for the showcase: **$0/mo** (entirely free tier). Cost at 1k daily users: **~$65–165/mo** — see `docs/COST.md` for the breakdown.

---

## How a run actually works

1. **Client hits `POST /api/orchestrator/run`** with `{ "input": "...", "trigger": "showcase" }`.
2. `dispatch()` in `src/router.py` configures CORS from `env.ALLOWED_ORIGINS`, generates a `X-Request-Id`, and routes to `orchestrator.run()`.
3. The orchestrator inserts a row into `pipeline_runs` and a row per phase into `pipeline_steps`, then loops through **Scout → Architect → Forge → Hype → Store**. Each phase:
   - sets its row to `running` + timestamp
   - calls the agent's pure function
   - sets the row to `success` / `failed` + duration + one-line summary + truncated result
4. The showcase page polls `GET /api/orchestrator/run/{id}` every 1.5 s and re-renders the trace.
5. On success, the new `tool_id` is in the run row and the tool is queryable via `GET /api/store/tools/{id}`.

No background workers, no queues, no event bus. The whole run lives inside one HTTP request, and CF Workers' 30 s wall-time is the only ceiling. In practice the pipeline finishes in 15–25 s with a 450K-context model.

---

## What I learned (the honest version)

These are the things that cost me a day each. I'm writing them down so the next person doesn't pay the same tuition.

- **Module state on CF Workers persists across requests in the same isolate.** Good for caches, dangerous for config. CORS origins and request-id have to be *set on every request* via `configure_cors(env=env)` — never assume first-request values carry over. This is now enforced in `dispatch()`.
- **`router.py` was importing 4 of 11 handler modules.** Everything else 404'd in production while tests passed (they bypass the router). The fix: an explicit import block in `dispatch()` with a comment that says "must import ALL handler modules" and a regression test that asserts every handler module has at least one route registered. See `tests/test_router.py`.
- **D1 (and the `FakeD1` we use in tests) doesn't support `COUNT()`, `SUM()`, or `DATE()` aggregations** in the way you'd expect. The pattern that works: fetch rows with `.all()`, then aggregate in Python. We hit this in the Helper daily report and in the Hype stats endpoints.
- **Mock LLM routing is order-sensitive.** The Hype system prompt contains the word "spec", so a naive mock that decides which fake response to return by keyword needs to check Hype *before* Architect, or the tests are silently lying.
- **Hype's `tool_id` had to be derived from `tool_name` *before* the pipeline started**, so the campaign record could reference the same id the Store phase would later insert. Otherwise the campaign pointed at a tool that didn't exist yet.
- **The user wanted less monitoring, not more.** I built KV-backed error logging + admin endpoints + a severity histogram. The user cut all of it. Cloudflare's native observability (stdout → logs dashboard) is enough for a project at this scale. `X-Request-Id` is the only thing that survived the review, and it's the only one that earns its place on the live demo.
- **Cron triggers have hard limits on the free tier: 5 per account.** Pick the 5 that actually matter. Mine: Scout daily, Helper daily report, Hype daily ad report. Architect's "stale handoff" check and Forge's "approved handoff" check were theoretical and got cut.
- **Vietnamese-first UI was a constraint, not a style choice.** The target user is a Vietnamese MMO creator, not a global SaaS buyer. All the LLM prompts, all the auto-replies, all the landing copy are Vietnamese. Translating the agents to English was a non-goal.

---

## Project layout

```
toolforge/
├── src/
│   ├── worker.py               # CF Worker entry point (class Default)
│   ├── router.py               # method+path → handler (must import all handlers!)
│   ├── llm.py                  # MiniMax M3 client (Anthropic format)
│   ├── scout/                  # 🔭 pain-point analyzer
│   ├── architect/              # 📐 spec generator
│   ├── forge/                  # ⚒️ code gen + Tauri build
│   ├── hype/                   # 📣 campaign generator
│   ├── store/                  # 🏪 catalog + admin
│   ├── helper/                 # 🤝 Telegram bot
│   ├── orchestrator/           # 🎼 5-phase pipeline runner
│   ├── builder/                # 🛠️ user-facing "describe → build" flow
│   ├── handlers/               # HTTP entry points (47 endpoints)
│   └── lib/                    # response, log, rate_limit, telegram, monitoring
├── migrations/                 # 5 D1 migrations
├── tests/                      # 263 tests, all unit, mocked LLM
├── .mavis/agents/<name>/       # PERSONA.md per agent (system prompt + vibe)
├── .github/workflows/          # CI + deploy
├── web/                        # React/Vite frontend (optional)
└── docs/                       # SETUP, SMOKE-TEST, COST
```

---

## Roadmap

- [x] **P0** — Worker + LLM wrapper + D1 + CI
- [x] **P1** — Scout + Architect + Forge (E2E test)
- [x] **P2** — Store API + Landing + SePay + Admin
- [x] **P3** — Builder Tool (user-facing describe → build)
- [x] **P3.5** — Hype + Orchestrator + Showcase demo
- [x] **P3.7** — Agency-agents patterns (PERSONA.md frontmatter + /agents roster)
- [ ] **P4** — Tauri build pipeline on GitHub Actions → R2 → signed URL
- [ ] **P4.5** — Freemium tracking for Builder (3 free / day)
- [ ] **P5** — Helper Telegram bot live (waiting on owner bot token)
- [ ] **P6** — Public marketplace at `toolforge.vn`

---

## Contributing

Issues and PRs welcome. The agents in `.mavis/agents/<name>/` are designed to be edited in isolation — change a persona, re-run `/showcase`, watch the live trace pick up the new behaviour. That's the whole feedback loop.

If you want to add a 7th agent, the contract is:

1. Create `src/<your_agent>/__init__.py` with one public async function.
2. Create a `PERSONA.md` in `.mavis/agents/<your_agent>/`.
3. Add a `_phase_<your_agent>` function in `src/orchestrator/__init__.py` and append it to `PHASES`.
4. Add a row in `migrations/0006_<your_agent>.sql` if you need new tables.
5. Add a phase card in `SHOWCASE_HTML` in `src/handlers/showcase.py`.
6. Write at least one test that calls the function directly with a mocked LLM.

---

## Author

**Built by [Zui](https://github.com/TungIT98)** — Vietnamese AI engineer, currently shipping ToolForge and a couple of other things at the edge.

I write about the messy middle of building AI systems in production (Vietnamese + English) at [erocathanh.com](https://erocathanh.com). No newsletter, no funnel — just a blog if you want to follow along.

---

## License

MIT — see [LICENSE](./LICENSE). Build something cool with it.
