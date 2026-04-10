-- ============================================================
-- Statistics & Contracts tables
-- ============================================================

-- Monthly statistics per workspace (confirmed by user)
CREATE TABLE IF NOT EXISTS monthly_stats (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  month TEXT NOT NULL,          -- '2026-04' format
  proposals INTEGER DEFAULT 0,  -- 提案数（ピン数）
  viewings INTEGER DEFAULT 0,   -- 内見数
  applications INTEGER DEFAULT 0, -- 申込数
  approvals INTEGER DEFAULT 0,  -- 審査通過数
  contracts INTEGER DEFAULT 0,  -- 契約数
  confirmed_at TIMESTAMPTZ,     -- 確定日時
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(workspace_id, month)
);

-- Contract management (for approved properties)
CREATE TABLE IF NOT EXISTS contracts (
  id TEXT PRIMARY KEY,
  property_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  property_name TEXT DEFAULT '',
  status TEXT DEFAULT '準備中',  -- 準備中, 書類提出, 審査中, 契約締結, 入居済
  contract_date TEXT DEFAULT '', -- 契約予定日
  move_in_date TEXT DEFAULT '',  -- 入居予定日
  deposit_deadline TEXT DEFAULT '', -- 敷金/保証金支払期限
  key_delivery_date TEXT DEFAULT '', -- 鍵引渡日
  notes TEXT DEFAULT '',
  tasks JSONB DEFAULT '[]',     -- [{title, date, done, memo}]
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE monthly_stats;
ALTER PUBLICATION supabase_realtime ADD TABLE contracts;

-- RLS (allow all - Flask backend handles auth)
ALTER TABLE monthly_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE contracts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all access" ON monthly_stats FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all access" ON contracts FOR ALL USING (true) WITH CHECK (true);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_monthly_stats_ws ON monthly_stats(workspace_id);
CREATE INDEX IF NOT EXISTS idx_contracts_ws ON contracts(workspace_id);
CREATE INDEX IF NOT EXISTS idx_contracts_property ON contracts(property_id);
