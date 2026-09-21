CREATE TABLE IF NOT EXISTS campaigns (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  brand TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  score REAL,
  rate_per_1k REAL,
  budget_left REAL,
  platforms_json TEXT NOT NULL DEFAULT '[]',
  detail_json TEXT NOT NULL DEFAULT '{}',
  plan_json TEXT,
  updated_at TEXT NOT NULL,
  first_seen_at TEXT,
  last_seen_at TEXT,
  priority_components_json TEXT NOT NULL DEFAULT '{}',
  competition_proxy_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  progress INTEGER NOT NULL DEFAULT 0,
  message TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

CREATE TABLE IF NOT EXISTS previews (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  rank INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending_review',
  video_key TEXT,
  thumbnail_key TEXT,
  download_url TEXT,
  validation_json TEXT NOT NULL DEFAULT '{}',
  caption_draft TEXT,
  checklist_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
CREATE INDEX IF NOT EXISTS idx_campaigns_first_seen ON campaigns(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_campaigns_last_seen ON campaigns(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_previews_job ON previews(job_id);
