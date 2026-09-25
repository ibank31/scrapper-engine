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