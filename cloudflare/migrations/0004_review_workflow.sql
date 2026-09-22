ALTER TABLE previews ADD COLUMN review_reason TEXT;
ALTER TABLE previews ADD COLUMN reviewed_by TEXT;
ALTER TABLE previews ADD COLUMN reviewed_at TEXT;

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

CREATE INDEX IF NOT EXISTS idx_preview_events_preview ON preview_events(preview_id, created_at);
