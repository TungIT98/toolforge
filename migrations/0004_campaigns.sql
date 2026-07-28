-- Migration 0004: Hype marketing campaigns
-- Stores generated landing copy + ad variants + TikTok script per tool

CREATE TABLE IF NOT EXISTS campaigns (
    tool_id TEXT PRIMARY KEY,
    tool_name TEXT NOT NULL,
    pricing_vnd INTEGER NOT NULL DEFAULT 0,
    content_json TEXT NOT NULL,  -- full campaign dict (landing, fb_a, fb_b, tiktok)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_campaigns_updated ON campaigns(updated_at DESC);
