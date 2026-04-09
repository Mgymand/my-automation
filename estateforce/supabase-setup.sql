-- ============================================================
-- Estateforce - Supabase Database Setup
-- ============================================================
-- Run this in Supabase SQL Editor (Dashboard > SQL Editor)
-- ============================================================

-- 1. Create Tables
-- ============================================================

CREATE TABLE IF NOT EXISTS workspaces (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  stations JSONB DEFAULT '[]'::jsonb,
  center JSONB DEFAULT '{"lat": 35.6812, "lon": 139.7671}'::jsonb,
  zoom INTEGER DEFAULT 14,
  criteria JSONB DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS properties (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  address TEXT DEFAULT '',
  lat DOUBLE PRECISION,
  lon DOUBLE PRECISION,
  filename TEXT DEFAULT '',
  pdf_url TEXT DEFAULT '',
  details JSONB DEFAULT '{}'::jsonb,
  memo TEXT DEFAULT '',
  color TEXT DEFAULT 'blue',
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  phone TEXT DEFAULT '',
  area TEXT DEFAULT '',
  manager_area TEXT DEFAULT '',
  memo TEXT DEFAULT '',
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS schedules (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  agent_id TEXT DEFAULT '',
  property_id TEXT DEFAULT '',
  type TEXT DEFAULT 'その他',
  date TEXT NOT NULL,
  start_time TEXT DEFAULT '10:00',
  end_time TEXT DEFAULT '11:00',
  memo TEXT DEFAULT '',
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value JSONB
);

-- 2. Enable Realtime
-- ============================================================

ALTER PUBLICATION supabase_realtime ADD TABLE workspaces;
ALTER PUBLICATION supabase_realtime ADD TABLE properties;
ALTER PUBLICATION supabase_realtime ADD TABLE agents;
ALTER PUBLICATION supabase_realtime ADD TABLE schedules;
ALTER PUBLICATION supabase_realtime ADD TABLE app_settings;

-- 3. Row Level Security (RLS)
-- ============================================================
-- Allow all authenticated users full access (team sharing)

ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE properties ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_settings ENABLE ROW LEVEL SECURITY;

-- Workspaces: authenticated users can do everything
CREATE POLICY "Allow all for authenticated users" ON workspaces
  FOR ALL USING (auth.role() = 'authenticated')
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Allow all for authenticated users" ON properties
  FOR ALL USING (auth.role() = 'authenticated')
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Allow all for authenticated users" ON agents
  FOR ALL USING (auth.role() = 'authenticated')
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Allow all for authenticated users" ON schedules
  FOR ALL USING (auth.role() = 'authenticated')
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Allow all for authenticated users" ON app_settings
  FOR ALL USING (auth.role() = 'authenticated')
  WITH CHECK (auth.role() = 'authenticated');

-- 4. Indexes
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_properties_workspace ON properties(workspace_id);
CREATE INDEX IF NOT EXISTS idx_properties_color ON properties(color);
CREATE INDEX IF NOT EXISTS idx_schedules_date ON schedules(date);

-- 5. Auto-update updated_at trigger
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER workspaces_updated_at BEFORE UPDATE ON workspaces
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER properties_updated_at BEFORE UPDATE ON properties
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER agents_updated_at BEFORE UPDATE ON agents
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER schedules_updated_at BEFORE UPDATE ON schedules
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- 6. Storage Bucket for PDFs
-- ============================================================
-- Run this separately in the Storage section, or use:

INSERT INTO storage.buckets (id, name, public)
VALUES ('pdfs', 'pdfs', true)
ON CONFLICT (id) DO NOTHING;

-- Storage policy: authenticated users can upload/read
CREATE POLICY "Allow authenticated uploads" ON storage.objects
  FOR INSERT WITH CHECK (
    bucket_id = 'pdfs' AND auth.role() = 'authenticated'
  );

CREATE POLICY "Allow public reads" ON storage.objects
  FOR SELECT USING (bucket_id = 'pdfs');

-- 7. Initial Data (Active Workspace Setting)
-- ============================================================

INSERT INTO app_settings (key, value)
VALUES ('activeWorkspace', '"ws_1"'::jsonb)
ON CONFLICT (key) DO NOTHING;

-- ============================================================
-- EXISTING DATA MIGRATION (uncomment and run if needed)
-- ============================================================

-- Workspaces
INSERT INTO workspaces (id, name, stations, center, zoom) VALUES
('ws_1', '新オフィス用',
 '[{"name":"渋谷駅","lat":35.658,"lon":139.7016,"r":180},{"name":"表参道駅","lat":35.6654,"lon":139.7122,"r":120},{"name":"明治神宮前駅","lat":35.6699,"lon":139.7024,"r":100}]'::jsonb,
 '{"lat":35.6595,"lon":139.7005}'::jsonb, 16),
('ws_1775556114635', 'K新宿',
 '[{"name":"新宿駅","lat":35.6921769,"lon":139.6996969,"r":180}]'::jsonb,
 '{"lat":35.660364705092164,"lon":139.70528125762942}'::jsonb, 16),
('ws_1775558821375', 'T新宿',
 '[{"name":"新宿駅","lat":35.6921769,"lon":139.6996969,"r":180}]'::jsonb,
 '{"lat":35.693308316633754,"lon":139.70444440841678}'::jsonb, 16)
ON CONFLICT (id) DO NOTHING;

-- Agents
INSERT INTO agents (id, name, email, phone, area, manager_area, memo) VALUES
('agent_1775590767649', '田中太郎', 'tanaka@example.com', '03-1234-5678', 'ws_1,ws_1775556114635', '', ''),
('agent_1775591394547', '岩本賢伸', 'k.iwamoto@lime-fit.com', '090-1386-7439', 'ws_1,ws_1775556114635', '', '')
ON CONFLICT (id) DO NOTHING;
