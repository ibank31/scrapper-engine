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
- API dan UI progress sudah mendukung status `queued`, `processing`, `review`, dan `error`; workflow `.github/workflows/clipper-worker.yml` menjalankan pipeline pada GitHub runner dan mengunggah preview R2.
- Mode deployment disederhanakan: Pages Function memakai binding R2 langsung, GitHub Actions mengambil job `queued` lewat schedule 5 menit, sehingga pengguna tidak perlu memberikan GitHub token atau R2 S3 key.
- Auto-publish tetap disabled by design sampai pipeline render dan approval selesai.
- Dokumentasi handoff lengkap tersedia di `AGENTS.md` dan `docs/AGENT_HANDOFF.md`; dokumen tersebut adalah pintu masuk wajib untuk agent berikutnya.
- Material harvester sekarang menyimpan `RULES_SNAPSHOT.md`, membaca Google Docs publik, mengikuti sumber Drive/YouTube/direct media yang ditemukan dari materi campaign, dan memproses seluruh video source yang berhasil diambil.
- Output review dibatasi maksimal dua kandidat final per job. Kandidat dipilih lintas semua sumber setelah relevance gate, lalu diurutkan berdasarkan score terbaik.

## Next milestone

Berikutnya: deploy Pages Function dari branch main, seed satu campaign fixture, lalu uji alur antre → worker → preview dari URL Pages. Setelah itu, prioritas teknis berikutnya adalah visual relevance check untuk asset yang tidak menyebut brand di audio.

- Pages deployment filter diperluas ke seluruh repository agar Pages Function ikut ter-deploy.
- Campaign radar sekarang memakai priority score berbasis relevance, recency, sisa budget, kemudahan materials/rules, dan competition proxy yang diberi label sebagai estimasi (bukan jumlah kompetitor nyata).
- Status `new` diputuskan dari histori D1 (`first_seen_at`/`last_seen_at`), bukan dari file `campaigns.json`; migration tersedia di `cloudflare/migrations/0002_campaign_history.sql`.
- Trial campaign kedua berhasil pada ForgeGUI: detail → rules snapshot → Drive asset intake → faster-whisper → candidate selection → vertical render → relevance validation → review queue. Catatan lengkap ada di `docs/TRIAL_FORGEGUI.md`.
