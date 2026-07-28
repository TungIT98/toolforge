# Launch copy — Show HN + Twitter thread

Live drafts for the public launch. Edit before pasting. No `→` arrows, no emoji spam, no marketing voice.

---

## Show HN

**Title:** Show HN: I built six AI agents that collaborate end-to-end on Cloudflare Workers

**Body:**

I wanted to learn multi-agent orchestration by shipping it, not reading about it. ToolForge is the result: six small LLM agents (Scout, Architect, Forge, Hype, Store, Helper) that each own one concern, plus a thin orchestrator that runs them in sequence. You give it a pain point, ~30 seconds later you have a tool spec, generated code, a marketing campaign, and a Telegram bot ready to take orders.

Everything runs on Cloudflare's free tier: Workers (Python / pyodide), D1, R2, KV. The LLM is MiniMax M3 via the Anthropic API format. No queues, no Redis, no event bus — every phase writes a row to D1 and the showcase page just polls that table. 263 tests, all unit, all mocked-LLM.

The most useful lesson from building this: **module state on Workers persists across requests in the same isolate.** CORS config, request IDs, anything request-scoped — you have to set them on every request. I also hit a fun bug where my router was importing 4 of 11 handler modules and the rest 404'd in production while every test passed. There's a regression test for that now.

Live demo (one click runs the whole pipeline with live trace): https://toolforge-api.tungit98.workers.dev/showcase

Source + setup guide: https://github.com/TungIT98/toolforge

Happy to answer questions about the orchestration choices, the LLM prompt structure, or why I cut half of the monitoring code after a critical self-review.

---

### Talking points (for the comment thread)

These are the answers I'd pre-load before the first "how does X work" comment lands.

1. **"Why six agents instead of one big prompt?"** Because handoffs force structure. Each agent has a single public function, a single test surface, and a single prompt. The orchestrator doesn't peek inside — it calls functions. If you want to swap Forge's prompt, you change one file and the rest of the system doesn't care. The test count (263, all unit) is the proof: monolithic agents produce flaky integration tests.

2. **"Why Cloudflare Workers Python (pyodide) instead of Node?"** Because I wanted to see how far the free tier could go for a serious workload. Workers Python is genuinely fast now, and 30 s wall-time is enough for a 5-phase LLM pipeline if you keep prompts tight. D1 being edge-SQLite means latency is consistent globally without me thinking about regions. Total cost at the showcase's traffic: $0.

3. **"Why MiniMax M3 / that specific provider?"** 450K context, sub-second p50, Anthropic-format API so the client code is standard. The choice of provider isn't load-bearing — swap `LLM_BASE_URL` and `LLM_MODEL` in `wrangler.jsonc` and the whole thing runs on Claude, GPT, Gemini, whatever. The point of the codebase is the orchestration, not the model.

4. **"What about real-time streaming?"** The showcase polls every 1.5 s. That's deliberate. Streaming an LLM response over Workers requires SSE with backpressure handling and a way to keep the connection warm across isolates — it's a lot of code for a demo. Polling is honest about what's actually happening (each phase is a discrete row insert), and 1.5 s feels live to humans.

5. **"How do the agents share state?"** They don't, not directly. The orchestrator passes the relevant slice to each one — Scout's pain point goes to Architect, Architect's spec goes to Forge and Hype, the tool_id is derived once up front so Hype and Store agree. No shared mutable state, no global bus. This is the part that made testing tractable.

6. **"Why Vietnamese-first UI?"** Because the target user is a Vietnamese MMO creator, not a global SaaS buyer. The landing copy, the Telegram replies, the Hype campaigns — all Vietnamese. Translating them was a non-goal. If you want a non-Vietnamese build, swap the system prompts in `.mavis/agents/*/PERSONA.md`.

7. **"What's the part you're most proud of?"** Cutting the monitoring KV layer. I'd built error logging to KV + admin endpoints + a severity histogram, and the user cut all of it because Cloudflare's native observability (stdout → dashboard) is enough at this scale. The discipline of deleting working code is the actual win. `X-Request-Id` is the only piece that survived, because it earns its place on the live trace.

8. **"What's the part you'd do differently?"** The router should have had a static analysis check that verifies every file in `src/handlers/` is imported in `dispatch()`. I have a runtime test for it now (`tests/test_router.py`) but a CI lint that catches the missing import at PR time would have saved me a day.

9. **"Why is the repo public already if the showcase only just went live?"** Because the code is the artifact. The showcase is the entry point, not the product. I'd rather people read the orchestration code than watch a demo and move on.

10. **"What are you going to do with it?"** Ship the Tauri build pipeline so generated tools can actually be downloaded as signed binaries, then open a small marketplace for the niche. The course/community angle is on the table but not the priority — I want the system to be solid first. More in the README under "Roadmap."

---

## Twitter thread (10 tweets)

Tone: technical, no marketing voice, no "10x" / "game-changer" / "🚀". Each tweet stands on its own.

---

**1/10**

I wanted to learn multi-agent orchestration by shipping it, not reading papers about it.

So I built ToolForge: six small LLM agents that take a pain point and turn it into a published tool with a marketing campaign in ~30 seconds.

Code + live demo: github.com/TungIT98/toolforge

---

**2/10**

The six agents:

🔭 Scout — finds pain points
📐 Architect — writes a 10-section spec
⚒️ Forge — generates code
📣 Hype — writes landing + ads + TikTok script
🏪 Store — publishes to the catalog
🤝 Helper — Telegram bot for customers

Each one is one file with one public function.

---

**3/10**

The orchestrator is ~380 lines. It loops through Scout → Architect → Forge → Hype → Store, and writes a row to a D1 table *before* each phase starts and *after* it finishes.

The showcase page just polls that table every 1.5s. No event bus. No Redis. No streaming.

---

**4/10**

Tech stack, in one line:

Cloudflare Workers (Python/pyodide) + D1 + R2 + KV + Pages, LLM = MiniMax M3 via Anthropic format, Tauri 2 for desktop binaries, SePay for payments, Telegram for support.

Total monthly cost at MVP traffic: $0. At 1k daily users: ~$65-165.

---

**5/10**

The most useful lesson:

Module state on Cloudflare Workers persists across requests in the same isolate. Anything request-scoped (CORS origins, request IDs, config) has to be set on every request via a setter in dispatch().

I cut the feature where CORS was set at module import time. It worked for an hour and then broke in production.

---

**6/10**

The bug I'm most embarrassed by:

My router was importing 4 of 11 handler modules. The other 7 returned 404 in production. Every test passed because the tests bypass the router.

There's now a regression test that asserts every handler module has at least one route registered. Saved in tests/test_router.py.

---

**7/10**

Things I cut because someone told me to:

- KV-backed error logging
- /api/admin/errors endpoint
- Severity histogram

Cloudflare's native observability (stdout → dashboard) is enough at this scale. X-Request-Id is the only piece that survived, because it earns its place on the live trace.

The discipline of deleting working code is the actual win.

---

**8/10**

Vietnamese-first was a constraint, not a style choice. The target user is a Vietnamese MMO creator. Landing copy, Telegram replies, ad scripts — all Vietnamese.

Translating the agents to English was a non-goal. If you want a non-VN build, swap the prompts in .mavis/agents/*/PERSONA.md.

---

**9/10**

What's next:

- Tauri build pipeline on GitHub Actions → R2 → signed URL
- Freemium tracking for the user-facing Builder (3 free / day)
- Helper Telegram bot live (waiting on a bot token from the owner)
- Small marketplace at toolforge.vn

The codebase is the artifact. The demo is just the entry point.

---

**10/10**

If you want to see the agents run, hit the live demo and click "Run Pipeline":

toolforge-api.tungit98.workers.dev/showcase

Code, 263 tests, architecture, and the lessons-learned section are in the README. Star the repo if it's useful, open an issue if something breaks.

Built by me (Zui, github.com/TungIT98) 🇻🇳

---

## Posting checklist

- [ ] Show HN: paste title + body, then monitor first 2 hours
- [ ] Twitter: thread from `1/10` to `10/10`, post at peak (Tue–Thu, 9–11am ET for US AI crowd, or 8–10pm ICT for VN + SEA)
- [ ] Pin the GitHub repo to my profile
- [ ] Reply to *every* HN comment in the first 24 hours
- [ ] Quote-tweet / reply to every Twitter reply in the first 12 hours
- [ ] If a question gets asked 3+ times, write it into the README and link the answer
