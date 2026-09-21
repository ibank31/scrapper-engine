ALTER TABLE campaigns ADD COLUMN first_seen_at TEXT;
ALTER TABLE campaigns ADD COLUMN last_seen_at TEXT;
ALTER TABLE campaigns ADD COLUMN priority_components_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE campaigns ADD COLUMN competition_proxy_json TEXT NOT NULL DEFAULT '{}';

UPDATE campaigns
SET first_seen_at = COALESCE(first_seen_at, updated_at),
    last_seen_at = COALESCE(last_seen_at, updated_at)
WHERE first_seen_at IS NULL OR last_seen_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_campaigns_first_seen ON campaigns(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_campaigns_last_seen ON campaigns(last_seen_at);
