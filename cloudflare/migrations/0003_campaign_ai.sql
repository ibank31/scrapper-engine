ALTER TABLE campaigns ADD COLUMN rules_hash TEXT;
ALTER TABLE campaigns ADD COLUMN ai_rules_json TEXT;
ALTER TABLE campaigns ADD COLUMN ai_rules_status TEXT NOT NULL DEFAULT 'unavailable';
ALTER TABLE campaigns ADD COLUMN ai_analyzed_at TEXT;

CREATE INDEX IF NOT EXISTS idx_campaigns_rules_hash ON campaigns(rules_hash);
CREATE INDEX IF NOT EXISTS idx_campaigns_ai_status ON campaigns(ai_rules_status);
