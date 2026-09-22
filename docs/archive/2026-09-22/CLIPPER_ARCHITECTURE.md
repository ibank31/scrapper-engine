# Rancangan Mesin Clipper Otomatis untuk Campaign Whop

## Kesimpulan desain

Mesin ini akan menjadi **pipeline produksi clip yang campaign-aware**, bukan sekadar pemotong video otomatis. Setiap pekerjaan dimulai dari halaman campaign. Mesin membaca deskripsi, persyaratan, resource, platform yang diizinkan, dan batas pembayaran. Informasi tersebut dikompilasi menjadi `plan.json` yang menjadi sumber kebenaran untuk semua tahap berikutnya.

Target pertama adalah menghasilkan video yang siap ditinjau dengan kualitas tinggi dan risiko penolakan rendah. Mesin tidak akan mengakali bot detection, memanipulasi view, menghapus watermark yang diwajibkan campaign, atau mempublikasikan tanpa approval. Prinsip ini penting karena Content Rewards menggunakan triage fraud, verifikasi view, dan keputusan moderator untuk menentukan apakah submission dibayar.[1]

## Cara kerja campaign Whop/Content Rewards

Content Rewards memiliki dua model utama. **Clipping** menggunakan konten yang sudah disediakan brand, seperti podcast, livestream, webinar, musik, atau footage. **UGC** meminta creator membuat konten baru berdasarkan panduan brand. Repo ini berfokus pada clipping karena bahan video sering disediakan di dalam campaign.[2]

Campaign menetapkan reward per 1.000 view, total budget, platform yang diterima, batas minimum payout, dan maksimum payout. Setelah creator membuat dan memposting clip, creator mengirim URL publik atau draft apabila campaign mengaktifkan pre-post review. Brand dapat menyetujui atau menolak submission berdasarkan persyaratan yang tertulis di halaman campaign.[1] [2]

Whop dan Content Rewards tidak sama dengan mesin pembuat video. Content Rewards menangani submission, verifikasi view, fraud review, dan saldo payout. Whop menangani penarikan saldo dan proses terkait akun. Untuk campaign CPM, terms saat ini menjelaskan bahwa approval memulai periode validasi sekitar tujuh hari, kemudian ada sekitar tiga hari hold sebelum payout settle; periode tersebut dapat berubah.[1]

Karena campaign dapat memiliki aturan yang sangat spesifik, kalimat seperti berikut harus diperlakukan sebagai aturan mesin, bukan sekadar catatan:

- wajib memakai footage yang disediakan;
- wajib menggunakan audio resmi dan menambahkannya dari library platform saat posting;
- wajib memakai watermark resmi pada posisi, opacity, dan durasi tertentu;
- dilarang menggunakan watermark pihak ketiga;
- wajib memakai rasio 9:16;
- wajib menyebut handle atau CTA tertentu;
- dilarang membuat re-upload mentah, AI spam, konten tidak relevan, botting, view farm, atau engagement pod.

## Prinsip gratis dengan kualitas terbaik

Tidak ada solusi yang sekaligus gratis, selalu aktif di cloud, memiliki GPU tanpa batas, memakai model AI terbesar, dan mempublikasikan otomatis ke semua platform tanpa proses approval. Agar biaya tetap nol, mesin akan dijalankan di komputer pengguna atau server lokal yang sudah tersedia. Mesin tidak bergantung pada layanan clipping berbayar atau API AI berbayar.

Stack produksi yang dipilih adalah sebagai berikut:

| Bagian | Pilihan gratis | Alasan |
|---|---|---|
| Pengambilan bahan | HTTP downloader resmi, file lokal, dan link campaign yang memang diberikan brand | Tidak melawan bot wall dan tidak mengunduh dari sumber yang tidak diizinkan |
| Informasi video | `ffprobe` | Mengambil durasi, resolusi, audio, frame rate, dan codec secara deterministik |
| Transkripsi | `faster-whisper` | Model lokal MIT; implementasinya mengklaim hingga sekitar empat kali lebih cepat dan memakai lebih sedikit memori dibanding implementasi Whisper biasa, dengan opsi INT8 untuk CPU.[4] |
| Pembuatan subtitle | Word timestamps dari faster-whisper + generator SRT/ASS | Subtitle dapat mengikuti kata dan mudah divalidasi |
| Editing dan encoding | FFmpeg | Gratis, matang, mendukung crop, scale, overlay, subtitle, audio mix, dan encoding.[5] |
| Pemilihan momen | Scoring transkrip, jeda, durasi, perubahan scene, dan aturan campaign | Deterministik, dapat diaudit, dan tidak memerlukan biaya API |
| AI lokal opsional | Model lokal kecil untuk meranking kandidat | Dipakai hanya jika perangkat cukup kuat; pipeline dasar tetap berfungsi tanpa model chat |
| Approval | Folder review + halaman manifest | Tidak membutuhkan server atau integrasi berbayar |
| Publikasi awal | Manual dari perangkat pengguna | Paling aman untuk audio resmi, akun, caption, dan verifikasi campaign |

Untuk transkripsi, default CPU adalah model `small` atau `medium` INT8 sesuai RAM dan bahasa. Jika tersedia GPU, model yang lebih besar dapat dipakai. Dokumentasi Whisper menunjukkan bahwa model memiliki pertukaran antara akurasi, memory, dan kecepatan; model `turbo` ditujukan untuk transkripsi cepat tetapi bukan untuk menerjemahkan bahasa non-Inggris.[3] [4]

## Pipeline end-to-end

### 1. Radar campaign

Modul yang sudah ada mengambil daftar campaign dan menghitung skor awal berdasarkan kategori, rate, budget tersisa, platform, status, dan kata terlarang. Radar hanya memilih kandidat. Ia tidak boleh menganggap campaign layak produksi sebelum halaman detail dibaca.

### 2. Detail puller

Untuk campaign terpilih, mesin mengambil halaman detail dan menyimpan payload asli, brief, requirements, serta daftar resource. Payload asli perlu disimpan agar keputusan mesin dapat diaudit ketika brand mengubah aturan.

### 3. Campaign rule compiler

Compiler menghasilkan:

- identitas dan status campaign;
- platform yang diterima;
- semua requirements asli;
- URL bahan video dan asset;
- rasio dan durasi;
- audio resmi;
- watermark, posisi, opacity, dan durasi watermark;
- CTA dan handle;
- aturan caption, hashtag, disclosure, atau pinned comment;
- larangan;
- minimum view atau minimum payout;
- gate yang harus lolos sebelum render dan sebelum approval.

Parser menggunakan ekstraksi terstruktur jika field tersedia dan menggunakan teks bebas sebagai fallback. Ia harus menyimpan kalimat asli, bukan hanya hasil interpretasi. Jika parser menemukan kata yang ambigu, pekerjaan diberi status `needs_review` dan tidak boleh otomatis dipublikasikan.

### 4. Asset intake

Mesin membuat workspace terpisah untuk setiap campaign dan setiap asset. Link Dropbox, Google Drive, Frame.io, atau sumber lain yang dicantumkan brand dicatat sebagai sumber resmi. Downloader hanya menggunakan akses normal yang diberikan oleh link tersebut.

Jika folder membutuhkan login, CAPTCHA, atau akses yang tidak tersedia, mesin membuat task manual dengan URL dan alasan kegagalan. Mesin tidak memakai teknik bypass, scraping akun orang lain, atau menghapus proteksi sumber.

Setiap asset diberi checksum, nama sumber, ukuran, codec, durasi, dan waktu pengambilan. Asset yang sama tidak diunduh ulang.

### 5. Transkripsi dan analisis

Untuk setiap video, mesin:

1. menjalankan `ffprobe`;
2. mengekstrak audio sementara;
3. membuat transkrip word-level;
4. menyimpan JSON dan SRT;
5. mendeteksi jeda, pergantian speaker jika memungkinkan, dan perubahan scene;
6. mengaitkan timestamp dengan kalimat asli.

Tidak semua kalimat layak menjadi clip. Candidate scorer memberi nilai lebih tinggi pada hook yang cepat, pernyataan lengkap, konflik atau kontras, angka yang jelas, cerita dengan payoff, dan segmen yang dapat dipahami tanpa konteks panjang. Scorer memberi nilai rendah pada pembukaan yang terlalu panjang, kalimat yang terpotong, sponsor read yang tidak relevan, dan segmen yang bertentangan dengan requirement campaign.

### 6. Pembuatan kandidat clip

Default output kandidat adalah durasi 20–60 detik, tetapi batas campaign selalu mengalahkan default. Setiap kandidat harus menyimpan:

- `source_video`;
- `start` dan `end` timestamp;
- teks transkrip;
- alasan pemilihan;
- skor;
- campaign ID;
- daftar requirement yang relevan;
- status validasi.

Mesin dapat membuat beberapa kandidat dari satu video, tetapi menghindari overlap yang berlebihan. Tujuannya bukan membuat puluhan clip buruk, melainkan menghasilkan sejumlah kecil kandidat yang bisa diperiksa dan dipakai.

### 7. Render vertical 9:16

Renderer menggunakan strategi berikut secara berurutan:

1. jika video sudah vertical, pertahankan framing;
2. jika landscape dan wajah terdeteksi, gunakan crop dinamis yang menjaga wajah;
3. jika tidak ada deteksi wajah yang stabil, gunakan center crop dengan safe area;
4. jika crop akan menghilangkan informasi penting, gunakan background blur atau layout split yang tetap memenuhi rasio campaign;
5. tambahkan subtitle sesuai aturan campaign;
6. tambahkan watermark resmi hanya jika diwajibkan;
7. campur audio hanya jika campaign mengizinkan dan tidak mewajibkan audio resmi platform;
8. encode MP4 H.264 dengan audio AAC pada resolusi target 1080x1920 jika sumber dan perangkat memungkinkan.

Audio resmi yang harus dipasang melalui library TikTok atau Instagram tidak boleh dianggap selesai hanya karena file musik ditempel ke MP4. Mesin akan menandai `official_audio_platform_action_required` sehingga pengguna memasang sound resmi ketika posting.

### 8. Compliance validator

Validator menjalankan pemeriksaan teknis dan aturan campaign sebelum clip masuk review. Contoh pemeriksaan teknis mencakup resolusi, rasio, durasi, codec, audio, subtitle, frame rate, dan keberadaan watermark. Contoh pemeriksaan semantik mencakup kata wajib, CTA, handle, sumber asset, kata terlarang, dan penggunaan footage yang disediakan.

Hasil validator memiliki tiga status:

- `pass`: semua gate yang dapat diukur mesin lulus;
- `needs_review`: aturan ambigu atau memerlukan pemeriksaan visual/manusia;
- `fail`: ada pelanggaran terukur.

Satu `fail` pada aturan wajib menghentikan submission. Validator tidak akan mengubah aturan agar clip terlihat lulus.

### 9. Approval queue

Setiap clip yang lulus atau membutuhkan review ditempatkan ke folder review dengan:

- video MP4;
- thumbnail;
- `plan.json`;
- transkrip;
- SRT;
- laporan validator;
- daftar tindakan manual sebelum posting;
- caption draft;
- link submission setelah pengguna memposting.

Default sistem adalah `publish_allowed=false`. Setelah pengguna memeriksa video, pengguna dapat menandai `approved_for_manual_post`. Ini bukan approval Whop; ini hanya persetujuan internal bahwa file siap diposting.

### 10. Posting dan submission

Untuk tahap awal, pengguna memposting manual agar dapat memilih sound resmi, akun, tag, disclosure, dan pengaturan platform dengan benar. Setelah mendapatkan URL publik, pengguna memasukkan URL tersebut ke job. Mesin menyimpan URL, waktu posting, platform, dan status submission.

YouTube memiliki Data API untuk upload video dengan OAuth dan resumable upload.[6] TikTok menyediakan Content Posting API, tetapi direct posting membutuhkan registered app, scope `video.publish`, otorisasi creator, dan audit; client yang belum diaudit dibatasi ke private viewing.[7] Instagram publishing membutuhkan akun profesional, token, permission, dan media yang dapat diakses melalui server publik.[8] Karena itu, API publikasi tidak menjadi bagian dari MVP gratis. Ia dapat ditambahkan sebagai adapter opt-in setelah pipeline lokal dan approval stabil.

## Guardrail yang tidak boleh dihilangkan

Mesin tidak boleh:

- membuat view, like, comment, follower, atau engagement palsu;
- memakai view farm, bot, engagement pod, atau automation untuk memanipulasi metrik;
- mengambil footage dari campaign lain;
- menghapus watermark yang diwajibkan;
- memakai musik berhak cipta tanpa izin atau mengganti audio resmi campaign secara diam-diam;
- mempublikasikan pada platform yang tidak diizinkan campaign;
- menganggap draft approval sebagai approval final atas posting;
- menyembunyikan kegagalan validator;
- mengirim submission tanpa URL atau data yang diminta campaign.

Terms Content Rewards juga menetapkan bahwa content harus lawful, tidak melanggar hak kekayaan intelektual, tidak menipu, dan tidak melanggar aturan platform tempat clip diposting.[1]

## Roadmap implementasi repo

### Fase A — selesai

Radar campaign, detail puller, dan compiler aturan campaign telah tersedia. Compiler menghasilkan `plan.json` dan `PLAN.md`, termasuk gate human review. Publishing masih disabled.

### Fase B — berikutnya

Bangun job workspace dan asset intake. Fase ini akan menambahkan struktur folder, manifest asset, checksum, deduplikasi, retry, dan status `needs_manual_download` untuk resource yang memerlukan login.

### Fase C — video intelligence

Tambahkan `ffprobe`, ekstraksi audio, faster-whisper, word timestamps, SRT/ASS, scene detection, dan candidate scorer. Semua hasil harus disimpan sehingga clip dapat direproduksi dari source dan timestamp.

### Fase D — renderer dan validator

Tambahkan crop 9:16, subtitle style, watermark sesuai aturan, audio handling, encoding, technical checks, visual review report, dan campaign compliance report.

### Fase E — approval queue

Tambahkan manifest review, thumbnail contact sheet, caption draft, checklist tindakan manual, dan penyimpanan URL submission.

### Fase F — adapter publikasi opsional

Setelah MVP terbukti dan akun siap, tambahkan adapter YouTube terlebih dahulu. TikTok dan Instagram menyusul hanya jika prasyarat app, scope, audit, akun, dan hosting publik terpenuhi. Semua adapter memakai default private/draft jika platform mendukungnya.

## Keputusan awal yang saya ambil

Karena prioritas pengguna adalah gratis dan kualitas terbaik, mesin akan memakai **komputer lokal sebagai worker**, **FFmpeg sebagai renderer**, **faster-whisper sebagai transcriber lokal**, dan **approval manual sebelum posting**. Ini menghindari biaya berulang, menghindari ketergantungan pada layanan clipping berbayar, dan menjaga kontrol pengguna awam melalui laporan yang jelas.

Jika suatu saat ingin mesin berjalan 24/7 tanpa komputer pribadi, itu menjadi keputusan deployment terpisah. Hosting permanen, storage video, GPU, dan akses platform dapat menimbulkan biaya. Menyebut sistem itu “gratis” tanpa mengungkap batas tersebut akan menyesatkan.

## References

[1]: https://contentrewards.com/terms "Content Rewards Creator Terms of Service, updated September 3, 2026"
[2]: https://docs.whop.com/memberships-and-access/third-party-apps/content-rewards "Whop Content Rewards documentation"
[3]: https://github.com/openai/whisper "OpenAI Whisper repository and model documentation"
[4]: https://github.com/SYSTRAN/faster-whisper "SYSTRAN faster-whisper repository and benchmarks"
[5]: https://ffmpeg.org/documentation.html "FFmpeg official documentation"
[6]: https://developers.google.com/youtube/v3/guides/uploading_a_video "YouTube Data API upload guide"
[7]: https://developers.tiktok.com/doc/content-posting-api-get-started "TikTok Content Posting API direct-post guide"
[8]: https://developers.facebook.com/documentation/instagram-platform/content-publishing "Instagram Platform Content Publishing documentation"
