# Scrapper Engine — Agent Handoff

**Status dokumen:** diperbarui 21 September 2026  
**Repository:** `ibank31/scrapper-engine`  
**Branch produksi:** `main`  
**Tujuan sistem:** mengubah campaign Content Rewards yang relevan menjadi preview video short-form yang telah diperiksa rules dan siap direview manusia melalui dashboard mobile.

## 1. Ringkasan sistem

Scrapper Engine adalah pipeline campaign-aware clipping. Sistem tidak boleh diperlakukan sebagai downloader video generik. Setiap job harus dimulai dari campaign yang dipilih, mengambil detail campaign, mengompilasi rules menjadi production plan, mengambil material yang dicantumkan campaign, memilih momen yang berpotensi kuat, merender video vertical, memeriksa kepatuhan teknis dan relevansi campaign, lalu menaruh hanya hasil yang layak ke review queue.

> **Prinsip utama:** pengguna hanya melakukan review visual dan keputusan ACC. Mesin wajib menangani pembacaan rules, pengambilan material publik yang diizinkan, seleksi kandidat, transkripsi, crop, subtitle, validasi, dan pembuatan preview.

Publishing otomatis tetap dimatikan. Tombol ACC tidak boleh dianggap sebagai izin untuk bypass rules atau mengunggah tanpa pemeriksaan akhir platform.

## 2. Status implementasi saat ini

Fitur yang sudah ada di branch `main`:

- Radar campaign Content Rewards melalui `modules/reward_campaign/scrape.py`.
- Detail puller untuk payload Content Rewards terbaru melalui `modules/reward_campaign/pull_detail.py`.
- Compiler rules melalui `core/campaign_rules.py` dan command `reward_plan`.
- Workspace campaign terisolasi dengan manifest dan checksum.
- Rules snapshot dan asset harvester untuk Google Docs publik, Google Drive file/folder publik, YouTube yang tercantum dalam materi campaign, dan direct media URL.
- Transkripsi lokal/cloud dengan faster-whisper.
- Scoring kandidat highlight dan penghilangan overlap.
- Face-aware crop dengan smooth viewport expression jika OpenCV detector tersedia.
- Subtitle phrase-level dengan cleanup filler, duplicate word, batas kata, dan safe zone lower-middle.
- Semantic campaign relevance gate. Clip teknis yang salah konteks dapat diblokir.
- Validator teknis dan campaign-aware.
- Review queue dengan thumbnail, caption draft, checklist, manifest JSON, dan status blocked/pending review.
- Dashboard Cloudflare Pages untuk campaign, queue, preview, dan download.
- D1 untuk metadata/job dan R2 untuk preview sementara.
- GitHub Actions worker untuk pengguna yang hanya memiliki HP.
- Worker telah diubah untuk memproses seluruh video asset yang berhasil diambil, bukan hanya video pertama.

Commit penting:

| Commit | Fungsi |
|---|---|
| `01ee6be` | Rules normalization, Google Docs/Drive/material harvester, multi-source worker |
| `0b07d34` | Face-aware renderer, subtitle cleanup, semantic relevance gate |
| `7235f6b` | Approved campaign video asset intake |
| `915576c` | Live Content Rewards sync ke D1 |

## 3. Struktur repository

```text
run.py                              dispatcher satu pintu
README.md                           ringkasan penggunaan
STATUS.md                           milestone singkat
AGENTS.md                           instruksi pintu masuk untuk agent

core/
  campaign_rules.py                 compiler campaign detail menjadi plan
  captioning.py                     cleanup word/segment dan SRT cues
  clip_candidates.py                scoring kandidat highlight
  relevance.py                      relevance gate berbasis campaign topic
  visual_crop.py                    face-aware crop dan smooth keyframes
  fetch.py                          HTTP helper dengan retry/timeout
  job_workspace.py                  workspace, checksum, timestamp
  nextjs_flight.py                  decoder payload Next.js Flight
  textutil.py                       parser angka/money

modules/reward_campaign/
  scrape.py                         radar campaign publik
  pull_detail.py                    mengambil detail/rules/resources
  build_plan.py                     command compiler plan
  intake.py                         rules snapshot dan material harvester

modules/clipping/
  transcribe.py                     faster-whisper word timestamps
  select.py                         command kandidat highlight
  render.py                         FFmpeg vertical renderer
  validate.py                       technical + semantic validator
  review_queue.py                   preview review manifest

worker/
  run_job.py                         job runner GitHub Actions
  sync_campaigns.py                  sync radar live ke D1

cloudflare/
  api.js                             API Pages Function/Worker
  schema.sql                         schema D1
  wrangler.toml.example              contoh binding
  FREE_COST_POLICY.md                kebijakan zero-cost
  PHONE_ONLY_ARCHITECTURE.md         arsitektur phone-only
  README.md                          deployment Cloudflare

web/
  index.html                         shell dashboard
  app.js                             API calls, polling, preview, download
  styles.css                         UI dashboard mobile/desktop
  config.js                          API_BASE_URL dan DEMO_MODE

.github/workflows/clipper-worker.yml scheduled/manual worker

tests/                               unit/regression tests
```

## 4. Alur end-to-end yang benar

### 4.1 Radar dan campaign selection

`reward_campaign` membaca campaign publik dari Content Rewards dan menyimpan hasil normalisasi di `data/reward_campaign/campaigns.json`. Dashboard mengambil campaign tersebut melalui `/api/campaigns`.

Pengguna memilih campaign dari UI. API membuat job D1 berstatus `queued`. Worker tidak boleh merender tanpa `campaign_plan` yang berasal dari detail campaign terbaru.

### 4.2 Detail pull dan plan

Jika job belum memiliki plan, `worker/run_job.py` menjalankan:

```bash
python run.py reward_detail <campaign-id> --no-translate
python run.py reward_plan <path/to/detail.json>
```

Detail puller mengekstrak:

- identitas campaign;
- brand dan status;
- platform;
- deskripsi;
- payout;
- content requirements;
- reference materials;
- resource URL.

`reward_plan` membuat `detail.plan.json` dan plan Markdown. Plan tersebut adalah source of truth untuk seluruh proses berikutnya.

### 4.3 Rule compiler

`core/campaign_rules.py` tidak boleh diganti dengan asumsi global. Setiap campaign harus dikompilasi dari teks detailnya. Compiler saat ini mengenali, bila disebutkan:

- asset yang disediakan;
- link dan reference material;
- format vertical/9:16;
- official audio/sound;
- watermark resmi;
- larangan third-party watermark;
- handle/tag;
- CTA URL;
- minimum views;
- maximum payout;
- prohibited content;
- human review gate;
- topic terms untuk relevance.

Requirement string dan requirement object dinormalisasi ke `source_of_truth.normalized_requirements`. ID yang sudah dikenali antara lain `demographic_information`, `caption_hashtag`, `source_asset`, `watermark`, `official_audio`, `cta`, dan `custom`.

Jika struktur live Content Rewards berubah, perbaiki `pull_detail.py` dan test fixture terlebih dahulu. Jangan menambal hasil UI secara manual.

### 4.4 Material harvesting

`reward_intake` membuat workspace terisolasi dan melakukan hal berikut:

1. Menyalin plan ke workspace.
2. Membaca Google Docs publik dengan endpoint export text.
3. Menyimpan isi dokumen ke `materials/reference-XX.txt`.
4. Menemukan URL di dalam dokumen.
5. Memprioritaskan sumber Google Drive publik.
6. Mengunduh file/folder Drive menggunakan `gdown`.
7. Mengunduh URL direct media dengan HTTP helper.
8. Mengunduh YouTube yang memang tercantum sebagai sumber campaign menggunakan `yt-dlp`.
9. Menghitung ukuran dan SHA-256 setiap file.
10. Menulis `assets.json` dan `MANUAL_ASSETS.md`.
11. Menulis `materials/RULES_SNAPSHOT.md`.

Command manual:

```bash
python run.py reward_intake path/to/detail.plan.json --workspace data/jobs
```

`--no-download` hanya digunakan untuk dry run atau debugging. Worker cloud tidak boleh menambahkan flag tersebut karena job produksi harus mencoba mengambil material publik secara otomatis.

Access control tidak boleh dibypass. Jika file membutuhkan login, permission, CAPTCHA, atau navigasi privat, catat alasan di `MANUAL_ASSETS.md` dan jangan mengklaim asset berhasil diambil.

### 4.5 Pemilihan semua sumber video

Worker mengumpulkan seluruh file dengan extension video dari `workspace/assets/`. Untuk setiap sumber:

```text
transcribe source-N
→ select candidates
→ render setiap kandidat
→ copy hasil ke outputs/ dengan global rank
```

Candidate JSON gabungan disimpan di `workspace/transcripts/candidates.json`. Field penting kandidat adalah `start`, `end`, `duration`, `text`, `score`, `reasons`, `rank`, dan `source`.

Jangan kembali mengubah worker menjadi `sources[0]`. Campaign dapat memiliki beberapa sumber approved dan peluang terbaik bisa berada di file kedua atau ketiga.

### 4.6 Transkripsi

`modules/clipping/transcribe.py` menggunakan faster-whisper dengan:

- `word_timestamps=True`;
- VAD filter;
- `condition_on_previous_text=False`;
- CPU `int8` secara default;
- model default `small`.

File hasil:

```text
transcript.json
transcript.srt
```

Jika model perlu diubah karena waktu/CPU:

```bash
CLIPPER_WHISPER_MODEL=base
```

Model lebih kecil lebih cepat tetapi dapat menurunkan akurasi. Jangan mengganti ke API berbayar tanpa keputusan arsitektur yang jelas.

### 4.7 Candidate selection

`core/clip_candidates.py` memberi skor berdasarkan hook, signal words, pertanyaan, angka konkret, dan kepadatan spoken content. Scoring ini adalah ranking awal, bukan keputusan final.

Kandidat wajib melewati relevance gate. Candidate scoring tidak boleh meloloskan clip hanya karena menarik atau memiliki angka jika topiknya tidak berhubungan dengan campaign.

### 4.8 Renderer

`modules/clipping/render.py` menghasilkan H.264/AAC MP4 1080×1920.

Perilaku renderer:

- face-aware crop bila detector tersedia;
- fallback crop tengah bila detector tidak tersedia;
- smooth viewport expression;
- framing 9:16;
- subtitle phrase-level;
- maksimal sekitar lima kata per cue dan maksimal dua baris secara visual;
- filler dan pengulangan kata berurutan dihapus;
- subtitle lower-middle dengan margin safe zone;
- putih dengan outline/drop shadow hitam;
- audio dipertahankan;
- watermark campaign dapat ditambahkan jika plan mewajibkannya.

OpenCV dipin pada `>=4.10,<5`. Jika environment memakai versi 5 yang tidak menyediakan API detector yang dipakai, face tracking akan fallback. Periksa ini jika kualitas crop mendadak kembali statis.

### 4.9 Validation

`modules/clipping/validate.py` menjalankan:

- ffprobe;
- resolusi 1080×1920;
- H.264;
- frame rate 23–60 fps;
- AAC audio;
- watermark/manual rule checks;
- candidate relevance check.

Status validator:

| Status | Arti |
|---|---|
| `pass` | Tidak ada issue teknis dan tidak ada manual campaign check tambahan |
| `needs_review` | Teknis aman, tetapi ada rule yang membutuhkan verifikasi platform/visual |
| `fail` | Ada issue teknis atau relevance failure |
| `blocked` | Status review queue untuk clip yang fail |

Video yang membahas topik yang tidak cocok harus berisi issue seperti:

```text
campaign relevance failed: candidate transcript does not match campaign topic signals
```

Video Boxabl yang hanya membahas Starbase/Starship adalah regression case dan harus tetap diblokir.

### 4.10 Review queue dan UI

`review_queue.py` membuat:

- video copy;
- thumbnail;
- `review.json`;
- `INDEX.md`;
- caption draft;
- checklist;
- validation payload per clip.

Worker hanya mengupload preview yang tidak `blocked`. UI melakukan polling status job dan menampilkan:

```text
queued → processing → review
```

Jika terjadi error, UI menampilkan message dari API. Pengguna idealnya hanya melihat video, membaca alasan validasi, dan menekan ACC atau menolak.

## 5. Kontrak workspace

Contoh workspace:

```text
data/jobs/<job-id>/
  plan.json
  assets.json
  MANUAL_ASSETS.md
  materials/
    RULES_SNAPSHOT.md
    reference-01.txt
  assets/
    source-01.mp4
    source-02.mp4
  transcripts/
    source-01/
      transcript.json
      transcript.srt
      candidates.json
      candidate-001.json
      render-001/clip-001.mp4
    candidates.json
  outputs/
    clip-001.mp4
    clip-002.mp4
  validation.json
  validation.md
  review/
    review.json
    INDEX.md
    clip-001.mp4
    clip-001.jpg
    clip-001.md
```

`assets.json` adalah provenance manifest. Jangan menghapus URL, checksum, atau source type dari manifest karena data tersebut diperlukan untuk audit campaign.

## 6. API dashboard

Endpoint yang digunakan UI dan worker:

| Endpoint | Method | Pengguna | Fungsi |
|---|---|---|---|
| `/api/campaigns` | GET | UI/worker | Daftar campaign |
| `/api/campaigns/:id` | GET | UI | Detail campaign dan plan |
| `/api/campaigns/:id/jobs` | POST | UI | Membuat job queued |
| `/api/jobs` | GET | worker | Mencari job queued |
| `/api/jobs/:id` | GET | UI/worker | Status job |
| `/api/jobs/:id` | PATCH | worker | Update status/progress |
| `/api/jobs/:id/upload` | POST | worker | Upload preview melalui Pages Function ke R2 |
| `/api/jobs/:id/previews` | POST | worker | Menyimpan metadata preview |
| `/api/jobs/:id/previews` | GET | UI | Mengambil preview review |

Worker memakai header `x-worker-token`. Token tidak boleh dimasukkan ke source, workflow YAML, atau UI.

## 7. Cloudflare dan GitHub Actions

Cloudflare Pages menampung UI dan Pages Function. D1 menyimpan metadata kecil. R2 menyimpan preview sementara. FFmpeg dan faster-whisper berjalan di GitHub Actions standard runner, bukan di Pages/Workers.

Workflow `.github/workflows/clipper-worker.yml`:

- schedule setiap lima menit;
- dapat dipicu manual dengan `workflow_dispatch`;
- mengambil job `queued`;
- menjalankan sync campaign;
- menjalankan `worker/run_job.py`;
- timeout saat ini 90 menit;
- membutuhkan `CLIPPER_API_URL` dan `CLIPPER_WORKER_TOKEN` sebagai repository secrets.

Jangan memasukkan GitHub PAT atau R2 S3 key ke Cloudflare API. Arsitektur sekarang memakai queue D1 dan upload melalui Pages Function sehingga user tidak perlu memberikan credential tambahan untuk setiap job.

Baca dokumen berikut sebelum mengubah deployment:

- `cloudflare/README.md` untuk setup dan kontrak API.
- `cloudflare/FREE_COST_POLICY.md` untuk retention dan guardrail biaya.
- `cloudflare/PHONE_ONLY_ARCHITECTURE.md` untuk asumsi pengguna HP.
- `cloudflare/schema.sql` sebelum mengubah tabel.

## 8. Setup developer

Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
```

Termux membutuhkan padanan package FFmpeg dan Python yang sesuai. GPU tidak diasumsikan.

Perintah dasar:

```bash
python run.py reward_campaign
python run.py reward_detail <campaign-id> --no-translate
python run.py reward_plan path/to/detail.json
python run.py reward_intake path/to/detail.plan.json --workspace data/jobs
python run.py transcribe path/to/source.mp4 --model small
python run.py select_clips path/to/transcript.json --limit 10
python run.py render_clips source.mp4 candidates.json --transcript transcript.json --plan plan.json --out-dir outputs
python run.py validate_clips --plan plan.json --candidates candidates.json --glob 'outputs/*.mp4' --out validation.json
python run.py review_queue --plan plan.json --candidates candidates.json --validation validation.json --rendered-dir outputs --out-dir review
```

## 9. Testing rules

Sebelum commit:

```bash
python3 -m py_compile core/*.py modules/*/*.py worker/*.py
python3 -m unittest discover -s tests -v
python3 -m compileall -q core modules worker
python3 -m pip check
git diff --check
git status --short
```

Regression cases wajib dipertahankan:

1. Requirement string dan object menghasilkan normalized requirement yang benar.
2. Google Docs non-URL tidak menimbulkan network failure.
3. Subtitle menghapus filler dan duplicate word.
4. Subtitle terbagi menjadi cue pendek.
5. Crop expression memiliki escaping yang valid.
6. Topic Boxabl yang relevan lolos.
7. Topic Starship/Starbase yang tidak relevan diblokir untuk Boxabl.
8. Output render menghasilkan 1080×1920 H.264/AAC.
9. Asset manifest menyimpan checksum.
10. Worker memproses lebih dari satu source video.

## 10. Troubleshooting

### Job tetap `queued`

Periksa apakah GitHub Actions aktif dan workflow schedule berjalan. Schedule dapat terlambat. Untuk smoke test, jalankan workflow manual dari GitHub Actions dengan `job_id` dan `campaign_id` yang tepat.

### Job `error` dengan “tidak ada video asset langsung”

Buka `MANUAL_ASSETS.md`, `assets.json`, dan `materials/reference-*.txt`. Penyebab umum adalah Google Doc tidak publik, Drive file memerlukan login, link hanya menunjuk halaman bukan file, atau campaign tidak mencantumkan media yang dapat diunduh.

### Subtitle hilang

Periksa apakah transcript memiliki `segments[].words`. Renderer memiliki fallback dari segment text, tetapi transcript kosong tetap menghasilkan SRT kosong. Periksa path `--transcript` dan file `transcript.json`.

### Crop kembali ke tengah

Periksa versi OpenCV dan apakah `cv2.CascadeClassifier` tersedia. Jika tidak, renderer memakai fallback crop. Jangan menganggap fallback setara dengan face tracking.

### Clip salah campaign masih lolos

Periksa `source_of_truth.description`, topic terms di `core/relevance.py`, isi `candidates.json`, dan hasil `validation.json`. Tambahkan regression test untuk campaign tersebut. Jangan hanya menambahkan keyword tanpa memahami apakah term terlalu umum.

### Semua kandidat diblokir

Ini dapat menjadi perilaku benar. Buka alasan relevance di `validation.json`. Jika asset visual relevan tetapi tidak menyebut brand dalam audio, sistem mungkin memerlukan visual relevance model atau aturan asset-level yang lebih kuat.

## 11. Batasan yang diketahui

Semantic relevance saat ini terutama berbasis transcript dan topic signals. Sistem belum menjadi vision-language judge penuh untuk semua campaign. Asset yang hanya menampilkan produk tanpa menyebut brand dapat ditandai uncertain atau gagal relevance. Perbaikan berikutnya yang paling bernilai adalah visual relevance check per sampled frame dengan model lokal/free, disertai threshold konservatif dan alasan yang dapat diaudit.

Platform-native requirements seperti pemasangan official sound di TikTok/Instagram, tag native, bio CTA, dan submit final tetap tidak dapat dibuktikan seluruhnya oleh file MP4. Sistem harus menampilkan checklist yang jelas, bukan menyatakan semua gate pass secara palsu.

Auto-publish sengaja disabled. Jangan mengaktifkannya hanya untuk mengurangi satu langkah review.

## 12. Aturan untuk agent berikutnya

Agent yang melanjutkan repository ini harus:

1. Membaca dokumen ini dan `STATUS.md` sebelum mengubah pipeline.
2. Mempertahankan provenance asset dan snapshot rules.
3. Tidak menghapus human review gate.
4. Tidak memasukkan secret ke source, fixture, log, atau dokumentasi.
5. Tidak menganggap campaign Boxabl sebagai satu-satunya schema. Rules harus berasal dari campaign.
6. Tidak memproses hanya sumber video pertama.
7. Menambah regression test untuk setiap perubahan parser, validator, renderer, atau worker.
8. Menjalankan test dan compile check sebelum push.
9. Memisahkan technical pass dari campaign relevance pass.
10. Memblokir kandidat yang tidak relevan daripada mengirimkannya ke pengguna sebagai preview siap ACC.

## Referensi

[1]: https://github.com/ibank31/scrapper-engine "Scrapper Engine repository"
[2]: https://docs.whop.com/memberships-and-access/third-party-apps/content-rewards "Whop Content Rewards documentation"
[3]: https://developers.cloudflare.com/pages/ "Cloudflare Pages documentation"
[4]: https://developers.cloudflare.com/d1/ "Cloudflare D1 documentation"
[5]: https://developers.cloudflare.com/r2/ "Cloudflare R2 documentation"
[6]: https://docs.github.com/en/actions "GitHub Actions documentation"
[7]: https://ffmpeg.org/documentation.html "FFmpeg documentation"
[8]: https://github.com/SYSTRAN/faster-whisper "faster-whisper repository"
