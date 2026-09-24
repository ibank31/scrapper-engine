const cfg = window.CLIPPER_CONFIG || { API_BASE_URL: "", DEMO_MODE: true };
const $ = (sel) => document.querySelector(sel);
const state = { campaigns: [], jobs: [], reviews: [], bufferChannels: [], pollTimer: null };
const statusNames = { queued: "ANTRI", processing: "BERJALAN", review: "SIAP REVIEW", error: "GAGAL", blocked: "DIBLOKIR", cancelled: "DIBATALKAN" };
const readinessOrder = { siap: 0, ketat: 1, belum_siap: 2, lewati: 3 };
const demoCampaigns = [
  { id: "demo-ai-clips", title: "AI Founder Clips", brand: "Demo Studio", category: "technology", score: 86.5, rate_per_1k: 7, budget_left: 3850, platforms: ["tiktok", "youtube", "instagram"], type: "clipping", content_kind: "clipping", is_clipping: true, verified: true, description: "Use the provided podcast footage.", readiness_status: "siap", readiness_label: "Siap dikerjakan", readiness_reason: "Bahan resmi ada dan aturan sederhana (demo).", flags: [] },
  { id: "demo-podcast", title: "Podcast Growth Campaign", brand: "North Star Media", category: "education", score: 78.2, rate_per_1k: 4, budget_left: 12400, platforms: ["youtube", "tiktok"], type: "clipping", content_kind: "clipping", is_clipping: true, verified: true, description: "Official content library.", readiness_status: "ketat", readiness_label: "Bisa, tapi ketat", readiness_reason: "Ada caption wajib dan watermark (demo).", flags: ["9:16 required"] },
  { id: "demo-music", title: "Artist Discovery Clips", brand: "Indie Records", category: "music", score: 69.4, rate_per_1k: 2.5, budget_left: 8200, platforms: ["tiktok", "instagram"], type: "clipping", content_kind: "clipping", is_clipping: true, verified: false, description: "Official footage.", readiness_status: "belum_siap", readiness_label: "Belum siap", readiness_reason: "Bahan di portal berlogin (demo).", flags: ["official audio"] }
];
function money(value) { return value == null ? "-" : "$" + Number(value).toLocaleString(); }
function escapeHtml(value) {
  // Build entities without embedding raw HTML entities in source (tool-safe).
  const amp = String.fromCharCode(38);
  const map = {
    "&": amp + "amp;",
    "<": amp + "lt;",
    ">": amp + "gt;",
    '"': amp + "quot;",
  };
  return String(value == null ? "" : value).replace(/[&<>"]/g, function (c) { return map[c] || c; });
}
function showToast(message) { const el = $("#toast"); el.textContent = message; el.classList.remove("hidden"); setTimeout(() => el.classList.add("hidden"), 2800); }
function api(path, options) { return fetch((cfg.API_BASE_URL || "") + path, options).then(async (r) => { const payload = await r.json().catch(() => ({})); if (!r.ok) throw new Error(payload.message || payload.error || "API " + r.status); return payload; }); }
function parseObject(value, fallback) { if (value && typeof value === "object") return value; try { const parsed = JSON.parse(value || ""); return parsed && typeof parsed === "object" ? parsed : (fallback || {}); } catch (_) { return fallback || {}; } }
function outputContractSummary(job) {
  const selection = parseObject(job.output_selection_json, {});
  const actual = selection.actual_selected || selection.actual || {};
  const t1 = Number(actual.tier_1 || 0); const t2 = Number(actual.tier_2 || 0);
  if (job.output_contract_status === "review_ready") return "Target output · Tier 1 1/1 · Tier 2 1/1";
  if (job.output_contract_status === "blocked") return "Output belum lengkap · Tier 1 " + t1 + "/1 · Tier 2 " + t2 + "/1";
  return "Target output · Tier 1 1 · Tier 2 1";
}
function readinessClass(status) {
  if (status === "siap") return "ready-siap";
  if (status === "ketat") return "ready-ketat";
  if (status === "belum_siap") return "ready-belum";
  if (status === "lewati") return "ready-lewati";
  return "ready-unknown";
}
function canStart(c) {
  const s = c.readiness_status;
  if (s === "lewati" || s === "belum_siap") return false;
  if (s === "siap" || s === "ketat") return true;
  return String(c.title || "").toLowerCase().includes("clip");
}
async function loadCampaigns() {
  try {
    state.campaigns = cfg.DEMO_MODE ? demoCampaigns : (await api("/api/campaigns")).campaigns;
  } catch (error) {
    state.campaigns = [];
    showToast(cfg.DEMO_MODE ? "Demo tidak tersedia" : "API production gagal — tidak menampilkan data demo");
  }
  renderCampaigns();
}
function renderCampaigns() {
  const q = $("#searchInput").value.toLowerCase();
  const platform = $("#platformFilter").value;
  const sort = $("#sortSelect").value;
  let rows = state.campaigns.filter((c) => (!q || (String(c.title) + " " + String(c.brand) + " " + String(c.category) + " " + String(c.readiness_label || "")).toLowerCase().includes(q)) && (!platform || (c.platforms || []).includes(platform)));
  if (sort === "rate") rows.sort((a, b) => Number(b.rate_per_1k || 0) - Number(a.rate_per_1k || 0));
  else if (sort === "budget") rows.sort((a, b) => Number(b.budget_left || 0) - Number(a.budget_left || 0));
  else if (sort === "recency") rows.sort((a, b) => Number((b.priority_components && b.priority_components.recency) || 0) - Number((a.priority_components && a.priority_components.recency) || 0));
  else rows.sort((a, b) => (readinessOrder[a.readiness_status] ?? 9) - (readinessOrder[b.readiness_status] ?? 9) || Number(b.readiness_ease || 0) - Number(a.readiness_ease || 0) || Number(b.score || 0) - Number(a.score || 0));
  $("#activeCount").textContent = state.campaigns.length;
  $("#campaignMeta").textContent = rows.length + " campaign · diurutkan mesin";
  $("#campaignGrid").innerHTML = rows.map((c) => {
    const label = c.readiness_label || "Belum dinilai mesin";
    const reason = c.readiness_reason || "Jalankan sync harian agar mesin menilai mudah/aman.";
    const startable = canStart(c);
    return '<article class="campaign-card ' + readinessClass(c.readiness_status) + '">' +
      '<div class="card-top"><span class="category-pill">' + escapeHtml(c.category || "clipping") + '</span>' +
        '<span class="readiness-badge ' + readinessClass(c.readiness_status) + '">' + escapeHtml(label) + '</span></div>' +
      '<h4>' + escapeHtml(c.title) + '</h4>' +
      '<p class="brand">' + escapeHtml(c.brand) + '</p>' +
      '<p class="readiness-reason">' + escapeHtml(reason) + '</p>' +
      '<div class="chips">' + (c.platforms || []).map((p) => '<span>' + escapeHtml(p) + '</span>').join("") + '</div>' +
      '<div class="metrics">' +
        '<div><small>Bayaran / 1K</small><strong>' + money(c.rate_per_1k) + '</strong></div>' +
        '<div><small>Sisa budget</small><strong>' + money(c.budget_left) + '</strong></div>' +
        '<div><small>Jenis</small><strong>' + escapeHtml(c.content_kind || c.type || "-") + '</strong></div>' +
      '</div>' +
      '<button class="primary-button start-button" data-id="' + escapeHtml(c.id) + '" ' + (startable ? "" : "disabled") + '>' +
        (startable ? 'Mulai clipping <span>→</span>' : 'Belum bisa dimulai') +
      '</button></article>';
  }).join("") || '<div class="empty-state">Tidak ada campaign yang cocok.</div>';
  document.querySelectorAll(".start-button:not([disabled])").forEach((button) => button.addEventListener("click", () => openCampaign(button.dataset.id)));
}
function openCampaign(id) {
  const c = state.campaigns.find((x) => x.id === id); if (!c) return;
  const label = c.readiness_label || "Belum dinilai";
  const reason = c.readiness_reason || "-";
  $("#modalContent").innerHTML =
    '<p class="eyebrow">DETAIL CAMPAIGN</p>' +
    '<h2>' + escapeHtml(c.title) + '</h2>' +
    '<p class="modal-brand">' + escapeHtml(c.brand) + ' · ' + escapeHtml(c.content_kind || "clipping") + '</p>' +
    '<p class="readiness-badge ' + readinessClass(c.readiness_status) + '">' + escapeHtml(label) + '</p>' +
    '<p class="description">' + escapeHtml(reason) + '</p>' +
    '<div class="rule-preview"><strong>Yang akan dikerjakan mesin</strong>' +
      '<span>Membaca rules dan bahan resmi campaign</span>' +
      '<span>Memotong dan merender preview vertical</span>' +
      '<span>Menyiapkan paket caption (bahasa Inggris) untuk review</span></div>' +
    '<p class="modal-note">Setelah preview siap, Anda dapat memilih channel dan memasukkannya ke queue Buffer dari kartu review.</p>' +
    '<button class="primary-button" id="startJob">Mulai clipping otomatis <span>→</span></button>';
  $("#detailModal").classList.remove("hidden");
  $("#startJob").addEventListener("click", () => startJob(c));
}
async function startJob(campaign) {
  $("#detailModal").classList.add("hidden");
  const localJob = { id: "local-" + Date.now(), campaign_id: campaign.id, campaign_title: campaign.title, campaign_brand: campaign.brand, status: "queued", progress: 0, message: "Menyiapkan worker cloud…" };
  state.jobs.unshift(localJob); renderJobs(); showView("jobs");
  try {
    if (!cfg.DEMO_MODE) {
      const response = await api("/api/campaigns/" + encodeURIComponent(campaign.id) + "/jobs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ campaign_id: campaign.id }) });
      Object.assign(localJob, response.job);
      localJob.campaign_title = campaign.title;
      localJob.campaign_brand = campaign.brand;
      renderJobs();
      await triggerWorker(localJob);
      localJob.message = "Worker GitHub sudah dipicu · menunggu runner";
      renderJobs();
      startPolling();
    } else simulateJob(localJob);
  } catch (error) {
    localJob.status = "error";
    localJob.message = "Gagal memulai workflow";
    localJob.error = error.message;
    renderJobs();
    showToast(error.message || "Workflow gagal dimulai");
  }
}
async function triggerWorker(job) {
  const response = await api("/api/jobs/" + encodeURIComponent(job.id) + "/run", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ campaign_id: job.campaign_id })
  });
  if (!response.dispatched) throw new Error(response.message || response.error || "Manual worker belum siap");
  return response;
}
function simulateJob(job) {
  const steps = [["Mengantri di worker cloud", 5], ["Membaca rules campaign", 20], ["Mengambil bahan resmi", 38], ["Transkripsi dengan AI", 58], ["Render video vertical", 78], ["Validasi syarat", 94], ["Preview siap direview", 100]];
  let i = 0;
  const tick = () => {
    if (i >= steps.length) {
      job.status = "review"; job.message = "2 preview siap direview";
      state.reviews = [{ job: job, title: job.campaign_title, video: "", download_url: null }, { job: job, title: job.campaign_title + " · Kandidat 2", video: "", download_url: null }];
      renderJobs(); renderReviews(); return;
    }
    job.status = i === 0 ? "queued" : i === steps.length - 1 ? "review" : "processing";
    job.message = steps[i][0]; job.progress = steps[i][1]; renderJobs(); i++; setTimeout(tick, 850);
  };
  tick();
}
function statusText(status) { return statusNames[status] || String(status || "UNKNOWN").toUpperCase(); }
function formatAge(iso) {
  if (!iso) return "belum ada update";
  const age = Math.max(0, Date.now() - new Date(iso).getTime());
  const seconds = Math.floor(age / 1000);
  if (seconds < 60) return seconds + "s lalu";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return minutes + "m " + (seconds % 60) + "s lalu";
  return Math.floor(minutes / 60) + "j " + (minutes % 60) + "m lalu";
}
function jobPhase(job) {
  const p = Number(job.progress || 0);
  const msg = String(job.message || "").toLowerCase();
  if (job.status === "queued") return { label: job.error ? "Gagal dispatch" : "Menunggu runner", detail: job.error || (job.message || "Job sudah masuk antrean dan menunggu worker cloud."), key: job.error ? "dispatch-error" : "queue" };
  if (job.status === "review") return { label: "Selesai", detail: "Preview sudah diunggah dan siap diperiksa.", key: "done" };
  if (job.status === "error") return { label: "Pipeline gagal", detail: job.error || "Worker berhenti karena error.", key: "error" };
  if (job.status === "blocked") return { label: "Diblokir sebelum produksi", detail: job.message || "Rules campaign belum memenuhi syarat.", key: "blocked" };
  if (msg.includes("detail") || msg.includes("syarat")) return { label: "Menganalisis campaign", detail: job.message, key: "analysis" };
  if (p < 24) return { label: "Menyiapkan asset", detail: job.message || "Mengambil bahan resmi.", key: "assets" };
  if (p < 78) return { label: "AI processing", detail: job.message || "Transkripsi dan pemilihan clip sedang berjalan.", key: "ai" };
  if (p < 92) return { label: "Validasi video", detail: job.message || "Memeriksa hasil render terhadap rules.", key: "validate" };
  return { label: "Mengunggah preview", detail: job.message || "Preview sedang dikirim ke storage.", key: "upload" };
}
function isStale(job) {
  if (!job.updated_at || !["queued", "processing"].includes(job.status)) return false;
  const age = Date.now() - new Date(job.updated_at).getTime();
  return age > (job.status === "queued" ? 8 * 60 * 1000 : 5 * 60 * 1000);
}
async function cancelJob(job) {
  if (!job || !["queued", "processing"].includes(job.status)) return;
  if (!window.confirm("Hentikan proses " + (job.campaign_title || "ini") + "?")) return;
  try {
    await api("/api/jobs/" + encodeURIComponent(job.id) + "/cancel", { method: "POST" });
    showToast("Proses dihentikan");
    await loadJobs();
  } catch (error) {
    showToast("Proses belum dapat dihentikan");
  }
}
function renderJobs() {
  const active = state.jobs.filter((j) => j.status === "queued" || j.status === "processing").length;
  const processing = state.jobs.filter((j) => j.status === "processing").length;
  const queued = state.jobs.filter((j) => j.status === "queued").length;
  const failed = state.jobs.filter((j) => ["error", "blocked"].includes(j.status)).length;
  $("#queueCount").textContent = active;
  const summary = $("#queueSummary");
  if (summary) summary.innerHTML = '<div class="queue-live"><i></i><strong>' + (active ? "Live queue" : "Queue idle") + '</strong><span>' + (active ? "memantau worker cloud" : "tidak ada job aktif") + '</span></div><div class="queue-stats"><span><b>' + processing + '</b> berjalan</span><span><b>' + queued + '</b> antri</span><span class="' + (failed ? "has-alert" : "") + '"><b>' + failed + '</b> gagal</span><span>sync <b id="queueSyncAge">baru saja</b></span></div>';
  $("#jobsList").innerHTML = state.jobs.map((j) => {
    const phase = jobPhase(j);
    const stale = isStale(j);
    const progress = Math.max(0, Math.min(100, Number(j.progress || 0)));
    const live = ["queued", "processing"].includes(j.status);
    const icon = j.status === "review" ? "✓" : j.status === "error" ? "!" : j.status === "blocked" ? "!" : "◌";
    return '<article class="job-card job-' + escapeHtml(j.status) + (stale ? " job-stale" : "") + '">' +
      '<div class="job-icon' + (j.status === "processing" ? " spinning" : "") + (live ? " live-icon" : "") + '">' + icon + '</div>' +
      '<div class="job-main">' +
        '<div class="job-head"><div class="job-title-wrap"><strong>' + escapeHtml(j.campaign_title || j.campaign_id) + '</strong><span class="job-phase">' + escapeHtml(phase.label) + '</span></div><span class="status ' + escapeHtml(j.status) + '">' + statusText(j.status) + '</span></div>' +
        '<p class="job-message"><b>' + escapeHtml(j.message || phase.detail || "Menunggu update…") + '</b>' + (j.error ? " · " + escapeHtml(j.error) : "") + '</p>' +
        '<div class="job-output-contract">' + escapeHtml(outputContractSummary(j)) + '</div>' +
        '<div class="job-progress-row"><div class="progress"><i style="width:' + progress + '%"></i></div><span class="progress-number">' + progress + '%</span></div>' +
        '<div class="job-meta"><span>Update ' + formatAge(j.updated_at) + '</span><span>·</span><span>' + escapeHtml(phase.detail || "") + '</span>' + (stale ? '<span class="stale-warning">⚠ Tidak ada update terbaru</span>' : "") + '</div>' +
        ((j.status === "queued" || j.status === "processing") ? '<button class="stop-button" data-stop-id="' + escapeHtml(j.id) + '" type="button">Stop proses</button>' : "") +
      '</div></article>';
  }).join("") || '<div class="empty-state">Belum ada job. Pilih campaign untuk memulai.</div>';
  document.querySelectorAll(".stop-button").forEach((button) => button.addEventListener("click", () => {
    const job = state.jobs.find((item) => item.id === button.dataset.stopId);
    cancelJob(job);
  }));
}
async function loadJobs() {
  if (cfg.DEMO_MODE) return;
  try {
    const response = await api("/api/jobs");
    state.jobs = response.jobs || [];
    state.reviews = [];
    renderJobs();
    for (const job of state.jobs.filter((j) => j.status === "review")) await loadPreviews(job);
  } catch (error) {
    showToast("Status worker belum dapat diambil");
  }
}
async function loadPreviews(job) {
  try {
    const response = await api("/api/jobs/" + encodeURIComponent(job.id) + "/previews");
    for (const preview of response.previews || []) {
      state.reviews.push(Object.assign({}, preview, { title: (job.campaign_title || "Campaign") + " · Kandidat " + preview.rank, job: job }));
    }
    renderReviews();
  } catch (error) { /* keep job visible */ }
}
async function reviewPreview(preview, action) {
  const labels = { approve: "ACC untuk upload manual", reject: "Tolak preview", request_rerender: "Minta render ulang" };
  const needsReason = action !== "approve";
  const reason = needsReason ? window.prompt("Alasan " + (labels[action] || action) + " (wajib):", "") : "";
  if (needsReason && !String(reason || "").trim()) return;
  try {
    const headers = { "content-type": "application/json" };
    if (cfg.REVIEW_TOKEN) headers["x-review-token"] = cfg.REVIEW_TOKEN;
    const response = await api("/api/previews/" + encodeURIComponent(preview.id) + "/review", {
      method: "POST", headers,
      body: JSON.stringify({ action, reason: String(reason || "").trim(), reviewer: cfg.REVIEWER || "manual-user" })
    });
    const updated = response.preview || {};
    Object.assign(preview, updated);
    renderReviews();
    showToast(labels[action] + " berhasil disimpan");
    await loadJobs();
  } catch (error) {
    showToast("Review gagal disimpan: " + error.message);
  }
}
async function editCaption(preview) {
  const text = window.prompt("Caption revision baru (rules wajib tetap terpenuhi):", preview.caption_draft || "");
  if (text == null || text === preview.caption_draft) return;
  try {
    const headers = { "content-type": "application/json" }; if (cfg.REVIEW_TOKEN) headers["x-review-token"] = cfg.REVIEW_TOKEN;
    const response = await api("/api/previews/" + encodeURIComponent(preview.id) + "/caption-revisions", { method: "POST", headers, body: JSON.stringify({ text, fields: { hashtags: (text.match(/#[A-Za-z0-9_]+/g) || []) }, reviewer: cfg.REVIEWER || "manual-user" }) });
    Object.assign(preview, { caption_draft: response.revision.text, caption_revision_id: response.revision.revision_id, caption_hash: response.revision.caption_hash });
    renderReviews(); showToast("Caption revision v" + response.revision.revision_number + " tersimpan");
  } catch (error) { showToast("Caption revision ditolak: " + error.message); }
}
async function openBufferUpload(preview) {
  try {
    if (!state.bufferChannels.length) state.bufferChannels = (await api("/api/buffer/channels")).channels || [];
    if (!state.bufferChannels.length) throw new Error("Tidak ada channel Buffer yang tersedia");
    const groups = state.bufferChannels.reduce((acc, channel) => { (acc[channel.organizationName || "Buffer"] ||= []).push(channel); return acc; }, {});
    const checks = Object.entries(groups).map(([organization, channels]) => '<fieldset class="buffer-channel-group"><legend>' + escapeHtml(organization) + '</legend>' + channels.map((channel) => '<label class="buffer-channel"><input type="checkbox" value="' + escapeHtml(channel.id) + '" data-service="' + escapeHtml(channel.service || "") + '"><span>' + escapeHtml(channel.name || channel.service) + '</span><small>' + escapeHtml(channel.service || "") + '</small></label>').join("") + '</fieldset>').join("");
    $("#modalContent").innerHTML = '<p class="eyebrow">BUFFER</p><h2>Upload otomatis</h2><p class="description">Pilih channel Buffer. Video akan masuk ke queue Buffer menggunakan jadwal channel.</p><div class="buffer-channel-list">' + checks + '</div><label class="buffer-caption-label">Caption<textarea id="bufferCaption" rows="4">' + escapeHtml(preview.caption_draft || "") + '</textarea></label><div class="modal-actions"><button class="secondary-button" data-close="true">Batal</button><button class="primary-button" id="confirmBufferUpload">Upload ke Buffer <span>→</span></button></div>';
    $("#detailModal").classList.remove("hidden");
    $("#modalContent [data-close]").addEventListener("click", () => $("#detailModal").classList.add("hidden"));
    $("#confirmBufferUpload").addEventListener("click", async () => {
      const selected = [...document.querySelectorAll(".buffer-channel input:checked")];
      const channel_ids = selected.map((input) => input.value);
      if (!channel_ids.length) return showToast("Pilih minimal satu channel Buffer");
      if (!window.confirm("Masukkan video ini ke queue Buffer pada " + channel_ids.length + " channel?")) return;
      const button = $("#confirmBufferUpload"); button.disabled = true; button.textContent = "Mengirim…";
      try {
        const headers = { "content-type": "application/json" };
        if (cfg.REVIEW_TOKEN) headers["x-review-token"] = cfg.REVIEW_TOKEN;
        const response = await api("/api/previews/" + encodeURIComponent(preview.id) + "/buffer", { method: "POST", headers, body: JSON.stringify({ channel_ids, channels: selected.map((input) => ({ id: input.value, service: input.dataset.service })), text: $("#bufferCaption").value, artifact_hash: preview.approval_artifact_hash || preview.artifact_hash, caption_revision_id: preview.approval_caption_revision_id || preview.caption_revision_id }) });
        const ok = (response.uploads || []).filter((item) => item.status === "queued").length;
        $("#detailModal").classList.add("hidden"); showToast(ok + " channel berhasil masuk ke queue Buffer");
      } catch (error) { button.disabled = false; button.textContent = "Upload ke Buffer →"; showToast("Upload Buffer gagal: " + error.message); }
    });
  } catch (error) { showToast("Buffer belum siap: " + error.message); }
}
function startPolling() {
  if (cfg.DEMO_MODE || state.pollTimer) return;
  state.pollTimer = setInterval(async () => {
    await loadJobs();
    if (!state.jobs.some((j) => j.status === "queued" || j.status === "processing")) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }, 5000);
}
function renderReviews() {
  $("#reviewGrid").innerHTML = state.reviews.map((r) => {
    const src = r.video_url || r.download_url;
    let validation = {};
    try { validation = typeof r.validation_json === "string" ? JSON.parse(r.validation_json) : (r.validation_json || {}); } catch (_) { validation = {}; }
    const semantic = validation.semantic || {};
    const tierLabel = r.tier === "tier_1" ? "Audience Tier 1" : r.tier === "tier_2" ? "Audience Tier 2" : "Audience belum terklasifikasi";
    const distinctness = parseObject(r.distinctness_json, r.distinctness || {});
    const subtitle = parseObject(r.subtitle_delivery_json, r.subtitle_delivery || {});
    const sound = parseObject(r.sound_tags_json, r.sound_tags || {});
    const semanticLine = semantic.semantic_score == null ? "Semantic fallback belum tersedia" :
      "Semantic " + Number(semantic.semantic_score).toFixed(0) + " · Hook " + Number(semantic.hook_score || 0).toFixed(0) + " · Context " + Number(semantic.context_score || 0).toFixed(0) + " · Payoff " + Number(semantic.payoff_score || 0).toFixed(0) + " · Complete " + Number(semantic.completeness_score || 0).toFixed(0);
    const status = String(r.status || "pending_review");
    const actionButtons = status === "pending_review" || status === "changes_requested" ?
      '<button class="secondary-button review-action" data-review-action="request_rerender">Minta render ulang</button>' +
      '<button class="secondary-button review-action danger" data-review-action="reject">Tolak</button>' +
      '<button class="primary-button review-action" data-review-action="approve">ACC upload manual <span>✓</span></button>' :
      '<span class="review-decision">' + escapeHtml(status.replaceAll("_", " ")) + (r.review_reason ? " · " + escapeHtml(r.review_reason) : "") + "</span>";
    return '<article class="review-card">' +
      (src ? '<video class="review-video" controls preload="none" poster="' + escapeHtml(r.thumbnail_url || "") + '" src="' + escapeHtml(src) + '"></video>' : '<div class="preview-placeholder"><span>Preview menunggu URL</span><small>Worker sedang mengunggah hasil</small></div>') +
      '<div class="review-body"><span class="status review">' + escapeHtml(status.replaceAll("_", " ").toUpperCase()) + '</span><h4>' + escapeHtml(r.title || "Clip") + '</h4>' +
      '<div class="review-contract"><strong>' + escapeHtml(tierLabel) + '</strong>' + (r.candidate_id ? '<span>Candidate terverifikasi</span>' : '<span>Candidate ID belum tersedia</span>') + (distinctness.distinct ? '<span>Berbeda secara material</span>' : '') + (subtitle.mode ? '<span>Subtitle: ' + escapeHtml(subtitle.mode) + '</span>' : '') + (sound.status ? '<span>Sound: ' + escapeHtml(sound.status) + '</span>' : '') + '</div>' +
      '<p>Periksa video penuh, validasi, dan checklist campaign sebelum mengambil keputusan.</p>' +
      (r.rules_summary_id ? '<div class="rules-summary"><strong>Ringkasan rules campaign</strong><p>' + escapeHtml(r.rules_summary_id) + '</p></div>' : '') +
      '<div class="review-validation"><span>Validator: <b>' + escapeHtml((validation.status || "needs_review").toUpperCase()) + '</b></span><span>' + escapeHtml(semanticLine) + '</span>' + (r.caption_draft ? '<span>Caption revision ' + escapeHtml(r.caption_revision_id || "draft") + '</span>' : '<span>Caption belum tersedia</span>') + '</div>' +
      (semantic.reason ? '<p class="semantic-reason">' + escapeHtml(semantic.reason) + '</p>' : '') +
      '<div class="review-actions">' +
      (r.download_url ? '<a class="secondary-button download-link" href="' + escapeHtml(r.download_url) + '" download>Download MP4 <span>↓</span></a>' + ((status === "pending_review" || status === "changes_requested") ? '<button class="secondary-button caption-edit-button" type="button">Edit caption</button>' : '') + (status === "approved_for_manual_post" ? '<button class="primary-button buffer-upload-button" type="button">Upload ke Buffer <span>↗</span></button>' : '') : '<button class="secondary-button" type="button">Menunggu file <span>◌</span></button>') + actionButtons +
      '</div></div></article>';
  }).join("") || '<div class="empty-state">Belum ada preview siap review.</div>';
  document.querySelectorAll("video.review-video").forEach((video) => {
    video.addEventListener("error", () => video.closest(".review-card")?.classList.add("video-load-error"), { once: true });
  });
  document.querySelectorAll(".review-action").forEach((button) => button.addEventListener("click", () => {
    const card = button.closest(".review-card");
    const index = Array.from(document.querySelectorAll(".review-card")).indexOf(card);
    const preview = state.reviews[index];
    if (preview) reviewPreview(preview, button.dataset.reviewAction);
  }));
  document.querySelectorAll(".buffer-upload-button").forEach((button) => button.addEventListener("click", () => {
    const card = button.closest(".review-card"); const index = Array.from(document.querySelectorAll(".review-card")).indexOf(card); const preview = state.reviews[index];
    if (preview) openBufferUpload(preview);
  }));
  document.querySelectorAll(".caption-edit-button").forEach((button) => button.addEventListener("click", () => {
    const card = button.closest(".review-card"); const index = Array.from(document.querySelectorAll(".review-card")).indexOf(card); const preview = state.reviews[index];
    if (preview) editCaption(preview);
  }));
}
function showView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  $("#" + name + "View").classList.remove("hidden");
  $("#pageTitle").textContent = name === "campaigns" ? "Campaign radar" : name === "jobs" ? "Processing queue" : "Ready for review";
  document.querySelectorAll(".nav-item").forEach((n) => n.classList.toggle("active", n.getAttribute("href") === "#" + name));
}
document.querySelectorAll(".nav-item").forEach((n) => n.addEventListener("click", (e) => { e.preventDefault(); showView(n.getAttribute("href").slice(1)); }));
$("#refreshButton").addEventListener("click", async () => { await loadCampaigns(); await loadJobs(); showToast("Data diperbarui"); });
$("#searchInput").addEventListener("input", renderCampaigns);
$("#platformFilter").addEventListener("change", renderCampaigns);
$("#sortSelect").addEventListener("change", renderCampaigns);
document.querySelectorAll("[data-close]").forEach((x) => x.addEventListener("click", () => $("#detailModal").classList.add("hidden")));
$("#workerStatus").textContent = cfg.DEMO_MODE ? "demo mode" : "connected · polling 5s";
loadCampaigns();
loadJobs();
setInterval(() => { if (state.jobs.length) renderJobs(); }, 1000);
