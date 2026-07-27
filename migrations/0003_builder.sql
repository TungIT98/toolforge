-- ToolForge D1 Schema v3 (P3) — Builder Tool (user-facing)
-- Created: 2026-07-27

-- ============================================================
-- builder_sessions — chat sessions between user and AI
-- ============================================================
CREATE TABLE IF NOT EXISTS builder_sessions (
  id TEXT PRIMARY KEY,                     -- "sess-<uuid8>"
  user_email TEXT,                          -- optional
  user_ip TEXT,                             -- for freemium tracking
  user_agent TEXT,
  status TEXT NOT NULL DEFAULT 'chatting',  -- chatting | ready_to_build | building | done | failed
  tool_name TEXT,                           -- final tool name (extracted from spec)
  final_spec TEXT,                          -- markdown spec
  spec_json TEXT,                           -- JSON of spec sections
  messages_count INTEGER DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON builder_sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_ip ON builder_sessions(user_ip, created_at DESC);

-- ============================================================
-- builder_messages — chat history
-- ============================================================
CREATE TABLE IF NOT EXISTS builder_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,                       -- user | assistant | system
  content TEXT NOT NULL,
  ts TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON builder_messages(session_id, id);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON builder_messages(ts DESC);

-- ============================================================
-- builder_jobs — generated code artifacts
-- ============================================================
CREATE TABLE IF NOT EXISTS builder_jobs (
  id TEXT PRIMARY KEY,                     -- "job-<uuid8>"
  session_id TEXT NOT NULL,
  code_files_json TEXT NOT NULL,           -- JSON: {filepath: content}
  file_count INTEGER DEFAULT 0,
  total_lines INTEGER DEFAULT 0,
  test_result TEXT,                        -- pass | partial | fail
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | building | done | failed
  size_bytes INTEGER DEFAULT 0,
  error_message TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_jobs_session ON builder_jobs(session_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON builder_jobs(status);
