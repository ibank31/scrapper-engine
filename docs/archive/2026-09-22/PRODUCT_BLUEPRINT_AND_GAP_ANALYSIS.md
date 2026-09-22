# Blueprint Mesin Clipping: Target Produk dan Gap terhadap Implementasi Saat Ini

## Kesimpulan eksekutif

Tujuan mesin sebaiknya didefinisikan sebagai **studio clipping campaign-aware dengan human approval**, bukan sekadar script pemotong video. Pengguna memilih campaign yang sudah dianalisis AI, menekan **Mulai clipping**, lalu mesin mengambil bahan yang memang diberikan campaign, memproses seluruh sumber yang relevan, menghasilkan beberapa kandidat terbaik, merender preview vertical berkualitas tinggi, menjalankan pemeriksaan kepatuhan, dan menampilkan hasil untuk di-ACC. Setelah itu pengguna tetap mengunduh dan mengunggah secara manual.

Fondasi untuk alur tersebut sudah tersedia. Repository saat ini memiliki radar campaign, analisis AI, compiler rules, intake Google Drive dan YouTube, transkripsi lokal, pemilihan kandidat, crop berbasis wajah, subtitle, render FFmpeg, validator, review queue, dashboard job, dan upload preview ke R2. Workflow GitHub Actions juga sudah terbukti hijau setelah tiga secret Google Drive dikonfigurasi.

Namun, mesin **belum sepenuhnya menjadi produk yang Anda gambarkan**. Gap terbesar bukan lagi pengambilan media dasar. Gap terbesar adalah penyelesaian dashboard production, transparansi hasil per tahap, quality-control visual yang lebih kuat, kontrol jumlah dan kualitas kandidat, serta mekanisme review yang menyimpan keputusan ACC dan checklist posting. Status mesin saat ini lebih tepat disebut **pipeline preview yang sudah berjalan**, bukan studio clipping final yang sudah matang.

## Definisi produk yang disarankan

> **Input:** satu campaign clipping yang sudah dipilih dan dianalisis AI.
>
> **Output:** maksimal beberapa preview clip yang sudah dirender, diberi subtitle, diframing vertical, diperiksa terhadap rules campaign, dan dilengkapi alasan pemilihan, laporan validasi, caption draft, serta checklist manual.
>
> **Keputusan akhir:** pengguna meninjau preview, menyetujui atau menolak setiap kandidat, lalu mengunduh dan mengunggah secara manual.

Keputusan manual pada tahap posting harus dipertahankan. Audio resmi dari TikTok atau Instagram sering harus ditambahkan melalui library platform. Selain itu, caption, disclosure, akun tujuan, handle, dan pengaturan publikasi dapat berbeda antar-platform. Mesin boleh menyiapkan semuanya, tetapi tidak boleh menganggap file MP4 saja sebagai bukti bahwa seluruh syarat posting sudah terpenuhi.

## Alur produk end-to-end yang dimaksimalkan

### 1. Campaign radar dan pemilihan campaign

Dashboard menampilkan hanya campaign yang relevan untuk clipping atau campaign yang belum cukup terklasifikasi tetapi memiliki material yang dapat diproses. Setiap kartu campaign harus memperlihatkan judul, brand, platform, payout, budget tersisa, status kesiapan, status analisis AI, dan alasan mengapa campaign dapat atau belum dapat dikerjakan.

Pengguna membuka detail campaign sebelum memulai. Detail tersebut perlu menampilkan material resmi yang ditemukan, rasio, durasi, audio, watermark, CTA, handle, larangan, platform target, dan ambiguitas. Dengan demikian tombol **Mulai clipping** tidak menjadi tombol hitam yang menjalankan proses tanpa konteks.

### 2. Preflight sebelum job dibuat

Sebelum job masuk antrean, mesin menjalankan pemeriksaan ringan:

- campaign berjenis clipping atau memiliki sumber yang dapat diproses;
- analisis AI berstatus `pass` dengan confidence di atas ambang;
- tidak ada ambiguitas kritis;
- sumber Drive, YouTube, atau direct media memiliki URL;
- akun OAuth memiliki konfigurasi yang dibutuhkan untuk Drive;
- target platform dan aturan minimum sudah dapat dibaca;
- tidak ada job aktif ganda untuk campaign yang sama.

Jika pemeriksaan gagal, dashboard harus menampilkan alasan yang bisa ditindaklanjuti. Contohnya, **Akun Google belum memiliki akses ke folder**, bukan pesan umum seperti “pipeline gagal”.

### 3. Intake semua bahan resmi

Worker membuat workspace terisolasi untuk job. Ia menyimpan snapshot rules, plan, manifest asset, checksum, metadata sumber, dan daftar material manual.

Untuk Google Drive, mesin memakai OAuth `drive.readonly` dan hanya mengambil file yang dapat dibaca serta diunduh oleh akun yang diotorisasi. Untuk YouTube, mesin memakai `yt-dlp` pada URL yang memang tercantum sebagai material campaign. Untuk direct media, mesin mengunduh dengan timeout dan retry. Sumber yang gagal tidak boleh diam-diam hilang; sumber tersebut masuk ke `MANUAL_ASSETS.md` dan dashboard menampilkan tindakan manual yang diperlukan.

Intake perlu membedakan tiga keadaan:

1. **Downloaded:** file berhasil disimpan dan checksum tersedia.
2. **Needs manual download:** URL tersedia tetapi membutuhkan login, permission, CAPTCHA, atau tindakan pengguna.
3. **Failed:** mesin mencoba mengambil file tetapi sumber mengembalikan error teknis.

### 4. Analisis video dan pembentukan kandidat

Setiap video dianalisis dengan `ffprobe` dan transkripsi word-level. Mesin menyimpan transkrip JSON, SRT, durasi, dan metadata sumber. Candidate scorer kemudian mencari segmen yang memiliki hook kuat, konteks cukup, kalimat lengkap, payoff, dan relevansi terhadap campaign.

Pemilihan kandidat tidak cukup berdasarkan skor transkrip. Versi yang lebih matang harus menggabungkan:

- kualitas hook dan kelengkapan kalimat;
- relevansi terhadap brand, topic terms, dan prohibited terms;
- durasi yang sesuai campaign;
- kejelasan audio dan tingkat noise;
- perubahan scene dan ritme visual;
- keberadaan wajah atau objek utama;
- penalti untuk sponsor read, dead air, kalimat terpotong, dan overlap;
- diversitas antar-kandidat agar dua preview tidak berasal dari momen yang hampir sama.

Mesin sebaiknya membuat lebih banyak kandidat internal daripada yang ditampilkan. Misalnya, 10 kandidat per sumber dapat diranking, lalu hanya 3–5 kandidat final yang dirender untuk review. Saat ini output final dibatasi maksimal dua kandidat. Batas dua kandidat baik untuk biaya dan kecepatan awal, tetapi terlalu sempit untuk campaign dengan banyak sumber atau kebutuhan pilihan kreatif.

### 5. Render preview berkualitas tinggi

Setiap kandidat final diproses melalui preset yang ditentukan campaign dan profil kualitas. Render ideal terdiri atas tahapan berikut:

1. mempertahankan framing jika sumber sudah vertical;
2. mendeteksi wajah dan menjaga wajah utama tetap berada di safe area;
3. menggunakan object-aware atau speaker-aware framing jika deteksi wajah tidak cukup;
4. menggunakan center crop, blurred background, atau split layout sebagai fallback;
5. menghasilkan subtitle yang terbaca pada layar ponsel;
6. menjaga subtitle tidak menutupi wajah, watermark, atau area UI penting;
7. menambahkan watermark resmi hanya bila diwajibkan;
8. menjaga audio sumber dan menandai kebutuhan official platform audio;
9. menghasilkan MP4 H.264/AAC dengan resolusi, frame rate, dan durasi yang sesuai plan.

Kualitas preview perlu memiliki dua profil. **Fast preview** dipakai untuk validasi awal dan antrean murah. **Final preview** memakai CRF dan preset yang lebih baik setelah kandidat dipilih. Ini menjaga GitHub Actions tetap cepat tanpa mengorbankan kualitas file yang akan diunggah manual.

### 6. Validasi teknis dan campaign compliance

Validator harus menghasilkan tiga status yang mudah dipahami:

- **PASS:** semua pemeriksaan yang dapat diukur mesin lulus.
- **NEEDS REVIEW:** tidak ada kegagalan teknis, tetapi ada hal yang hanya dapat dipastikan manusia.
- **FAIL:** ada pelanggaran terukur atau output tidak dapat dipakai.

Pemeriksaan teknis meliputi resolusi, rasio, codec, frame rate, audio, durasi, ukuran file, dan keberadaan subtitle jika diwajibkan. Pemeriksaan campaign meliputi sumber resmi, watermark, handle, CTA, kata wajib, kata terlarang, platform, audio resmi, dan kesesuaian topik.

Pemeriksaan visual sebaiknya menambahkan contact sheet dan frame sampel. Validator tidak harus langsung memakai model vision berbayar. Pada tahap awal, frame sampel dapat dipakai untuk memeriksa apakah wajah terpotong, subtitle bertabrakan, watermark hilang, atau objek utama keluar dari area aman. Hasil yang tidak dapat dipastikan mesin harus ditandai `needs_review`, bukan dipaksa menjadi `pass`.

### 7. Review, ACC, dan paket posting manual

Halaman review harus menjadi pusat keputusan pengguna. Setiap kandidat menampilkan video, thumbnail, sumber, timestamp, skor, alasan pemilihan, status validator, warning visual, caption draft, dan checklist.

Tindakan minimum per kandidat adalah:

- **ACC untuk upload manual**;
- **tolak** dengan alasan;
- **minta render ulang** dengan opsi crop, subtitle, atau durasi;
- **download MP4**;
- **download paket posting** yang berisi caption, hashtag, disclosure, SRT, dan checklist platform.

Status `approved_for_manual_post` harus disimpan terpisah dari status `review`. `review` berarti preview tersedia. `approved_for_manual_post` berarti pengguna sudah memeriksa preview dan siap mengunggahnya. Status ini bukan persetujuan dari platform atau Content Rewards.

### 8. Upload manual dan pencatatan submission

Setelah mengunggah secara manual, pengguna dapat memasukkan URL posting, platform, waktu posting, dan catatan. Mesin menyimpan data tersebut untuk audit dan pelacakan campaign. Tahap ini tidak perlu otomatis pada MVP, tetapi struktur datanya perlu disiapkan agar alur tidak berhenti setelah download.

## Perbandingan target dengan status mesin saat ini

| Area | Target produk | Status saat ini | Penilaian |
|---|---|---|---|
| Campaign radar | Memilih campaign yang layak clipping | Radar, ranking, readiness, dan filter clipping sudah ada | **Sudah tersedia** |
| Analisis AI | Rules menjadi plan terstruktur dan memblokir ambiguitas kritis | Gemini sync, `ai_rules`, confidence gate, dan `rules_hash` sudah ada | **Sudah tersedia, perlu observability** |
| Tombol Mulai clipping | Satu klik dari campaign terpilih ke job | Dashboard membuat job dan memicu worker pada mode production | **Tersedia secara kode; deployment UI belum selesai** |
| Google Drive | Mengambil bahan resmi dengan OAuth read-only | Drive API OAuth sudah terhubung dan workflow hijau | **Sudah tersedia dan teruji secara operasional** |
| YouTube | Mengambil URL YouTube yang ditemukan pada material | `yt-dlp` tersedia, maksimal 300 detik dan 800 MB per sumber | **Tersedia dengan batasan** |
| Direct media | Mengambil MP4/audio langsung dengan retry | Downloader direct media tersedia | **Tersedia** |
| Semua sumber | Memproses seluruh sumber yang berhasil diambil | Intake mengumpulkan sumber, worker memilih maksimal `CLIPPER_MAX_VIDEO_SOURCES` | **Belum penuh** |
| Transkripsi | Word-level transcript dan SRT | `faster-whisper`, transcript JSON, dan SRT tersedia | **Sudah tersedia** |
| Candidate scoring | Ranking relevansi, hook, durasi, dan diversitas | Scoring transkrip dan relevance gate tersedia | **Sebagian tersedia** |
| Crop objek/wajah | Framing dinamis menjaga wajah/objek utama | Haar cascade mendeteksi wajah dan crop mengikuti wajah; fallback center crop | **Wajah dasar tersedia; object tracking belum ada** |
| Subtitle | Subtitle terbaca dan mengikuti rules | SRT dan FFmpeg subtitles tersedia | **Tersedia; style dan safe area masih statis** |
| Watermark | Sesuai posisi, opacity, dan durasi campaign | Overlay watermark tersedia bila file diberikan; sebagian besar masih manual review | **Sebagian tersedia** |
| Audio | Mematuhi audio resmi dan menandai tindakan platform | Validator memberi checklist official audio | **Tersedia sebagai guardrail manual** |
| Render quality | Preview maksimal dengan profil kualitas | H.264/AAC 1080x1920; workflow memakai `veryfast` dan CRF 23 | **Berfungsi; belum profil final berkualitas maksimal** |
| Validator | Teknis + campaign + visual | Teknis dan sebagian rules/relevance tersedia; visual masih manual | **Belum lengkap** |
| Preview storage | Video dapat diputar dan diunduh aman | MP4/thumb diunggah ke R2 dan URL disimpan | **Berfungsi; akses masih perlu diamankan** |
| Review UI | Preview, warning, checklist, ACC, reject, rerender | Video dan tombol download tersedia; status pending review | **Belum lengkap** |
| ACC | Menyimpan persetujuan manual per kandidat | Belum ada endpoint atau UI approval | **Belum tersedia** |
| Posting manual | Paket caption/checklist dan pencatatan URL posting | Caption/checklist dibuat di worker, tetapi UI belum menyediakan alur lengkap | **Sebagian tersedia** |
| Upload otomatis | Opsional dan bukan MVP | Sengaja disabled | **Sesuai keputusan desain** |
| Dashboard production | Pages + Worker + D1 + R2 aktif dan terlindungi | Struktur kode tersedia; `web/config.js` masih tanpa API URL, deployment belum tuntas | **Gap utama** |
| Keamanan media | Auth atau signed URL | Endpoint file saat ini dapat mengirim object R2 berdasarkan key dan memakai CORS wildcard | **Harus diperbaiki sebelum produksi** |
| Pengujian | Pipeline bisa direproduksi dan aman diubah | 42 unit test lulus | **Fondasi baik; belum ada integration/visual regression test** |

## Prioritas gap

### P0 — Menutup loop produk dasar

P0 harus membuat alur berikut benar-benar dapat dipakai dari ponsel:

`Campaign siap → Detail → Mulai clipping → Job berjalan → Preview muncul → ACC atau tolak → Download paket posting`.

Pekerjaan P0 adalah deployment Pages/Worker/D1/R2, pengisian `API_BASE_URL`, pengujian satu campaign nyata, endpoint approval, UI approval, dan verifikasi preview URL. Tanpa P0, pipeline GitHub Actions memang berjalan, tetapi pengguna belum memiliki studio yang konsisten untuk mengoperasikannya.

### P1 — Meningkatkan kualitas preview

P1 meliputi profil render fast/final, subtitle safe area, deteksi wajah yang lebih stabil, object tracking atau saliency fallback, scene-aware cutting, loudness normalization, dan frame contact sheet. P1 juga perlu menambah pilihan rerender tanpa mengulang intake dan transkripsi.

### P2 — Meningkatkan kualitas pemilihan kandidat

P2 meliputi ranking multi-sinyal, diversitas kandidat, speaker segmentation, audio quality score, duplicate detection, dan visual relevance check. Targetnya bukan membuat lebih banyak video, tetapi meningkatkan peluang bahwa dua atau tiga preview pertama memang layak diposting.

### P3 — Audit dan submission tracking

P3 menambahkan status `approved_for_manual_post`, `rejected`, `posted`, dan `submitted`. Pengguna dapat memasukkan URL publik dan mesin menyimpan platform, waktu, caption yang dipakai, serta bukti bahwa checklist campaign sudah diperiksa.

### P4 — Adapter publikasi opsional

P4 bukan bagian dari MVP. YouTube dapat dipertimbangkan lebih dulu karena API upload resminya jelas. TikTok dan Instagram harus tetap opt-in karena membutuhkan aplikasi terdaftar, permission, token, dan prasyarat akun. Default tetap manual atau private/draft jika platform mendukungnya.

## Arsitektur target yang disarankan

### State machine job

Gunakan status yang eksplisit agar pengguna memahami posisi job:

```text
queued
  -> preflight
  -> intake
  -> transcribe
  -> select
  -> render
  -> validate
  -> review
  -> approved_for_manual_post
  -> downloaded
  -> posted_manual
  -> submitted
```

Cabang kegagalan harus menjelaskan tahapnya:

```text
preflight_failed
asset_manual_required
asset_failed
render_failed
validation_failed
error
cancelled
```

Status progres numerik tetap boleh dipakai untuk progress bar, tetapi pesan tahap dan alasan harus menjadi sumber informasi utama.

### Data minimal yang harus disimpan

Setiap job perlu menyimpan campaign ID, plan version, rules hash, daftar source URL, manifest asset, checksum, transcript version, kandidat, render profile, validation report, preview metadata, keputusan review, dan submission record. Dengan data tersebut, rerender dapat dilakukan tanpa mengulang proses yang tidak berubah.

### Batas sumber dan kualitas

Untuk biaya gratis, worker boleh membatasi jumlah source dan kandidat. Batas tersebut harus terlihat di UI dan dapat diubah per job. Rekomendasi awal adalah memproses maksimal 3 source video, membuat 10 kandidat internal per source, merender maksimal 3 preview final, dan menyimpan hanya preview serta metadata di R2/D1. Raw video tetap bersifat sementara di runner.

## Rencana implementasi konkret

### Sprint 1 — Production loop

Pertama, deploy Pages Function, Worker, D1, dan R2 sesuai dokumentasi. Set `DEMO_MODE: false` dengan API URL nyata. Seed atau sinkronkan satu campaign fixture. Jalankan dari dashboard, pastikan job masuk D1, GitHub Actions menerima job, preview masuk R2, dan dashboard menampilkan video.

Pada sprint yang sama, tambahkan endpoint untuk approval per preview. Endpoint tersebut harus menerima hanya status yang diizinkan dan mencatat waktu serta alasan. UI review harus memiliki tombol ACC, Tolak, dan Download paket posting.

### Sprint 2 — Secure preview dan observability

Ganti URL file publik dengan URL yang terlindungi atau signed URL berumur pendek. Hilangkan CORS wildcard untuk deployment production. Tambahkan log job per tahap, asset failure reason, dan correlation ID. Pengguna harus dapat membedakan error permission Drive, error YouTube, error transkripsi, error FFmpeg, dan error upload R2.

### Sprint 3 — Quality profile dan rerender

Tambahkan render profile `fast`, `balanced`, dan `final`. Pindahkan CRF 23/`veryfast` sebagai preview cepat dan sediakan final profile dengan CRF lebih rendah serta preset yang lebih baik. Simpan profile pada job agar hasil dapat direproduksi.

Tambahkan safe area subtitle, deteksi overlap subtitle dengan wajah, audio loudness check, dan contact sheet frame. Tambahkan endpoint rerender yang memakai asset/transcript yang sudah ada.

### Sprint 4 — Visual intelligence

Perkuat crop dari Haar cascade menjadi pipeline yang dapat memilih wajah utama, mempertahankan beberapa wajah, dan memakai fallback saliency/object detection. Uji pada video landscape, multi-speaker, objek tanpa wajah, dan sumber vertical. Buat visual regression fixtures sehingga perubahan renderer tidak menurunkan kualitas lama.

### Sprint 5 — Candidate ranking dan submission record

Tambahkan ranking multi-sinyal, diversitas kandidat, duplicate suppression, serta status posting/submission. Setelah tahap ini, mesin bukan hanya menghasilkan preview, tetapi juga menyimpan jejak keputusan dari campaign sampai submission manual.

## Kriteria produk dianggap siap digunakan

Mesin dapat dianggap mencapai MVP ketika semua pernyataan berikut benar:

1. Pengguna dapat memilih campaign clipping yang telah dianalisis AI dari dashboard production.
2. Satu klik membuat satu job dan mencegah job aktif ganda untuk campaign yang sama.
3. Worker dapat mengambil material Google Drive dan YouTube yang memang diberikan campaign.
4. Setiap asset yang gagal memiliki alasan dan tindakan manual yang jelas.
5. Worker menghasilkan minimal satu preview valid atau status gagal yang dapat ditindaklanjuti.
6. Preview dapat diputar dan diunduh dari dashboard melalui akses yang aman.
7. Dashboard menampilkan validator, warning manual, caption draft, dan checklist campaign.
8. Pengguna dapat ACC atau menolak tiap kandidat, dan keputusan tersebut tersimpan.
9. Posting tetap manual dan mesin tidak mengirim upload ke platform tanpa tindakan eksplisit pengguna.
10. Semua test unit, satu integration test end-to-end, dan satu visual regression fixture lulus.

## Penilaian akhir terhadap posisi mesin saat ini

Mesin saat ini sudah melewati tahap eksperimen dasar. Ia bukan lagi sekadar radar campaign atau script download. Pipeline produksi inti telah terbukti berjalan sampai upload preview, dan Google Drive OAuth sudah aktif. Karena itu, pekerjaan berikutnya sebaiknya **tidak dimulai dari nol** dan tidak mengulang bagian intake.

Fokus terbaik sekarang adalah mengubah pipeline yang sudah berjalan menjadi produk yang terlihat dan dapat dikendalikan pengguna: selesaikan deployment dashboard, tampilkan status per tahap, amankan preview, tambahkan ACC/reject, lalu tingkatkan kualitas render dan visual validation. Dengan urutan tersebut, tujuan Anda tercapai secara bertahap tanpa menambah kompleksitas publikasi otomatis sebelum kualitas preview benar-benar stabil.

## References

[1]: https://github.com/ibank31/scrapper-engine/blob/main/README.md "Scrapper Engine README and current product behavior"

[2]: https://github.com/ibank31/scrapper-engine/blob/main/STATUS.md "Scrapper Engine project status"

[3]: https://github.com/ibank31/scrapper-engine/blob/main/worker/run_job.py "Clipper worker pipeline entrypoint"

[4]: https://github.com/ibank31/scrapper-engine/blob/main/modules/reward_campaign/intake.py "Campaign asset intake and source downloaders"

[5]: https://github.com/ibank31/scrapper-engine/blob/main/modules/clipping/render.py "Video renderer"

[6]: https://github.com/ibank31/scrapper-engine/blob/main/modules/clipping/validate.py "Clip technical and campaign validator"

[7]: https://github.com/ibank31/scrapper-engine/blob/main/web/app.js "Clipping dashboard behavior"

[8]: https://github.com/ibank31/scrapper-engine/blob/main/cloudflare/api.js "Cloudflare API and job/preview endpoints"

[9]: https://github.com/ibank31/scrapper-engine/blob/main/cloudflare/README.md "Cloudflare deployment plan"

[10]: https://developers.google.com/workspace/drive/api/guides/manage-downloads "Google Drive API download guide"

[11]: https://ffmpeg.org/documentation.html "FFmpeg official documentation"

[12]: https://developers.google.com/youtube/v3/guides/uploading_a_video "YouTube Data API upload guide"

[13]: https://developers.tiktok.com/doc/content-posting-api-get-started "TikTok Content Posting API guide"

[14]: https://developers.facebook.com/documentation/instagram-platform/content-publishing "Instagram content publishing documentation"

[15]: https://github.com/SYSTRAN/faster-whisper "faster-whisper repository and documentation"
