# Trial ForgeGUI — 21 September 2026

## Ringkasan

Trial kedua menggunakan campaign live **ForgeGUI Clipping [Roblox]**, bukan Boxabl. Campaign ini dipilih karena memiliki bentuk rules dan material yang berbeda dari regression case Boxabl: asset disediakan melalui folder Google Drive, targetnya Roblox/AI tooling, dan aturan publik mencakup caption disclosure, hashtag berurutan, CTA ForgeGUI, serta batasan warm-up akun.

Campaign detail berhasil diambil dari Content Rewards dan dikompilasi menjadi production plan. Detail dan plan lokal berada di `data/trials/live-forgegui/campaign/`; asset hasil intake tidak dimasukkan ke Git karena merupakan video binary campaign.

## Pipeline yang dijalankan

| Tahap | Hasil |
|---|---|
| Live campaign detail pull | Berhasil; campaign ID `1db63081-715e-4e04-9b11-fbc1d4e8e700` |
| Rules snapshot | Berhasil; Google Doc publik tersimpan di workspace |
| Asset intake | Berhasil membaca folder Google Drive approved |
| Asset selection | Satu asset kecil dipertahankan untuk trial; folder besar tidak diproses seluruhnya |
| Transkripsi | Berhasil dengan `faster-whisper` model `tiny`, 7 segmen, bahasa Inggris |
| Candidate selection | Berhasil setelah minimum duration diturunkan dari 20 ke 8 detik karena asset berdurasi 17.6 detik |
| Render | Berhasil; 1080×1920, H.264/AAC, 30 fps, 11.7 detik |
| Relevance validation | Pass; matches `forge g-u-i` dan `roblox` |
| Review queue | Berhasil; satu item `pending_review`, thumbnail dan caption draft tersedia |

Workspace trial: `data/trials/1db63081-715e-4e04-9b11-fbc1d4e8e700/`.

## Perbaikan mesin yang ditemukan dari trial

Validation awal memblokir clip karena vocabulary relevance hanya memiliki signals khusus Boxabl dan FundingPips. Padahal transcript ForgeGUI secara jelas menyebut Roblox dan “forge G-U-I”. Solusinya adalah menambahkan topic vocabulary ForgeGUI ke `core/relevance.py` dan regression test di `tests/test_relevance.py`. Setelah perubahan tersebut, validator memberi status `pass` tanpa menonaktifkan relevance gate.

Selector awal mengembalikan nol kandidat karena default minimum duration adalah 20 detik, sedangkan asset trial berdurasi 17.6 detik. Untuk produksi, minimum duration perlu mengikuti panjang asset atau dikonfigurasi per campaign; trial ini menggunakan `--min-seconds 8 --max-seconds 16` secara eksplisit.

## Batasan trial

Video yang digunakan adalah satu asset approved dari folder Drive ForgeGUI. Trial hanya menguji pipeline sampai **review queue**; tidak ada upload, publish, atau submission eksternal. Caption draft belum dianggap final karena aturan ForgeGUI mewajibkan pemeriksaan manual atas CTA/logo dan penempatan disclosure `#forgeguipartner #robloxdev #roblox` sebelum publikasi.

Folder Drive berisi banyak video sehingga proses intake penuh sempat mencapai sekitar 9.3 GB. Proses tersebut dihentikan untuk mencegah pemborosan storage; satu asset kecil berukuran sekitar 3.9 MB dipertahankan sebagai fixture trial lokal.
