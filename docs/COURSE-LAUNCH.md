# Course launch — Twitter thread + bio + post plan

Hướng Y pivot: ToolForge = case study cho course "Build AI Agency on Cloudflare Workers".

**Validation rule (Eroca framework):**
- Thread 50K+ impressions trong 7 ngày → build full course trên Gumroad ($199-999)
- Thread 10-50K → narrow audience, test angle mới
- Thread <10K → pivot topic hoặc đổi audience (corporate AI team chứ không indie?)

---

## Twitter bio (≤160 chars)

`Building ToolForge — 6 AI agents on Cloudflare Workers. Open source. Next: course on how to build yours. 🇻🇳`

`→ github.com/TungIT98/toolforge`

---

## Thread "I built 6 AI agents. Here's what I'd teach you." (10 tweets)

Tone: honest journey, specific numbers, "build in public". No hype. Cuối thread: soft CTA early access.

---

**1/10**

I spent 8 weeks building 6 AI agents that collaborate end-to-end on Cloudflare Workers.

The system takes a pain point → ~30s later you have a tool spec, generated code, a marketing campaign, and a Telegram bot ready to take orders.

Free + open source: github.com/TungIT98/toolforge

---

**2/10**

The 6 agents, each one file with one public function:

🔭 Scout — finds pain points from forums + trends
📐 Architect — writes a 10-section technical spec
⚒️ Forge — generates the code
📣 Hype — writes landing copy + ads + TikTok script
🏪 Store — publishes to the catalog
🤝 Helper — Telegram bot for customers

No framework. No LangChain. Just a 380-line orchestrator.

---

**3/10**

The orchestrator is the interesting part. It runs Scout → Architect → Forge → Hype → Store in sequence, and writes a row to a D1 table *before* each phase starts and *after* it finishes.

The showcase page just polls that table every 1.5s.

No event bus. No Redis. No streaming. Just SQL rows and HTTP.

---

**4/10**

Tech stack, one line:

Cloudflare Workers (Python/pyodide) + D1 + R2 + KV, LLM = MiniMax M3 via Anthropic format, Tauri 2 for desktop binaries, SePay for payments, Telegram for support.

Total monthly cost at MVP traffic: $0.
At 1k daily users: ~$65-165.

The free tier is real, not a marketing lie.

---

**5/10**

The bug I'm most embarrassed by:

My router was importing 4 of 11 handler modules. The other 7 returned 404 in production. Every test passed.

Cause: tests bypass the router. They call handlers directly. So missing imports only break in prod.

Fix: a regression test that asserts every handler file has at least one route registered.

Lesson: if your test doesn't exercise the same entry point as prod, you're testing the wrong thing.

---

**6/10**

3 things I cut after a critical self-review:

- KV-backed error logging (replaced by `console.log` → CF dashboard)
- /api/admin/errors endpoint (nobody looked at it)
- Severity histogram (over-engineering at 50 req/day)

What survived: X-Request-Id in every response header. Earning its place on the live trace.

Discipline of deleting working code is the actual win.

---

**7/10**

The honest accounting of my time:

- 2 weeks: pipeline + agents (the fun part)
- 1 week: D1/R2/KV integration + secrets (the grind)
- 2 weeks: deploy to Cloudflare + 10 CF Python gotchas (the rabbit hole)
- 1 week: polish + tests + docs (the invisible 30%)
- 2 weeks: launch assets (HN, Twitter, landing, screenshots)

Build = 30%. Ship = 70%. Most people quit at week 3.

---

**8/10**

What I'd teach differently if I started over:

1. Skip the Builder agent. Nobody asked for it. The pipeline is enough.
2. Set CORS at request start in `dispatch()`, not at module import. Module state persists across requests on Workers.
3. Write the showcase page before the 4th agent. Forces you to make the pipeline observable from day 1.
4. Mock the LLM from day 1. Don't burn $200 in API calls before your tests run in CI.

---

**9/10**

What I'd charge money for (the actual business):

A course teaching this exact build, end-to-end.

8 modules. 1 capstone. ToolForge as the live case study.

Target: AI engineers who want to ship their own SaaS but don't know how to start.

Estimated price: $199 standalone, $499 with community + code review, $999 with 1:1.

Launching only if this thread hits 50K impressions — that's my validation signal.

---

**10/10**

If you want early access (50% off, first cohort only), reply to this thread with the word "AGENCY".

I'll DM you the waitlist link.

If you're curious about the code first, the repo is at github.com/TungIT98/toolforge — 303 tests, full architecture, the "What I learned" section in the README is the real read.

Built by me. 🇻🇳

---

## Post plan

**Timing (the Hướng Y sweet spot):**
- Tue / Wed / Thu
- 8-10pm ICT (UTC+7) → US + SEA cùng đọc
- Hoặc 9-11am ET → US AI crowd + EU overlap

**First tweet visual:**
- Không cần. Text thread đủ.
- Nếu muốn: 1 screenshot `/showcase` page (đã có trong docs/screenshots/showcase.png)

**Hashtags (cuối tweet 1 only):**
`#AI #buildinpublic #cloudflare`

**Reply strategy first 12h:**
- Reply mọi retweet / quote trong 12h đầu
- Nếu câu nào hỏi 3+ lần → FAQ thread (pin vào profile)
- Nếu có 1 câu hỏi technical hay → write blog post dài

---

## Tracking plan

| Time | Metric | Action if hit | Action if miss |
|------|--------|---------------|----------------|
| 24h | Impressions, likes, RT | Continue engaging | Look at hook (tweet 1) |
| 48h | Replies with "AGENCY" count | Build waitlist page | Narrow audience angle |
| 7d | Total impressions | If 50K+ → build course on Gumroad | Pivot: corporate audience? Video instead? |
| 14d | Profile visits, new follows | If strong → commit $999 VIP | Drop course idea, return to ship-only |

**Tools for tracking:**
- Twitter Analytics (free, native)
- TweetDeck for first 24h monitoring
- Google Sheet: log daily impressions, replies, "AGENCY" count

---

## What NOT to do this week

- ❌ Don't build Gumroad page yet (premature, no validation)
- ❌ Don't write course content (chưa có demand signal)
- ❌ Don't post HN yet (cùng audience, dồn vào Twitter first)
- ❌ Don't promote erocathanh.com in tweets (bị gắn "self-promo")
- ❌ Don't cross-post to LinkedIn (khác audience behavior, làm sau)

## What TO do this week

- ✅ Post thread (Tue/Wed/Thu 8-10pm ICT)
- ✅ Reply "AGENCY" DMs trong 48h
- ✅ Pin thread trên profile
- ✅ Update GitHub repo description với link Twitter
- ✅ Nếu "AGENCY" count >30 trong 48h → em build waitlist page + Gumroad skeleton
