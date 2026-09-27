const cfg = window.CLIPPER_CONFIG || { API_BASE_URL: "", DEMO_MODE: true };
const $ = (selector) => document.querySelector(selector);
const state = {
  campaigns: [],
  jobs: [],
  reviews: [],
  bufferChannels: [],
  pollTimer: null,
  activeView: "home",
  activeReviewJobId: null,
  activeReviewIndex: 0,
  videoLoaded: false,
  pendingDecision: null
};

const statusNames = {
  queued: "Menunggu",
  processing: "Sedang diproses",
  review: "Siap ditinjau",
  error: "Perlu diperbaiki",
  blocked: "Tidak dapat dilanjutkan",
  cancelled: "Dibatalkan",
  pending_review: "Menunggu pemeriksaan",
  changes_requested: "Perlu diperbaiki",
  approved_for_manual_post: "Sudah disetujui",
  rejected: "Ditolak",
  pending_render: "Sedang dibuat ulang"
};

const operationNames = {
  pending: "Menunggu dikirim",
  attempting: "Sedang mengirim",
  unknown: "Belum pasti",
  scheduled: "Sudah masuk antrean",
  published: "Sudah terbit",
  failed: "Gagal mengirim",
  cancelled: "Dibatalkan",
  unresolved: "Belum terselesaikan"
};

const stageNames = {
  claim: "Menyiapkan pekerjaan",
  campaign_rules: "Memahami campaign",
  asset_preflight: "Memeriksa bahan",
  transcription: "Membaca audio",
  selector: "Mencari potongan",
  semantic_ranking: "Menilai kandidat",
  render: "Membuat video",
  validation: "Memeriksa video",
  r2_upload: "Menyiapkan preview",
  manual_review: "Menyiapkan review"
};

const demoCampaigns = [
  { id: "demo-ai-clips", title: "AI Founder Clips", brand: "Demo Studio", category: "technology", score: 86.5, rate_per_1k: 7, budget_left: 3850, platforms: ["tiktok", "youtube", "instagram"], type: "clipping", content_kind: "clipping", readiness_status: "siap", readiness_label: "Siap dikerjakan", readiness_reason: "Bahan resmi tersedia.", flags: [] },
  { id: "demo-podcast", title: "Podcast Growth Campaign", brand: "North Star Media", category: "education", score: 78.2, rate_per_1k: 4, budget_left: 12400, platforms: ["youtube", "tiktok"], type: "clipping", content_kind: "clipping", readiness_status: "ketat", readiness_label: "Bisa, tapi ketat", readiness_reason: "Ada beberapa syarat campaign yang perlu diperhatikan.", flags: ["9:16"] },
  { id: "demo-music", title: "Artist Discovery Clips", brand: "Indie Records", category: "music", score: 69.4, rate_per_1k: 2.5, budget_left: 8200, platforms: ["tiktok", "instagram"], type: "clipping", content_kind: "clipping", readiness_status: "belum_siap", readiness_label: "Belum siap", readiness_reason: "Bahan belum dapat diverifikasi.", flags: ["audio resmi"] }
];

function escapeHtml(value) {
  const amp = String.fromCharCode(38);
  const map = { "&": amp + "amp;", "<": amp + "lt;", ">": amp + "gt;", '"': amp + "quot;" };
  return String(value == null ? "" : value).replace(/[&<>"]/g, (c) => map[c] || c);
}

function parseObject(value, fallback = {}) {
  if (value && typeof value === "object") return value;
  try {
    const parsed = JSON.parse(value || "");
    return parsed && typeof parsed === "object" ? parsed : fallback;
  } catch (_) {
    return fallback;
  }
}

function api(path, options) {
  return fetch((cfg.API_BASE_URL || "") + path, options).then(async (response) => {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.message || payload.error || "API " + response.status);
    return payload;
  });
}

function showToast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => el.classList.add("hidden"), 2800);
}

function humanDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
}

function money(value) {
  return value == null ? "-" : "$" + Number(value).toLocaleString();
}

function statusLabel(status) {
  return statusNames[String(status || "").toLowerCase()] || String(status || "Belum diketahui");
}

function friendlyOperation(status) {
  return operationNames[String(status || "").toLowerCase()] || "Status pengiriman belum diketahui";
}

function friendlyError(value) {
  const text = String(value || "");
  if (/capacity_preflight|capacity.*exhausted|request_budget/i.test(text)) return "Antrean Buffer sedang penuh. Tunggu sampai tersedia.";
  if (/channel_not_found|channel.*required/i.test(text)) return "Channel tujuan belum terhubung.";
  if (/caption_compliance|caption.*mismatch|caption_required/i.test(text)) return "Caption belum memenuhi aturan campaign.";
  if (/approval_provenance|not_approved|approval_revision/i.test(text)) return "Persetujuan video sudah tidak berlaku untuk versi ini.";
  if (/review_contract_missing|review_contract_stale|review_contract_not_approvable/i.test(text)) return "Versi review sudah berubah. Periksa ulang video sebelum menyetujui.";
  if (/ca09_review_blocked|ca09_review_contract/i.test(text)) return "Campaign belum memenuhi pemeriksaan akhir untuk review.";
  if (/unknown_requires_reconciliation|unknown/i.test(text)) return "Hasil pengiriman belum pasti. Periksa statusnya sebelum mengirim ulang.";
  if (/timeout|503|429|rate limit|temporar/i.test(text)) return "Layanan sedang sibuk. Coba lagi setelah beberapa saat.";
  if (/source_media_invalid|media_preflight_failed|video_stream_missing|audio_stream_missing|ffprobe_failed/i.test(text)) return "Bahan video tidak lolos pemeriksaan media.";
  if (/source_assets_unavailable|tidak dapat diakses|tidak dapat diunduh|youtube.*429/i.test(text)) return "Bahan campaign tidak bisa diakses dari worker.";
  return text || "Mesin berhenti sebelum selesai.";
}

function readinessClass(status) {
  if (status === "siap") return "ready";
  if (status === "ketat") return "attention";
  if (status === "belum_siap" || status === "lewati") return "blocked";
  return "neutral";
}

function canStart(campaign) {
  return ["siap", "ketat"].includes(campaign.readiness_status) || String(campaign.title || "").toLowerCase().includes("clip");
}

function reviewBadgeClass(status) {
  if (status === "approved_for_manual_post" || status === "pass" || status === "ready" || status === "siap_ditinjau") return "safe";
  if (status === "pending_render" || status === "processing" || status === "review" || status === "pending_review" || status === "changes_requested" || status === "perlu_perhatian") return "attention";
  return "danger";
}

function reviewStatusText(preview, contract) {
  if (preview.status === "approved_for_manual_post") return "Sudah disetujui";
  if (preview.status === "rejected") return "Ditolak";
  if (preview.status === "pending_render") return "Sedang dibuat ulang";
  if (contract?.decision_state === "blocked") return "Tidak dapat dilanjutkan";
  if (preview.status === "changes_requested") return "Perlu diperbaiki";
  return "Menunggu pemeriksaan";
}

function getCurrentReviews(jobId) {
  const rows = state.reviews.filter((item) => item.job?.id === jobId && !item.superseded_at);
  const latest = new Map();
  for (const item of rows) {
    const key = String(item.rank || item.id || "");
    const previous = latest.get(key);
    if (!previous || Number(item.revision_number || 1) >= Number(previous.revision_number || 1)) latest.set(key, item);
  }
  return [...latest.values()].sort((a, b) => Number(a.rank || 0) - Number(b.rank || 0));
}

function activeReview() {
  const rows = getCurrentReviews(state.activeReviewJobId);
  return rows[state.activeReviewIndex] || rows[0] || null;
}

function releaseVideoPreview() {
  const video = $("#activeReviewVideo");
  if (video) {
    video.pause();
    video.removeAttribute("src");
    video.load();
  }
  state.videoLoaded = false;
}

function renderVideoStage(preview) {
  if (!preview) return "";
  const poster = preview.thumbnail_url || "";
  if (state.videoLoaded && preview.video_url) {
    return '<div class="video-stage"><video id="activeReviewVideo" class="review-video" controls preload="none" playsinline poster="' + escapeHtml(poster) + '"><source src="' + escapeHtml(preview.video_url) + '" type="video/mp4"></video><div class="video-foot"><span>Preview ringan</span><a href="' + escapeHtml(preview.download_url || "#") + '" download>Unduh versi penuh ↓</a></div></div>';
  }
  const label = preview.status === "pending_render" ? "Menunggu render selesai" : preview.thumbnail_url ? "Putar preview" : "Preview belum tersedia";
  const disabled = !preview.video_url || preview.status === "pending_render";
  return '<div class="video-stage poster-stage">' +
    (poster ? '<img src="' + escapeHtml(poster) + '" alt="" loading="eager">' : '<div class="poster-fallback"><span>Preview</span></div>') +
    '<div class="poster-shade"></div>' +
    '<button class="play-preview" type="button" data-play-preview="true" ' + (disabled ? "disabled" : "") + '><span class="play-icon">' + (disabled ? "…" : "▶") + '</span><strong>' + escapeHtml(label) + '</strong><small>' + (disabled ? "File sedang disiapkan" : "Video ringan akan dimuat hanya saat diputar") + '</small></button>' +
  '</div>';
}

function checkIcon(status) {
  if (status === "pass") return "✓";
  if (status === "review") return "!";
  return "×";
}

function renderChecks(contract) {
  const checks = Array.isArray(contract?.checks) ? contract.checks : [];
  return checks.map((check) =>
    '<div class="check-row ' + reviewBadgeClass(check.status) + '">' +
      '<span class="check-icon">' + checkIcon(check.status) + '</span>' +
      '<div><strong>' + escapeHtml(check.label || "Pemeriksaan") + '</strong><p>' + escapeHtml(check.detail || "") + '</p></div>' +
    '</div>'
  ).join("");
}

function renderExceptions(contract) {
  const items = Array.isArray(contract?.exceptions) ? contract.exceptions : [];
  if (!items.length) {
    return '<div class="all-clear"><span>✓</span><div><strong>Tidak ada masalah yang perlu ditangani</strong><p>Pemeriksaan campaign tidak memberikan pengecualian tambahan.</p></div></div>';
  }
  return items.slice(0, 5).map((item) =>
    '<div class="exception-row ' + (item.severity === "critical" ? "critical" : "warning") + '">' +
      '<span>' + (item.severity === "critical" ? "!" : "i") + '</span>' +
      '<div><strong>' + escapeHtml(item.label || "Perlu diperiksa") + '</strong><p>' + escapeHtml(item.reason || "") + '</p>' + (item.action ? '<small>' + escapeHtml(item.action) + '</small>' : '') + '</div>' +
    '</div>'
  ).join("") + (items.length > 5 ? '<p class="muted">+' + (items.length - 5) + ' pemeriksaan lain</p>' : "");
}

function renderTechnicalDetails(preview, contract) {
  const validation = parseObject(preview.validation, {});
  const semantic = parseObject(validation.semantic, {});
  const provenance = contract?.provenance || {};
  const rows = [
    ["Review Contract", contract?.review_contract_id],
    ["Compliance Gate", contract?.compliance_gate_id],
    ["Artifact", contract?.artifact_hash],
    ["Caption revision", contract?.caption_revision_id],
    ["Source hash", contract?.source_hash],
    ["Kandidat", preview.candidate_id],
    ["Sumber bahan", preview.source_asset_id],
    ["Semantic", semantic.semantic_score == null ? null : Number(semantic.semantic_score).toFixed(3)]
  ];
  return '<details class="technical-detail"><summary>Detail mesin</summary><div class="technical-grid">' +
    rows.filter((row) => row[1]).map((row) => '<div><small>' + escapeHtml(row[0]) + '</small><code>' + escapeHtml(row[1]) + '</code></div>').join("") +
  '</div><p class="technical-note">Data ini untuk audit. Tidak diperlukan untuk mengambil keputusan review.</p></details>';
}

function renderCaption(preview) {
  const editable = ["pending_review", "changes_requested"].includes(preview.status);
  if (!editable) {
    return '<section class="review-section"><div class="section-label">CAPTION</div><div class="caption-static">' + escapeHtml(preview.caption_draft || "Caption belum tersedia.") + '</div></section>';
  }
  return '<section class="review-section"><div class="section-label">CAPTION</div><textarea id="captionEditor" class="caption-editor" rows="5">' + escapeHtml(preview.caption_draft || "") + '</textarea><div class="caption-footer"><span id="captionState">Perubahan belum disimpan</span><div><button class="secondary-button" id="cancelCaption" type="button">Batal</button><button class="primary-button small" id="saveCaption" type="button">Simpan caption</button></div></div></section>';
}

function renderReviewGuide() {
  return '<details class="simple-detail review-guide"><summary>Panduan review</summary><div class="simple-detail-body">' +
    '<div class="rule-line"><span>1. Pembuka</span><strong>Apakah video langsung masuk ke inti?</strong></div>' +
    '<div class="rule-line"><span>2. Konteks</span><strong>Apakah isi video jelas untuk campaign?</strong></div>' +
    '<div class="rule-line"><span>3. Caption</span><strong>Apakah caption sesuai video dan aturan?</strong></div>' +
    '<div class="rule-line"><span>4. Keputusan</span><strong>Setujui, minta render ulang, atau tolak.</strong></div>' +
  '</div></details>';
}

function renderOperations(preview) {
  const operations = Array.isArray(preview.operations) ? preview.operations : [];
  if (!operations.length) return "";
  return '<section class="review-section delivery-section"><div class="section-label">PENGIRIMAN</div>' +
    '<div class="safe-note buffer-safe-note"><strong>Persetujuan tetap menjadi syarat pengiriman.</strong><span>Buffer hanya menerima versi video, caption, dan aturan yang sudah disetujui.</span></div>' +
    operations.map((operation) =>
      '<div class="delivery-row"><div><strong>' + escapeHtml(operation.channel_id || "Channel") + '</strong><span>' + escapeHtml(friendlyOperation(operation.provider_state)) + '</span></div>' +
      '<div class="delivery-actions">' +
      (operation.provider_state === "failed" ? '<button class="link-button operation-retry-button" data-retry-operation="' + escapeHtml(operation.operation_key) + '" type="button">Coba lagi</button>' : '') +
      (operation.provider_state === "unknown" ? '<button class="link-button operation-reconcile-button" data-reconcile-operation="' + escapeHtml(operation.operation_key) + '" type="button">Cek status</button>' : '') +
      '</div></div>'
    ).join("") + '</section>';
}

function renderCandidateRail(rows, activeIndex) {
  return '<div class="candidate-rail">' + rows.map((preview, index) => {
    const contract = preview.review_contract || {};
    const active = index === activeIndex;
    return '<button class="candidate-item ' + (active ? "active" : "") + '" data-candidate-index="' + index + '" type="button">' +
      '<span class="candidate-thumb">' + (preview.thumbnail_url ? '<img src="' + escapeHtml(preview.thumbnail_url) + '" loading="lazy" alt="">' : '<span>—</span>') + '</span>' +
      '<span class="candidate-copy"><strong>Video ' + escapeHtml(String(index + 1)) + '</strong><small>' + escapeHtml(contract.summary?.label || reviewStatusText(preview, contract)) + '</small></span>' +
      '<span class="candidate-mark ' + reviewBadgeClass(preview.status) + '"></span>' +
    '</button>';
  }).join("") + '</div>';
}

function renderReviewWorkspace() {
  const container = $("#reviewWorkspace");
  const inbox = $("#reviewInbox");
  const job = state.jobs.find((item) => item.id === state.activeReviewJobId);
  const rows = getCurrentReviews(state.activeReviewJobId);
  if (!job || !rows.length) {
    state.activeReviewJobId = null;
    state.activeReviewIndex = 0;
    state.videoLoaded = false;
    container.classList.add("hidden");
    inbox.classList.remove("hidden");
    renderReviewInbox();
    return;
  }

  if (state.activeReviewIndex >= rows.length) state.activeReviewIndex = 0;
  const preview = rows[state.activeReviewIndex];
  const contract = preview.review_contract || {};
  const summary = contract.summary || {};
  const blocked = contract.decision_state === "blocked";
  const approved = preview.status === "approved_for_manual_post";
  const pendingRender = preview.status === "pending_render";
  const editable = ["pending_review", "changes_requested"].includes(preview.status);

  releaseVideoPreview();

  inbox.classList.add("hidden");
  container.classList.remove("hidden");
  container.innerHTML =
    '<div class="review-topbar"><button class="back-button" id="backToReviewInbox" type="button">← Semua review</button><span class="review-progress">Video ' + (state.activeReviewIndex + 1) + ' dari ' + rows.length + '</span></div>' +
    '<div class="review-context"><div><p class="eyebrow">CAMPAIGN</p><h2>' + escapeHtml(job.campaign_title || job.campaign_id || "Campaign") + '</h2><p>' + escapeHtml(job.campaign_brand || "") + (job.campaign_brand ? " · " : "") + escapeHtml((job.output_contract_status === "review_ready" ? "Output selesai" : "Clipping")) + '</p></div><span class="status-pill ' + reviewBadgeClass(summary.status || (blocked ? "blocked" : "review")) + '">' + escapeHtml(summary.label || reviewStatusText(preview, contract)) + '</span></div>' +
    '<div class="review-layout">' +
      '<aside class="candidate-panel"><div class="section-label">KANDIDAT</div>' + renderCandidateRail(rows, state.activeReviewIndex) + '</aside>' +
      '<article class="review-main">' +
        renderVideoStage(preview) +
        '<div class="review-copy">' +
          '<div class="review-title-row"><div><div class="section-label">VIDEO</div><h3>Video ' + escapeHtml(String(state.activeReviewIndex + 1)) + '</h3></div><span class="tier-pill">' + escapeHtml(preview.tier === "tier_1" ? "Audiens utama" : preview.tier === "tier_2" ? "Audiens cadangan" : "Kandidat") + '</span></div>' +
          (summary.message ? '<div class="decision-summary ' + (blocked ? "danger" : summary.status === "perlu_perhatian" ? "attention" : "safe") + '"><span>' + (blocked ? "!" : summary.status === "perlu_perhatian" ? "!" : "✓") + '</span><div><strong>' + escapeHtml(summary.label || "Status review") + '</strong><p>' + escapeHtml(summary.message) + '</p></div></div>' : '') +
          '<section class="review-section"><div class="section-label">PEMERIKSAAN</div><div class="checks-list">' + renderChecks(contract) + '</div></section>' +
          renderReviewGuide() +
          '<section class="review-section"><div class="section-label">PERLU ANDA PERHATIKAN</div><div>' + renderExceptions(contract) + '</div></section>' +
          renderCaption(preview) +
          '<section class="review-section"><div class="section-label">ATURAN CAMPAIGN</div><details class="simple-detail"><summary>Lihat ringkasan aturan</summary><div class="simple-detail-body">' +
            '<div class="rule-line"><span>Status compliance</span><strong>' + escapeHtml(contract.summary?.label || "Belum diketahui") + '</strong></div>' +
            '<div class="rule-line"><span>Platform</span><strong>' + escapeHtml((job.platforms || preview.platform ? ((job.platforms || []).join(", ") || preview.platform || "-") : "-")) + '</strong></div>' +
            '<div class="rule-line"><span>Source</span><strong>' + escapeHtml(preview.source_asset_id || "Teridentifikasi") + '</strong></div>' +
          '</div></details></section>' +
          renderOperations(preview) +
          renderTechnicalDetails(preview, contract) +
          '<div class="review-navigation"><button class="secondary-button" id="prevCandidate" type="button" ' + (state.activeReviewIndex === 0 ? "disabled" : "") + '>← Sebelumnya</button><button class="secondary-button" id="nextCandidate" type="button" ' + (state.activeReviewIndex >= rows.length - 1 ? "disabled" : "") + '>Berikutnya →</button></div>' +
        '</div>' +
        '<div class="review-actionbar ' + (blocked ? "blocked" : approved ? "approved" : "") + '">' +
          (blocked ? '<div class="action-lock"><strong>Review dihentikan</strong><span>Masalah compliance harus diselesaikan lebih dulu.</span></div>' :
           pendingRender ? '<div class="action-lock"><strong>Menunggu render ulang</strong><span>Versi baru sedang disiapkan.</span></div>' :
           approved ? '<div class="action-lock"><strong>Video sudah disetujui</strong><span>Langkah berikutnya adalah pengiriman.</span></div><button class="primary-button" id="bufferButton" type="button">Kirim ke Buffer <span>↗</span></button>' :
           editable ? '<button class="secondary-button danger" id="rejectButton" type="button">Tolak</button><button class="secondary-button" id="changesButton" type="button">Minta perbaikan</button><button class="primary-button" id="approveButton" type="button" ' + (!contract.review_actions?.approve ? "disabled" : "") + '>✓ Setujui video</button>' :
           '<div class="action-lock"><strong>' + escapeHtml(reviewStatusText(preview, contract)) + '</strong></div>') +
        '</div>' +
      '</article>' +
    '</div>';

  bindReviewWorkspace(preview, rows);
}

function bindReviewWorkspace(preview, rows) {
  $("#backToReviewInbox")?.addEventListener("click", () => { releaseVideoPreview(); state.activeReviewJobId = null; renderReviewInbox(); });
  document.querySelectorAll("[data-candidate-index]").forEach((button) => button.addEventListener("click", () => {
    const next = Number(button.dataset.candidateIndex);
    if (!Number.isInteger(next)) return;
    releaseVideoPreview();
    state.activeReviewIndex = next;
    renderReviewWorkspace();
  }));
  $("#play-preview")?.addEventListener("click", () => {});
  document.querySelector("[data-play-preview]")?.addEventListener("click", async () => {
    if (!preview.video_url) return;
    const button = document.querySelector("[data-play-preview]");
    if (button) button.disabled = true;
    try {
      state.videoLoaded = true;
      renderReviewWorkspace();
      const video = $("#activeReviewVideo");
      if (!video) throw new Error("video_element_missing");
      video.load();
      await video.play();
    } catch (error) {
      state.videoLoaded = false;
      renderReviewWorkspace();
      showToast("Preview video gagal diputar: " + friendlyError(error.message));
    }
  });
  $("#prevCandidate")?.addEventListener("click", () => {
    if (state.activeReviewIndex > 0) { releaseVideoPreview(); state.activeReviewIndex -= 1; renderReviewWorkspace(); }
  });
  $("#nextCandidate")?.addEventListener("click", () => {
    if (state.activeReviewIndex < rows.length - 1) { releaseVideoPreview(); state.activeReviewIndex += 1; renderReviewWorkspace(); }
  });
  $("#saveCaption")?.addEventListener("click", () => saveCaption(preview));
  $("#cancelCaption")?.addEventListener("click", () => { renderReviewWorkspace(); });
  $("#approveButton")?.addEventListener("click", () => openDecisionModal(preview, "approve"));
  $("#rejectButton")?.addEventListener("click", () => openDecisionModal(preview, "reject"));
  $("#changesButton")?.addEventListener("click", () => openDecisionModal(preview, "request_rerender"));
  $("#bufferButton")?.addEventListener("click", () => openBufferUpload(preview));
  document.querySelectorAll("[data-retry-operation]").forEach((button) => button.addEventListener("click", () => retryOperation(button.dataset.retryOperation)));
  document.querySelectorAll("[data-reconcile-operation]").forEach((button) => button.addEventListener("click", () => reconcileOperation(button.dataset.reconcileOperation)));
}

async function saveCaption(preview) {
  const editor = $("#captionEditor");
  if (!editor) return;
  const text = editor.value.trim();
  const button = $("#saveCaption");
  button.disabled = true;
  button.textContent = "Memeriksa…";
  try {
    const headers = { "content-type": "application/json" };
    if (cfg.REVIEW_TOKEN) headers["x-review-token"] = cfg.REVIEW_TOKEN;
    const response = await api("/api/previews/" + encodeURIComponent(preview.id) + "/caption-revisions", {
      method: "POST",
      headers,
      body: JSON.stringify({
        text,
        fields: { hashtags: (text.match(/#[A-Za-z0-9_]+/g) || []) },
        reviewer: cfg.REVIEWER || "manual-user"
      })
    });
    preview.caption_draft = response.revision.text;
    preview.caption_revision_id = response.revision.revision_id;
    preview.caption_hash = response.revision.caption_hash;
    if (response.review_contract) preview.review_contract = response.review_contract;
    renderReviewWorkspace();
    showToast("Caption tersimpan sebagai versi baru");
  } catch (error) {
    button.disabled = false;
    button.textContent = "Simpan caption";
    showToast("Caption belum disimpan: " + friendlyError(error.message));
  }
}

function openDecisionModal(preview, action) {
  state.pendingDecision = { preview, action };
  const requiredReason = action !== "approve";
  $("#decisionEyebrow").textContent = action === "approve" ? "KONFIRMASI" : action === "reject" ? "TOLAK VIDEO" : "MINTA PERBAIKAN";
  $("#decisionTitle").textContent = action === "approve" ? "Setujui video ini?" : action === "reject" ? "Mengapa video ditolak?" : "Apa yang perlu diperbaiki?";
  $("#decisionDescription").textContent = action === "approve"
    ? "Persetujuan akan dikunci ke versi video, caption, aturan campaign, dan Review Contract saat ini."
    : "Alasan akan disimpan di riwayat review agar render atau keputusan berikutnya punya konteks yang jelas.";
  const input = $("#decisionReason");
  input.value = "";
  input.required = requiredReason;
  input.placeholder = requiredReason ? "Contoh: pembukaan terlalu lambat, minta versi yang lebih singkat." : "Opsional";
  input.classList.toggle("hidden", !requiredReason);
  $("#decisionConfirm").textContent = action === "approve" ? "Ya, setujui" : action === "reject" ? "Tolak video" : "Minta perbaikan";
  $("#decisionModal").classList.remove("hidden");
  if (requiredReason) input.focus(); else $("#decisionConfirm").focus();
}

async function executeDecision() {
  const pending = state.pendingDecision;
  if (!pending) return;
  const { preview, action } = pending;
  const reason = String($("#decisionReason").value || "").trim();
  if (action !== "approve" && !reason) {
    $("#decisionReason").focus();
    return;
  }
  const button = $("#decisionConfirm");
  button.disabled = true;
  button.textContent = "Menyimpan…";
  try {
    const headers = { "content-type": "application/json" };
    if (cfg.REVIEW_TOKEN) headers["x-review-token"] = cfg.REVIEW_TOKEN;
    const response = await api("/api/previews/" + encodeURIComponent(preview.id) + "/review", {
      method: "POST",
      headers,
      body: JSON.stringify({
        action,
        reason,
        reviewer: cfg.REVIEWER || "manual-user",
        artifact_hash: preview.artifact_hash,
        caption_revision_id: preview.caption_revision_id,
        review_contract_id: preview.review_contract?.review_contract_id || null,
        compliance_gate_id: preview.review_contract?.compliance_gate_id || null
      })
    });
    Object.assign(preview, response.preview || {});
    if (action === "approve") {
      preview.status = "approved_for_manual_post";
      preview.approval_review_contract_id = response.preview?.approval_review_contract_id;
      preview.approval_compliance_gate_id = response.preview?.approval_compliance_gate_id;
    }
    $("#decisionModal").classList.add("hidden");
    state.pendingDecision = null;
    renderReviewWorkspace();
    showToast(action === "approve" ? "Video disetujui" : action === "reject" ? "Video ditolak" : "Perbaikan diminta");
    await loadJobs({ preserveReview: true });
  } catch (error) {
    button.disabled = false;
    button.textContent = action === "approve" ? "Ya, setujui" : action === "reject" ? "Tolak video" : "Minta perbaikan";
    showToast("Keputusan belum tersimpan: " + friendlyError(error.message));
  }
}

async function openBufferUpload(preview) {
  try {
    if (!state.bufferChannels.length) {
      const headers = {};
      if (cfg.REVIEW_TOKEN) headers["x-review-token"] = cfg.REVIEW_TOKEN;
      state.bufferChannels = (await api("/api/buffer/channels", { headers })).channels || [];
    }
    if (!state.bufferChannels.length) throw new Error("channel_not_found");
    const groups = state.bufferChannels.reduce((acc, channel) => {
      const key = channel.organizationName || "Buffer";
      (acc[key] ||= []).push(channel);
      return acc;
    }, {});
    const checks = Object.entries(groups).map(([organization, channels]) =>
      '<fieldset class="buffer-group"><legend>' + escapeHtml(organization) + '</legend>' +
      channels.map((channel) => '<label class="buffer-channel"><input type="checkbox" value="' + escapeHtml(channel.id) + '"><span>' + escapeHtml(channel.name || channel.service || "Channel") + '</span><small>' + escapeHtml(channel.service || "") + '</small></label>').join("") +
      '</fieldset>'
    ).join("");

    $("#modalContent").innerHTML =
      '<p class="eyebrow">LANGKAH BERIKUTNYA</p><h2>Kirim ke Buffer</h2><p class="modal-note">Video yang sudah disetujui akan dikirim ke slot antrean berikutnya pada channel yang dipilih.</p>' +
      '<div class="safe-note"><strong>Versi terkunci</strong><span>Video, caption, dan persetujuan mengikuti versi yang baru saja Anda review.</span></div>' +
      '<div class="buffer-list">' + checks + '</div>' +
      '<label class="buffer-caption"><span>Caption</span><textarea id="bufferCaption" rows="5">' + escapeHtml(preview.caption_draft || "") + '</textarea></label>' +
      '<div class="modal-actions"><button class="secondary-button" data-close="true" type="button">Batal</button><button class="primary-button" id="confirmBuffer" type="button">Periksa sebelum kirim</button></div>';

    $("#detailModal").classList.remove("hidden");
    document.querySelector("#modalContent [data-close]")?.addEventListener("click", closeDetailModal);
    $("#confirmBuffer").addEventListener("click", () => confirmBuffer(preview));
  } catch (error) {
    showToast("Buffer belum siap: " + friendlyError(error.message));
  }
}

async function confirmBuffer(preview) {
  const selected = [...document.querySelectorAll(".buffer-channel input:checked")];
  const channel_ids = selected.map((input) => input.value);
  if (!channel_ids.length) return showToast("Pilih minimal satu channel.");
  const button = $("#confirmBuffer");
  button.disabled = true;
  button.textContent = "Memeriksa…";
  try {
    const headers = { "content-type": "application/json" };
    if (cfg.REVIEW_TOKEN) headers["x-review-token"] = cfg.REVIEW_TOKEN;
    const request = {
      channel_ids,
      text: $("#bufferCaption").value.trim(),
      artifact_hash: preview.approval_artifact_hash || preview.artifact_hash,
      caption_revision_id: preview.approval_caption_revision_id || preview.caption_revision_id
    };
    const preflight = await api("/api/previews/" + encodeURIComponent(preview.id) + "/buffer/preflight", { method: "POST", headers, body: JSON.stringify(request) });
    if (!preflight.ok) throw new Error((preflight.channels || []).filter((item) => !item.valid).map((item) => item.error).join("; ") || "capacity_preflight_failed");
    $("#modalContent").innerHTML =
      '<p class="eyebrow">SIAP DIKIRIM</p><h2>Konfirmasi pengiriman</h2><p class="modal-note">Video akan masuk ke slot antrean berikutnya. Sistem tidak mengubah jadwal manual di luar Buffer.</p>' +
      '<div class="confirm-summary"><div><small>Channel</small><strong>' + channel_ids.length + '</strong></div><div><small>Caption</small><strong>Valid</strong></div><div><small>Versi video</small><strong>Terkunci</strong></div></div>' +
      '<div class="modal-actions"><button class="secondary-button" data-close="true" type="button">Batal</button><button class="primary-button" id="sendBuffer" type="button">Kirim ke Buffer ↗</button></div>';
    document.querySelector("#modalContent [data-close]")?.addEventListener("click", closeDetailModal);
    $("#sendBuffer").addEventListener("click", async () => {
      const send = $("#sendBuffer");
      send.disabled = true;
      send.textContent = "Mengirim…";
      try {
        const response = await api("/api/previews/" + encodeURIComponent(preview.id) + "/buffer", { method: "POST", headers, body: JSON.stringify(request) });
        closeDetailModal();
        showToast(response.outcome === "all_succeeded" ? "Video sudah masuk antrean Buffer." : "Sebagian pengiriman perlu diperiksa.");
        await loadJobs({ preserveReview: true });
      } catch (error) {
        send.disabled = false;
        send.textContent = "Kirim ke Buffer ↗";
        showToast("Belum masuk Buffer: " + friendlyError(error.message));
      }
    });
  } catch (error) {
    button.disabled = false;
    button.textContent = "Periksa sebelum kirim";
    showToast("Belum siap dikirim: " + friendlyError(error.message));
  }
}

function closeDetailModal() {
  $("#detailModal").classList.add("hidden");
  $("#modalContent").innerHTML = "";
}

async function retryOperation(operationKey) {
  try {
    const headers = {};
    if (cfg.REVIEW_TOKEN) headers["x-review-token"] = cfg.REVIEW_TOKEN;
    await api("/api/delivery-operations/" + encodeURIComponent(operationKey) + "/retry", { method: "POST", headers });
    showToast("Pengiriman ditandai untuk dicoba lagi.");
    await loadJobs({ preserveReview: true });
  } catch (error) {
    showToast("Belum bisa mencoba lagi: " + friendlyError(error.message));
  }
}

async function reconcileOperation(operationKey) {
  try {
    const headers = {};
    if (cfg.REVIEW_TOKEN) headers["x-review-token"] = cfg.REVIEW_TOKEN;
    await api("/api/delivery-operations/" + encodeURIComponent(operationKey) + "/reconcile", { method: "POST", headers });
    showToast("Status pengiriman dicek ulang.");
    await loadJobs({ preserveReview: true });
  } catch (error) {
    showToast("Belum bisa mengecek status: " + friendlyError(error.message));
  }
}

function renderReviewInbox() {
  const inbox = $("#reviewInbox");
  const container = $("#reviewWorkspace");
  container.classList.add("hidden");
  inbox.classList.remove("hidden");
  const jobsWithReviews = state.jobs.filter((job) => getCurrentReviews(job.id).length);
  const pending = state.reviews.filter((item) => ["pending_review", "changes_requested"].includes(item.status) && !item.superseded_at).length;
  $("#reviewCount").textContent = pending;
  if (!jobsWithReviews.length) {
    inbox.innerHTML =
      '<div class="empty-work"><div class="empty-icon">✓</div><h2>Belum ada video yang perlu ditinjau</h2><p>Setelah mesin menyelesaikan sebuah campaign, video akan muncul di sini.</p><button class="secondary-button" data-view="campaigns" type="button">Cari campaign</button></div>';
    inbox.querySelector("[data-view]")?.addEventListener("click", () => showView("campaigns"));
    return;
  }

  inbox.innerHTML =
    '<div class="section-heading"><div><p class="eyebrow">REVIEW</p><h3>Video yang menunggu keputusan</h3></div><span class="muted">' + pending + ' perlu tindakan</span></div>' +
    '<div class="review-inbox-list">' +
    jobsWithReviews.map((job) => {
      const rows = getCurrentReviews(job.id);
      const pendingRows = rows.filter((item) => ["pending_review", "changes_requested"].includes(item.status)).length;
      const approvedRows = rows.filter((item) => item.status === "approved_for_manual_post").length;
      const jobStatus = pendingRows ? "attention" : approvedRows === rows.length ? "safe" : "neutral";
      return '<button class="review-inbox-card" data-review-job="' + escapeHtml(job.id) + '" type="button">' +
        '<div class="inbox-thumbs">' + rows.slice(0, 3).map((item) => item.thumbnail_url ? '<img src="' + escapeHtml(item.thumbnail_url) + '" loading="lazy" alt="">' : '<span></span>').join("") + '</div>' +
        '<div class="inbox-copy"><p class="eyebrow">CAMPAIGN</p><h3>' + escapeHtml(job.campaign_title || job.campaign_id) + '</h3><p>' + escapeHtml(job.campaign_brand || "") + '</p><div class="inbox-meta"><span>' + rows.length + ' video</span><span class="' + jobStatus + '">' + escapeHtml(pendingRows ? pendingRows + " perlu diperiksa" : approvedRows + " disetujui") + '</span></div></div><span class="inbox-arrow">→</span>' +
      '</button>';
    }).join("") +
    '</div>';

  document.querySelectorAll("[data-review-job]").forEach((button) => button.addEventListener("click", () => {
    state.activeReviewJobId = button.dataset.reviewJob;
    state.activeReviewIndex = 0;
    state.videoLoaded = false;
    renderReviewWorkspace();
  }));
}

function renderHome() {
  const pending = state.reviews.filter((item) => ["pending_review", "changes_requested"].includes(item.status) && !item.superseded_at).length;
  const approved = state.reviews.filter((item) => item.status === "approved_for_manual_post" && !item.superseded_at).length;
  const activeJobs = state.jobs.filter((job) => ["queued", "processing"].includes(job.status)).length;
  const blocked = state.jobs.filter((job) => ["blocked", "error"].includes(job.status)).length;

  const actions = [];
  if (pending) {
    actions.push('<button class="action-card attention" data-open-review="true" type="button"><span class="action-icon">!</span><div><small>PERLU TINDAKAN</small><strong>' + pending + ' video menunggu review</strong><p>Periksa video, caption, dan pengecualian campaign.</p></div><span>→</span></button>');
  } else if (approved) {
    actions.push('<button class="action-card safe" data-open-review="true" type="button"><span class="action-icon">✓</span><div><small>LANGKAH BERIKUTNYA</small><strong>' + approved + ' video siap dikirim</strong><p>Buka review untuk mengirim video yang sudah disetujui.</p></div><span>→</span></button>');
  } else if (activeJobs) {
    actions.push('<button class="action-card safe" data-view="jobs" type="button"><span class="action-icon">◷</span><div><small>MESIN BEKERJA</small><strong>' + activeJobs + ' campaign sedang diproses</strong><p>Status akan diperbarui otomatis.</p></div><span>→</span></button>');
  } else {
    actions.push('<button class="action-card neutral" data-view="campaigns" type="button"><span class="action-icon">+</span><div><small>BERIKUTNYA</small><strong>Pilih campaign untuk dikerjakan</strong><p>Mesin akan menangani proses setelah Anda memulai.</p></div><span>→</span></button>');
  }
  $("#actionGrid").innerHTML = actions.join("");
  $("#actionGrid").querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
  $("#actionGrid").querySelector("[data-open-review]")?.addEventListener("click", () => showView("review"));

  $("#homeStats").innerHTML =
    statCard(activeJobs, "Sedang diproses", activeJobs ? "Mesin bekerja" : "Tidak ada proses") +
    statCard(pending, "Menunggu review", pending ? "Perlu tindakan Anda" : "Tidak ada antrean") +
    statCard(approved, "Sudah disetujui", approved ? "Siap dikirim" : "Belum ada") +
    statCard(blocked, "Perlu perhatian", blocked ? "Ada proses tertahan" : "Tidak ada masalah");

  const latestCampaigns = state.campaigns.slice(0, 6);
  $("#homeCampaigns").innerHTML = latestCampaigns.length ? latestCampaigns.map((campaign) =>
    '<div class="home-campaign-row"><div><strong>' + escapeHtml(campaign.title) + '</strong><span>' + escapeHtml(campaign.brand || "") + '</span></div><span class="readiness-dot ' + readinessClass(campaign.readiness_status) + '"></span><span class="muted">' + escapeHtml(campaign.readiness_label || "Belum dinilai") + '</span><button class="link-button" data-campaign="' + escapeHtml(campaign.id) + '" type="button">Buka</button></div>'
  ).join("") : '<div class="empty-inline">Campaign belum tersedia.</div>';
  document.querySelectorAll("[data-campaign]").forEach((button) => button.addEventListener("click", () => openCampaign(button.dataset.campaign)));
}

function statCard(value, title, note) {
  return '<div class="stat-card"><strong>' + escapeHtml(String(value)) + '</strong><span>' + escapeHtml(title) + '</span><small>' + escapeHtml(note) + '</small></div>';
}

function renderCampaigns() {
  const q = ($("#searchInput")?.value || "").toLowerCase();
  const platform = $("#platformFilter")?.value || "";
  const sort = $("#sortSelect")?.value || "readiness";
  let rows = state.campaigns.filter((c) => {
    const blob = [c.title, c.brand, c.category, c.readiness_label, c.readiness_reason].join(" ").toLowerCase();
    return (!q || blob.includes(q)) && (!platform || (c.platforms || []).includes(platform));
  });
  if (sort === "rate") rows.sort((a, b) => Number(b.rate_per_1k || 0) - Number(a.rate_per_1k || 0));
  else if (sort === "budget") rows.sort((a, b) => Number(b.budget_left || 0) - Number(a.budget_left || 0));
  else if (sort === "recency") rows.sort((a, b) => new Date(b.updated_at || 0) - new Date(a.updated_at || 0));
  else rows.sort((a, b) => (a.readiness_status === "siap" ? 0 : a.readiness_status === "ketat" ? 1 : 2) - (b.readiness_status === "siap" ? 0 : b.readiness_status === "ketat" ? 1 : 2));

  $("#campaignMeta").textContent = rows.length + " campaign";
  $("#campaignGrid").innerHTML = rows.map((c) => {
    const startable = canStart(c);
    return '<article class="campaign-card">' +
      '<div class="campaign-top"><span class="category-pill">' + escapeHtml(c.category || "clipping") + '</span><span class="readiness-badge ' + readinessClass(c.readiness_status) + '">' + escapeHtml(c.readiness_label || "Belum dinilai") + '</span></div>' +
      '<h3>' + escapeHtml(c.title) + '</h3><p class="campaign-brand">' + escapeHtml(c.brand || "") + '</p>' +
      '<p class="campaign-reason">' + escapeHtml(c.readiness_reason || "Belum ada ringkasan readiness.") + '</p>' +
      '<div class="campaign-platforms">' + (c.platforms || []).map((p) => '<span>' + escapeHtml(p) + '</span>').join("") + '</div>' +
      '<div class="campaign-footer"><div><small>Bayaran / 1K</small><strong>' + escapeHtml(money(c.rate_per_1k)) + '</strong></div><div><small>Sisa budget</small><strong>' + escapeHtml(money(c.budget_left)) + '</strong></div><button class="primary-button small" data-start-campaign="' + escapeHtml(c.id) + '" ' + (startable ? "" : "disabled") + '>' + (startable ? "Mulai" : "Belum siap") + ' <span>→</span></button></div>' +
      '</article>';
  }).join("") || '<div class="empty-work"><div class="empty-icon">⌕</div><h2>Campaign tidak ditemukan</h2><p>Coba ubah pencarian atau filter.</p></div>';

  document.querySelectorAll("[data-start-campaign]:not([disabled])").forEach((button) => button.addEventListener("click", () => openCampaign(button.dataset.startCampaign)));
}

function openCampaign(id) {
  const campaign = state.campaigns.find((item) => item.id === id);
  if (!campaign) return;
  const plan = parseObject(campaign.plan, {});
  const production = parseObject(plan.production, {});
  const source = parseObject(plan.source_of_truth, {});
  $("#modalContent").innerHTML =
    '<p class="eyebrow">CAMPAIGN</p><h2>' + escapeHtml(campaign.title) + '</h2><p class="modal-brand">' + escapeHtml(campaign.brand || "") + '</p>' +
    '<div class="campaign-modal-status ' + readinessClass(campaign.readiness_status) + '"><strong>' + escapeHtml(campaign.readiness_label || "Belum dinilai") + '</strong><span>' + escapeHtml(campaign.readiness_reason || "") + '</span></div>' +
    '<section class="modal-section"><div class="section-label">ATURAN UTAMA</div><div class="rule-list">' +
      ruleRow("Platform", (campaign.platforms || []).join(", ") || "-") +
      ruleRow("Format", production.aspect_ratio || "-") +
      ruleRow("Durasi", [production.min_duration_seconds, production.max_duration_seconds].filter((x) => x != null).join("–") || "-") +
      ruleRow("Subtitle", production.subtitle_delivery_profile || (production.subtitle_required ? "Wajib" : "Tidak disebutkan")) +
    '</div></section>' +
    '<section class="modal-section"><div class="section-label">SUMBER</div><p class="source-text">' + escapeHtml(String(source.docs_text || source.description || campaign.description || "").slice(0, 700)) + '</p></section>' +
    '<div class="modal-actions"><button class="secondary-button" data-close="true" type="button">Batal</button><button class="primary-button" id="startJob" type="button">Mulai proses <span>→</span></button></div>';
  $("#detailModal").classList.remove("hidden");
  document.querySelector("#modalContent [data-close]")?.addEventListener("click", closeDetailModal);
  $("#startJob").addEventListener("click", () => startJob(campaign));
}

function ruleRow(label, value) {
  return '<div class="rule-line"><span>' + escapeHtml(label) + '</span><strong>' + escapeHtml(value) + '</strong></div>';
}

async function startJob(campaign) {
  closeDetailModal();
  showView("jobs");
  const localJob = { id: "local-" + Date.now(), campaign_id: campaign.id, campaign_title: campaign.title, campaign_brand: campaign.brand, status: "queued", progress: 0, message: "Menyiapkan worker cloud…" };
  state.jobs.unshift(localJob);
  renderJobs();
  try {
    if (!cfg.DEMO_MODE) {
      const response = await api("/api/campaigns/" + encodeURIComponent(campaign.id) + "/jobs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ campaign_id: campaign.id }) });
      Object.assign(localJob, response.job);
      localJob.campaign_title = campaign.title;
      localJob.campaign_brand = campaign.brand;
      renderJobs();
      const trigger = await api("/api/jobs/" + encodeURIComponent(localJob.id) + "/run", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ campaign_id: campaign.id }) });
      if (!trigger.dispatched) throw new Error(trigger.message || trigger.error || "Worker belum siap");
      localJob.message = "Worker GitHub dipicu · menunggu runner";
      renderJobs();
      startPolling();
    } else {
      simulateJob(localJob);
    }
  } catch (error) {
    localJob.status = "error";
    localJob.message = "Gagal memulai workflow";
    localJob.error = error.message;
    renderJobs();
    showToast(friendlyError(error.message));
  }
}

function simulateJob(job) {
  const steps = [["Menyiapkan campaign", 8], ["Memeriksa bahan resmi", 32], ["Mencari potongan", 55], ["Membuat video", 75], ["Memeriksa hasil", 92], ["Video siap ditinjau", 100]];
  let index = 0;
  const tick = () => {
    if (index >= steps.length) {
      job.status = "review";
      job.message = "2 video siap ditinjau";
      state.reviews = [
        demoPreview(job, 1),
        demoPreview(job, 2)
      ];
      renderJobs();
      renderReviewInbox();
      renderHome();
      return;
    }
    job.status = index === 0 ? "queued" : index === steps.length - 1 ? "review" : "processing";
    job.message = steps[index][0];
    job.progress = steps[index][1];
    renderJobs();
    index += 1;
    setTimeout(tick, 700);
  };
  tick();
}

function demoPreview(job, rank) {
  return {
    id: job.id + "-preview-" + rank,
    job,
    rank,
    status: "pending_review",
    tier: rank === 1 ? "tier_1" : "tier_2",
    candidate_id: "demo-candidate-" + rank,
    source_asset_id: "demo-source-" + rank,
    caption_draft: "Caption demo campaign #" + rank,
    artifact_hash: "demo-artifact-" + rank,
    caption_revision_id: "demo-caption-" + rank,
    thumbnail_url: "",
    video_url: "",
    review_contract: {
      schema_version: 1,
      review_contract_id: "demo-review-" + rank,
      campaign_id: job.campaign_id,
      source_hash: "demo-source-hash",
      compliance_gate_id: "demo-gate",
      preview_id: job.id + "-preview-" + rank,
      artifact_hash: "demo-artifact-" + rank,
      caption_revision_id: "demo-caption-" + rank,
      decision_state: "ready_for_review",
      summary: { status: "siap_ditinjau", label: "Siap ditinjau", message: "Video siap diperiksa sebelum dipublikasikan." },
      checks: [
        { id: "campaign_compliance", status: "pass", label: "Aturan campaign", detail: "Semua pemeriksaan wajib lolos." },
        { id: "video_identity", status: "pass", label: "Identitas potongan", detail: "Potongan dan bahan sumber teridentifikasi." },
        { id: "validation", status: "pass", label: "Pemeriksaan video", detail: "Pemeriksaan teknis dasar lolos." }