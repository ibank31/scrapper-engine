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
  competition_proxy_json TEXT NOT NULL DEFAULT '{}',
  rules_hash TEXT,
  ai_rules_json TEXT,
  ai_rules_status TEXT NOT NULL DEFAULT 'unavailable',
  ai_analyzed_at TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  progress INTEGER NOT NULL DEFAULT 0,
  message TEXT,
  error TEXT,
  dispatch_token TEXT,
  claimed_at TEXT,
  claimed_by TEXT,
  run_id TEXT,
  plan_snapshot_json TEXT,
  rules_hash TEXT,
  plan_schema_version INTEGER,
  source_fingerprint_json TEXT NOT NULL DEFAULT '{}',
  execution_generation INTEGER NOT NULL DEFAULT 1,
  output_contract_json TEXT NOT NULL DEFAULT '{}',
  output_selection_json TEXT NOT NULL DEFAULT '{}',
  output_contract_status TEXT NOT NULL DEFAULT 'pending',
  cancelled_at TEXT,
  active_run_token TEXT,
  manifest_key TEXT,
  manifest_schema_version INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
);

CREATE TABLE IF NOT EXISTS job_stage_events (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT,
  ended_at TEXT,
  metrics_json TEXT NOT NULL DEFAULT '{}',
  error_code TEXT,
  error_detail TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS previews (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  rank INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending_review',
  tier TEXT,
  candidate_id TEXT,
  source_asset_id TEXT,
  video_key TEXT,
  review_video_key TEXT,
  thumbnail_key TEXT,
  download_url TEXT,
  validation_json TEXT NOT NULL DEFAULT '{}',
  caption_draft TEXT,
  checklist_json TEXT NOT NULL DEFAULT '[]',
  review_reason TEXT,
  reviewed_by TEXT,
  reviewed_at TEXT,
  artifact_hash TEXT,
  distinctness_json TEXT NOT NULL DEFAULT '{}',
  platform TEXT,
  platform_profile_json TEXT NOT NULL DEFAULT '{}',
  subtitle_delivery_json TEXT NOT NULL DEFAULT '{}',
  sound_tags_json TEXT NOT NULL DEFAULT '{}',
  caption_revision_id TEXT,
  caption_hash TEXT,
  approval_artifact_hash TEXT,
  approval_caption_revision_id TEXT,
  approval_rules_hash TEXT,
  platform_profile_version TEXT,
  schedule_intent_hash TEXT,
  rules_summary_id TEXT,
  parent_preview_id TEXT,
  revision_number INTEGER NOT NULL DEFAULT 1,
  render_revision TEXT NOT NULL DEFAULT 'render-v1',
  superseded_at TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS caption_revisions (
  id TEXT PRIMARY KEY,
  preview_id TEXT NOT NULL,
  revision_number INTEGER NOT NULL,
  text TEXT NOT NULL,
  fields_json TEXT NOT NULL DEFAULT '{}',
  platform TEXT NOT NULL,
  editor TEXT NOT NULL,
  character_count_method TEXT NOT NULL,
  character_count INTEGER NOT NULL,
  caption_hash TEXT NOT NULL,
  rules_hash TEXT NOT NULL,
  platform_profile_version TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (preview_id) REFERENCES previews(id),
  UNIQUE (preview_id, revision_number),
  UNIQUE (preview_id, caption_hash)
);

CREATE TABLE IF NOT EXISTS preview_events (
  id TEXT PRIMARY KEY,
  preview_id TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT NOT NULL,
  action TEXT NOT NULL,
  reason TEXT,
  actor TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (preview_id) REFERENCES previews(id)
);

CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
CREATE INDEX IF NOT EXISTS idx_campaigns_first_seen ON campaigns(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_campaigns_last_seen ON campaigns(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_campaigns_rules_hash ON campaigns(rules_hash);
CREATE INDEX IF NOT EXISTS idx_campaigns_ai_status ON campaigns(ai_rules_status);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_claimed ON jobs(status, claimed_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_one_open_per_campaign ON jobs(campaign_id) WHERE status IN ('queued','processing');
CREATE INDEX IF NOT EXISTS idx_job_stage_events_job ON job_stage_events(job_id, created_at);
CREATE INDEX IF NOT EXISTS idx_job_stage_events_run ON job_stage_events(run_id, stage, created_at);
CREATE INDEX IF NOT EXISTS idx_previews_job ON previews(job_id);
CREATE INDEX IF NOT EXISTS idx_preview_events_preview ON preview_events(preview_id, created_at);
CREATE TABLE IF NOT EXISTS buffer_uploads (
  id TEXT PRIMARY KEY,
  preview_id TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  buffer_post_id TEXT,
  status TEXT NOT NULL,
  error TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (preview_id) REFERENCES previews(id)
);

CREATE TABLE IF NOT EXISTS delivery_operations (
  operation_key TEXT PRIMARY KEY,
  preview_id TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  schedule_revision TEXT NOT NULL,
  caption_revision_id TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  schedule_intent_json TEXT NOT NULL DEFAULT '{}',
  provider_state TEXT NOT NULL DEFAULT 'pending',
  retry_class TEXT NOT NULL DEFAULT 'not_attempted',
  attempt_count INTEGER NOT NULL DEFAULT 0,
  provider_post_id TEXT,
  provider_due_at TEXT,
  provider_status TEXT,
  provider_response_json TEXT NOT NULL DEFAULT '{}',
  last_error TEXT,
  last_observed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (preview_id) REFERENCES previews(id),
  UNIQUE (preview_id, channel_id, schedule_revision, caption_revision_id)
);
CREATE INDEX IF NOT EXISTS idx_delivery_operations_preview ON delivery_operations(preview_id, created_at);
CREATE INDEX IF NOT EXISTS idx_delivery_operations_state ON delivery_operations(provider_state, updated_at);

CREATE TABLE IF NOT EXISTS retention_events (
  id TEXT PRIMARY KEY,
  preview_id TEXT,
  object_key TEXT,
  decision TEXT NOT NULL,
  reason TEXT NOT NULL,
  dependency_json TEXT NOT NULL DEFAULT '{}',
  evaluated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_retention_events_preview ON retention_events(preview_id, evaluated_at);

CREATE TABLE IF NOT EXISTS provider_request_ledger (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  request_class TEXT NOT NULL,
  period_key TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_provider_request_ledger_period ON provider_request_ledger(provider, period_key, created_at);
CREATE INDEX IF NOT EXISTS idx_buffer_uploads_preview ON buffer_uploads(preview_id, created_at);
