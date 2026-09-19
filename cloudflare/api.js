const cors = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,PATCH,OPTIONS",
  "access-control-allow-headers": "content-type,x-worker-token"
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { ...cors, "content-type": "application/json; charset=utf-8" } });
}
function now() { return new Date().toISOString(); }
function parse(row) {
  if (!row) return row;
  return { ...row, platforms: JSON.parse(row.platforms_json || "[]"), detail: JSON.parse(row.detail_json || "{}"), plan: row.plan_json ? JSON.parse(row.plan_json) : null };
}
function workerAuthorized(request, env) {
  return env.WORKER_TOKEN && request.headers.get("x-worker-token") === env.WORKER_TOKEN;
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { headers: cors });
    const url = new URL(request.url);
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts[0] !== "api") return json({ error: "not_found" }, 404);
    try {
      if (parts[1] === "campaigns" && request.method === "GET" && !parts[2]) {
        const result = await env.DB.prepare("SELECT * FROM campaigns WHERE status = 'active' ORDER BY score DESC").all();
        return json({ campaigns: (result.results || []).map(parse) });
      }
      if (parts[1] === "campaigns" && parts[2] && request.method === "GET") {
        const row = await env.DB.prepare("SELECT * FROM campaigns WHERE id = ?").bind(parts[2]).first();
        return row ? json({ campaign: parse(row) }) : json({ error: "campaign_not_found" }, 404);
      }
      if (parts[1] === "campaigns" && parts[2] && parts[3] === "jobs" && request.method === "POST") {
        const id = crypto.randomUUID(); const timestamp = now();
        await env.DB.prepare("INSERT INTO jobs (id,campaign_id,status,progress,message,created_at,updated_at) VALUES (?,?,?,?,?,?,?)").bind(id, parts[2], "queued", 0, "Queued for local worker", timestamp, timestamp).run();
        return json({ job: { id, campaign_id: parts[2], status: "queued", progress: 0 } }, 201);
      }
      if (parts[1] === "jobs" && parts[2] && request.method === "GET" && !parts[3]) {
        const row = await env.DB.prepare("SELECT * FROM jobs WHERE id = ?").bind(parts[2]).first();
        return row ? json({ job: row }) : json({ error: "job_not_found" }, 404);
      }
      if (parts[1] === "jobs" && parts[2] && parts[3] === "previews" && request.method === "GET") {
        const result = await env.DB.prepare("SELECT * FROM previews WHERE job_id = ? ORDER BY rank").bind(parts[2]).all();
        return json({ previews: result.results || [] });
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
