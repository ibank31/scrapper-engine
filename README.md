# Scrapper Engine

Engine scraping pribadi (ibank31). Dua misi:
1. **Data affiliate** - foto/spek produk dari sumber resmi untuk situs affiliate (sortirin.com).
2. **Reward campaigns** - radar + detail campaign contentrewards.com untuk project clipping.

> Repo ini berisi data hasil scrape dan strategi pribadi. **Jaga tetap PRIVATE.**

## Handoff untuk agent

Agent atau maintainer baru wajib membaca [`AGENTS.md`](AGENTS.md), [`docs/AGENT_HANDOFF.md`](docs/AGENT_HANDOFF.md), dan [`STATUS.md`](STATUS.md) sebelum mengubah pipeline. Manual handoff menjelaskan arsitektur aktual, kontrak workspace/API, alur rules dan material harvesting, worker multi-source, pengujian, batasan, serta troubleshooting.

## Struktur

```
core/                    helper bersama
  fetch.py               HTTP (UA, retry, timeout)
  nextjs_flight.py       decoder payload Next.js Flight
  pagemeta.py            og:image / twitter:image / deteksi gambar langsung
  imgconv.py             konversi webp (cwebp/dwebp atau ImageMagick)
  textutil.py            parsing uang dll
modules/
  reward_campaign/       scrape.py (radar) + pull_detail.py (detail per campaign)
  product_image/         foto hero produk dari halaman resmi (manifest-driven)
manifests/               input batch untuk product_image
data/                    output scrape (reward_campaign)
run.py                   dispatcher: python run.py <modul> [args]
```

## Setup (Termux)

```
pip install requests
pkg install -y libwebp          # untuk product_image
pip install deep-translator     # opsional, terjemahan brief campaign
pip install -r requirements.txt # requests + faster-whisper untuk worker AI lokal
sudo apt install ffmpeg         # Ubuntu/Debian
```

## Pemakaian

```
python run.py reward_campaign
python run.py reward_detail <campaign_id>
python run.py reward_plan <detail.json atau HTML/Flight detail>
python run.py product_image --manifest manifests/sortirin_photos.json --repo ~/sortirin
```

## Campaign-aware clipping

`reward_plan` membaca `campaign`, `staticDetails.requirements`, `staticDetails.resources`, dan teks deskripsi campaign. Outputnya adalah `*.plan.json` dan `*.PLAN.md` yang berisi material wajib, URL asset, rasio video, audio resmi, watermark, CTA, handle, batas views/payout, larangan, dan gate validasi. Plan ini menjadi **source of truth** sebelum pipeline clipping merender atau mengantrekan video.

Publishing sengaja dikunci (`publish_allowed: false`) sampai semua gate wajib lolos dan ada human review. URL Dropbox/Google Drive/Frame.io/YouTube/Vimeo yang tertanam dalam aturan akan dicatat sebagai kandidat asset; downloader berikutnya harus mengunduhnya ke job workspace tanpa mengabaikan aturan campaign.

Contoh dari detail lokal:

```bash
python run.py reward_plan path/to/detail.json
python run.py reward_intake path/to/detail.plan.json --workspace data/jobs
python run.py transcribe data/jobs/<campaign-id>/assets/source.mp4 --model small
python run.py select_clips data/jobs/<campaign-id>/assets/transcript/transcript.json
python run.py render_clips data/jobs/<campaign-id>/assets/source.mp4 data/jobs/<campaign-id>/assets/transcript/candidates.json --transcript data/jobs/<campaign-id>/assets/transcript/transcript.json
python run.py validate_clips --plan data/jobs/<campaign-id>/plan.json --glob 'data/jobs/<campaign-id>/outputs/*.mp4'
python run.py review_queue --plan data/jobs/<campaign-id>/plan.json --candidates data/jobs/<campaign-id>/assets/transcript/candidates.json --validation validation.json --rendered-dir data/jobs/<campaign-id>/outputs --out-dir data/jobs/<campaign-id>/review
python -m unittest discover -s tests -v
```

`reward_intake` membuat workspace campaign dengan `plan.json`, `assets.json`, folder `assets/`, `materials/`, `outputs/`, dan `review/`. Mesin menyimpan `RULES_SNAPSHOT.md`, membaca Google Docs publik yang dicantumkan campaign, mengikuti link Drive/YouTube/direct media yang memang ditemukan di materi campaign, lalu mengunduh asset publik dengan retry dan checksum. Link yang membutuhkan login atau tidak dapat dibaca tanpa bypass tetap dicatat di `MANUAL_ASSETS.md`; mesin tidak menembus kontrol akses.

`review_queue` menyalin clip ke folder review, membuat thumbnail, membuat `INDEX.md`, `review.json`, caption draft, dan checklist manual per clip. Clip yang gagal validator diberi status `blocked`; clip lain tetap berstatus `pending_review` sampai Anda memeriksanya.

Worker produksi menggabungkan kandidat dari seluruh video asset campaign, menjalankan relevance gate, lalu hanya merender dan mengunggah **maksimal dua kandidat terbaik** per job. Perintah `select_clips` juga memakai default limit dua; gunakan `--limit` lebih besar hanya untuk diagnostik internal.

## Campaign priority radar

Campaign radar mengurutkan prioritas dengan komponen relevance, recency, sisa budget, kemudahan bahan/rules, dan **competition proxy**. Competition proxy adalah estimasi dari payout, sisa budget, dan lebar platform; sumber publik tidak menyediakan jumlah kompetitor nyata. Status `new` bukan lagi dihitung dari `campaigns.json`: D1 menyimpan `first_seen_at` dan `last_seen_at`, sehingga run terjadwal tetap konsisten.

## Cloudflare Pages dashboard

Dashboard awal tersedia di `web/`. Ia memiliki menu campaign radar, filter, detail campaign, tombol mulai otomatis, processing queue, review preview, dan download. Mode awal adalah demo agar UI dapat diuji tanpa kredensial. Arsitektur produksi memakai Cloudflare Pages untuk UI, Worker untuk API kecil, D1 untuk metadata, dan R2 untuk MP4/thumbnail. FFmpeg dan faster-whisper tetap berjalan pada worker Python lokal karena proses video berat tidak cocok dijalankan di Pages/Workers Free. Lihat `cloudflare/README.md` sebelum deployment.

## Prinsip sumber (product_image)

Urutan kandidat di manifest = urutan prioritas:
1. Situs resmi brand (regional Indonesia > global).
2. Toko/distributor resmi (contoh: jblstore.co.id, anker.com.bd).
3. Marketplace = pilihan terakhir. Tandai jelas di `sumber`; risiko hak pakai lebih tinggi, wajib cek manual.

**Bot-wall (Akamai dll) tidak dilawan.** Kalau kena 403: ganti sumber di manifest, jangan tambah teknik bypass. Kasus nyata: www.jbl.com 403 -> id.jbl.com + jblstore.co.id sukses.

## Gemini campaign intelligence

`campaign-sync-ai` adalah jalur scraping harian yang memakai Gemini API melalui `GEMINI_API_KEY`. Detail setiap campaign aktif diambil, aturan dan material disnapshot, AI mengubah rules tidak terstruktur menjadi `ai_rules`, lalu plan dikompilasi dan disimpan ke D1. Kunci hanya dipasang sebagai environment variable GitHub Actions dan tidak ditulis ke source atau log.

AI hanya dijalankan untuk campaign baru atau `rules_hash` yang berubah. Hasil AI berisi campaign-fit, sumber asset, platform, aspect ratio, durasi, subtitle, watermark, audio, CTA, handle/hashtag, disclosure, topic terms, allowed/prohibited content, posting/account rules, evidence, ambiguities, dan confidence.

Campaign yang hasil AI-nya belum cukup yakin tidak boleh masuk produksi otomatis. Worker akan menghentikan job tersebut sebelum asset intake sehingga mesin tidak mengarang aturan campaign.

Workflow tidak mengunduh model lokal; runner hanya memasang dependency scraper lalu memanggil Gemini dengan output JSON terstruktur.
