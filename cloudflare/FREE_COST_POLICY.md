# Kebijakan biaya nol untuk Clipper Engine

## Keputusan utama

D1 dan R2 dipakai sebagai **control plane dan delivery layer**, bukan tempat penyimpanan semua bahan video. Video mentah, transkrip lengkap, cache Whisper, dan file kerja FFmpeg berada hanya di execution worker sementara. Untuk pengguna HP, execution worker ini adalah GitHub Actions runner yang hidup selama job dan dibersihkan setelah selesai; bukan HP pengguna dan bukan komputer pribadi. Cloudflare hanya menerima data yang diperlukan oleh dashboard.

Kebijakan ini menjaga biaya awal sedekat mungkin dengan nol selama volume masih berada di dalam kuota Free. Tidak ada konfigurasi cloud yang dapat menjamin biaya nol jika penggunaan melampaui kuota atau akun berubah ke plan berbayar. Karena itu mesin akan memiliki batas harian, batas storage, dan cleanup otomatis.

## Kuota yang relevan

| Resource | Kuota Workers Free | Implikasi desain |
|---|---:|---|
| D1 rows read | 5 juta per hari | Semua list memakai index, pagination, dan hanya memilih kolom yang diperlukan |
| D1 rows written | 100 ribu per hari | Status job tidak ditulis setiap detik; update hanya saat tahap berubah |
| D1 storage | 5 GB total | Jangan simpan video, transcript, atau raw HTML besar di D1 |
| R2 Standard storage | 10 GB-month per bulan | Simpan preview kecil dan final hanya sementara |
| R2 Class A | 1 juta operasi per bulan | Hindari upload berkali-kali untuk file yang sama |
| R2 Class B | 10 juta operasi per bulan | Preview memakai URL stabil/cache; jangan polling file berulang |
| R2 egress | Gratis | Download tidak membebani bandwidth egress, tetapi tetap dapat menghasilkan operasi baca |
| Workers requests | 100 ribu per hari | Polling job dibuat lambat dan dibatasi; UI tidak melakukan polling per detik |

Kuota D1 Free reset setiap hari pada 00:00 UTC. Kuota R2 Free berlaku bulanan. D1 rows read dihitung berdasarkan baris yang dipindai, sehingga query tanpa index dan full table scan harus dihindari.[1] R2 Free mencakup storage, Class A, Class B, dan egress sesuai tabel pricing Standard Storage.[2]

## Penyimpanan yang boleh masuk cloud

### D1

D1 hanya menyimpan campaign summary, job state, preview metadata, validation summary, object key, dan waktu kedaluwarsa. D1 tidak menyimpan raw campaign page, file video, audio, transcript word-level, atau cache model.

`plan_json` boleh menyimpan ringkasan aturan yang kecil. Plan lengkap tetap disimpan di workspace lokal. Jika audit jangka panjang diperlukan, plan lengkap dapat dikompresi dan disimpan sebagai satu objek R2 yang punya TTL.

### R2

R2 menyimpan tiga jenis object:

1. **Review proxy** dengan resolusi 360×640 atau 540×960, bitrate rendah, dan durasi clip asli. Ini dipakai untuk preview UI.
2. **Thumbnail** JPEG/WebP berukuran kecil.
3. **Final MP4** hanya setelah pengguna menekan ACC. Final tersedia untuk download selama 24–72 jam, kemudian dihapus.

Raw footage tidak boleh disimpan permanen di R2. Sumber berada pada workspace ephemeral GitHub Actions selama proses, lalu dihapus ketika job selesai. Backup permanen hanya boleh diaktifkan secara sengaja.

## Retensi wajib

| Object | Retensi default |
|---|---:|
| Thumbnail rejected | 3 hari |
| Preview rejected | 3 hari |
| Preview pending review | 14 hari |
| Preview approved | 3 hari setelah approval |
| Final download package | 24 jam setelah dibuat |
| Raw footage | GitHub runner ephemeral, dihapus setelah job |

Jika pengguna belum mereview preview dalam 14 hari, job ditandai `expired` dan object dihapus. R2 lifecycle rules digunakan sebagai pengaman kedua, sedangkan worker lokal menghapus metadata D1 secara periodik.

## Batas operasional konservatif

Mesin memakai batas yang lebih kecil daripada kuota Cloudflare agar ada ruang aman:

- maksimal 20 campaign aktif tersimpan di D1;
- maksimal 50 job baru per hari;
- maksimal 10 preview clip per job;
- maksimal 25 MB untuk satu preview proxy;
- maksimal 200 MB total upload final per hari;
- maksimal 100 job status update per jam;
- maksimal 1 refresh campaign setiap 10 menit dari UI kecuali tombol manual ditekan;
- maksimal 14 hari retensi preview.

Batas ini dapat dinaikkan setelah penggunaan dan metrik nyata terlihat. Jika batas tercapai, mesin menghentikan upload baru dan menampilkan `storage_guard` atau `daily_quota_guard`, bukan terus mencoba sampai menimbulkan biaya.

## Contoh kapasitas gratis

Dengan asumsi preview proxy rata-rata 10 MB:

- 10 clip per hari selama 14 hari = sekitar 1,4 GB-month;
- 20 clip per hari selama 14 hari = sekitar 2,8 GB-month;
- 50 clip per hari selama 14 hari = sekitar 7 GB-month.

Dengan demikian, review proxy kecil memberi ruang luas di bawah 10 GB. Final MP4 tidak dihitung sebagai retensi permanen karena hanya dibuat setelah ACC dan dihapus otomatis setelah download window berakhir.

Jika preview 1080×1920 disimpan permanen, storage akan cepat habis. Karena itu UI menggunakan proxy untuk review; tombol download meminta worker mengunggah final sementara setelah ACC.

## Query D1 hemat

API harus:

- menggunakan `SELECT` kolom yang diperlukan, bukan `SELECT *`;
- menggunakan `LIMIT` dan cursor pagination;
- memakai index pada `status`, `updated_at`, `campaign_id`, dan `job_id`;
- menggabungkan update status yang berdekatan;
- tidak mengubah timestamp setiap heartbeat;
- tidak melakukan polling dari browser lebih cepat dari 15–30 detik;
- menyimpan transcript dan validation detail di lokal, lalu mengirim summary kecil ke D1.

Contoh query yang diperbolehkan:

```sql
SELECT id, title, brand, score, rate_per_1k, budget_left, platforms_json
FROM campaigns
WHERE status = 'active'
ORDER BY score DESC
LIMIT 30;
```

Contoh query yang dilarang pada request biasa:

```sql
SELECT * FROM campaigns;
SELECT * FROM previews;
```

## Pengaman agar tidak tiba-tiba berbayar

Sebelum upload atau query, worker menghitung ukuran file dan jenis operasi. Worker menolak file yang terlalu besar, menolak upload raw footage, dan menolak job baru setelah batas harian tercapai. Dashboard menampilkan penggunaan lokal dan status guard.

Cloudflare dashboard tetap menjadi sumber monitoring terakhir. Terms dan kuota dapat berubah, sehingga angka pada dokumen ini harus diverifikasi kembali sebelum production deployment.[1] [2] [3]

## Kesimpulan

Konfigurasi termurah untuk pengguna HP adalah **Pages untuk UI, D1 untuk metadata kecil, R2 untuk preview proxy sementara, dan GitHub Actions runner ephemeral untuk semua kerja berat**. Dengan kebijakan ini, kita tidak perlu membayar server GPU, tidak menyimpan bahan mentah permanen di cloud, dan tidak membayar storage video permanen. Biaya baru menjadi kemungkinan jika jumlah campaign, preview, request, atau retensi melebihi batas konservatif.

## References

[1]: https://developers.cloudflare.com/d1/platform/pricing/ "Cloudflare D1 pricing and Free plan limits"
[2]: https://developers.cloudflare.com/r2/pricing/ "Cloudflare R2 pricing and Free tier"
[3]: https://developers.cloudflare.com/workers/platform/limits/ "Cloudflare Workers platform limits"
