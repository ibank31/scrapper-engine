engine online

## Current milestone

- Campaign radar dan detail puller tersedia.
- Campaign rule compiler tersedia melalui `python run.py reward_plan ...`.
- Compiler mendeteksi asset URL, syarat 9:16, audio resmi, watermark, CTA, handle, minimum views, larangan, dan gate human review.
- Campaign asset intake tersedia melalui `python run.py reward_intake ...` dengan workspace terisolasi, manifest, checksum, retry, dan fallback manual.
- Worker video lokal tersedia: `transcribe`, `select_clips`, dan `render_clips`; transkripsi memakai faster-whisper dan render memakai FFmpeg.
- Validator clip tersedia melalui `validate_clips`; ia membedakan `pass`, `needs_review`, dan `fail` untuk pemeriksaan teknis serta tindakan manual campaign.
- Review queue tersedia melalui `review_queue`; ia membuat thumbnail, `INDEX.md`, `review.json`, caption draft, dan checklist manual per clip.
- Dashboard Cloudflare Pages awal tersedia di `web/`, dengan mode demo dan kontrak API Worker/D1/R2 di `cloudflare/`.
- Kebijakan gratis D1/R2 ditetapkan di `cloudflare/FREE_COST_POLICY.md`: raw video lokal, R2 hanya preview sementara, D1 hanya metadata, dan guard harian sebelum upload/query.
- Asumsi komputer lokal dicabut; untuk pengguna HP, compute video diarahkan ke GitHub Actions standard runner pada repository public. Detail ada di `cloudflare/PHONE_ONLY_ARCHITECTURE.md`.
- Auto-publish tetap disabled by design sampai pipeline render dan approval selesai.

## Next milestone

Berikutnya: buat workflow GitHub Actions yang menerima job dari dashboard, menjalankan pipeline Python, dan mengunggah preview ke R2.
