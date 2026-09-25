import { validateCaptionRevision } from "./caption_compliance.js";

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
function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]));
  return value;
}
async function sha256Hex(value) {
  const bytes = new TextEncoder().encode(JSON.stringify(canonicalize(value)));
  return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), (b) => b.toString(16).padStart(2, "0")).join("");
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
async function executionAuthorized(request, env, jobId, body = {}) {
  if (!(await workerOrDispatchAuthorized(request, env, jobId))) return { ok: false, error: "worker_unauthorized", status: 401 };
  const job = await env.DB.prepare("SELECT status,execution_generation,run_id,active_run_token FROM jobs WHERE id=?").bind(jobId).first();
  if (!job) return { ok: false, error: "job_not_found", status: 404 };
  const claimToken = request.headers.get("x-claim-token") || request.headers.get("x-dispatch-token") || "";
  if (!job.active_run_token || claimToken !== job.active_run_token) return { ok: false, error: "stale_claim", status: 409 };
  if (Number(body.execution_generation || 0) !== Number(job.execution_generation || 1)) return { ok: false, error: "stale_generation", status: 409 };
  if (body.run_id && job.run_id && String(body.run_id) !== String(job.run_id)) return { ok: false, error: "stale_run", status: 409 };
  if (["cancelled", "review", "blocked", "error"].includes(job.status)) return { ok: false, error: "job_terminal", status: 409 };
  return { ok: true, job };
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
  for (const [name, definition] of Object.entries({ review_video_key: "TEXT", review_reason: "TEXT", reviewed_by: "TEXT", reviewed_at: "TEXT", tier: "TEXT", candidate_id: "TEXT", source_asset_id: "TEXT", artifact_hash: "TEXT", distinctness_json: "TEXT NOT NULL DEFAULT '{}'", platform: "TEXT", platform_profile_json: "TEXT NOT NULL DEFAULT '{}'", subtitle_delivery_json: "TEXT NOT NULL DEFAULT '{}'", sound_tags_json: "TEXT NOT NULL DEFAULT '{}'", caption_revision_id: "TEXT", caption_hash: "TEXT", approval_artifact_hash: "TEXT", approval_caption_revision_id: "TEXT", approval_rules_hash: "TEXT", platform_profile_version: "TEXT", schedule_intent_hash: "TEXT", rules_summary_id: "TEXT", parent_preview_id: "TEXT", revision_number: "INTEGER NOT NULL DEFAULT 1", render_revision: "TEXT NOT NULL DEFAULT 'render-v1'", superseded_at: "TEXT" })) {
    if (!previewColumns.has(name)) await db.prepare("ALTER TABLE previews ADD COLUMN " + name + " " + definition).run();
  }
  await db.prepare("CREATE TABLE IF NOT EXISTS preview_events (id TEXT PRIMARY KEY, preview_id TEXT NOT NULL, from_status TEXT, to_status TEXT NOT NULL, action TEXT NOT NULL, reason TEXT, actor TEXT, created_at TEXT NOT NULL)").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_preview_events_preview ON preview_events(preview_id, created_at)").run();
  await db.prepare("CREATE TABLE IF NOT EXISTS caption_revisions (id TEXT PRIMARY KEY, preview_id TEXT NOT NULL, revision_number INTEGER NOT NULL, text TEXT NOT NULL, fields_json TEXT NOT NULL DEFAULT '{}', platform TEXT NOT NULL, editor TEXT NOT NULL, character_count_method TEXT NOT NULL, character_count INTEGER NOT NULL, caption_hash TEXT NOT NULL, rules_hash TEXT NOT NULL, platform_profile_version TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE (preview_id, revision_number), UNIQUE (preview_id, caption_hash))").run();
  const jobInfo = await db.prepare("PRAGMA table_info(jobs)").all();
  const jobColumns = new Set((jobInfo.results || []).map((row) => row.name));
  for (const [name, definition] of Object.entries({ dispatch_token: "TEXT", claimed_at: "TEXT", claimed_by: "TEXT", run_id: "TEXT", plan_snapshot_json: "TEXT", rules_hash: "TEXT", plan_schema_version: "INTEGER", source_fingerprint_json: "TEXT NOT NULL DEFAULT '{}'", execution_generation: "INTEGER NOT NULL DEFAULT 1", output_contract_json: "TEXT NOT NULL DEFAULT '{}'", output_selection_json: "TEXT NOT NULL DEFAULT '{}'", output_contract_status: "TEXT NOT NULL DEFAULT 'pending'", cancelled_at: "TEXT", active_run_token: "TEXT", manifest_key: "TEXT", manifest_schema_version: "INTEGER" })) {
    if (!jobColumns.has(name)) await db.prepare("ALTER TABLE jobs ADD COLUMN " + name + " " + definition).run();
  }
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_jobs_claimed ON jobs(status, claimed_at)").run();
  await db.prepare("CREATE TABLE IF NOT EXISTS job_stage_events (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, run_id TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT, ended_at TEXT, metrics_json TEXT NOT NULL DEFAULT '{}', error_code TEXT, error_detail TEXT, created_at TEXT NOT NULL)").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_job_stage_events_job ON job_stage_events(job_id, created_at)").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_job_stage_events_run ON job_stage_events(run_id, stage, created_at)").run();
  await db.prepare("CREATE TABLE IF NOT EXISTS buffer_uploads (id TEXT PRIMARY KEY, preview_id TEXT NOT NULL, channel_id TEXT NOT NULL, buffer_post_id TEXT, status TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL, FOREIGN KEY (preview_id) REFERENCES previews(id))").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_buffer_uploads_preview ON buffer_uploads(preview_id, created_at)").run();
  await db.prepare("CREATE TABLE IF NOT EXISTS delivery_operations (operation_key TEXT PRIMARY KEY, preview_id TEXT NOT NULL, channel_id TEXT NOT NULL, schedule_revision TEXT NOT NULL, caption_revision_id TEXT NOT NULL, payload_hash TEXT NOT NULL, schedule_intent_json TEXT NOT NULL DEFAULT '{}', provider_state TEXT NOT NULL DEFAULT 'pending', retry_class TEXT NOT NULL DEFAULT 'not_attempted', attempt_count INTEGER NOT NULL DEFAULT 0, provider_post_id TEXT, provider_due_at TEXT, provider_status TEXT, provider_response_json TEXT NOT NULL DEFAULT '{}', last_error TEXT, last_observed_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE (preview_id, channel_id, schedule_revision, caption_revision_id))").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_delivery_operations_preview ON delivery_operations(preview_id, created_at)").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_delivery_operations_state ON delivery_operations(provider_state, updated_at)").run();
  await db.prepare("CREATE TABLE IF NOT EXISTS retention_events (id TEXT PRIMARY KEY, preview_id TEXT, object_key TEXT, decision TEXT NOT NULL, reason TEXT NOT NULL, dependency_json TEXT NOT NULL DEFAULT '{}', evaluated_at TEXT NOT NULL)").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_retention_events_preview ON retention_events(preview_id, evaluated_at)").run();
  await db.prepare("CREATE TABLE IF NOT EXISTS provider_request_ledger (id TEXT PRIMARY KEY, provider TEXT NOT NULL, request_class TEXT NOT NULL, period_key TEXT NOT NULL, created_at TEXT NOT NULL)").run();
  await db.prepare("CREATE INDEX IF NOT EXISTS idx_provider_request_ledger_period ON provider_request_ledger(provider, period_key, created_at)").run();
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
  if (!env.REVIEW_TOKEN) return false;
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
  try {
    const periodKey = new Date().toISOString().slice(0, 7);
    await env.DB.prepare("INSERT INTO provider_request_ledger (id,provider,request_class,period_key,created_at) VALUES (?,?,?,?,?)").bind(crypto.randomUUID(), "buffer", query.includes("mutation") ? "mutation" : "read", periodKey, now()).run();
  } catch (_) { /* request accounting must not hide the provider response */ }
  const payload = await response.json();
  if (!response.ok || payload.errors?.length) throw new Error(payload.errors?.map((x) => x.message).join("; ") || `Buffer HTTP ${response.status}`);
  return payload.data;
}

async function resolveBufferChannels(env) {
  const orgData = await bufferRequest(env, "query { account { organizations { id name } } }");
  const channels = [];
  for (const organization of orgData.account?.organizations || []) {
    const data = await bufferRequest(env, "query($organizationId: OrganizationId!) { channels(input: { organizationId: $organizationId }) { id name service } }", { organizationId: organization.id });
    for (const channel of data.channels || []) channels.push({ ...channel, organizationId: organization.id, organizationName: organization.name });
  }
  return channels;
}

async function bufferCapacityPreflight(env, channelIds) {
  const periodKey = new Date().toISOString().slice(0, 7);
  const budget = await env.DB.prepare("SELECT COUNT(*) AS count FROM provider_request_ledger WHERE provider='buffer' AND period_key=?").bind(periodKey).first();
  const failures = [];
  if (Number(budget?.count || 0) >= 3000) failures.push({ code: "request_budget_exhausted", limit: 3000, actual: Number(budget?.count || 0) });
  if (channelIds.length > 3) failures.push({ code: "free_plan_channel_limit", limit: 3, actual: channelIds.length });
  for (const channelId of channelIds) {
    const usage = await env.DB.prepare("SELECT COUNT(*) AS count FROM delivery_operations WHERE channel_id=? AND provider_state IN ('pending','attempting','unknown','scheduled','unresolved')").bind(channelId).first();
    if (Number(usage?.count || 0) >= 10) failures.push({ code: "scheduled_capacity_exhausted", channel_id: channelId, limit: 10, actual: Number(usage?.count || 0) });
  }
  return { ok: failures.length === 0, failures, request_count: Number(budget?.count || 0), request_budget: 3000 };
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
        if (!reviewAuthorized(request, env)) return json({ error: "review_unauthorized" }, 401);
        const channels = await resolveBufferChannels(env);
        return json({ channels });
      }
      if (parts[1] === "previews" && parts[2] && parts[3] === "buffer" && parts[4] === "preflight" && request.method === "POST") {
        if (!reviewAuthorized(request, env)) return json({ error: "review_unauthorized" }, 401);
        const body = await request.json();
        const preview = await env.DB.prepare("SELECT p.id,p.status,p.video_key,p.caption_draft,p.artifact_hash,p.caption_revision_id,p.approval_artifact_hash,p.approval_caption_revision_id,p.approval_rules_hash,p.platform,p.platform_profile_json,j.rules_hash FROM previews p JOIN jobs j ON j.id=p.job_id WHERE p.id=?").bind(parts[2]).first();
        if (!preview || !preview.video_key) return json({ error: "preview_not_found" }, 404);
        if (preview.status !== "approved_for_manual_post") return json({ error: "preview_not_approved", status: preview.status }, 409);
        const channelIds = [...new Set((body.channel_ids || []).map(String).filter(Boolean))].slice(0, 3);
        if (!channelIds.length) return json({ error: "channel_ids_required" }, 400);
        const channels = await resolveBufferChannels(env);
        const channelMap = new Map(channels.map((channel) => [String(channel.id), channel]));
        const missing = channelIds.filter((id) => !channelMap.has(id));
        if (missing.length) return json({ error: "channel_not_found", channel_ids: missing }, 400);
        const capacity = await bufferCapacityPreflight(env, channelIds);
        if (!capacity.ok) return json({ error: "capacity_preflight_failed", capacity }, 409);
        const text = String(body.text || preview.caption_draft || "").trim();
        const revision = await env.DB.prepare("SELECT * FROM caption_revisions WHERE id=? AND preview_id=?").bind(preview.caption_revision_id, preview.id).first();
        if (!revision || text !== String(revision.text)) return json({ error: "caption_revision_mismatch" }, 409);
        const compliance = validateCaptionRevision({ ...revision, fields: parseJson(revision.fields_json, {}) }, parseJson(preview.platform_profile_json, { platform: preview.platform }), preview.rules_hash);
        if (!compliance.ok) return json({ error: "caption_compliance_failed", compliance }, 422);
        const scheduleIntent = { schema_version: 1, contract: "next_queue_slot", provider: "buffer", capability_version: "schedule-capability-v1", timezone: String(body.timezone || "UTC"), requested_local: body.requested_local || null, requested_utc: null, provider_mode: "automatic/addToQueue", provider_due_at: null };
        const checks = channelIds.map((channelId) => { const channel = channelMap.get(channelId); const limit = bufferTextLimit(channel.service); return { channel_id: channelId, service: channel.service, name: channel.name, valid: text.length <= limit, character_count: text.length, limit, error: text.length <= limit ? null : `Caption melebihi batas ${limit} untuk ${channel.service || "channel"}` }; });
        return json({ ok: checks.every((item) => item.valid), preview_id: preview.id, schedule_intent: scheduleIntent, channels: checks });
      }
      if (parts[1] === "previews" && parts[2] && parts[3] === "buffer" && request.method === "POST") {
        if (!reviewAuthorized(request, env)) return json({ error: "review_unauthorized" }, 401);
        const body = await request.json();
        const preview = await env.DB.prepare("SELECT p.id,p.status,p.video_key,p.caption_draft,p.artifact_hash,p.caption_revision_id,p.approval_artifact_hash,p.approval_caption_revision_id,p.approval_rules_hash,p.platform,p.platform_profile_json,j.rules_hash FROM previews p JOIN jobs j ON j.id=p.job_id WHERE p.id=?").bind(parts[2]).first();
        if (!preview || !preview.video_key) return json({ error: "preview_not_found" }, 404);
        if (preview.status !== "approved_for_manual_post") return json({ error: "preview_not_approved", status: preview.status }, 409);
        if (!preview.approval_artifact_hash || preview.approval_artifact_hash !== preview.artifact_hash || preview.approval_caption_revision_id !== preview.caption_revision_id || preview.approval_rules_hash !== preview.rules_hash) return json({ error: "approval_provenance_invalid" }, 409);
        if (String(body.artifact_hash || "") !== preview.approval_artifact_hash || String(body.caption_revision_id || "") !== preview.approval_caption_revision_id) return json({ error: "approval_revision_mismatch" }, 409);
        const channelIds = [...new Set((body.channel_ids || []).map(String).filter(Boolean))].slice(0, 3);
        if (!channelIds.length) return json({ error: "channel_ids_required" }, 400);
        const text = String(body.text || preview.caption_draft || "").trim();
        if (!text) return json({ error: "caption_required", message: "Caption dan tagar wajib tersedia sebelum upload." }, 400);
        const revision = await env.DB.prepare("SELECT * FROM caption_revisions WHERE id=? AND preview_id=?").bind(preview.caption_revision_id, preview.id).first();
        if (!revision || text !== String(revision.text)) return json({ error: "caption_revision_mismatch" }, 409);
        const compliance = validateCaptionRevision({ ...revision, fields: parseJson(revision.fields_json, {}) }, parseJson(preview.platform_profile_json, { platform: preview.platform }), preview.rules_hash);
        if (!compliance.ok) return json({ error: "caption_compliance_failed", compliance }, 422);
        const channels = await resolveBufferChannels(env);
        const channelMap = new Map(channels.map((channel) => [String(channel.id), channel]));
        const missing = channelIds.filter((id) => !channelMap.has(id));
        if (missing.length) return json({ error: "channel_not_found", channel_ids: missing }, 400);
        const capacity = await bufferCapacityPreflight(env, channelIds);
        if (!capacity.ok) return json({ error: "capacity_preflight_failed", capacity }, 409);
        const scheduleRevision = "schedule-capability-v1";
        const scheduleIntent = { schema_version: 1, contract: "next_queue_slot", provider: "buffer", capability_version: scheduleRevision, timezone: String(body.timezone || "UTC"), requested_local: body.requested_local || null, requested_utc: null, provider_mode: "automatic/addToQueue", provider_due_at: null };
        const outcomes = [];
        for (const channelId of channelIds) {
          const channel = channelMap.get(channelId);
          const payload = { text, channelId, schedulingType: "automatic", mode: "addToQueue", asset_url: publicMediaUrl(request, env, preview.video_key) };
          const key = `delivery-${(await sha256Hex({ preview_id: preview.id, channel_id: channelId, schedule_revision: scheduleRevision, caption_revision_id: preview.caption_revision_id })).slice(0, 32)}`;
          const hash = await sha256Hex(payload);
          const existing = await env.DB.prepare("SELECT * FROM delivery_operations WHERE operation_key=?").bind(key).first();
          if (existing && ["scheduled", "published"].includes(existing.provider_state)) { outcomes.push({ channel_id: channelId, operation_key: key, status: existing.provider_state, provider_post_id: existing.provider_post_id, due_at: existing.provider_due_at, idempotent: true }); continue; }
          if (existing && ["attempting", "unknown"].includes(existing.provider_state)) { outcomes.push({ channel_id: channelId, operation_key: key, status: existing.provider_state, retryable: false, idempotent: true }); continue; }
          const timestamp = now();
          await env.DB.prepare("INSERT OR IGNORE INTO delivery_operations (operation_key,preview_id,channel_id,schedule_revision,caption_revision_id,payload_hash,schedule_intent_json,provider_state,retry_class,attempt_count,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)").bind(key, preview.id, channelId, scheduleRevision, preview.caption_revision_id, hash, JSON.stringify(scheduleIntent), "pending", "not_attempted", 0, timestamp, timestamp).run();
          await env.DB.prepare("UPDATE delivery_operations SET provider_state='attempting',attempt_count=attempt_count+1,retry_class='provider_request',updated_at=? WHERE operation_key=? AND provider_state IN ('pending','failed')").bind(timestamp, key).run();
          const limit = bufferTextLimit(channel.service);
          if (text.length > limit) { const error = `Caption melebihi batas ${limit} untuk ${channel.service || "channel"}`; await env.DB.prepare("UPDATE delivery_operations SET provider_state='failed',retry_class='permanent',last_error=?,updated_at=? WHERE operation_key=?").bind(error, now(), key).run(); outcomes.push({ channel_id: channelId, operation_key: key, status: "failed", retryable: false, error }); continue; }
          try {
            const data = await bufferRequest(env, "mutation($input: CreatePostInput!) { createPost(input: $input) { ... on PostActionSuccess { post { id dueAt channelId } } ... on MutationError { message } } }", { input: { text, channelId, schedulingType: "automatic", mode: "addToQueue", assets: [{ video: { url: payload.asset_url } }] } });
            const result = data.createPost || {}; const post = result.post || {};
            if (!post.id || (!post.dueAt && !post.channelId)) {
              const error = result.message || "malformed_or_unknown_provider_success";
              await env.DB.prepare("UPDATE delivery_operations SET provider_state='unknown',retry_class='unknown_outcome',last_error=?,provider_response_json=?,updated_at=? WHERE operation_key=?").bind(error, JSON.stringify(result).slice(0, 4000), now(), key).run();
              outcomes.push({ channel_id: channelId, operation_key: key, status: "unknown", retryable: false, error }); continue;
            }
            await env.DB.prepare("UPDATE delivery_operations SET provider_state='scheduled',retry_class='none',provider_post_id=?,provider_due_at=?,provider_status='scheduled',provider_response_json=?,last_observed_at=?,updated_at=? WHERE operation_key=?").bind(post.id, post.dueAt || null, JSON.stringify(result).slice(0, 4000), now(), now(), key).run();
            await env.DB.prepare("INSERT INTO buffer_uploads (id,preview_id,channel_id,buffer_post_id,status,error,created_at) VALUES (?,?,?,?,?,?,?)").bind(crypto.randomUUID(), preview.id, channelId, post.id, "scheduled", null, now()).run();
            outcomes.push({ channel_id: channelId, operation_key: key, status: "scheduled", provider_post_id: post.id, due_at: post.dueAt || null });
          } catch (error) {
            const message = String(error.message || error).slice(0, 1000);
            const retryable = /HTTP (429|5\d\d)|rate limit|temporar|connection reset/i.test(message);
            const state = retryable ? "failed" : "unknown";
            const retryClass = retryable ? (/429|rate limit/i.test(message) ? "throttled" : "transient") : "unknown_outcome";
            await env.DB.prepare("UPDATE delivery_operations SET provider_state=?,retry_class=?,last_error=?,updated_at=? WHERE operation_key=?").bind(state, retryClass, message, now(), key).run();
            outcomes.push({ channel_id: channelId, operation_key: key, status: state, retryable, error: message });
          }
        }
        const counts = { scheduled: outcomes.filter((item) => item.status === "scheduled").length, failed: outcomes.filter((item) => item.status === "failed").length, unknown: outcomes.filter((item) => item.status === "unknown").length };
        const outcome = counts.unknown ? "unknown" : counts.scheduled === channelIds.length ? "all_succeeded" : counts.scheduled ? "partial" : "none";
        return json({ ok: outcome === "all_succeeded", outcome, preview_id: preview.id, schedule_intent: scheduleIntent, counts, operations: outcomes });
      }
      if (parts[1] === "previews" && parts[2] && parts[3] === "operations" && request.method === "GET") {
        if (!reviewAuthorized(request, env)) return json({ error: "review_unauthorized" }, 401);
        const result = await env.DB.prepare("SELECT operation_key,preview_id,channel_id,schedule_revision,caption_revision_id,payload_hash,schedule_intent_json,provider_state,retry_class,attempt_count,provider_post_id,provider_due_at,provider_status,provider_response_json,last_error,last_observed_at,created_at,updated_at FROM delivery_operations WHERE preview_id=? ORDER BY channel_id").bind(parts[2]).all();
        return json({ operations: result.results || [] });
      }
      if (parts[1] === "delivery-operations" && parts[2] && parts[3] === "retry" && request.method === "POST") {
        if (!reviewAuthorized(request, env)) return json({ error: "review_unauthorized" }, 401);
        const operation = await env.DB.prepare("SELECT * FROM delivery_operations WHERE operation_key=?").bind(parts[2]).first();
        if (!operation) return json({ error: "operation_not_found" }, 404);
        if (operation.provider_state === "unknown") return json({ error: "unknown_requires_reconciliation" }, 409);
        if (!["failed"].includes(operation.provider_state)) return json({ error: "operation_not_retryable", status: operation.provider_state }, 409);
        if (!["transient", "throttled"].includes(operation.retry_class) || Number(operation.attempt_count || 0) >= 3) return json({ error: "retry_budget_exhausted", retry_class: operation.retry_class, attempt_count: operation.attempt_count }, 409);
        await env.DB.prepare("UPDATE delivery_operations SET provider_state='pending',retry_class='operator_retry',last_error=NULL,updated_at=? WHERE operation_key=? AND provider_state='failed'").bind(now(), parts[2]).run();
        return json({ ok: true, operation_key: parts[2], status: "pending" });
      }
      if (parts[1] === "delivery-operations" && parts[2] && parts[3] === "reconcile" && request.method === "POST") {
        if (!reviewAuthorized(request, env)) return json({ error: "review_unauthorized" }, 401);
        const operation = await env.DB.prepare("SELECT * FROM delivery_operations WHERE operation_key=?").bind(parts[2]).first();
        if (!operation) return json({ error: "operation_not_found" }, 404);
        if (!operation.provider_post_id) return json({ error: "provider_post_id_missing" }, 409);
        const data = await bufferRequest(env, "query($id: ID!) { post(id: $id) { id status dueAt channelId } }", { id: operation.provider_post_id });
        const post = data.post;
        if (!post) {
          await env.DB.prepare("UPDATE delivery_operations SET provider_state='failed',retry_class='permanent',last_error='provider_post_not_found',last_observed_at=?,updated_at=? WHERE operation_key=?").bind(now(), now(), parts[2]).run();
          return json({ error: "provider_post_not_found", operation_key: parts[2], provider_state: "failed" }, 404);
        }
        const status = String(post.status || "").toLowerCase();
        const localState = status === "sent" || status === "published" ? "published" : status === "error" ? "failed" : "scheduled";
        await env.DB.prepare("UPDATE delivery_operations SET provider_state=?,provider_status=?,provider_due_at=?,provider_response_json=?,last_observed_at=?,updated_at=? WHERE operation_key=?").bind(localState, post.status || null, post.dueAt || null, JSON.stringify(post).slice(0, 4000), now(), now(), parts[2]).run();
        return json({ ok: true, operation_key: parts[2], provider: post, provider_state: localState });
      }
      if (parts[1] === "delivery-operations" && parts[2] === "alerts" && request.method === "GET") {
        if (!reviewAuthorized(request, env)) return json({ error: "review_unauthorized" }, 401);
        const threshold = new Date(Date.now() - 15 * 60 * 1000).toISOString();
        const result = await env.DB.prepare("SELECT operation_key,preview_id,channel_id,provider_state,retry_class,updated_at,last_error FROM delivery_operations WHERE provider_state IN ('attempting','unknown') AND updated_at < ? ORDER BY updated_at LIMIT 100").bind(threshold).all();
        return json({ alerts: (result.results || []).map((operation) => ({ ...operation, severity: "high", code: "stuck_delivery_operation" })), threshold });
      }
      if (parts[1] === "maintenance" && parts[2] === "cleanup-previews" && request.method === "POST") {
        if (!(await cleanupAuthorized(request, env))) return json({ error: "cleanup_unauthorized" }, 401);
        const cutoff = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
        const scanCutoff = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString();
        const oldPreviews = await env.DB.prepare("SELECT id,job_id,status,created_at,video_key,review_video_key,thumbnail_key FROM previews WHERE created_at < ?").bind(scanCutoff).all();
        const oldJobs = await env.DB.prepare("SELECT id,manifest_key FROM jobs WHERE created_at < ? AND status IN ('review','blocked','error','cancelled')").bind(cutoff).all();
        const activeStates = new Set(["planned", "pending", "attempting", "unknown", "scheduled", "unresolved"]);
        const deletablePreviews = []; const retainedPreviews = []; const retentionStatements = []; const evaluatedAt = now();
        for (const row of oldPreviews.results || []) {
          const operations = await env.DB.prepare("SELECT operation_key,provider_state FROM delivery_operations WHERE preview_id=?").bind(row.id).all();
          const active = (operations.results || []).filter((operation) => activeStates.has(String(operation.provider_state || "").toLowerCase()));
          const ageDays = (Date.now() - Date.parse(row.created_at)) / 86400000;
          const reviewWindow = ["pending_review", "changes_requested", "pending_render"].includes(row.status) ? 14 : ["approved_for_manual_post"].includes(row.status) ? 3 : 1;
          const retain = active.length > 0 || ageDays < reviewWindow;
          const reason = active.length ? "active_delivery_dependency" : retain ? "review_or_approved_window" : "no_active_dependency";
          retentionStatements.push(env.DB.prepare("INSERT INTO retention_events (id,preview_id,object_key,decision,reason,dependency_json,evaluated_at) VALUES (?,?,?,?,?,?,?)").bind(crypto.randomUUID(), row.id, row.video_key || row.review_video_key || row.thumbnail_key || null, retain ? "retain" : "delete", reason, JSON.stringify((operations.results || []).map((operation) => ({ operation_key: operation.operation_key, provider_state: operation.provider_state }))).slice(0, 4000), evaluatedAt));
          (retain ? retainedPreviews : deletablePreviews).push(row);
        }
        const retainedJobIds = new Set(retainedPreviews.map((row) => String(row.job_id)));
        const deletableJobs = (oldJobs.results || []).filter((row) => !retainedJobIds.has(String(row.id)));
        const keys = new Set();
        for (const row of deletablePreviews) { if (row.video_key) keys.add(row.video_key); if (row.review_video_key) keys.add(row.review_video_key); if (row.thumbnail_key) keys.add(row.thumbnail_key); }
        for (const row of deletableJobs) if (row.manifest_key) keys.add(row.manifest_key);
        if (env.CLIPS && keys.size) await env.CLIPS.delete([...keys]);
        const statements = [];
        statements.push(...retentionStatements);
        for (const row of deletablePreviews) statements.push(env.DB.prepare("DELETE FROM preview_events WHERE preview_id=?").bind(row.id));
        for (const row of deletablePreviews) statements.push(env.DB.prepare("DELETE FROM caption_revisions WHERE preview_id=?").bind(row.id));
        for (const row of deletablePreviews) statements.push(env.DB.prepare("DELETE FROM delivery_operations WHERE preview_id=?").bind(row.id));
        for (const row of deletablePreviews) statements.push(env.DB.prepare("DELETE FROM previews WHERE id=?").bind(row.id));
        for (const row of deletableJobs) statements.push(env.DB.prepare("DELETE FROM job_stage_events WHERE job_id=?").bind(row.id));
        for (const row of deletableJobs) statements.push(env.DB.prepare("DELETE FROM jobs WHERE id=?").bind(row.id));
        if (statements.length) await env.DB.batch(statements);
        return json({ ok: true, cutoff, scan_cutoff: scanCutoff, deleted_previews: deletablePreviews.length, retained_previews: retainedPreviews.length, deleted_jobs: deletableJobs.length, retained_jobs: (oldJobs.results || []).length - deletableJobs.length, deleted_objects: keys.size });
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
        const exists = await env.DB.prepare("SELECT id,title,brand,status,plan_json,rules_hash,detail_json FROM campaigns WHERE id = ? AND status = 'active'").bind(parts[2]).first();
        if (!exists) return json({ error: "campaign_not_found" }, 404);
        const plan = parseJson(exists.plan_json, null);
        if (!plan || typeof plan !== "object" || !plan.source_of_truth || !plan.production) {
          return json({ error: "campaign_plan_required", message: "Campaign harus memiliki plan dan source_of_truth sebelum job dibuat." }, 409);
        }
        const sourceFingerprint = {
          docs_text: plan.source_of_truth.docs_text || exists.detail_json && parseJson(exists.detail_json, {}).docs_text || "",
          source_urls: plan.production.asset_urls || [],
          source_fields: Object.keys(plan.source_of_truth).sort(),
        };
        const rulesHash = await sha256Hex({ plan, source: sourceFingerprint });
        const snapshot = { ...plan, provenance: { rules_hash: rulesHash, captured_at: timestamp, campaign_id: parts[2] } };
        try {
          await env.DB.prepare("INSERT INTO jobs (id,campaign_id,status,progress,message,plan_snapshot_json,rules_hash,plan_schema_version,source_fingerprint_json,execution_generation,output_contract_json,output_contract_status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)").bind(id, parts[2], "queued", 0, "Menunggu worker cloud", JSON.stringify(snapshot), rulesHash, Number(plan.schema_version || 1), JSON.stringify(sourceFingerprint), 1, JSON.stringify(plan.output_contract || {}), "pending", timestamp, timestamp).run();
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
        const dispatchClaim = await env.DB.prepare("UPDATE jobs SET dispatch_token=?,active_run_token=?,message=?,error=NULL,updated_at=? WHERE id=? AND status='queued' AND dispatch_token IS NULL").bind(dispatchToken, dispatchToken, "Worker GitHub dipicu · dispatching", now(), jobId).run();
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
            body: JSON.stringify({ ref, inputs: { job_id: jobId, dispatch_token: dispatchToken }, return_run_details: true })
          });
          if (!response.ok) {
            const detail = await response.text();
            const message = detail.slice(0, 500) || `GitHub HTTP ${response.status}`;
            await env.DB.prepare("UPDATE jobs SET dispatch_token=NULL,active_run_token=NULL,message=?,error=?,updated_at=? WHERE id=? AND dispatch_token=?").bind("Gagal memicu worker GitHub", message, now(), jobId, dispatchToken).run();
            return json({ error: "github_dispatch_failed", message, github_status: response.status }, 502);
          }
          const dispatchResult = await response.json().catch(() => ({}));
          const workflowRunId = String(dispatchResult.workflow_run_id || "").trim();
          if (!workflowRunId) {
            const message = "GitHub menerima dispatch tetapi tidak mengembalikan workflow_run_id";
            await env.DB.prepare("UPDATE jobs SET dispatch_token=NULL,active_run_token=NULL,message=?,error=?,updated_at=? WHERE id=? AND dispatch_token=?").bind("Dispatch GitHub tidak terkonfirmasi", message, now(), jobId, dispatchToken).run();
            return json({ error: "github_dispatch_unconfirmed", message, job_id: jobId, workflow, ref }, 502);
          }
          await env.DB.prepare("UPDATE jobs SET run_id=?,message=?,error=NULL,updated_at=? WHERE id=? AND dispatch_token=?").bind(workflowRunId, `Worker GitHub dibuat · run ${workflowRunId} · menunggu runner`, now(), jobId, dispatchToken).run();
          return json({ ok: true, dispatched: true, job_id: jobId, workflow, ref, workflow_run_id: workflowRunId, run_url: dispatchResult.run_url || null, html_url: dispatchResult.html_url || null });
        } catch (error) {
          const message = String(error.message || error).slice(0, 500);
          await env.DB.prepare("UPDATE jobs SET dispatch_token=NULL,active_run_token=NULL,message=?,error=?,updated_at=? WHERE id=? AND dispatch_token=?").bind("Tidak dapat menghubungi GitHub Actions", message, now(), jobId, dispatchToken).run();
          return json({ error: "github_dispatch_network_error", message }, 502);
        }
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "claim" && request.method === "POST") {
        const body = await request.json(); const claimToken = String(body.claim_token || "").slice(0, 200); const runnerId = String(body.runner_id || `ephemeral:${claimToken}`).slice(0, 200); const runId = String(body.run_id || "").slice(0, 200);
        if (!claimToken) return json({ error: "claim_token_required" }, 400);
        if (!(await workerOrDispatchAuthorized(request, env, parts[2]))) return json({ error: "worker_unauthorized" }, 401);
        const timestamp = now();
        const result = await env.DB.prepare("UPDATE jobs SET status='processing',progress=1,message=?,error=NULL,claimed_at=?,claimed_by=?,active_run_token=?,run_id=COALESCE(?,run_id),updated_at=? WHERE id=? AND status='queued' AND (dispatch_token IS NULL OR dispatch_token=?)").bind("Worker claimed job", timestamp, runnerId, claimToken, runId || null, timestamp, parts[2], claimToken).run();
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
        const result = await env.DB.prepare("UPDATE jobs SET status='queued',progress=0,message=?,error=NULL,dispatch_token=NULL,active_run_token=NULL,claimed_at=NULL,claimed_by=NULL,run_id=NULL,updated_at=? WHERE id=? AND status='processing' AND claimed_at=? AND claimed_by=?").bind("Stale claim dipulihkan; menunggu worker baru", timestamp, parts[2], job.claimed_at, job.claimed_by).run();
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
          const update = await env.DB.prepare("UPDATE jobs SET status='queued',progress=0,message=?,error=NULL,dispatch_token=NULL,active_run_token=NULL,claimed_at=NULL,claimed_by=NULL,run_id=NULL,updated_at=? WHERE id=? AND status='processing' AND claimed_at=? AND claimed_by=?").bind("Stale claim dipulihkan; menunggu worker baru", timestamp, job.id, job.claimed_at, job.claimed_by).run();
          if (update.meta?.changes > 0) recovered.push({ id: job.id, evidence: evidence.reason });
          else skipped.push({ id: job.id, reason: "claim_recovery_lost" });
        }
        return json({ ok: true, recovered, skipped });
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "stages" && request.method === "POST") {
        const body = await request.json(); const timestamp = now();
        const auth = await executionAuthorized(request, env, parts[2], body);
        if (!auth.ok) return json({ error: auth.error }, auth.status);
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
        const body = await request.json(); const key = String(body.manifest_key || "").slice(0, 500); const version = Number(body.schema_version || 1);
        const auth = await executionAuthorized(request, env, parts[2], body);
        if (!auth.ok) return json({ error: auth.error }, auth.status);
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
        const result = await env.DB.prepare("SELECT j.id,j.campaign_id,j.status,j.progress,j.message,j.error,j.output_contract_status,j.output_contract_json,j.output_selection_json,j.created_at,j.updated_at,c.title AS campaign_title,c.brand AS campaign_brand FROM jobs j JOIN campaigns c ON c.id=j.campaign_id ORDER BY j.updated_at DESC LIMIT 30").all();
        return json({ jobs: result.results || [] });
      }
      if (parts[1] === "jobs" && parts[2] && request.method === "GET" && !parts[3]) {
        const row = await env.DB.prepare("SELECT j.*,c.title AS campaign_title,c.brand AS campaign_brand FROM jobs j JOIN campaigns c ON c.id=j.campaign_id WHERE j.id = ?").bind(parts[2]).first();
        if (!row) return json({ error: "job_not_found" }, 404);
        return json({ job: row });
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "previews" && request.method === "GET") {
        const result = await env.DB.prepare("SELECT id,job_id,rank,status,tier,candidate_id,source_asset_id,video_key,review_video_key,thumbnail_key,download_url,validation_json,caption_draft,caption_revision_id,caption_hash,artifact_hash,distinctness_json,platform,platform_profile_json,subtitle_delivery_json,sound_tags_json,approval_artifact_hash,approval_caption_revision_id,approval_rules_hash,rules_summary_id,checklist_json,review_reason,reviewed_by,reviewed_at,created_at FROM previews WHERE job_id = ? ORDER BY rank").bind(parts[2]).all();
        const previews = await Promise.all((result.results || []).map(async (preview) => ({
          ...preview,
          operations: (await env.DB.prepare("SELECT operation_key,channel_id,schedule_intent_json,provider_state,retry_class,provider_post_id,provider_due_at,last_error,attempt_count,updated_at FROM delivery_operations WHERE preview_id=? ORDER BY channel_id").bind(preview.id).all()).results || [],
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
      if (parts[1] === "previews" && parts[2] && parts[3] === "media-probe" && request.method === "GET") {
        if (!reviewAuthorized(request, env)) return json({ error: "review_unauthorized" }, 401);
        const preview = await env.DB.prepare("SELECT id,video_key,artifact_hash FROM previews WHERE id=?").bind(parts[2]).first();
        if (!preview || !preview.video_key) return json({ error: "preview_not_found" }, 404);
        const url = publicMediaUrl(request, env, preview.video_key);
        let response = null; let probeError = null;
        try { response = await fetch(url, { headers: { range: "bytes=0-0" } }); } catch (error) { probeError = String(error.message || error); }
        const contentType = response?.headers.get("content-type") || null;
        const contentRange = response?.headers.get("content-range") || "";
        const contentLength = Number(response?.headers.get("content-length") || (contentRange.match(/\/(\d+)$/) || [])[1] || 0) || null;
        const acceptsRanges = response?.status === 206 || String(response?.headers.get("accept-ranges") || "").toLowerCase() === "bytes";
        const failures = [];
        if (!url.startsWith("https://")) failures.push({ field: "url", code: "https_required" });
        if (!response || ![200, 206].includes(response.status)) failures.push({ field: "http", code: "media_unreachable", actual: response?.status || probeError || "no_response" });
        if (!contentType || !contentType.toLowerCase().startsWith("video/")) failures.push({ field: "content_type", code: "video_content_type_required", actual: contentType });
        if (!contentLength || contentLength <= 0) failures.push({ field: "content_length", code: "positive_length_required", actual: contentLength });
        if (!acceptsRanges) failures.push({ field: "accept_ranges", code: "byte_ranges_required" });
        return json({ preview_id: preview.id, artifact_hash: preview.artifact_hash, url, status: failures.length ? "fail" : "pass", ok: !failures.length, http_status: response?.status || null, content_type: contentType, content_length: contentLength, accepts_ranges: acceptsRanges, failures, probed_at: now() });
      }
      if (parts[1] === "previews" && parts[2] && parts[3] === "review" && request.method === "POST") {
        if (!reviewAuthorized(request, env)) return json({ error: "review_unauthorized" }, 401);
        const body = await request.json();
        const action = String(body.action || "").toLowerCase();
        const transitions = { approve: "approved_for_manual_post", reject: "rejected", request_rerender: "changes_requested" };
        if (!Object.prototype.hasOwnProperty.call(transitions, action)) return json({ error: "invalid_review_action" }, 400);
        const reason = String(body.reason || "").trim().slice(0, 1000);
        if ((action === "reject" || action === "request_rerender") && !reason) return json({ error: "review_reason_required" }, 400);
        const current = await env.DB.prepare("SELECT p.*,j.rules_hash FROM previews p JOIN jobs j ON j.id=p.job_id WHERE p.id = ?").bind(parts[2]).first();
        if (!current) return json({ error: "preview_not_found" }, 404);
        if (!["pending_review", "changes_requested"].includes(current.status)) return json({ error: "preview_not_reviewable", status: current.status }, 409);
        const next = transitions[action];
        const timestamp = now();
        const actor = reviewActor(request, body);
        const eventId = crypto.randomUUID();
        if (action === "approve" && (!current.artifact_hash || !current.caption_revision_id || !current.rules_hash)) return json({ error: "approval_provenance_missing" }, 409);
        const artifactHash = String(body.artifact_hash || current.artifact_hash || "");
        const captionRevisionId = String(body.caption_revision_id || current.caption_revision_id || "");
        if (action === "approve" && (artifactHash !== current.artifact_hash || captionRevisionId !== current.caption_revision_id)) return json({ error: "approval_revision_mismatch" }, 409);
        if (action === "approve") {
          const revision = await env.DB.prepare("SELECT * FROM caption_revisions WHERE id=? AND preview_id=?").bind(captionRevisionId, parts[2]).first();
          if (!revision) return json({ error: "caption_revision_missing" }, 409);
          const compliance = validateCaptionRevision({ ...revision, fields: parseJson(revision.fields_json, {}) }, parseJson(current.platform_profile_json, { platform: current.platform }), current.rules_hash);
          if (!compliance.ok) return json({ error: "caption_compliance_failed", compliance }, 422);
        }
        if (action === "request_rerender") {
          const latest = await env.DB.prepare("SELECT COALESCE(MAX(revision_number),1) AS revision FROM previews WHERE id=? OR parent_preview_id=?").bind(parts[2], parts[2]).first();
          const revisionNumber = Number(latest?.revision || 1) + 1;
          const newId = `${parts[2]}-r${revisionNumber}`;
          await env.DB.prepare("INSERT INTO previews (id,job_id,rank,status,tier,candidate_id,source_asset_id,validation_json,caption_draft,checklist_json,platform,platform_profile_json,subtitle_delivery_json,sound_tags_json,rules_summary_id,parent_preview_id,revision_number,render_revision,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)").bind(newId, current.job_id, current.rank, "pending_render", current.tier, current.candidate_id, current.source_asset_id, current.validation_json || "{}", current.caption_draft || null, current.checklist_json || "[]", current.platform || null, current.platform_profile_json || "{}", current.subtitle_delivery_json || "{}", current.sound_tags_json || "{}", current.rules_summary_id || null, current.id, revisionNumber, `render-${revisionNumber}`, timestamp).run();
          await env.DB.prepare("UPDATE previews SET status='changes_requested',review_reason=?,reviewed_by=?,reviewed_at=?,approval_artifact_hash=NULL,approval_caption_revision_id=NULL,approval_rules_hash=NULL,superseded_at=? WHERE id=? AND status IN ('pending_review','changes_requested')").bind(reason, actor, timestamp, timestamp, parts[2]).run();
          await env.DB.prepare("INSERT INTO preview_events (id,preview_id,from_status,to_status,action,reason,actor,created_at) VALUES (?,?,?,?,?,?,?,?)").bind(eventId, parts[2], current.status, "changes_requested", action, reason, actor, timestamp).run();
          return json({ ok: true, rerender_requested: true, preview: { id: newId, parent_preview_id: current.id, revision_number: revisionNumber, render_revision: `render-${revisionNumber}`, job_id: current.job_id, status: "pending_render", review_reason: reason, reviewed_by: actor, reviewed_at: timestamp } });
        }
        const updated = await env.DB.prepare("UPDATE previews SET status=?,review_reason=?,reviewed_by=?,reviewed_at=?,approval_artifact_hash=?,approval_caption_revision_id=?,approval_rules_hash=? WHERE id=? AND status IN ('pending_review','changes_requested')").bind(next, reason || null, actor, timestamp, action === "approve" ? artifactHash : null, action === "approve" ? captionRevisionId : null, action === "approve" ? current.rules_hash : null, parts[2]).run();
        if (!(updated.meta?.changes > 0)) return json({ error: "review_transition_lost" }, 409);
        await env.DB.prepare("INSERT INTO preview_events (id,preview_id,from_status,to_status,action,reason,actor,created_at) VALUES (?,?,?,?,?,?,?,?)").bind(eventId, parts[2], current.status, next, action, reason || null, actor, timestamp).run();
        return json({ ok: true, preview: { id: parts[2], job_id: current.job_id, status: next, review_reason: reason || null, reviewed_by: actor, reviewed_at: timestamp } });
      }
      if (parts[1] === "previews" && parts[2] && parts[3] === "caption-revisions" && request.method === "POST") {
        if (!reviewAuthorized(request, env)) return json({ error: "review_unauthorized" }, 401);
        const body = await request.json();
        const current = await env.DB.prepare("SELECT p.id,p.platform,p.platform_profile_json,j.rules_hash FROM previews p JOIN jobs j ON j.id=p.job_id WHERE p.id=?").bind(parts[2]).first();
        if (!current) return json({ error: "preview_not_found" }, 404);
        const profile = parseJson(current.platform_profile_json, { platform: current.platform });
        const text = String(body.text || "");
        const profileVersion = String(profile.version || "unknown");
        const revisionNumber = Number((await env.DB.prepare("SELECT COALESCE(MAX(revision_number),0)+1 AS next_revision FROM caption_revisions WHERE preview_id=?").bind(parts[2]).first())?.next_revision || 1);
        const base = { text, fields: body.fields || {}, platform: body.platform || current.platform || profile.platform || "unknown", revision_number: revisionNumber, editor: reviewActor(request, body), character_count_method: "unicode-codepoints-v1", character_count: text.length, rules_hash: current.rules_hash || "", platform_profile_version: profileVersion };
        const captionHash = await sha256Hex(base);
        const revision = { ...base, caption_hash: captionHash, revision_id: `caption-${captionHash.slice(0, 20)}` };
        const compliance = validateCaptionRevision(revision, profile, current.rules_hash || null);
        if (!compliance.ok) return json({ error: "caption_compliance_failed", compliance }, 422);
        const timestamp = now();
        await env.DB.prepare("INSERT INTO caption_revisions (id,preview_id,revision_number,text,fields_json,platform,editor,character_count_method,character_count,caption_hash,rules_hash,platform_profile_version,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)").bind(revision.revision_id, parts[2], revisionNumber, text, JSON.stringify(revision.fields), revision.platform, revision.editor, revision.character_count_method, revision.character_count, captionHash, revision.rules_hash, profileVersion, timestamp).run();
        await env.DB.prepare("UPDATE previews SET caption_draft=?,caption_revision_id=?,caption_hash=? WHERE id=?").bind(text, revision.revision_id, captionHash, parts[2]).run();
        return json({ ok: true, revision, compliance });
      }
      if (parts[1] === "previews" && parts[2] && parts[3] === "caption-revisions" && request.method === "GET") {
        if (!reviewAuthorized(request, env)) return json({ error: "review_unauthorized" }, 401);
        const result = await env.DB.prepare("SELECT id,preview_id,revision_number,text,fields_json,platform,editor,character_count_method,character_count,caption_hash,rules_hash,platform_profile_version,created_at FROM caption_revisions WHERE preview_id=? ORDER BY revision_number").bind(parts[2]).all();
        return json({ revisions: result.results || [] });
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
        const cancelled = await env.DB.prepare("UPDATE jobs SET status='cancelled', message=?, error=NULL, cancelled_at=?, execution_generation=COALESCE(execution_generation,1)+1, active_run_token=NULL, updated_at=? WHERE id=? AND status IN ('queued','processing')").bind("Dihentikan oleh pengguna", timestamp, timestamp, parts[2]).run();
        if (!(cancelled.meta?.changes > 0)) return json({ error: "job_cancel_race" }, 409);
        return json({ ok: true, job: { id: job.id, status: "cancelled", progress: job.progress, message: "Dihentikan oleh pengguna", updated_at: timestamp } });
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "previews" && request.method === "POST") {
        const body = await request.json(); const timestamp = now();
        const auth = await executionAuthorized(request, env, parts[2], body);
        if (!auth.ok) return json({ error: auth.error }, auth.status);
        for (const preview of body.previews || []) {
          await env.DB.prepare("INSERT INTO previews (id,job_id,rank,status,tier,candidate_id,source_asset_id,video_key,review_video_key,thumbnail_key,download_url,validation_json,caption_draft,caption_revision_id,caption_hash,artifact_hash,distinctness_json,platform,platform_profile_json,subtitle_delivery_json,sound_tags_json,rules_summary_id,checklist_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,tier=excluded.tier,candidate_id=excluded.candidate_id,source_asset_id=excluded.source_asset_id,video_key=excluded.video_key,review_video_key=excluded.review_video_key,thumbnail_key=excluded.thumbnail_key,download_url=excluded.download_url,validation_json=excluded.validation_json,caption_draft=excluded.caption_draft,caption_revision_id=excluded.caption_revision_id,caption_hash=excluded.caption_hash,artifact_hash=excluded.artifact_hash,distinctness_json=excluded.distinctness_json,platform=excluded.platform,platform_profile_json=excluded.platform_profile_json,subtitle_delivery_json=excluded.subtitle_delivery_json,sound_tags_json=excluded.sound_tags_json,rules_summary_id=excluded.rules_summary_id,checklist_json=excluded.checklist_json").bind(preview.id || crypto.randomUUID(), parts[2], preview.rank || 0, preview.status || "pending_review", preview.tier || null, preview.candidate_id || null, preview.source_asset_id || null, preview.video_key || null, preview.review_video_key || null, preview.thumbnail_key || null, preview.download_url || null, JSON.stringify(preview.validation || {}), preview.caption_draft || null, preview.caption_revision_id || "draft-v1", preview.caption_hash || null, preview.artifact_hash || preview.video_key || null, JSON.stringify(preview.distinctness || {}), preview.platform || null, JSON.stringify(preview.platform_profile || {}), JSON.stringify(preview.subtitle_delivery || {}), JSON.stringify(preview.sound_tags || {}), preview.rules_summary_id || null, JSON.stringify(preview.checklist || []), timestamp).run();
          const revision = preview.caption_revision || {};
          if (revision.revision_id && revision.text != null) {
            await env.DB.prepare("INSERT INTO caption_revisions (id,preview_id,revision_number,text,fields_json,platform,editor,character_count_method,character_count,caption_hash,rules_hash,platform_profile_version,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING").bind(revision.revision_id, preview.id, Number(revision.revision_number || 1), String(revision.text), JSON.stringify(revision.fields || {}), revision.platform || preview.platform || "unknown", revision.editor || "system", revision.character_count_method || "unicode-codepoints-v1", Number(revision.character_count || String(revision.text).length), revision.caption_hash || preview.caption_hash || "", revision.rules_hash || "", revision.platform_profile_version || "", timestamp).run();
          }
        }
        await env.DB.prepare("UPDATE jobs SET status='review',progress=100,message=?,output_contract_status='review_ready',output_selection_json=?,updated_at=? WHERE id=? AND status='processing' AND execution_generation=? AND active_run_token=?").bind(`${(body.previews || []).length} preview siap review`, JSON.stringify(body.output_selection || {}), timestamp, parts[2], Number(body.execution_generation || 1), request.headers.get("x-claim-token") || request.headers.get("x-dispatch-token") || "").run();
        return json({ ok: true });
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "upload" && request.method === "POST") {
        const form = await request.formData(); const file = form.get("file"); const key = String(form.get("key") || "");
        const auth = await executionAuthorized(request, env, parts[2], { execution_generation: Number(form.get("execution_generation") || 1), run_id: form.get("run_id") || "" });
        if (!auth.ok) return json({ error: auth.error }, auth.status);
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
        const body = await request.json(); const timestamp = now();
        const auth = await executionAuthorized(request, env, parts[2], body);
        if (!auth.ok) return json({ error: auth.error }, auth.status);
        const terminal = ["review", "blocked", "error", "cancelled"];
        const result = await env.DB.prepare("UPDATE jobs SET status = ?, progress = ?, message = ?, error = ?, output_contract_status = COALESCE(?, output_contract_status), output_selection_json = COALESCE(?, output_selection_json), updated_at = ? WHERE id = ? AND execution_generation=? AND active_run_token=? AND status NOT IN ('review','blocked','error','cancelled')").bind(body.status, body.progress || 0, body.message || null, body.error || null, body.output_contract_status || null, body.output_selection ? JSON.stringify(body.output_selection) : null, timestamp, parts[2], Number(body.execution_generation || 1), request.headers.get("x-claim-token") || request.headers.get("x-dispatch-token") || "").run();
        if (!(result.meta?.changes > 0)) return json({ error: "stale_job_write" }, 409);
        return json({ ok: true });
      }
      return json({ error: "not_found" }, 404);
    } catch (error) { return json({ error: "server_error", message: String(error.message || error) }, 500); }
  }
};
