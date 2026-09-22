# Integrasi Google Drive untuk Materi Campaign

Pipeline clipping menggunakan folder asset campaign sebagai sumber video resmi. Untuk campaign Ryan Zofay, folder yang terdeteksi adalah:

`https://drive.google.com/drive/folders/1g2wgEVd9BT4bFhKxR3Jztd6b5kywaE4s?usp=sharing`

## Mengapa integrasi diperlukan

Versi lama memakai `gdown.download_folder()` pada tahap `reward_intake`. Pemanggilan tersebut tidak memiliki timeout terkontrol, tidak memakai daftar file dari Drive API, dan dapat menunggu halaman/permission Drive tanpa mengirim progress baru. Karena progress `8%` ditulis tepat sebelum `reward_intake`, kondisi ini cocok dengan job Ryan Zofay yang stale di `8%`.

Versi baru memakai Drive API resmi apabila tiga environment variable OAuth tersedia. Client akan memperbarui access token dari refresh token, memeriksa isi folder, mengabaikan file yang tidak dapat di-download, lalu mengunduh media secara streaming dengan retry dan timeout. Tidak ada password atau token yang ditulis ke source code.

## Credential yang diperlukan

Buat OAuth client tipe **Web application** atau **Desktop application** pada Google Cloud project yang memiliki Google Drive API aktif. Gunakan scope read-only:

`https://www.googleapis.com/auth/drive.readonly`

Scope ini diperlukan karena folder campaign dapat sudah ada sebelum aplikasi terhubung. Scope `drive.file` hanya mencakup file yang dibuat atau dibuka oleh aplikasi dan tidak cukup untuk folder existing yang hanya dipilih melalui link.

Selesaikan consent OAuth sekali untuk akun Google yang memiliki akses ke folder campaign, dengan offline access agar refresh token dapat dipakai oleh worker tanpa browser terbuka.

## GitHub Actions secrets

Tambahkan tiga repository secrets berikut. Nilainya tidak boleh dimasukkan ke source atau log:

| Secret | Isi |
|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | OAuth client ID dari Google Cloud |
| `GOOGLE_OAUTH_CLIENT_SECRET` | OAuth client secret dari Google Cloud |
| `GOOGLE_DRIVE_REFRESH_TOKEN` | Refresh token hasil consent akun Google |

Workflow `clipper-worker` sudah meneruskan ketiga secret tersebut ke worker. `GOOGLE_DRIVE_MAX_FILES` default-nya 3 dan `CLIPPER_MAX_VIDEO_SOURCES` default-nya 1, sehingga mesin hanya memilih satu sumber video terbaik setelah folder diambil.

## Perilaku akses

Folder atau file harus dapat dibaca oleh akun Google yang diotorisasi. Untuk file video, Drive API juga memeriksa `capabilities.canDownload`. Jika akses tidak cukup, pipeline gagal dengan pesan yang dapat ditindaklanjuti dan membuat `MANUAL_ASSETS.md`; mesin tidak membypass permission, tidak memakai cookie browser, dan tidak mengarang asset.

Jika OAuth belum dikonfigurasi, pipeline masih memiliki fallback link publik menggunakan `gdown`, tetapi sekarang fallback tersebut berjalan sebagai subprocess dengan timeout `GOOGLE_DRIVE_PUBLIC_TIMEOUT_SECONDS` (default 180 detik). Dengan demikian worker tidak dapat menggantung tanpa batas di progress 8%.

## Rujukan resmi

- [Google Drive API: Download and export files](https://developers.google.com/workspace/drive/api/guides/manage-downloads)
- [Google OAuth 2.0 for web server applications](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Google Drive API: Share files and folders](https://developers.google.com/workspace/drive/api/guides/manage-sharing)
