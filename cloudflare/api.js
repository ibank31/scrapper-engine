const cors = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,PATCH,OPTIONS",
  "access-control-allow-headers": "content-type,x-worker-token,x-review-token,authorization"
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { ...cors, "content-type": "application/json; charset=utf-8" } });
}
function now() { return new Date().toISOString(); }
function parseJson(value, fallback = {}) {
  if (value == null || value === "") return fallback;
  if (typeof value === "object") return value;
  try { return JSON.parse(value); } catch (_) { return fallback; }
}
function parse(row) {
  if (!row) return row;
  const detail = parseJson(row.detail_json, {});
  const priorityComponents = parseJson(row.priority_components_json || detail.priority_components_json, {});
  const competitionProxy = parseJson(row.competition_proxy_json || detail.competition_proxy_json, {});
  const readinessStatus = detail.readiness_status || null;
  return {
    ...row,
    platforms: parseJson(row.platforms_json, []),
    detail,
    plan: parseJson(row.plan_json, null),
    ai_rules: parseJson(row.ai_rules_json, null),
    priority_components: priorityComponents,
    competition_proxy: competitionProxy,
    new: Boolean(row.first_seen_at && row.first_seen_at === row.last_seen_at),
    category: detail.category,
    type: detail.type,
    flags: detail.flags || [],
    link: detail.link,
    verified: Boolean(detail.verified),
    description: detail.description,
    // Phase 1 readiness (machine ranking for non-expert users)
    content_kind: detail.content_kind || null,
    is_clipping: detail.is_clipping === true || detail.content_kind === "clipping",
    readiness_status: readinessStatus,
    readiness_label: detail.readiness_label || null,
    readiness_reason: detail.readiness_reason || null,
    readiness_ease: detail.readiness_ease,
    readiness_safety: detail.readiness_safety,
    readiness_materials: detail.readiness_materials || null,
    readiness_flags: detail.readiness_flags || [],
  };
}
function readinessRank(status) {
  if (status === "siap") return 0;
  if (status === "ketat") return 1;
  if (status === "belum_siap") return 2;
  if (status === "lewati") return 3;
  return 4;
}
function workerAuthorized(request, env) {
  if (!env.WORKER_TOKEN) return false;
  const bearer = request.headers.get("authorization") || "";
  return request.headers.get("x-worker-token") === env.WORKER_TOKEN || bearer === `Bearer ${env.WORKER_TOKEN}`;
}
async function cleanupAuthorized(request, env) {
  if (workerAuthorized(request, env)) return true;
  const token = request.headers.get("x-github-token") || "";
  if (!token) return false;
  const repo = env.GITHUB_REPOSITORY || "ibank31/scrapper-engine";
  const response = await fetch(`https://api.github.com/repos/${repo}`, {
    headers: { authorization: `Bearer ${token}`, accept: "application/vnd.github+json", "x-github-api-version": "2022-11-28", "user-agent": "clipper-preview-cleanup" }
  });
  return response.ok;
}
async function workerOrDispatchAuthorized(request, env, jobId) {
  if (workerAuthorized(request, env)) return true;
  const dispatchToken = request.headers.get("x-dispatch-token") || "";
  if (!dispatchToken) return false;
  const job = await env.DB.prepare("SELECT dispatch_token FROM jobs WHERE id=?").bind(jobId).first();
  return Boolean(job && job.dispatch_token && job.dispatch_token === dispatchToken);
}

async function ensureSchema(db) {
  const info = await db.prepare("PRAGMA table_info(campaigns)").all();
  const existing = new Set((info.results || []).map((row) => row.name));
  const columns = {
    first_seen_at: "TEXT",
    last_seen_at: "TEXT",
    priority_components_json: "TEXT NOT NULL DEFAULT '{}'",
    competition_proxy_json: "TEXT NOT NULL DEFAULT '{}'",
    rules_hash: "TEXT",
    ai_rules_json: "TEXT",
    ai_rules_status: "TEXT NOT NULL DEFAULT 'unavailable'",
    ai_analyzed_at: "TEXT",
  };
  for (const [name, definition] of Object.entries(columns)) {
    if (!existing.has(name)) {
      await db.prepare("ALTER TABLE campaigns ADD COLUMN " + name + " " + definition).run();
    }
  }
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_campaigns_first_seen ON campaigns(first_seen_at)").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_campaigns_last_seen ON campaigns(last_seen_at)").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_campaigns_rules_hash ON campaigns(rules_hash)").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_campaigns_ai_status ON campaigns(ai_rules_status)").run();
  const previewInfo = await db.prepare("PRAGMA table_info(previews)").all();
  const previewColumns = new Set((previewInfo.results || []).map((row) => row.name));
  for (const [name, definition] of Object.entries({ review_video_key: "TEXT", review_reason: "TEXT", reviewed_by: "TEXT", reviewed_at: "TEXT", rules_summary_id: "TEXT" })) {
    if (!previewColumns.has(name)) await db.prepare("ALTER TABLE previews ADD COLUMN " + name + " " + definition).run();
  }
  await db.prepare("CREATE TABLE IF NOT EXISTS preview_events (id TEXT PRIMARY KEY, preview_id TEXT NOT NULL, from_status TEXT, to_status TEXT NOT NULL, action TEXT NOT NULL, reason TEXT, actor TEXT, created_at TEXT NOT NULL)").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_preview_events_preview ON preview_events(preview_id, created_at)").run();
  const jobInfo = await db.prepare("PRAGMA table_info(jobs)").all();
  const jobColumns = new Set((jobInfo.results || []).map((row) => row.name));
  for (const [name, definition] of Object.entries({ dispatch_token: "TEXT", claimed_at: "TEXT", claimed_by: "TEXT", run_id: "TEXT", manifest_key: "TEXT", manifest_schema_version: "INTEGER" })) {
    if (!jobColumns.has(name)) await db.prepare("ALTER TABLE jobs ADD COLUMN " + name + " " + definition).run();
  }
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_jobs_claimed ON jobs(status, claimed_at)").run();
  await db.prepare("CREATE TABLE IF NOT EXISTS job_stage_events (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, run_id TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT, ended_at TEXT, metrics_json TEXT NOT NULL DEFAULT '{}', error_code TEXT, error_detail TEXT, created_at TEXT NOT NULL)").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_job_stage_events_job ON job_stage_events(job_id, created_at)").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_job_stage_events_run ON job_stage_events(run_id, stage, created_at)").run();
  await db.prepare("CREATE TABLE IF NOT EXISTS buffer_uploads (id TEXT PRIMARY KEY, preview_id TEXT NOT NULL, channel_id TEXT NOT NULL, buffer_post_id TEXT, status TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL, FOREIGN KEY (preview_id) REFERENCES previews(id))").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_buffer_uploads_preview ON buffer_uploads(preview_id, created_at)").run();
}

function claimLeaseSeconds(env) {
  const value = Number(env.CLAIM_LEASE_SECONDS || 3600);
  return Number.isFinite(value) ? Math.min(86400, Math.max(300, value)) : 3600;
}

async function runnerIsDead(env, claimedBy) {
  const match = String(claimedBy || "").match(/^github-run:(\d+)$/);
  if (!match) return { known: false, dead: false, reason: "runner_identity_unavailable" };
  const token = env.GITHUB_ACTIONS_TOKEN || env.GITHUB_TOKEN;
  if (!token) return { known: false, dead: false, reason: "github_token_unavailable" };
  const repo = env.GITHUB_REPOSITORY || "ibank31/scrapper-engine";
  const response = await fetch(`https://api.github.com/repos/${repo}/actions/runs/${match[1]}`, {
    headers: { authorization: `Bearer ${token}`, accept: "application/vnd.github+json", "x-github-api-version": "2022-11-28", "user-agent": "clipper-engine" }
  });
  if (response.status === 404) return { known: true, dead: true, reason: "github_run_not_found" };
  if (!response.ok) return { known: false, dead: false, reason: `github_http_${response.status}` };
  const run = await response.json();
  const failed = run.status === "completed" && run.conclusion !== "success";
  return { known: true, dead: failed, reason: run.status === "completed" ? `completed_${run.conclusion || "unknown"}` : `status_${run.status}` };
}

function reviewActor(request, body) {
  return String(request.headers.get("cf-access-authenticated-user-email") || body.reviewer || "manual-user").slice(0, 200);
}

function reviewAuthorized(request, env) {
  if (!env.REVIEW_TOKEN) return true;
  const bearer = request.headers.get("authorization") || "";
  return request.headers.get("x-review-token") === env.REVIEW_TOKEN || bearer === `Bearer ${env.REVIEW_TOKEN}`;
}

async function bufferRequest(env, query, variables = {}) {
  if (!env.BUFFER_API_KEY) throw new Error("BUFFER_API_KEY belum dikonfigurasi di Cloudflare Pages");
  const response = await fetch("https://api.buffer.com", {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${env.BUFFER_API_KEY}` },
    body: JSON.stringify({ query, variables }),
  });
  const payload = await response.json();
  if (!response.ok || payload.errors?.length) throw new Error(payload.errors?.map((x) => x.message).join("; ") || `Buffer HTTP ${response.status}`);
  return payload.data;
}

function bufferTextLimit(service) {
  const value = String(service || "").toLowerCase();
  if (value === "twitter" || value === "x") return 280;
  if (value === "threads" || value === "bluesky") return 300;
  if (value === "pinterest") return 500;
  if (value === "instagram") return 2196;
  if (value === "tiktok") return 2200;
  if (value === "linkedin") return 3000;
  if (value === "facebook" || value === "youtube") return 5000;
  return 2200;
}

function publicMediaUrl(request, env, key) {
  const configured = String(env.BUFFER_PUBLIC_MEDIA_BASE_URL || "").replace(/\/$/, "");
  if (configured) return `${configured}/${String(key).split("/").map(encodeURIComponent).join("/")}`;
  const url = new URL(request.url);
  return `${url.origin}/media/${String(key).split("/").map(encodeURIComponent).join("/")}`;
}

function hex(bytes) {
  return Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function previewSignature(secret, key, expires) {
  const cryptoKey = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return hex(await crypto.subtle.sign("HMAC", cryptoKey, new TextEncoder().encode(`${key}:${expires}`)));
}

async function previewUrl(request, env, key, ttlSeconds = 900) {
  const url = new URL(request.url);
  if (!env.PREVIEW_SIGNING_SECRET) return `${url.origin}/api/files?key=${encodeURIComponent(key)}`;
  const expires = Math.floor(Date.now() / 1000) + Math.min(3600, Math.max(60, ttlSeconds));
  const signature = await previewSignature(env.PREVIEW_SIGNING_SECRET, key, expires);
  return `${url.origin}/api/files?key=${encodeURIComponent(key)}&exp=${expires}&sig=${signature}`;
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });
    const url = new URL(request.url);
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts[0] === "media" && request.method === "GET") {
      if (!env.CLIPS) return json({ error: "media_not_configured" }, 503);
      const key = parts.slice(1).map(decodeURIComponent).join("/");
      if (!key || key.includes("..")) return json({ error: "media_not_found" }, 404);
      const object = await env.CLIPS.get(key);
      if (!object) return json({ error: "media_not_found" }, 404);
      const headers = new Headers({ "cache-control": "public, max-age=31536000, immutable", "access-control-allow-origin": "*" });
      object.writeHttpMetadata(headers); headers.set("etag", object.httpEtag);
      return new Response(object.body, { headers });
    }
    if (parts[0] !== "api") return json({ error: "not_found" }, 404);
      try {
        await ensureSchema(env.DB);
      if (parts[1] === "buffer" && parts[2] === "channels" && request.method === "GET") {
        const orgData = await bufferRequest(env, "query { account { organizations { id name } } }");
        const channels = [];
        for (const organization of orgData.account?.organizations || []) {
          const data = await bufferRequest(env, "query($organizationId: ID!) { channels(input: { organizationId: $organizationId }) { id name service } }", { organizationId: organization.id });
          for (const channel of data.channels || []) channels.push({ ...channel, organizationId: organization.id, organizationName: organization.name });
        }
        return json({ channels });
      }
      if (parts[1] === "previews" && parts[2] && parts[3] === "buffer" && request.method === "POST") {
        if (!reviewAuthorized(request, env)) return json({ error: "review_unauthorized" }, 401);
        const body = await request.json();
        const preview = await env.DB.prepare("SELECT id,status,video_key,caption_draft FROM previews WHERE id=?").bind(parts[2]).first();
        if (!preview || !preview.video_key) return json({ error: "preview_not_found" }, 404);
        if (!["pending_review", "approved_for_manual_post"].includes(preview.status)) return json({ error: "preview_not_available", status: preview.status }, 409);
        const channelIds = [...new Set((body.channel_ids || []).map(String).filter(Boolean))].slice(0, 10);
        if (!channelIds.length) return json({ error: "channel_ids_required" }, 400);
        const text = String(body.text || preview.caption_draft || "").trim();
        if (!text) return json({ error: "caption_required", message: "Caption dan tagar wajib tersedia sebelum upload." }, 400);
        const uploaded = [];
        for (const channelId of channelIds) {
          const channel = (body.channels || []).find((item) => String(item.id) === channelId) || {};
          const limit = bufferTextLimit(channel.service);
          if (text.length > limit) {
            const error = `Caption ${text.length} UTF-16 code units melebihi batas konservatif ${limit} untuk ${channel.service || "channel ini"}.`;
            await env.DB.prepare("INSERT INTO buffer_uploads (id,preview_id,channel_id,buffer_post_id,status,error,created_at) VALUES (?,?,?,?,?,?,?)").bind(crypto.randomUUID(), preview.id, channelId, null, "preflight_error", error, now()).run();
            uploaded.push({ channel_id: channelId, status: "preflight_error", error });
            continue;
          }
          try {
            const data = await bufferRequest(env, "mutation($input: CreatePostInput!) { createPost(input: $input) { ... on PostActionSuccess { post { id dueAt channelId } } ... on MutationError { message } } }", { input: { text, channelId, schedulingType: "automatic", mode: "addToQueue", assets: [{ video: { url: publicMediaUrl(request, env, preview.video_key) } }] } });
            const result = data.createPost || {};
            if (result.message && !result.post) throw new Error(result.message);
            await env.DB.prepare("INSERT INTO buffer_uploads (id,preview_id,channel_id,buffer_post_id,status,error,created_at) VALUES (?,?,?,?,?,?,?)").bind(crypto.randomUUID(), preview.id, channelId, result.post?.id || null, "queued", null, now()).run();
            uploaded.push({ channel_id: channelId, post: result.post || null, status: "queued" });
          } catch (error) {
            await env.DB.prepare("INSERT INTO buffer_uploads (id,preview_id,channel_id,buffer_post_id,status,error,created_at) VALUES (?,?,?,?,?,?,?)").bind(crypto.randomUUID(), preview.id, channelId, null, "error", String(error.message || error).slice(0, 1000), now()).run();
            uploaded.push({ channel_id: channelId, status: "error", error: String(error.message || error) });
          }
        }
        return json({ ok: uploaded.some((item) => item.status === "queued"), preview_id: preview.id, uploads: uploaded });
      }
      if (parts[1] === "maintenance" && parts[2] === "cleanup-previews" && request.method === "POST") {
        if (!(await cleanupAuthorized(request, env))) return json({ error: "cleanup_unauthorized" }, 401);
        const cutoff = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
        const oldPreviews = await env.DB.prepare("SELECT id,job_id,video_key,review_video_key,thumbnail_key FROM previews WHERE created_at < ?").bind(cutoff).all();
        const oldJobs = await env.DB.prepare("SELECT id,manifest_key FROM jobs WHERE created_at < ? AND status IN ('review','blocked','error','cancelled')").bind(cutoff).all();
        const keys = new Set();
        for (const row of oldPreviews.results || []) { if (row.video_key) keys.add(row.video_key); if (row.review_video_key) keys.add(row.review_video_key); if (row.thumbnail_key) keys.add(row.thumbnail_key); }
        for (const row of oldJobs.results || []) if (row.manifest_key) keys.add(row.manifest_key);
        if (env.CLIPS && keys.size) await env.CLIPS.delete([...keys]);
        const statements = [];
        for (const row of oldPreviews.results || []) statements.push(env.DB.prepare("DELETE FROM preview_events WHERE preview_id=?").bind(row.id));
        statements.push(env.DB.prepare("DELETE FROM previews WHERE created_at < ?").bind(cutoff));
        statements.push(env.DB.prepare("DELETE FROM job_stage_events WHERE job_id IN (SELECT id FROM jobs WHERE created_at < ?)").bind(cutoff));
        statements.push(env.DB.prepare("DELETE FROM jobs WHERE created_at < ? AND status IN ('review','blocked','error','cancelled')").bind(cutoff));
        if (statements.length) await env.DB.batch(statements);
        return json({ ok: true, cutoff, deleted_previews: (oldPreviews.results || []).length, deleted_jobs: (oldJobs.results || []).length, deleted_objects: keys.size });
      }
      if (parts[1] === "campaigns" && parts[2] === "sync" && request.method === "POST") {
        if (!workerAuthorized(request, env)) return json({ error: "worker_unauthorized" }, 401);
        const body = await request.json(); const timestamp = now(); let synced = 0;
        for (const campaign of body.campaigns || []) {
          if (!campaign.id || !campaign.title) continue;
          const planPayload = campaign.plan_json || campaign.plan || null;
          await env.DB.prepare("INSERT INTO campaigns (id,title,brand,status,score,rate_per_1k,budget_left,platforms_json,detail_json,plan_json,updated_at,first_seen_at,last_seen_at,priority_components_json,competition_proxy_json,rules_hash,ai_rules_json,ai_rules_status,ai_analyzed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,brand=excluded.brand,status=excluded.status,score=excluded.score,rate_per_1k=excluded.rate_per_1k,budget_left=excluded.budget_left,platforms_json=excluded.platforms_json,detail_json=excluded.detail_json,plan_json=COALESCE(excluded.plan_json, campaigns.plan_json),updated_at=excluded.updated_at,first_seen_at=COALESCE(campaigns.first_seen_at,excluded.first_seen_at),last_seen_at=excluded.last_seen_at,priority_components_json=excluded.priority_components_json,competition_proxy_json=excluded.competition_proxy_json,rules_hash=excluded.rules_hash,ai_rules_json=excluded.ai_rules_json,ai_rules_status=excluded.ai_rules_status,ai_analyzed_at=excluded.ai_analyzed_at").bind(String(campaign.id), campaign.title, campaign.brand || null, campaign.status || "active", campaign.score || 0, campaign.rate_per_1k || 0, campaign.budget_left || 0, JSON.stringify(campaign.platforms || []), JSON.stringify(campaign), planPayload ? JSON.stringify(planPayload) : null, timestamp, timestamp, timestamp, JSON.stringify(campaign.priority_components || {}), JSON.stringify(campaign.competition_proxy || {}), campaign.rules_hash || null, JSON.stringify(campaign.ai_rules || {}), campaign.ai_rules_status || "unavailable", campaign.ai_analyzed_at || null).run();
          synced += 1;
        }
        return json({ ok: true, synced, updated_at: timestamp });
      }
      if (parts[1] === "campaign-intelligence" && request.method === "GET") {
        if (!workerAuthorized(request, env)) return json({ error: "worker_unauthorized" }, 401);
        const result = await env.DB.prepare("SELECT id,rules_hash,ai_rules_json,ai_rules_status,ai_analyzed_at FROM campaigns WHERE status='active'").all();
        return json({ campaigns: result.results || [] });
      }
      if (parts[1] === "campaigns" && request.method === "GET" && !parts[2]) {
        const onlyClipping = url.searchParams.get("clipping") !== "0";
        const result = await env.DB.prepare("SELECT id,title,brand,status,score,rate_per_1k,budget_left,platforms_json,detail_json,plan_json,updated_at,first_seen_at,last_seen_at,priority_components_json,competition_proxy_json,rules_hash,ai_rules_json,ai_rules_status,ai_analyzed_at FROM campaigns WHERE status = 'active' ORDER BY score DESC LIMIT 80").all();
        let campaigns = (result.results || []).map(parse);
        if (onlyClipping) {
          // Keep clipping + unknown-with-materials; drop clear ugc/slideshow when classified
          campaigns = campaigns.filter((c) => {
            if (c.content_kind === "ugc" || c.content_kind === "slideshow") return false;
            if (c.content_kind === "clipping") return true;
            // Not yet classified by sync: keep if title suggests clipping
            const t = String(c.title || "").toLowerCase();
            if (t.includes("clip")) return true;
            return c.content_kind == null;
          });
        }
        campaigns.sort((a, b) => {
          const d = readinessRank(a.readiness_status) - readinessRank(b.readiness_status);
          if (d !== 0) return d;
          return Number(b.readiness_ease || 0) - Number(a.readiness_ease || 0) || Number(b.score || 0) - Number(a.score || 0);
        });
        return json({ campaigns: campaigns.slice(0, 50) });
      }
      if (parts[1] === "campaigns" && parts[2] && request.method === "GET" && !parts[3]) {
        const row = await env.DB.prepare("SELECT * FROM campaigns WHERE id = ?").bind(parts[2]).first();
        return row ? json({ campaign: parse(row) }) : json({ error: "campaign_not_found" }, 404);
      }
      if (parts[1] === "campaigns" && parts[2] && parts[3] === "jobs" && request.method === "POST") {
        const id = crypto.randomUUID(); const timestamp = now();
        const exists = await env.DB.prepare("SELECT id FROM campaigns WHERE id = ? AND status = 'active'").bind(parts[2]).first();
        if (!exists) return json({ error: "campaign_not_found" }, 404);
        try {
          await env.DB.prepare("INSERT INTO jobs (id,campaign_id,status,progress,message,created_at,updated_at) VALUES (?,?,?,?,?,?,?)").bind(id, parts[2], "queued", 0, "Menunggu worker cloud", timestamp, timestamp).run();
        } catch (error) {
          const open = await env.DB.prepare("SELECT id,campaign_id,status,progress,message,created_at,updated_at FROM jobs WHERE campaign_id = ? AND status IN ('queued','processing') ORDER BY created_at LIMIT 1").bind(parts[2]).first();
          if (!open) throw error;
          return json({ job: open, deduped: true }, 200);
        }
        return json({ job: { id, campaign_id: parts[2], status: "queued", progress: 0, message: "Masuk antrean worker cloud", created_at: timestamp } }, 201);
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "run" && request.method === "POST") {
        const jobId = parts[2];
        const job = await env.DB.prepare("SELECT id,campaign_id,status FROM jobs WHERE id = ?").bind(jobId).first();
        if (!job) return json({ error: "job_not_found" }, 404);
        if (job.status !== "queued") return json({ error: "job_not_queued", status: job.status }, 409);
        const githubToken = env.GITHUB_ACTIONS_TOKEN || env.GITHUB_TOKEN;
        if (!githubToken) {
          const message = "Manual dispatch belum tersedia: Pages Function tidak menerima GITHUB_ACTIONS_TOKEN pada runtime Production";
          await env.DB.prepare("UPDATE jobs SET message=?,error=?,updated_at=? WHERE id=? AND status='queued'").bind("Konfigurasi workflow belum siap", message, now(), jobId).run();
          return json({ error: "github_dispatch_not_configured", message, dispatch_mode: "manual_only" }, 503);
        }

        const dispatchToken = crypto.randomUUID();
        const dispatchClaim = await env.DB.prepare("UPDATE jobs SET dispatch_token=?,message=?,error=NULL,updated_at=? WHERE id=? AND status='queued' AND dispatch_token IS NULL").bind(dispatchToken, "Worker GitHub dipicu · dispatching", now(), jobId).run();
        if (!(dispatchClaim.meta?.changes > 0)) return json({ error: "job_already_dispatched" }, 409);
        const repo = env.GITHUB_REPOSITORY || "ibank31/scrapper-engine";
        const workflow = env.GITHUB_WORKFLOW_FILE || "clipper-worker.yml";
        const ref = env.GITHUB_WORKFLOW_REF || "main";
        const githubUrl = `https://api.github.com/repos/${repo}/actions/workflows/${encodeURIComponent(workflow)}/dispatches`;
        try {
          const response = await fetch(githubUrl, {
            method: "POST",
            headers: {
              "authorization": `Bearer ${githubToken}`,
              "accept": "application/vnd.github+json",
              "content-type": "application/json",
              "x-github-api-version": "2022-11-28",
              "user-agent": "clipper-engine"
            },
            body: JSON.stringify({ ref, inputs: { job_id: jobId, dispatch_token: dispatchToken } })
          });
          if (!response.ok) {
            const detail = await response.text();
            const message = detail.slice(0, 500) || `GitHub HTTP ${response.status}`;
            await env.DB.prepare("UPDATE jobs SET dispatch_token=NULL,message=?,error=?,updated_at=? WHERE id=? AND dispatch_token=?").bind("Gagal memicu worker GitHub", message, now(), jobId, dispatchToken).run();
            return json({ error: "github_dispatch_failed", message, github_status: response.status }, 502);
          }
          await env.DB.prepare("UPDATE jobs SET message=?,error=NULL,updated_at=? WHERE id=? AND dispatch_token=?").bind("Worker GitHub dipicu · menunggu runner", now(), jobId, dispatchToken).run();
          return json({ ok: true, dispatched: true, job_id: jobId, workflow, ref });
        } catch (error) {
          const message = String(error.message || error).slice(0, 500);
          await env.DB.prepare("UPDATE jobs SET dispatch_token=NULL,message=?,error=?,updated_at=? WHERE id=? AND dispatch_token=?").bind("Tidak dapat menghubungi GitHub Actions", message, now(), jobId, dispatchToken).run();
          return json({ error: "github_dispatch_network_error", message }, 502);
        }
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "claim" && request.method === "POST") {
        const body = await request.json(); const claimToken = String(body.claim_token || "").slice(0, 200); const runnerId = String(body.runner_id || `ephemeral:${claimToken}`).slice(0, 200);
        if (!claimToken) return json({ error: "claim_token_required" }, 400);
        if (!(await workerOrDispatchAuthorized(request, env, parts[2]))) return json({ error: "worker_unauthorized" }, 401);
        const timestamp = now();
        const result = await env.DB.prepare("UPDATE jobs SET status='processing',progress=1,message=?,error=NULL,claimed_at=?,claimed_by=?,updated_at=? WHERE id=? AND status='queued' AND (dispatch_token IS NULL OR dispatch_token=?)").bind("Worker claimed job", timestamp, runnerId, timestamp, parts[2], claimToken).run();
        if (!(result.meta?.changes > 0)) return json({ error: "job_claim_lost" }, 409);
        return json({ ok: true, job_id: parts[2], claimed_at: timestamp, claimed_by: runnerId });
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "recover" && request.method === "POST") {
        if (!workerAuthorized(request, env)) return json({ error: "worker_unauthorized" }, 401);
        const job = await env.DB.prepare("SELECT id,status,claimed_at,claimed_by FROM jobs WHERE id = ?").bind(parts[2]).first();
        if (!job) return json({ error: "job_not_found" }, 404);
        if (job.status !== "processing" || !job.claimed_at) return json({ error: "job_not_recoverable", status: job.status }, 409);
        const ageSeconds = (Date.now() - Date.parse(job.claimed_at)) / 1000;
        if (!Number.isFinite(ageSeconds) || ageSeconds < claimLeaseSeconds(env)) return json({ error: "claim_lease_active", age_seconds: Math.max(0, ageSeconds) }, 409);
        const evidence = await runnerIsDead(env, job.claimed_by);
        if (!evidence.dead) return json({ error: "runner_not_confirmed_dead", reason: evidence.reason }, evidence.known ? 409 : 503);
        const timestamp = now();
        const result = await env.DB.prepare("UPDATE jobs SET status='queued',progress=0,message=?,error=NULL,dispatch_token=NULL,claimed_at=NULL,claimed_by=NULL,updated_at=? WHERE id=? AND status='processing' AND claimed_at=? AND claimed_by=?").bind("Stale claim dipulihkan; menunggu worker baru", timestamp, parts[2], job.claimed_at, job.claimed_by).run();
        if (!(result.meta?.changes > 0)) return json({ error: "claim_recovery_lost" }, 409);
        return json({ ok: true, job_id: parts[2], recovered_from: job.claimed_by, evidence: evidence.reason });
      }
      if (parts[1] === "jobs" && parts[2] === "recover-stale" && request.method === "POST") {
        if (!workerAuthorized(request, env)) return json({ error: "worker_unauthorized" }, 401);
        const cutoff = new Date(Date.now() - claimLeaseSeconds(env) * 1000).toISOString();
        const result = await env.DB.prepare("SELECT id,claimed_at,claimed_by FROM jobs WHERE status='processing' AND claimed_at IS NOT NULL AND claimed_at < ? ORDER BY claimed_at LIMIT 10").bind(cutoff).all();
        const recovered = []; const skipped = [];
        for (const job of result.results || []) {
          const evidence = await runnerIsDead(env, job.claimed_by);
          if (!evidence.dead) { skipped.push({ id: job.id, reason: evidence.reason }); continue; }
          const timestamp = now();
          const update = await env.DB.prepare("UPDATE jobs SET status='queued',progress=0,message=?,error=NULL,dispatch_token=NULL,claimed_at=NULL,claimed_by=NULL,updated_at=? WHERE id=? AND status='processing' AND claimed_at=? AND claimed_by=?").bind("Stale claim dipulihkan; menunggu worker baru", timestamp, job.id, job.claimed_at, job.claimed_by).run();
          if (update.meta?.changes > 0) recovered.push({ id: job.id, evidence: evidence.reason });
          else skipped.push({ id: job.id, reason: "claim_recovery_lost" });
        }
        return json({ ok: true, recovered, skipped });
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "stages" && request.method === "POST") {
        if (!(await workerOrDispatchAuthorized(request, env, parts[2]))) return json({ error: "worker_unauthorized" }, 401);
        const body = await request.json(); const timestamp = now();
        const runId = String(body.run_id || "").slice(0, 200); const stage = String(body.stage || "").slice(0, 100); const status = String(body.status || "").slice(0, 40);
        if (!runId || !stage || !status) return json({ error: "stage_event_invalid" }, 400);
        await env.DB.prepare("INSERT INTO job_stage_events (id,job_id,run_id,stage,status,started_at,ended_at,metrics_json,error_code,error_detail,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)").bind(crypto.randomUUID(), parts[2], runId, stage, status, body.started_at || null, body.ended_at || null, JSON.stringify(body.metrics || {}), body.error_code || null, body.error_detail || null, timestamp).run();
        await env.DB.prepare("UPDATE jobs SET run_id=COALESCE(run_id,?),updated_at=? WHERE id=?").bind(runId, timestamp, parts[2]).run();
        return json({ ok: true });
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "stages" && request.method === "GET") {
        const result = await env.DB.prepare("SELECT id,job_id,run_id,stage,status,started_at,ended_at,metrics_json,error_code,error_detail,created_at FROM job_stage_events WHERE job_id=? ORDER BY created_at,id").bind(parts[2]).all();
        return json({ stages: result.results || [] });
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "manifest" && request.method === "POST") {
        if (!(await workerOrDispatchAuthorized(request, env, parts[2]))) return json({ error: "worker_unauthorized" }, 401);
        const body = await request.json(); const key = String(body.manifest_key || "").slice(0, 500); const version = Number(body.schema_version || 1);
        if (!key) return json({ error: "manifest_invalid" }, 400);
        const timestamp = now();
        await env.DB.prepare("UPDATE jobs SET manifest_key=?,manifest_schema_version=?,updated_at=? WHERE id=?").bind(key, Number.isFinite(version) ? version : 1, timestamp, parts[2]).run();
        return json({ ok: true, job_id: parts[2], manifest_key: key, schema_version: version });
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "manifest" && request.method === "GET") {
        const row = await env.DB.prepare("SELECT id,run_id,manifest_key,manifest_schema_version FROM jobs WHERE id=?").bind(parts[2]).first();
        return row ? json({ manifest: row }) : json({ error: "job_not_found" }, 404);
      }
      if (parts[1] === "jobs" && request.method === "GET" && !parts[2]) {
        const result = await env.DB.prepare("SELECT j.id,j.campaign_id,j.status,j.progress,j.message,j.error,j.created_at,j.updated_at,c.title AS campaign_title,c.brand AS campaign_brand FROM jobs j JOIN campaigns c ON c.id=j.campaign_id ORDER BY j.updated_at DESC LIMIT 30").all();
        return json({ jobs: result.results || [] });
      }
      if (parts[1] === "jobs" && parts[2] && request.method === "GET" && !parts[3]) {
        const row = await env.DB.prepare("SELECT j.*,c.title AS campaign_title,c.brand AS campaign_brand,c.plan_json AS campaign_plan_json FROM jobs j JOIN campaigns c ON c.id=j.campaign_id WHERE j.id = ?").bind(parts[2]).first();
        if (!row) return json({ error: "job_not_found" }, 404);
        row.campaign_plan = row.campaign_plan_json ? JSON.parse(row.campaign_plan_json) : null; delete row.campaign_plan_json;
        return json({ job: row });
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "previews" && request.method === "GET") {
        const result = await env.DB.prepare("SELECT id,job_id,rank,status,video_key,review_video_key,thumbnail_key,download_url,validation_json,caption_draft,rules_summary_id,checklist_json,review_reason,reviewed_by,reviewed_at,created_at FROM previews WHERE job_id = ? ORDER BY rank").bind(parts[2]).all();
        const previews = await Promise.all((result.results || []).map(async (preview) => ({
          ...preview,
          video_url: preview.review_video_key ? await previewUrl(request, env, preview.review_video_key, 3600) : null,
          download_url: preview.video_key ? await previewUrl(request, env, preview.video_key, 3600) : preview.download_url,
          thumbnail_url: preview.thumbnail_key ? await previewUrl(request, env, preview.thumbnail_key, 3600) : null,
        })));
        return json({ previews });
      }
      if (parts[1] === "previews" && parts[2] && parts[3] === "url" && request.method === "GET") {
        if (!reviewAuthorized(request, env)) return json({ error: "review_unauthorized" }, 401);
        const preview = await env.DB.prepare("SELECT id,status,video_key FROM previews WHERE id = ?").bind(parts[2]).first();
        if (!preview || !preview.video_key) return json({ error: "preview_not_found" }, 404);
        if (!["pending_review", "changes_requested", "approved_for_manual_post"].includes(preview.status)) return json({ error: "preview_not_available", status: preview.status }, 409);
        return json({ preview_id: parts[2], url: await previewUrl(request, env, preview.video_key) });
      }
      if (parts[1] === "previews" && parts[2] && parts[3] === "review" && request.method === "POST") {
        if (!reviewAuthorized(request, env)) return json({ error: "review_unauthorized" }, 401);
        const body = await request.json();
        const action = String(body.action || "").toLowerCase();
        const transitions = { approve: "approved_for_manual_post", reject: "rejected", request_rerender: "changes_requested" };
        if (!Object.prototype.hasOwnProperty.call(transitions, action)) return json({ error: "invalid_review_action" }, 400);
        const reason = String(body.reason || "").trim().slice(0, 1000);
        if ((action === "reject" || action === "request_rerender") && !reason) return json({ error: "review_reason_required" }, 400);
        const current = await env.DB.prepare("SELECT id,status,job_id FROM previews WHERE id = ?").bind(parts[2]).first();
        if (!current) return json({ error: "preview_not_found" }, 404);
        if (!["pending_review", "changes_requested"].includes(current.status)) return json({ error: "preview_not_reviewable", status: current.status }, 409);
        const next = transitions[action];
        const timestamp = now();
        const actor = reviewActor(request, body);
        const eventId = crypto.randomUUID();
        await env.DB.batch([
          env.DB.prepare("UPDATE previews SET status=?,review_reason=?,reviewed_by=?,reviewed_at=? WHERE id=? AND status IN ('pending_review','changes_requested')").bind(next, reason || null, actor, timestamp, parts[2]),
          env.DB.prepare("INSERT INTO preview_events (id,preview_id,from_status,to_status,action,reason,actor,created_at) VALUES (?,?,?,?,?,?,?,?)").bind(eventId, parts[2], current.status, next, action, reason || null, actor, timestamp),
        ]);
        return json({ ok: true, preview: { id: parts[2], job_id: current.job_id, status: next, review_reason: reason || null, reviewed_by: actor, reviewed_at: timestamp } });
      }
      if (parts[1] === "previews" && parts[2] && parts[3] === "events" && request.method === "GET") {
        if (!reviewAuthorized(request, env)) return json({ error: "review_unauthorized" }, 401);
        const result = await env.DB.prepare("SELECT id,preview_id,from_status,to_status,action,reason,actor,created_at FROM preview_events WHERE preview_id = ? ORDER BY created_at").bind(parts[2]).all();
        return json({ events: result.results || [] });
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "cancel" && request.method === "POST") {
        const job = await env.DB.prepare("SELECT id,status,progress FROM jobs WHERE id = ?").bind(parts[2]).first();
        if (!job) return json({ error: "job_not_found" }, 404);
        if (!["queued", "processing"].includes(job.status)) return json({ error: "job_not_active", status: job.status }, 409);
        const timestamp = now();
        await env.DB.prepare("UPDATE jobs SET status='cancelled', message=?, error=NULL, updated_at=? WHERE id=? AND status IN ('queued','processing')").bind("Dihentikan oleh pengguna", timestamp, parts[2]).run();
        return json({ ok: true, job: { id: job.id, status: "cancelled", progress: job.progress, message: "Dihentikan oleh pengguna", updated_at: timestamp } });
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "previews" && request.method === "POST") {
        if (!(await workerOrDispatchAuthorized(request, env, parts[2]))) return json({ error: "worker_unauthorized" }, 401);
        const body = await request.json(); const timestamp = now();
        for (const preview of body.previews || []) {
          await env.DB.prepare("INSERT OR REPLACE INTO previews (id,job_id,rank,status,video_key,review_video_key,thumbnail_key,download_url,validation_json,caption_draft,rules_summary_id,checklist_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)").bind(preview.id || crypto.randomUUID(), parts[2], preview.rank || 0, preview.status || "pending_review", preview.video_key || null, preview.review_video_key || null, preview.thumbnail_key || null, preview.download_url || null, JSON.stringify(preview.validation || {}), preview.caption_draft || null, preview.rules_summary_id || null, JSON.stringify(preview.checklist || []), timestamp).run();
        }
        await env.DB.prepare("UPDATE jobs SET status='review',progress=100,message=?,updated_at=? WHERE id=?").bind(`${(body.previews || []).length} preview siap review`, timestamp, parts[2]).run();
        return json({ ok: true });
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "upload" && request.method === "POST") {
        if (!(await workerOrDispatchAuthorized(request, env, parts[2]))) return json({ error: "worker_unauthorized" }, 401);
        const form = await request.formData(); const file = form.get("file"); const key = String(form.get("key") || "");
        if (!file || !key || !env.CLIPS) return json({ error: "upload_invalid" }, 400);
        await env.CLIPS.put(key, file.stream(), { httpMetadata: { contentType: file.type || "application/octet-stream", cacheControl: "private,no-store" } });
        return json({ ok: true, key, download_url: await previewUrl(request, env, key) });
      }
      if (parts[1] === "files" && request.method === "GET") {
        const key = url.searchParams.get("key"); if (!key || !env.CLIPS) return json({ error: "file_not_found" }, 404);
        if (env.PREVIEW_SIGNING_SECRET) {
          const expires = Number(url.searchParams.get("exp") || 0);
          const provided = url.searchParams.get("sig") || "";
          const expected = expires > Math.floor(Date.now() / 1000) ? await previewSignature(env.PREVIEW_SIGNING_SECRET, key, expires) : "";
          if (!expected || provided.length !== expected.length || provided !== expected) return json({ error: "preview_url_expired" }, 403);
        }
        const rangeHeader = request.headers.get("range");
        let range = null;
        if (rangeHeader) {
          const match = /^bytes=(\d*)-(\d*)$/i.exec(rangeHeader.trim());
          if (!match) return new Response(null, { status: 416, headers: { ...cors, "content-range": "bytes */*" } });
          const start = match[1] === "" ? null : Number(match[1]);
          const end = match[2] === "" ? null : Number(match[2]);
          if ((start !== null && !Number.isSafeInteger(start)) || (end !== null && !Number.isSafeInteger(end))) return new Response(null, { status: 416, headers: cors });
          range = start === null ? { suffix: end } : { offset: start, ...(end === null ? {} : { length: end - start + 1 }) };
        }
        const object = await env.CLIPS.get(key, range ? { range } : undefined); if (!object) return json({ error: "file_not_found" }, 404);
        const headers = new Headers(cors); object.writeHttpMetadata(headers); headers.set("etag", object.httpEtag); headers.set("accept-ranges", "bytes");
        if (rangeHeader && object.range) {
          const offset = object.range.offset || 0;
          const length = object.range.length || object.size;
          headers.set("content-range", `bytes ${offset}-${offset + length - 1}/${object.size}`);
          headers.set("content-length", String(length));
          return new Response(object.body, { status: 206, headers });
        }
        return new Response(object.body, { headers });
      }
      if (parts[1] === "jobs" && parts[2] && request.method === "PATCH") {
        if (!(await workerOrDispatchAuthorized(request, env, parts[2]))) return json({ error: "worker_unauthorized" }, 401);
        const body = await request.json(); const timestamp = now();
        await env.DB.prepare("UPDATE jobs SET status = ?, progress = ?, message = ?, error = ?, updated_at = ? WHERE id = ?").bind(body.status, body.progress || 0, body.message || null, body.error || null, timestamp, parts[2]).run();
        return json({ ok: true });
      }
      return json({ error: "not_found" }, 404);
    } catch (error) { return json({ error: "server_error", message: String(error.message || error) }, 500); }
  }
};
