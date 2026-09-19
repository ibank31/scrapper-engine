const cfg = window.CLIPPER_CONFIG || { API_BASE_URL: "", DEMO_MODE: true };
const $ = (sel) => document.querySelector(sel);
const state = { campaigns: [], jobs: [], reviews: [] };

const demoCampaigns = [
  { id: "demo-ai-clips", title: "AI Founder Clips", brand: "Demo Studio", category: "technology", score: 86.5, rate_per_1k: 7, budget_left: 3850, progress_pct: 45, platforms: ["tiktok", "youtube", "instagram"], type: "clipping", verified: true, description: "Use the provided podcast footage. Create native vertical clips with a clear hook and subtitles.", flags: [] },
  { id: "demo-podcast", title: "Podcast Growth Campaign", brand: "North Star Media", category: "education", score: 78.2, rate_per_1k: 4, budget_left: 12400, progress_pct: 12, platforms: ["youtube", "tiktok"], type: "clipping", verified: true, description: "Short educational clips from the official content library. No third-party watermark.", flags: ["9:16 required"] },
  { id: "demo-music", title: "Artist Discovery Clips", brand: "Indie Records", category: "music", score: 69.4, rate_per_1k: 2.5, budget_left: 8200, progress_pct: 22, platforms: ["tiktok", "instagram"], type: "clipping", verified: false, description: "Use official footage and attach the official sound when posting.", flags: ["official audio"] }
];

function money(value) { return value == null ? "—" : `$${Number(value).toLocaleString()}`; }
function escapeHtml(value) { return String(value ?? "").replace(/[&<>\"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c])); }
function showToast(message) { const el = $("#toast"); el.textContent = message; el.classList.remove("hidden"); setTimeout(() => el.classList.add("hidden"), 2800); }
function api(path, options) { return fetch(`${cfg.API_BASE_URL || ""}${path}`, options).then((r) => { if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); }); }

async function loadCampaigns() {
  try { state.campaigns = cfg.DEMO_MODE ? demoCampaigns : (await api("/api/campaigns")).campaigns; }
  catch (error) { state.campaigns = demoCampaigns; showToast("API belum terhubung — menampilkan demo"); }
  renderCampaigns();
}
function renderCampaigns() {
  const q = $("#searchInput").value.toLowerCase(); const platform = $("#platformFilter").value; const sort = $("#sortSelect").value;
  let rows = state.campaigns.filter((c) => (!q || `${c.title} ${c.brand} ${c.category}`.toLowerCase().includes(q)) && (!platform || (c.platforms || []).includes(platform)));
  rows.sort((a, b) => Number(b[sort === "rate" ? "rate_per_1k" : sort === "budget" ? "budget_left" : "score"] || 0) - Number(a[sort === "rate" ? "rate_per_1k" : sort === "budget" ? "budget_left" : "score"] || 0));
  $("#activeCount").textContent = state.campaigns.length; $("#campaignMeta").textContent = `${rows.length} campaign cocok`;
  $("#campaignGrid").innerHTML = rows.map((c) => `<article class="campaign-card"><div class="card-top"><span class="category-pill">${escapeHtml(c.category)}</span>${c.verified ? '<span class="verified">● Verified</span>' : ''}</div><h4>${escapeHtml(c.title)}</h4><p class="brand">${escapeHtml(c.brand)}</p><p class="description">${escapeHtml(c.description)}</p><div class="chips">${(c.platforms || []).map((p) => `<span>${escapeHtml(p)}</span>`).join("")}${(c.flags || []).map((f) => `<span class="flag">${escapeHtml(f)}</span>`).join("")}</div><div class="metrics"><div><small>Score</small><strong>${Number(c.score || 0).toFixed(1)}</strong></div><div><small>Rate / 1K</small><strong>${money(c.rate_per_1k)}</strong></div><div><small>Budget left</small><strong>${money(c.budget_left)}</strong></div></div><button class="primary-button start-button" data-id="${escapeHtml(c.id)}">Select campaign <span>→</span></button></article>`).join("") || '<div class="empty-state">No campaigns match your filter.</div>';
  document.querySelectorAll(".start-button").forEach((button) => button.addEventListener("click", () => openCampaign(button.dataset.id)));
}
function openCampaign(id) {
  const c = state.campaigns.find((x) => x.id === id); if (!c) return;
  $("#modalContent").innerHTML = `<p class="eyebrow">CAMPAIGN DETAIL</p><h2>${escapeHtml(c.title)}</h2><p class="modal-brand">${escapeHtml(c.brand)} · ${escapeHtml(c.type || "clipping")}</p><div class="rule-preview"><strong>What the engine will do</strong><span>Read requirements and assets</span><span>Transcribe and find highlights</span><span>Render 9:16 with subtitles</span><span>Validate before review</span></div><p class="modal-note">Publishing is disabled. You will review the output before any manual post.</p><button class="primary-button" id="startJob">Start automatic clipping <span>→</span></button>`;
  $("#detailModal").classList.remove("hidden"); $("#startJob").addEventListener("click", () => startJob(c));
}
async function startJob(campaign) {
  $("#detailModal").classList.add("hidden");
  const job = { id: `job-${Date.now()}`, campaign, status: "queued", progress: 0, message: "Waiting for local worker" }; state.jobs.unshift(job); renderJobs(); showView("jobs");
  try {
    if (!cfg.DEMO_MODE) await api(`/api/campaigns/${encodeURIComponent(campaign.id)}/jobs`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ campaign_id: campaign.id }) });
    if (cfg.DEMO_MODE) simulateJob(job);
  } catch (error) { job.status = "error"; job.message = "Could not reach worker"; renderJobs(); }
}
function simulateJob(job) { const steps = [["reading campaign rules", 20], ["downloading approved assets", 38], ["transcribing with local AI", 58], ["rendering vertical clips", 78], ["validating requirements", 94], ["ready for review", 100]]; let i = 0; const tick = () => { if (i >= steps.length) { job.status = "review"; job.message = "3 previews ready"; state.reviews = [{ job, video: "", title: job.campaign.title }, { job, video: "", title: `${job.campaign.title} · Candidate 2` }]; renderJobs(); renderReviews(); return; } job.status = i === steps.length - 1 ? "review" : "processing"; job.message = steps[i][0]; job.progress = steps[i][1]; renderJobs(); i++; setTimeout(tick, 850); }; tick(); }
function renderJobs() { $("#queueCount").textContent = state.jobs.filter((j) => j.status === "queued" || j.status === "processing").length; $("#jobsList").innerHTML = state.jobs.map((j) => `<article class="job-card"><div class="job-icon">${j.status === "review" ? "✓" : "◌"}</div><div class="job-main"><div class="job-head"><strong>${escapeHtml(j.campaign.title)}</strong><span class="status ${j.status}">${escapeHtml(j.status)}</span></div><p>${escapeHtml(j.message)}</p><div class="progress"><i style="width:${j.progress || 0}%"></i></div></div><span class="progress-number">${j.progress || 0}%</span></article>`).join("") || '<div class="empty-state">No jobs yet. Select a campaign to start.</div>'; }
function renderReviews() { $("#reviewGrid").innerHTML = state.reviews.map((r, i) => `<article class="review-card"><div class="preview-placeholder"><span>Preview ${i + 1}</span><small>Local worker output</small></div><div class="review-body"><span class="status review">pending review</span><h4>${escapeHtml(r.title)}</h4><p>Technical checks passed. Review the full video and campaign checklist.</p><div class="review-actions"><button class="primary-button" onclick="downloadReview(${i})">Download MP4 <span>↓</span></button><button class="ghost-button" onclick="showToast('Checklist dibuka pada workspace lokal')">Checklist</button></div></div></article>`).join("") || '<div class="empty-state">No clips ready yet.</div>'; }
function downloadReview(index) { if (cfg.DEMO_MODE) return showToast("Demo mode: connect the worker to enable downloads"); showToast("Preparing download…"); }
function showView(name) { document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden")); $(`#${name}View`).classList.remove("hidden"); $("#pageTitle").textContent = name === "campaigns" ? "Campaign radar" : name === "jobs" ? "Processing queue" : "Ready for review"; document.querySelectorAll(".nav-item").forEach((n) => n.classList.toggle("active", n.getAttribute("href") === `#${name}`)); }
document.querySelectorAll(".nav-item").forEach((n) => n.addEventListener("click", (e) => { e.preventDefault(); showView(n.getAttribute("href").slice(1)); }));
$("#refreshButton").addEventListener("click", loadCampaigns); $("#searchInput").addEventListener("input", renderCampaigns); $("#platformFilter").addEventListener("change", renderCampaigns); $("#sortSelect").addEventListener("change", renderCampaigns); document.querySelectorAll("[data-close]").forEach((x) => x.addEventListener("click", () => $("#detailModal").classList.add("hidden")));
$("#workerStatus").textContent = cfg.DEMO_MODE ? "demo mode" : "connected"; loadCampaigns();
