const cfg = window.CLIPPER_CONFIG || { API_BASE_URL: "", DEMO_MODE: true };
const $ = (sel) => document.querySelector(sel);
const state = { campaigns: [], jobs: [], reviews: [], bufferChannels: [], pollTimer: null };
const statusNames = { queued: "MENUNGGU", processing: "SEDANG DIPROSES", review: "SIAP DITINJAU", error: "PERLU DIPERBAIKI", blocked: "TERTAHAN", cancelled: "DIBATALKAN", pending_review: "MENUNGGU KEPUTUSAN", changes_requested: "MENUNGGU RENDER ULANG", approved_for_manual_post: "SUDAH DISETUJUI", rejected: "DITOLAK", pending_render: "MENUNGGU RENDER" };
const operationNames = { pending: "Menunggu dikirim", attempting: "Sedang mengirim", unknown: "Belum pasti — perlu cek", scheduled: "Sudah masuk antrean", published: "Sudah terbit", failed: "Gagal mengirim", cancelled: "Dibatalkan", unresolved: "Belum terselesaikan" };
const tierNames = { tier_1: "Audiens utama", tier_2: "Audiens cadangan", unknown: "Audiens belum terbaca" };
const subtitleNames = { burned_in: "Subtitle tertanam di video", native_caption_file: "File subtitle siap", none: "Tanpa subtitle", manual_required: "Perlu ditambahkan manual" };
const soundNames = { verified: "Audio resmi terverifikasi", manual_required: "Audio resmi ditambahkan saat posting", unsupported: "Audio belum diverifikasi", unknown: "Audio belum diketahui" };
function friendlyOperation(status) { return operationNames[String(status || "").toLowerCase()] || "Status pengiriman: " + String(status || "belum diketahui"); }
function friendlyValidation(status) { return ({ pass: "Pemeriksaan dasar lolos", needs_review: "Perlu diperiksa manusia", fail: "Ada syarat yang belum lolos" }[String(status || "").toLowerCase()] || "Menunggu pemeriksaan"); }
function friendlyError(value) {
  const text = String(value || "");
  if (/capacity_preflight|capacity.*exhausted|request_budget/i.test(text)) return "Antrean Buffer sedang penuh. Coba lagi setelah ada slot.";
  if (/channel_not_found|channel.*required/i.test(text)) return "Channel tujuan tidak ditemukan atau belum terhubung.";
  if (/caption_compliance|caption.*mismatch|caption_required/i.test(text)) return "Caption belum memenuhi aturan campaign. Edit caption lalu coba lagi.";
  if (/approval_provenance|not_approved|approval_revision/i.test(text)) return "Preview belum memiliki persetujuan yang sah. Buka review dan setujui versi terbaru.";
  if (/unknown_requires_reconciliation|unknown/i.test(text)) return "Hasil pengiriman belum pasti. Cek status provider sebelum mencoba ulang.";
  if (/timeout|503|429|rate limit|temporar/i.test(text)) return "Layanan sedang sibuk atau belum menjawab. Tunggu sebentar sebelum mencoba lagi.";
  if (/review_unauthorized|unauthorized/i.test(text)) return "Sesi review belum terhubung. Muat ulang halaman atau periksa akses.";
  if (/source_media_invalid|media_preflight_failed|video_stream_missing|audio_stream_missing|ffprobe_failed|duration_below_minimum/i.test(text)) return "Bahan video berhasil ditemukan, tetapi file tidak lolos pemeriksaan media (video/audio/durasi). Mesin menghentikan analisis mahal agar tidak membuang waktu.";
  if (/source_assets_unavailable|tidak dapat diakses|tidak dapat diunduh|sign in to confirm.*bot|youtube.*429/i.test(text)) return "Bahan video campaign tidak bisa diakses dari worker. Mesin akan menandai sumber yang bisa dipakai dan sumber yang perlu diperbaiki, bukan meneruskan file yang belum terverifikasi.";
  return text || "Mesin berhenti sebelum selesai. Coba ulangi dari campaign ini.";
}
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
  if (job.output_contract_status === "review_ready") return "Target selesai · Audiens utama 1/1 · Audiens cadangan 1/1";
  if (job.output_contract_status === "blocked") return "Belum lengkap · Audiens utama " + t1 + "/1 · Audiens cadangan " + t2 + "/1";
  return "Target: 2 video berbeda · 1 untuk tiap audiens";
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
      '<span>Membaca aturan dan bahan resmi campaign</span>' +
      '<span>Mencari dua video yang berbeda untuk dua audiens</span>' +
      '<span>Membuat subtitle, memeriksa syarat, lalu menyiapkan review</span></div>' +
      '<p class="modal-note">Setelah selesai, Anda menonton video dan memutuskan: ACC, tolak, atau minta render ulang. Setelah ACC, Anda memilih channel Buffer.</p>' +
      '<button class="primary-button" id="startJob">Mulai proses campaign <span>→</span></button>';
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
  const steps = [["Menunggu giliran mesin", 5], ["Membaca aturan campaign", 20], ["Memeriksa bahan resmi", 38], ["Membaca suara dan kata", 58], ["Membuat video vertikal", 78], ["Memeriksa semua syarat", 94], ["Video siap ditinjau", 100]];
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
  if (job.status === "queued") return { label: job.error ? "Gagal memulai" : "Menunggu giliran", detail: job.error ? friendlyError(job.error) : (job.message || "Campaign sudah masuk antrean. Worker akan mulai otomatis."), key: job.error ? "dispatch-error" : "queue" };
  if (job.status === "review") return { label: "Siap ditinjau", detail: "Video sudah selesai dan menunggu keputusan Anda.", key: "done" };
  if (job.status === "error") return { label: "Perlu diperbaiki", detail: friendlyError(job.error || job.message), key: "error" };
  if (job.status === "blocked") return { label: "Belum bisa diproses", detail: friendlyError(job.error || job.message || "Aturan campaign belum terpenuhi."), key: "blocked" };
  if (msg.includes("detail") || msg.includes("syarat")) return { label: "Memahami campaign", detail: job.message || "Mesin sedang membaca aturan dan bahan campaign.", key: "analysis" };
  if (p < 24) return { label: "Menyiapkan bahan", detail: job.message || "Memeriksa bahan resmi campaign.", key: "assets" };
  if (p < 78) return { label: "Mencari potongan terbaik", detail: job.message || "Membaca transkrip dan mencari dua video yang berbeda.", key: "ai" };
  if (p < 92) return { label: "Memeriksa video", detail: job.message || "Memastikan durasi, ukuran, subtitle, dan aturan campaign.", key: "validate" };
  return { label: "Menyiapkan preview", detail: job.message || "Preview sedang disiapkan untuk Anda.", key: "upload" };
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
  if (summary) summary.innerHTML = '<div class="queue-live"><i></i><strong>' + (active ? "Mesin sedang bekerja" : "Tidak ada proses aktif") + '</strong><span>' + (active ? "status diperbarui otomatis" : "Pilih campaign untuk memulai") + '</span></div><div class="queue-stats"><span><b>' + processing + '</b> diproses</span><span><b>' + queued + '</b> menunggu</span><span class="' + (failed ? "has-alert" : "") + '"><b>' + failed + '</b> perlu perhatian</span><span>pembaruan <b id="queueSyncAge">baru saja</b></span></div>';
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
        '<p class="job-message"><b>' + escapeHtml(phase.detail || j.message || "Menunggu pembaruan…") + '</b>' + (j.error ? " · " + escapeHtml(friendlyError(j.error)) : "") + '</p>' +
        '<div class="job-output-contract">' + escapeHtml(outputContractSummary(j)) + '</div>' +
        '<div class="job-progress-row"><div class="progress"><i style="width:' + progress + '%"></i></div><span class="progress-number">' + progress + '%</span></div>' +
        '<div class="job-meta"><span>Pembaruan ' + formatAge(j.updated_at) + '</span>' + (stale ? '<span class="stale-warning">⚠ Belum ada pembaruan cukup lama</span>' : "") + '</div>' +
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
  const labels = { approve: "Video disetujui", reject: "Video ditolak", request_rerender: "Render ulang diminta" };
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
    showToast("Keputusan belum tersimpan: " + friendlyError(error.message));
  }
}
async function editCaption(preview) {
  const text = window.prompt("Tulis caption baru. Mesin akan memeriksa aturan campaign sebelum menyimpan:", preview.caption_draft || "");
  if (text == null || text === preview.caption_draft) return;
  try {
    const headers = { "content-type": "application/json" }; if (cfg.REVIEW_TOKEN) headers["x-review-token"] = cfg.REVIEW_TOKEN;
    const response = await api("/api/previews/" + encodeURIComponent(preview.id) + "/caption-revisions", { method: "POST", headers, body: JSON.stringify({ text, fields: { hashtags: (text.match(/#[A-Za-z0-9_]+/g) || []) }, reviewer: cfg.REVIEWER || "manual-user" }) });
    Object.assign(preview, { caption_draft: response.revision.text, caption_revision_id: response.revision.revision_id, caption_hash: response.revision.caption_hash });
    renderReviews(); showToast("Caption revision v" + response.revision.revision_number + " tersimpan");
  } catch (error) { showToast("Caption belum disimpan: " + friendlyError(error.message)); }
}
async function openBufferUpload(preview) {
  try {
    if (!state.bufferChannels.length) state.bufferChannels = (await api("/api/buffer/channels")).channels || [];
    if (!state.bufferChannels.length) throw new Error("channel_not_found");
    const groups = state.bufferChannels.reduce((acc, channel) => { (acc[channel.organizationName || "Buffer"] ||= []).push(channel); return acc; }, {});
    const checks = Object.entries(groups).map(([organization, channels]) => '<fieldset class="buffer-channel-group"><legend>' + escapeHtml(organization) + '</legend>' + channels.map((channel) => '<label class="buffer-channel"><input type="checkbox" value="' + escapeHtml(channel.id) + '" data-service="' + escapeHtml(channel.service || "") + '"><span>' + escapeHtml(channel.name || channel.service) + '</span><small>' + escapeHtml(channel.service || "") + '</small></label>').join("") + '</fieldset>').join("");
    $("#modalContent").innerHTML = '<p class="eyebrow">LANGKAH TERAKHIR</p><h2>Masukkan ke Buffer</h2><p class="description">Pilih channel. Setelah dikonfirmasi, video masuk ke <b>slot antrean berikutnya</b> di Buffer — bukan jadwal jam yang dijamin.</p><div class="buffer-safe-note"><b>Sebelum mengirim</b><span>Pastikan video dan caption sudah benar.</span><span>Anda tetap mengirim manual ke Whop setelah upload.</span></div><div class="buffer-channel-list">' + checks + '</div><label class="buffer-caption-label">Caption yang akan dikirim<textarea id="bufferCaption" rows="4">' + escapeHtml(preview.caption_draft || "") + '</textarea></label><div class="modal-actions"><button class="secondary-button" data-close="true">Batal</button><button class="primary-button" id="confirmBufferUpload">Cek lalu masukkan ke Buffer <span>→</span></button></div>';
    $("#detailModal").classList.remove("hidden");
    $("#modalContent [data-close]").addEventListener("click", () => $("#detailModal").classList.add("hidden"));
    $("#confirmBufferUpload").addEventListener("click", async () => {
      const selected = [...document.querySelectorAll(".buffer-channel input:checked")];
      const channel_ids = selected.map((input) => input.value);
      if (!channel_ids.length) return showToast("Pilih minimal satu channel terlebih dahulu");
      const button = $("#confirmBufferUpload"); button.disabled = true; button.textContent = "Memeriksa…";
      try {
        const headers = { "content-type": "application/json" };
        if (cfg.REVIEW_TOKEN) headers["x-review-token"] = cfg.REVIEW_TOKEN;
        const request = { channel_ids, text: $("#bufferCaption").value, artifact_hash: preview.approval_artifact_hash || preview.artifact_hash, caption_revision_id: preview.approval_caption_revision_id || preview.caption_revision_id };
        const preflight = await api("/api/previews/" + encodeURIComponent(preview.id) + "/buffer/preflight", { method: "POST", headers, body: JSON.stringify(request) });
        if (!preflight.ok) throw new Error((preflight.channels || []).filter((item) => !item.valid).map((item) => item.service + ": " + item.error).join("; ") || "capacity_preflight_failed");
        if (!window.confirm("Masukkan video ini ke antrean berikutnya pada " + channel_ids.length + " channel? Setelah ini, Anda tetap submit manual ke Whop.")) { button.disabled = false; button.textContent = "Cek lalu masukkan ke Buffer →"; return; }
        const response = await api("/api/previews/" + encodeURIComponent(preview.id) + "/buffer", { method: "POST", headers, body: JSON.stringify(request) });
        const outcome = response.outcome || "";
        const operations = response.operations || [];
        const scheduled = operations.filter((item) => item.status === "scheduled").length;
        const unknown = operations.filter((item) => item.status === "unknown").length;
        $("#detailModal").classList.add("hidden"); showToast(unknown ? "Sebagian hasil belum pasti. Cek statusnya sebelum mencoba lagi." : scheduled + " video sudah masuk antrean Buffer.");
      } catch (error) { button.disabled = false; button.textContent = "Cek lalu masukkan ke Buffer →"; showToast("Belum masuk Buffer: " + friendlyError(error.message)); }
  });
  } catch (error) { showToast("Buffer belum siap: " + friendlyError(error.message)); }
}
async function retryOperation(operationKey) {
  try {
    const headers = {}; if (cfg.REVIEW_TOKEN) headers["x-review-token"] = cfg.REVIEW_TOKEN;
    await api("/api/delivery-operations/" + encodeURIComponent(operationKey) + "/retry", { method: "POST", headers });
    showToast("Pengiriman ditandai untuk dicoba lagi.");
  } catch (error) { showToast("Belum bisa mencoba lagi: " + friendlyError(error.message)); }
}
async function reconcileOperation(operationKey) {
  try {
    const headers = {}; if (cfg.REVIEW_TOKEN) headers["x-review-token"] = cfg.REVIEW_TOKEN;
    await api("/api/delivery-operations/" + encodeURIComponent(operationKey) + "/reconcile", { method: "POST", headers });
    await loadJobs(); showToast("Status pengiriman sudah dicek ulang.");
  } catch (error) { showToast("Belum bisa mengecek status: " + friendlyError(error.message)); }
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
    const tierLabel = tierNames[r.tier] || tierNames.unknown;
    const distinctness = parseObject(r.distinctness_json, r.distinctness || {});
    const subtitle = parseObject(r.subtitle_delivery_json, r.subtitle_delivery || {});
    const sound = parseObject(r.sound_tags_json, r.sound_tags || {});
    const operations = r.operations || [];
    const operationLine = operations.length ? '<div class="review-operations"><strong>Status pengiriman Buffer</strong><small class="operation-help">Video masuk ke antrean channel yang Anda pilih. Jika status belum pasti, jangan kirim ulang sebelum dicek.</small>' + operations.map((operation) => { const intent = parseObject(operation.schedule_intent_json, {}); return '<span class="operation-row"><b>' + escapeHtml(operation.channel_id) + '</b> <span class="operation-status">' + escapeHtml(friendlyOperation(operation.provider_state)) + '</span>' + (intent.timezone ? ' · zona ' + escapeHtml(intent.timezone) : '') + (operation.provider_due_at ? ' · perkiraan ' + escapeHtml(operation.provider_due_at) : '') + (operation.last_error ? ' · ' + escapeHtml(friendlyError(operation.last_error)) : '') + (operation.provider_state === "failed" ? ' <button class="operation-retry-button" data-operation-key="' + escapeHtml(operation.operation_key) + '" type="button">Coba lagi</button>' : '') + (operation.provider_state === "unknown" ? ' <button class="operation-reconcile-button" data-operation-key="' + escapeHtml(operation.operation_key) + '" type="button">Cek status</button>' : '') + '</span>'; }).join("") + '</div>' : '';
    const semanticLine = semantic.semantic_score == null ? "Pemeriksaan kualitas otomatis selesai" :
      "Kualitas potongan · pembuka " + Number(semantic.hook_score || 0).toFixed(0) + " · konteks " + Number(semantic.context_score || 0).toFixed(0) + " · penutup " + Number(semantic.payoff_score || 0).toFixed(0);
    const status = String(r.status || "pending_review");
    const actionButtons = status === "pending_review" || status === "changes_requested" ?
      '<button class="secondary-button review-action" data-review-action="request_rerender">Minta render ulang</button>' +
      '<button class="secondary-button review-action danger" data-review-action="reject">Tolak</button>' +
      '<button class="primary-button review-action" data-review-action="approve">ACC untuk Buffer <span>✓</span></button>' :
      '<span class="review-decision">' + escapeHtml(status.replaceAll("_", " ")) + (r.review_reason ? " · " + escapeHtml(r.review_reason) : "") + "</span>";
    return '<article class="review-card">' +
      (src ? '<video class="review-video" controls preload="none" poster="' + escapeHtml(r.thumbnail_url || "") + '" src="' + escapeHtml(src) + '"></video>' : '<div class="preview-placeholder"><span>Preview menunggu URL</span><small>Worker sedang mengunggah hasil</small></div>') +
      '<div class="review-body"><span class="status review">' + escapeHtml(status.replaceAll("_", " ").toUpperCase()) + '</span><h4>' + escapeHtml(r.title || "Clip") + '</h4>' +
      '<div class="review-contract"><strong>' + escapeHtml(tierLabel) + '</strong>' + (r.candidate_id ? '<span>Potongan teridentifikasi</span>' : '<span>Identitas potongan belum tersedia</span>') + (distinctness.distinct ? '<span>Berbeda dari video sebelahnya</span>' : '') + (subtitle.mode ? '<span>' + escapeHtml(subtitleNames[subtitle.mode] || "Status subtitle tersimpan") + '</span>' : '') + (sound.status ? '<span>' + escapeHtml(soundNames[sound.status] || "Status audio tersimpan") + '</span>' : '') + '</div>' +
      operationLine +
      '<p>Putar sampai selesai, cek apakah potongannya jelas, lalu pilih keputusan di bawah.</p>' +
      (r.rules_summary_id ? '<div class="rules-summary"><strong>Yang perlu Anda cek</strong><p>' + escapeHtml(r.rules_summary_id) + '</p></div>' : '') +
      '<div class="review-validation"><span>' + escapeHtml(friendlyValidation(validation.status || "needs_review")) + '</span><span>' + escapeHtml(semanticLine) + '</span>' + (r.caption_draft ? '<span>Caption siap diedit</span>' : '<span>Caption belum tersedia</span>') + '</div>' +
      (semantic.reason ? '<p class="semantic-reason">' + escapeHtml(semantic.reason) + '</p>' : '') +
      '<div class="review-actions">' +
      (r.download_url ? '<a class="secondary-button download-link" href="' + escapeHtml(r.download_url) + '" download>Unduh video <span>↓</span></a>' + ((status === "pending_review" || status === "changes_requested") ? '<button class="secondary-button caption-edit-button" type="button">Edit caption</button>' : '') + (status === "approved_for_manual_post" ? '<button class="primary-button buffer-upload-button" type="button">Masukkan ke Buffer <span>↗</span></button>' : '') : '<button class="secondary-button" type="button">Menunggu file <span>◌</span></button>') + actionButtons +
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
  document.querySelectorAll(".operation-retry-button").forEach((button) => button.addEventListener("click", () => retryOperation(button.dataset.operationKey)));
  document.querySelectorAll(".operation-reconcile-button").forEach((button) => button.addEventListener("click", () => reconcileOperation(button.dataset.operationKey)));
}
function showView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  $("#" + name + "View").classList.remove("hidden");
  $("#pageTitle").textContent = name === "campaigns" ? "Pilih campaign" : name === "jobs" ? "Proses berjalan" : "Tinjau video";
  document.querySelectorAll(".nav-item").forEach((n) => n.classList.toggle("active", n.getAttribute("href") === "#" + name));
}
document.querySelectorAll(".nav-item").forEach((n) => n.addEventListener("click", (e) => { e.preventDefault(); showView(n.getAttribute("href").slice(1)); }));
$("#refreshButton").addEventListener("click", async () => { await loadCampaigns(); await loadJobs(); showToast("Data diperbarui"); });
$("#searchInput").addEventListener("input", renderCampaigns);
$("#platformFilter").addEventListener("change", renderCampaigns);
$("#sortSelect").addEventListener("change", renderCampaigns);
document.querySelectorAll("[data-close]").forEach((x) => x.addEventListener("click", () => $("#detailModal").classList.add("hidden")));
$("#workerStatus").textContent = cfg.DEMO_MODE ? "mode demo" : "terhubung · pembaruan otomatis";
loadCampaigns();
loadJobs();
setInterval(() => { if (state.jobs.length) renderJobs(); }, 1000);