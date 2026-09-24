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
CREATE INDEX IF NOT EXISTS idx_buffer_uploads_preview ON buffer_uploads(preview_id, created_at);

-- Buffer fetches media later, so this integration uses the stable public /media/:key route.
-- Configure BUFFER_API_KEY and optionally BUFFER_PUBLIC_MEDIA_BASE_URL in Cloudflare Pages.
