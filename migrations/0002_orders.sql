-- ToolForge D1 Schema v2 (P2.3) — orders table for SePay payment tracking
-- Created: 2026-07-27

-- ============================================================
-- orders — payment orders from SePay
-- ============================================================
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,                    -- "order-<uuid8>"
  tool_id TEXT,                            -- FK -> tools.id (nullable for top-up orders)
  tool_name TEXT,                          -- cached for display
  customer_email TEXT,
  customer_telegram TEXT,
  customer_name TEXT,
  amount_vnd INTEGER NOT NULL,
  description TEXT NOT NULL,               -- payment content (tool_id + customer_id encoded)
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | paid | failed | refunded
  payment_method TEXT,                     -- sepay | vietqr | manual
  sepay_transaction_id TEXT,               -- from SePay webhook
  sepay_reference_code TEXT,
  sepay_transfer_type TEXT,                -- in | out
  sepay_account TEXT,
  paid_at TEXT,                            -- when payment confirmed
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  license_key TEXT,                        -- generated after successful payment
  FOREIGN KEY (tool_id) REFERENCES tools(id)
);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_tool ON orders(tool_id);
CREATE INDEX IF NOT EXISTS idx_orders_email ON orders(customer_email);
CREATE INDEX IF NOT EXISTS idx_orders_sepay_txn ON orders(sepay_transaction_id);

-- ============================================================
-- payment_events — audit log for all payment-related events
-- ============================================================
CREATE TABLE IF NOT EXISTS payment_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT,                           -- FK -> orders.id
  event_type TEXT NOT NULL,                -- webhook_received | license_activated | license_revoked | manual_adjust
  source TEXT,                             -- sepay | admin | test
  payload_json TEXT,                       -- raw event data (truncated)
  result TEXT,                             -- success | error
  error_message TEXT,
  ts TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_order ON payment_events(order_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_type ON payment_events(event_type, ts DESC);
