-- ToolForge D1 Schema v1 (P0)
-- Database: toolforge-db
-- Created: 2026-07-27
--
-- Tables: 8 core tables + 1 index
-- All timestamps in UTC ISO 8601

-- ============================================================
-- 1. tools — catalog sản phẩm (output từ Forge, list lên store)
-- ============================================================
CREATE TABLE IF NOT EXISTS tools (
  id TEXT PRIMARY KEY,                  -- slug: "capcut-reup"
  name TEXT NOT NULL,                   -- "Capcut Desktop - Reup Phim China"
  description TEXT,
  niche TEXT NOT NULL,                  -- "mmo_reup" | "content_creator" | "productivity"
  status TEXT NOT NULL DEFAULT 'draft', -- draft | approved | live | deprecated
  build_id TEXT,                        -- FK -> builds.id
  pricing_vnd INTEGER DEFAULT 0,        -- 0 = free
  binary_url TEXT,                      -- R2 signed URL
  license_required INTEGER DEFAULT 0,   -- 0 = no license, 1 = needs license
  tags TEXT,                            -- JSON array string
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tools_niche ON tools(niche);
CREATE INDEX IF NOT EXISTS idx_tools_status ON tools(status);

-- ============================================================
-- 2. briefs — pain point research từ Scout
-- ============================================================
CREATE TABLE IF NOT EXISTS briefs (
  id TEXT PRIMARY KEY,                  -- "brief-2026-07-27"
  scout_date TEXT NOT NULL,             -- YYYY-MM-DD
  content TEXT NOT NULL,                -- Markdown full text
  top_pain_json TEXT,                   -- JSON: [{title, severity, audience, market_size, ...}]
  severity_avg REAL,                    -- Average severity of top 10
  source_count INTEGER DEFAULT 0,       -- How many sources scanned
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_briefs_date ON briefs(scout_date DESC);

-- ============================================================
-- 3. specs — technical spec từ Architect
-- ============================================================
CREATE TABLE IF NOT EXISTS specs (
  id TEXT PRIMARY KEY,                  -- "spec-capcut-reup"
  tool_id TEXT NOT NULL,                -- FK -> tools.id (sparse - tool chưa tồn tại khi viết spec)
  brief_id TEXT,                        -- FK -> briefs.id
  content TEXT NOT NULL,                -- Markdown full spec
  status TEXT NOT NULL DEFAULT 'pending_owner_review',  -- pending_owner_review | approved | rejected | in_progress
  owner_feedback TEXT,                  -- owner's comment when approved/rejected
  effort_estimate_hours REAL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  approved_at TEXT,
  FOREIGN KEY (brief_id) REFERENCES briefs(id)
);
CREATE INDEX IF NOT EXISTS idx_specs_status ON specs(status);
CREATE INDEX IF NOT EXISTS idx_specs_tool ON specs(tool_id);

-- ============================================================
-- 4. handoff — Architect → Forge pipeline
-- ============================================================
CREATE TABLE IF NOT EXISTS handoff (
  id TEXT PRIMARY KEY,                  -- "handoff-capcut-reup"
  tool_id TEXT NOT NULL,
  spec_id TEXT NOT NULL,                -- FK -> specs.id
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected | in_progress | done
  priority TEXT DEFAULT 'medium',       -- high | medium | low
  owner_feedback TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  approved_at TEXT,
  forge_handoff_at TEXT,
  done_at TEXT,
  FOREIGN KEY (spec_id) REFERENCES specs(id)
);
CREATE INDEX IF NOT EXISTS idx_handoff_status ON handoff(status);
CREATE INDEX IF NOT EXISTS idx_handoff_tool ON handoff(tool_id);

-- ============================================================
-- 5. builds — code + test + binary từ Forge
-- ============================================================
CREATE TABLE IF NOT EXISTS builds (
  id TEXT PRIMARY KEY,                  -- "build-capcut-reup-v1"
  tool_id TEXT NOT NULL,                -- FK -> tools.id
  handoff_id TEXT NOT NULL,             -- FK -> handoff.id
  version TEXT NOT NULL DEFAULT '0.1.0',
  code_path TEXT,                       -- GitHub repo path
  binary_path TEXT,                     -- Path in R2
  binary_url TEXT,                      -- Signed R2 URL (TTL 7 days)
  test_result TEXT,                     -- pass | partial | fail
  test_report TEXT,                     -- Markdown
  effort_actual_hours REAL,
  size_bytes INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (handoff_id) REFERENCES handoff(id)
);
CREATE INDEX IF NOT EXISTS idx_builds_tool ON builds(tool_id);

-- ============================================================
-- 6. licenses — license key cho tools
-- ============================================================
CREATE TABLE IF NOT EXISTS licenses (
  key TEXT PRIMARY KEY,                 -- "XXXX-XXXX-XXXX-XXXX"
  tool_id TEXT NOT NULL,                -- FK -> tools.id
  status TEXT NOT NULL DEFAULT 'active',  -- active | revoked | expired
  customer_email TEXT,
  customer_telegram TEXT,
  activated_at TEXT,
  expires_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_licenses_tool ON licenses(tool_id);
CREATE INDEX IF NOT EXISTS idx_licenses_status ON licenses(status);

-- ============================================================
-- 7. conversations — Helper support log
-- ============================================================
CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  channel TEXT NOT NULL,                -- telegram | facebook | email
  direction TEXT NOT NULL,              -- in | out
  message TEXT NOT NULL,
  intent TEXT,                          -- tier1_faq_pricing | tier2_kb_lookup | tier3_escalated
  tool_id TEXT,
  resolved INTEGER DEFAULT 0,          -- 0 | 1
  response_time_ms INTEGER,
  ts TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_conv_channel ON conversations(channel, ts DESC);

-- ============================================================
-- 8. campaigns — Hype marketing campaign tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS campaigns (
  id TEXT PRIMARY KEY,                  -- "campaign-capcut-reup-2026-07"
  tool_id TEXT NOT NULL,                -- FK -> tools.id
  channel TEXT NOT NULL,                -- facebook | tiktok | google | organic
  variant TEXT,                         -- A | B | control
  content TEXT,                         -- Ad copy
  status TEXT NOT NULL DEFAULT 'draft',  -- draft | live | paused | ended
  spend_vnd INTEGER DEFAULT 0,
  reach INTEGER DEFAULT 0,
  clicks INTEGER DEFAULT 0,
  installs INTEGER DEFAULT 0,
  purchases INTEGER DEFAULT 0,
  revenue_vnd INTEGER DEFAULT 0,
  roas REAL,                            -- revenue / spend
  started_at TEXT,
  ended_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_campaigns_tool ON campaigns(tool_id);
CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);

-- ============================================================
-- 9. llm_usage — track token usage cho cost monitoring
-- ============================================================
CREATE TABLE IF NOT EXISTS llm_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent TEXT NOT NULL,                  -- scout | architect | forge | hype | helper | test
  model TEXT NOT NULL,                  -- "minimax/MiniMax-M3"
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  total_tokens INTEGER,
  cost_usd REAL,
  task TEXT,                            -- free text: "daily_pain_scan" | "test_connection"
  ts TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_llm_agent ON llm_usage(agent, ts DESC);
