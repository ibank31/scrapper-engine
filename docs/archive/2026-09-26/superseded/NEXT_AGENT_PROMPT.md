# Prompt Handoff Agent Berikutnya

Kamu melanjutkan repository `ibank31/scrapper-engine` pada branch `main`. Baca terlebih dahulu:

- `STATUS.md`
- `docs/AGENT_HANDOFF.md`
- `docs/SEMANTIC_CLIPPING_LOCAL.md`
- `AGENTS.md`

Jangan mengulang riset vendor clipping berbayar. Scope proyek adalah local-first dan gratis. Campaign rules di `plan.json` serta `source_of_truth` adalah source of truth yang tidak boleh dioverride oleh model semantic.

## Kondisi saat ini

Commit quality terbaru: `3f4fd58`.

Pipeline saat ini:

```text
campaign selection
-> campaign plan/rules
-> official asset intake
-> faster-whisper word timestamps
-> sentence/turn segmentation
-> deterministic candidate windows
-> optional Qwen2.5-1.5B-Instruct-GGUF Q4_K_M semantic ranking
-> duration/relevance/rules gates
-> FFmpeg vertical render
-> validation
-> review queue/dashboard
-> manual approval and manual posting
```

Semantic model berjalan melalui `llama-cpp-python` pada CPU di GitHub Actions. Jika dependency/model tidak tersedia, deterministic fallback harus tetap berjalan. Jangan menjadikan model eksternal atau API berbayar sebagai dependency wajib.

Regression suite saat ini berjumlah 53 test dan harus tetap lulus.

## Tugas utama tahap berikutnya

Perkuat kualitas hasil video, bukan menambah efek visual atau security kecil:

1. Tambahkan optional silence/voice-activity signals ke candidate payload.
2. Tambahkan scene-change scoring menggunakan FFmpeg atau OpenCV secara ringan.
3. Tambahkan active-speaker heuristic untuk video dua pembicara. Jika confidence rendah, pilih framing lebih lebar dan jangan memotong speaker.
4. Tambahkan source-quality preflight: durasi, audio, speech density, resolusi, duplicate hash, dan kemungkinan bumper/sponsor-only.
5. Jalankan semantic model aktual Qwen di GitHub Actions pada satu fixture source yang cukup panjang; pastikan fallback tetap diuji terpisah.
6. Simpan signal tersebut di candidate/validation metadata agar terlihat di review queue.
7. Tambahkan minimal satu fixture regression untuk silence, scene change, dan dua speaker.

## Aturan implementasi

- Jangan mengubah timestamp berdasarkan tebakan semantic model. Timestamp harus tetap berasal dari Whisper/segment source.
- Jangan membiarkan model mengubah minimum/maksimum durasi atau prohibited campaign rules.
- Jangan memaksa asset 3–5 detik menjadi clip bagus.
- Jangan menggunakan API clipping SaaS atau API AI berbayar.
- Jangan mem-publish otomatis.
- Jangan menjalankan production job hanya untuk debugging jika fixture lokal sudah cukup.
- Jika perlu menjalankan GitHub Action, gunakan fixture/source yang cukup panjang dan catat alasan serta hasilnya.

## Acceptance criteria

Sebelum selesai:

```bash
python3 -m unittest discover -s tests -q
node --check web/app.js
node --check cloudflare/api.js
git diff --check
```

Semua harus lulus. Update `STATUS.md` dan `docs/AGENT_HANDOFF.md` dengan commit terbaru, jumlah test, batasan, dan next step. Jika dokumentasi lama menjadi superseded, pindahkan ke `docs/archive/YYYY-MM-DD/`, jangan dihapus.

Commit perubahan dengan pesan yang jelas dan push ke `origin/main`. Laporkan file yang berubah, hasil test, apakah Qwen aktual berhasil dijalankan, dan fallback apa yang dipakai.
