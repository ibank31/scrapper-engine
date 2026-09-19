engine online

## Current milestone

- Campaign radar dan detail puller tersedia.
- Campaign rule compiler tersedia melalui `python run.py reward_plan ...`.
- Compiler mendeteksi asset URL, syarat 9:16, audio resmi, watermark, CTA, handle, minimum views, larangan, dan gate human review.
- Campaign asset intake tersedia melalui `python run.py reward_intake ...` dengan workspace terisolasi, manifest, checksum, retry, dan fallback manual.
- Worker video lokal tersedia: `transcribe`, `select_clips`, dan `render_clips`; transkripsi memakai faster-whisper dan render memakai FFmpeg.
- Validator clip tersedia melalui `validate_clips`; ia membedakan `pass`, `needs_review`, dan `fail` untuk pemeriksaan teknis serta tindakan manual campaign.
- Auto-publish tetap disabled by design sampai pipeline render dan approval selesai.

## Next milestone

Berikutnya: compliance validator, thumbnail/review queue, serta scheduler worker lokal.
