# Arsitektur Clipper untuk Pengguna HP

## Koreksi asumsi

Pengguna tidak memiliki komputer pribadi. Karena itu worker Python tidak boleh diasumsikan berjalan lokal. “Lokal” pada rancangan sebelumnya berarti komputer milik pengguna, dan asumsi tersebut dicabut.

## Pilihan gratis yang paling masuk akal

Repository `ibank31/scrapper-engine` saat ini public. GitHub menyatakan bahwa standard GitHub-hosted runners gratis untuk public repositories. Ini memungkinkan GitHub Actions menjadi worker video sementara: workflow hidup ketika ada job, menjalankan FFmpeg dan faster-whisper, mengunggah hasil ke R2, lalu selesai. GitHub Actions bukan server 24/7, tetapi untuk pola “pilih campaign dari HP lalu proses” model ini lebih hemat daripada menyewa VM.[1]

Hugging Face Spaces CPU Basic tidak dipilih sebagai worker utama. Dokumentasi Hugging Face menyatakan CPU Basic gratis secara hardware, tetapi Gradio/Docker Spaces yang berjalan di compute memerlukan paid plan, dengan pengecualian ZeroGPU tertentu. Space gratis juga dapat sleep ketika tidak dipakai, sehingga tidak cocok sebagai antrean produksi yang selalu tersedia.[2]

Google Colab tidak dipilih sebagai backend otomatis karena runtime gratis tidak dijamin, batas pemakaian berubah, dan notebook perlu sesi aktif. Colab tetap dapat dipakai sebagai fallback manual bila GitHub Actions sedang antre.[3]

## Alur baru

```text
HP pengguna
    ↓
Cloudflare Pages dashboard
    ↓
Cloudflare Worker API + D1
    ↓
GitHub Actions workflow_dispatch
    ↓
Ubuntu runner gratis
    ├── download asset yang authorized
    ├── faster-whisper CPU
    ├── highlight selection
    ├── FFmpeg render
    ├── compliance validator
    └── upload preview ke R2
    ↓
Cloudflare Pages menampilkan preview
    ↓
Pengguna menekan ACC / download dari HP
```

GitHub Actions tidak menyimpan artifact video sebagai storage utama karena akun GitHub Free memiliki batas artifact storage. Worker langsung mengunggah preview dan final sementara ke R2 lalu membersihkan workspace runner ketika job selesai.

## Batas realistis

Gratis tidak berarti tanpa batas. Worker akan dibatasi agar aman:

- satu workflow per campaign pada satu waktu;
- maksimal 10 kandidat per job;
- model Whisper CPU `small` atau `base` untuk kecepatan;
- preview proxy dikompresi sebelum upload;
- final MP4 hanya dibuat setelah ACC atau tetap disediakan dari job jika ukurannya kecil;
- job yang terlalu besar masuk status `needs_manual_asset` atau `quota_guard`;
- tidak ada loop worker yang hidup terus-menerus;
- scheduler campaign hanya berjalan melalui workflow terjadwal yang dibatasi.

Processing 30–90 menit video panjang di runner gratis dapat memakan waktu. UI menampilkan antrean dan progress, sehingga pengguna tidak perlu menunggu halaman tetap terbuka di HP.

## Secret dan keamanan

Secret tidak ditaruh di repository. GitHub Actions menyimpan:

- `CLIPPER_API_URL`;
- `CLIPPER_WORKER_TOKEN`;
- `R2_ENDPOINT`;
- `R2_ACCESS_KEY_ID`;
- `R2_SECRET_ACCESS_KEY`;
- `R2_BUCKET`.

Cloudflare Pages hanya menyimpan URL API publik, bukan R2 secret. API Worker hanya menerima status dari GitHub Actions jika header worker token benar. R2 bucket tidak dibuat public secara default; API akan memberikan object URL terbatas atau endpoint download yang dilindungi.

## Keputusan implementasi

Saya akan mengubah rancangan dari “Python worker lokal” menjadi “GitHub Actions ephemeral worker”. Cloudflare Pages tetap menjadi UI HP. D1 tetap metadata. R2 tetap preview sementara. FFmpeg dan faster-whisper berjalan di GitHub-hosted runner public repository.

Jika suatu hari repository harus dibuat private, GitHub Actions Free akan memiliki kuota menit bulanan dan storage terbatas. Pipeline harus tetap memiliki quota guard dan tidak boleh menganggap private runner gratis tanpa batas.

## References

[1]: https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions "GitHub Actions billing and free usage for public repositories"
[2]: https://huggingface.co/docs/hub/spaces-overview "Hugging Face Spaces overview, hardware, and lifecycle"
[3]: https://research.google.com/colaboratory/faq.html "Google Colaboratory FAQ and resource availability"
