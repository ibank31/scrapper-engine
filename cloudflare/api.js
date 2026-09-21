const cors = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,PATCH,OPTIONS",
  "access-control-allow-headers": "content-type,x-worker-token"
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
  return { ...row, platforms: parseJson(row.platforms_json, []), detail, plan: parseJson(row.plan_json, null), priority_components: priorityComponents, competition_proxy: competitionProxy, new: Boolean(row.first_seen_at && row.first_seen_at === row.last_seen_at), category: detail.category, type: detail.type, flags: detail.flags || [], link: detail.link, verified: Boolean(detail.verified), description: detail.description };
}
function workerAuthorized(request, env) {
  return Boolean(env.WORKER_TOKEN && request.headers.get("x-worker-token") === env.WORKER_TOKEN);
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });
    const url = new URL(request.url);
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts[0] !== "api") return json({ error: "not_found" }, 404);
    try {
      if (parts[1] === "campaigns" && parts[2] === "sync" && request.method === "POST") {
        if (!workerAuthorized(request, env)) return json({ error: "worker_unauthorized" }, 401);
        const body = await request.json(); const timestamp = now(); let synced = 0;
        for (const campaign of body.campaigns || []) {
          if (!campaign.id || !campaign.title) continue;
          await env.DB.prepare("INSERT INTO campaigns (id,title,brand,status,score,rate_per_1k,budget_left,platforms_json,detail_json,plan_json,updated_at,first_seen_at,last_seen_at,priority_components_json,competition_proxy_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,brand=excluded.brand,status=excluded.status,score=excluded.score,rate_per_1k=excluded.rate_per_1k,budget_left=excluded.budget_left,platforms_json=excluded.platforms_json,detail_json=excluded.detail_json,updated_at=excluded.updated_at,last_seen_at=excluded.last_seen_at,priority_components_json=excluded.priority_components_json,competition_proxy_json=excluded.competition_proxy_json").bind(String(campaign.id), campaign.title, campaign.brand || null, campaign.status || "active", campaign.score || 0, campaign.rate_per_1k || 0, campaign.budget_left || 0, JSON.stringify(campaign.platforms || []), JSON.stringify(campaign), null, timestamp, timestamp, timestamp, JSON.stringify(campaign.priority_components || {}), JSON.stringify(campaign.competition_proxy || {})).run();
          synced += 1;
        }
        return json({ ok: true, synced, updated_at: timestamp });
      }
      if (parts[1] === "campaigns" && request.method === "GET" && !parts[2]) {
        const result = await env.DB.prepare("SELECT id,title,brand,status,score,rate_per_1k,budget_left,platforms_json,detail_json,plan_json,updated_at,first_seen_at,last_seen_at,priority_components_json,competition_proxy_json FROM campaigns WHERE status = 'active' ORDER BY score DESC LIMIT 50").all();
        return json({ campaigns: (result.results || []).map(parse) });
      }
      if (parts[1] === "campaigns" && parts[2] && request.method === "GET" && !parts[3]) {
        const row = await env.DB.prepare("SELECT * FROM campaigns WHERE id = ?").bind(parts[2]).first();
        return row ? json({ campaign: parse(row) }) : json({ error: "campaign_not_found" }, 404);
      }
      if (parts[1] === "campaigns" && parts[2] && parts[3] === "jobs" && request.method === "POST") {
        const id = crypto.randomUUID(); const timestamp = now();
        const exists = await env.DB.prepare("SELECT id FROM campaigns WHERE id = ? AND status = 'active'").bind(parts[2]).first();
        if (!exists) return json({ error: "campaign_not_found" }, 404);
        await env.DB.prepare("INSERT INTO jobs (id,campaign_id,status,progress,message,created_at,updated_at) VALUES (?,?,?,?,?,?,?)").bind(id, parts[2], "queued", 0, "Menunggu worker cloud", timestamp, timestamp).run();
        return json({ job: { id, campaign_id: parts[2], status: "queued", progress: 0, message: "Masuk antrean worker cloud", created_at: timestamp } }, 201);
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
        const result = await env.DB.prepare("SELECT id,job_id,rank,status,video_key,thumbnail_key,download_url,validation_json,caption_draft,checklist_json,created_at FROM previews WHERE job_id = ? ORDER BY rank").bind(parts[2]).all();
        return json({ previews: result.results || [] });
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "previews" && request.method === "POST") {
        if (!workerAuthorized(request, env)) return json({ error: "worker_unauthorized" }, 401);
        const body = await request.json(); const timestamp = now();
        for (const preview of body.previews || []) {
          await env.DB.prepare("INSERT OR REPLACE INTO previews (id,job_id,rank,status,video_key,thumbnail_key,download_url,validation_json,caption_draft,checklist_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)").bind(preview.id || crypto.randomUUID(), parts[2], preview.rank || 0, preview.status || "pending_review", preview.video_key || null, preview.thumbnail_key || null, preview.download_url || null, JSON.stringify(preview.validation || {}), preview.caption_draft || null, JSON.stringify(preview.checklist || []), timestamp).run();
        }
        await env.DB.prepare("UPDATE jobs SET status='review',progress=100,message=?,updated_at=? WHERE id=?").bind(`${(body.previews || []).length} preview siap review`, timestamp, parts[2]).run();
        return json({ ok: true });
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "upload" && request.method === "POST") {
        if (!workerAuthorized(request, env)) return json({ error: "worker_unauthorized" }, 401);
        const form = await request.formData(); const file = form.get("file"); const key = String(form.get("key") || "");
        if (!file || !key || !env.CLIPS) return json({ error: "upload_invalid" }, 400);
        await env.CLIPS.put(key, file.stream(), { httpMetadata: { contentType: file.type || "application/octet-stream", cacheControl: "public,max-age=3600" } });
        return json({ ok: true, key, download_url: `${url.origin}/api/files?key=${encodeURIComponent(key)}` });
      }
      if (parts[1] === "files" && request.method === "GET") {
        const key = url.searchParams.get("key"); if (!key || !env.CLIPS) return json({ error: "file_not_found" }, 404);
        const object = await env.CLIPS.get(key); if (!object) return json({ error: "file_not_found" }, 404);
        const headers = new Headers(cors); object.writeHttpMetadata(headers); headers.set("etag", object.httpEtag); return new Response(object.body, { headers });
      }
      if (parts[1] === "jobs" && parts[2] && request.method === "PATCH") {
        if (!workerAuthorized(request, env)) return json({ error: "worker_unauthorized" }, 401);
        const body = await request.json(); const timestamp = now();
        await env.DB.prepare("UPDATE jobs SET status = ?, progress = ?, message = ?, error = ?, updated_at = ? WHERE id = ?").bind(body.status, body.progress || 0, body.message || null, body.error || null, timestamp, parts[2]).run();
        return json({ ok: true });
      }
      return json({ error: "not_found" }, 404);
    } catch (error) { return json({ error: "server_error", message: String(error.message || error) }, 500); }
  }
};
