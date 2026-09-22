ALTER TABLE jobs ADD COLUMN run_id TEXT;
ALTER TABLE jobs ADD COLUMN manifest_key TEXT;
ALTER TABLE jobs ADD COLUMN manifest_schema_version INTEGER;

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
CREATE INDEX IF NOT EXISTS idx_job_stage_events_job ON job_stage_events(job_id, created_at);
CREATE INDEX IF NOT EXISTS idx_job_stage_events_run ON job_stage_events(run_id, stage, created_at);
