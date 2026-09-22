-- Apply after reconciling any existing duplicate queued/processing rows.
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_one_open_per_campaign
  ON jobs(campaign_id) WHERE status IN ('queued','processing');
