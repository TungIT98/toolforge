-- Migration 0005: Pipeline runs (orchestrator)
-- Stores per-step trace for each end-to-end pipeline run

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id TEXT PRIMARY KEY,           -- run-{uuid12}
    trigger TEXT NOT NULL,         -- "showcase", "manual", "auto"
    input_text TEXT NOT NULL,      -- the pain point or topic
    status TEXT NOT NULL DEFAULT 'running',  -- running, success, failed
    current_step TEXT,             -- last completed step
    tool_id TEXT,                  -- result: tool_id created (if any)
    tool_name TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    total_steps INTEGER NOT NULL DEFAULT 5
);

CREATE TABLE IF NOT EXISTS pipeline_steps (
    id TEXT PRIMARY KEY,           -- step-{uuid12}
    run_id TEXT NOT NULL,
    step_index INTEGER NOT NULL,   -- 0..4
    phase TEXT NOT NULL,           -- scout, architect, forge, hype, store
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, running, success, failed
    started_at TEXT,
    ended_at TEXT,
    duration_ms INTEGER,
    summary TEXT,                  -- human-readable 1-line result
    result_json TEXT,              -- full result (truncated if huge)
    error TEXT,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_steps_run ON pipeline_steps(run_id, step_index);
CREATE INDEX IF NOT EXISTS idx_runs_started ON pipeline_runs(started_at DESC);
