# Evaluasi Mendetail Preview Clipping

**Tanggal:** 23 September 2026  
**Campaign:** Rolling Loud Movie Clipping  
**Brand:** Kyro Clips  
**Platform target:** TikTok  
**Preview yang dievaluasi:** Kandidat 1 dan Kandidat 2

## Kesimpulan utama

Kedua preview memiliki bahan editorial yang kuat. Keduanya relevan dengan campaign Rolling Loud, dimulai dengan konflik yang mudah dipahami, memiliki dialog komedi yang utuh, dan berakhir pada payoff yang jelas. Kualitas audio juga baik. Secara teknis, kedua file valid sebagai video vertikal 9:16 dengan H.264, AAC stereo, audio 48 kHz, dan pixel aspect ratio 1:1.

Namun, preview yang diuji **belum maksimal untuk diposting**. Kekurangan paling penting adalah subtitle sama sekali tidak terbakar ke video. Kandidat 2 juga memiliki framing yang terlalu sempit pada beberapa bagian sehingga wajah dan reaksi pembicara berisiko terpotong. Selain itu, ukuran file 26,2 MB dan 15,6 MB terlalu besar untuk tahap review manual di homepage.

Perbaikan mesin sudah diterapkan untuk pekerjaan berikutnya. Subtitle kini dipaksa aktif untuk setiap preview, bukan hanya ketika campaign mencantumkannya sebagai kewajiban. Sistem juga membuat proxy review 720×1280 yang jauh lebih ringan, sementara master 1080×1920 tetap disimpan untuk download akhir. Algoritma crop multi-wajah diperbaiki agar percakapan tidak selalu mengikuti satu wajah terbesar dan memotong lawan bicara.

## 1. Kepatuhan terhadap rules campaign

Campaign hanya menetapkan satu persyaratan wajib yang dapat dibaca secara eksplisit: **minimum durasi 7 detik**. Kandidat 1 berdurasi 43,2 detik dan Kandidat 2 berdurasi 28,1 detik. Keduanya memenuhi persyaratan tersebut.

| Pemeriksaan | Kandidat 1 | Kandidat 2 | Kesimpulan |
|---|---:|---:|---|
| Durasi minimum 7 detik | 43,2 detik | 28,1 detik | Lulus |
| Topik Rolling Loud | Disebut eksplisit dalam dialog | Disebut melalui festival hip-hop dan Megan Thee Stallion | Lulus secara editorial |
| Format vertikal | 1080×1920 | 1080×1920 | Lulus |
| Pixel aspect ratio | 1:1 | 1:1 | Lulus |
| Watermark wajib | Tidak diwajibkan | Tidak diwajibkan | Tidak ada masalah |
| Official audio wajib | Tidak diwajibkan | Tidak diwajibkan | Tidak ada masalah |
| Human review | Wajib | Wajib | Belum selesai sebelum approval |

Ada satu kelemahan pada sistem rules yang perlu dicatat. Mesin memberi status relevance `uncertain` karena konfigurasi AI campaign belum menghasilkan daftar `topic_terms` yang dapat diandalkan. Analisis transcript dan pemeriksaan visual menunjukkan bahwa kedua kandidat sebenarnya relevan. Artinya, masalahnya bukan pada isi video, melainkan pada **ekstraksi aturan campaign**. Pada campaign berikutnya, judul, deskripsi, brand, dan nama entitas harus digabung menjadi topic vocabulary sebelum relevance gate dijalankan. Status `uncertain` sebaiknya menjadi permintaan review manusia, bukan alasan untuk menolak clip yang jelas relevan.

## 2. Kualitas video dan audio

### Format dan encoding

Kedua file memiliki format yang tepat untuk workflow review dan TikTok: video H.264, ukuran 1080×1920, display aspect ratio 9:16, sample aspect ratio 1:1, serta audio AAC stereo 48 kHz. Perbaikan `setsar=1` terbukti menyelesaikan masalah teknis sebelumnya.

Kualitas master secara numerik cukup tinggi, tetapi bitrate terlalu besar untuk preview browser. Kandidat 1 berukuran sekitar 26,2 MB dengan bitrate 4,85 Mbps. Kandidat 2 berukuran sekitar 15,6 MB dengan bitrate 4,44 Mbps. Angka ini menjelaskan mengapa banyak kartu review terasa berat ketika dibuka dari jaringan mobile.

### Audio

Hasil pengukuran loudness menunjukkan bahwa normalisasi berjalan sesuai target:

| Parameter | Kandidat 1 | Kandidat 2 |
|---|---:|---:|
| Integrated loudness input | −14,82 LUFS | −14,24 LUFS |
| True peak input | −1,42 dBTP | −1,37 dBTP |
| Hasil normalisasi | −14,29 LUFS | −13,84 LUFS |
| True peak hasil | −1,50 dBTP | −1,50 dBTP |
| Loudness range hasil | 2,30 LU | 4,00 LU |

Keduanya berada pada rentang yang sehat untuk short-form video. Analisis audio juga tidak menemukan clipping, ketidaksinkronan dialog, atau ketidakseimbangan yang mengganggu. Audio merupakan bagian terkuat dari dua preview ini.

Peningkatan general yang tetap diperlukan adalah mendeteksi musik latar yang menutupi dialog, noise mendadak, dan jeda audio kosong. Normalisasi loudness tidak dapat memperbaiki musik yang sudah terlalu dominan; pemeriksaan speech-to-music ratio perlu menjadi sinyal review tambahan.

### Subtitle

Kedua preview **tidak memiliki subtitle sama sekali**. Ini adalah kegagalan paling penting untuk penggunaan TikTok. Dialog berisi nama rapper dan punchline yang mudah salah dengar, sehingga subtitle diperlukan untuk aksesibilitas, penonton tanpa suara, dan retensi.

Subtitle seharusnya memiliki tiga pemeriksaan tambahan:

1. Sinkronisasi awal dan akhir terhadap ucapan.
2. Maksimal dua baris dengan ukuran teks yang tetap terbaca di layar ponsel.
3. Safe zone yang tidak bertabrakan dengan caption TikTok, tombol kanan, atau area bawah layar.

Perubahan sudah diterapkan: setiap preview baru sekarang memakai `--force-subtitles`. Subtitle dibuat dari transcript dan dibakar ke video. Preview lama yang sedang tampil di homepage tetap merupakan artefak lama dan tidak otomatis berubah.

## 3. Face detection, framing, dan objek saat dialog

### Kandidat 1

Kandidat 1 memiliki framing yang baik. Anak menjadi fokus utama pada sebagian besar klip dan wajahnya terlihat jelas. Kemunculan wajah ayah di bagian akhir mendukung payoff komedi. Crop vertikal tidak menghilangkan konteks penting dan tidak ada watermark pihak ketiga.

Kandidat 1 dapat dinilai **lulus dengan review manual standar**. Hal yang tetap perlu diperiksa saat approval adalah apakah subtitle menutupi tangan, ponsel, atau ekspresi pada punchline akhir.

### Kandidat 2

Kandidat 2 relevan dan memiliki pacing yang baik, tetapi framing lebih lemah. Pada sekitar 00:00–00:02, crop terlalu agresif sehingga wajah kedua pembicara berada dekat atau sebagian keluar dari sisi frame. Pada sekitar 00:10–00:12, kepala dan dagu anak hampir menyentuh batas frame. Pada sekitar 00:13–00:17, komposisi masih terasa bergeser ketika anak bergerak.

Masalah ini terjadi karena crop sebelumnya mengikuti satu wajah terbesar. Itu cocok untuk monolog, tetapi kurang cocok untuk dialog dua orang. Algoritma sudah diperbaiki agar ketika mendeteksi dua wajah, titik crop dihitung dari keseluruhan area percakapan. Perbaikan ini tidak menjamin kedua wajah selalu masuk jika jarak fisik terlalu jauh untuk rasio 9:16, tetapi mengurangi pemotongan sepihak.

Untuk campaign baru dengan dialog, mesin sebaiknya menggunakan aturan berikut: jika dua wajah terdeteksi secara konsisten, prioritaskan framing percakapan yang lebih lebar; jika hanya satu wajah aktif, gunakan speaker-focused crop; jika face detection tidak stabil, gunakan centered crop dan tandai `needs_review`.

## 4. Nilai editorial dan struktur clip

### Kandidat 1

Kandidat 1 adalah kandidat yang lebih kuat. Clip dimulai langsung dengan permintaan berenergi tinggi, membangun konflik ayah-anak, lalu berkembang melalui salah paham terhadap nama-nama rapper. Payoff muncul ketika ayah menyampaikan komentar tentang kejahatan di parking lot. Struktur hook–escalation–payoff utuh dan tidak ada dead air yang signifikan.

Status editorial: **lulus dengan subtitle wajib**.

### Kandidat 2

Kandidat 2 juga memiliki struktur yang baik. Clip dimulai di tengah argumen, mempertahankan energi, lalu berakhir pada salah tafsir “Megan Thee Stallion” sebagai kuda. Pacing dan payoff bekerja, tetapi crop awal yang terlalu ketat mengurangi kualitas presentasi.

Status editorial: **lulus bersyarat**, dengan perbaikan framing dan subtitle.

## 5. Checklist kualitas general untuk campaign masa depan

Mesin sebaiknya memproses setiap campaign melalui empat lapisan berikut.

### Lapisan rules

Mesin harus mengekstrak durasi minimum dan maksimum, rasio, watermark, audio resmi, handle, CTA, disclosure, prohibited content, serta topic terms. Rules yang tidak jelas harus ditandai `needs_review`, bukan diasumsikan aman. Topic terms harus berasal dari judul, brand, deskripsi, nama entitas, dan instruksi campaign.

### Lapisan editorial

Setiap kandidat perlu memiliki hook pada awal clip, konteks yang cukup, dialog atau aksi yang tidak terputus, dan payoff yang dapat dipahami. Kandidat yang dimulai di tengah kalimat boleh masuk review, tetapi harus diberi warning yang terlihat jelas. Kandidat tanpa payoff atau dengan dead air panjang harus mendapat skor rendah sebelum render.

### Lapisan teknis

Validator wajib memeriksa durasi, dimensi, SAR, codec, audio sample rate, loudness, true peak, keberadaan audio, subtitle burn-in, dan keberadaan watermark. Master harus tetap berkualitas tinggi. Proxy review harus lebih kecil agar homepage cepat.

### Lapisan visual

Frame harus diperiksa untuk deteksi wajah, multi-speaker framing, kepala atau dagu yang terpotong, objek penting yang keluar frame, area subtitle, dan perubahan crop mendadak. Jika face detection tidak stabil, sistem harus menurunkan keyakinan dan menandai clip untuk review manusia.

## 6. Perubahan mesin yang sudah diterapkan

Perubahan berikut sudah dipublish pada repository:

- Subtitle dipaksa aktif pada setiap preview baru.
- Preview proxy 720×1280 dengan CRF lebih ringan dibuat untuk pemutaran review.
- Master 1080×1920 tetap disimpan sebagai file download akhir.
- Homepage tidak melakukan preload metadata video secara agresif.
- Thumbnail dipakai sebagai poster review.
- Crop multi-wajah menggunakan pusat area percakapan, bukan hanya wajah terbesar.
- Database menyimpan `review_video_key` terpisah dari `video_key` master.
- Cleanup 24 jam menghapus proxy, master, thumbnail, manifest, event review, telemetry, dan job lama.

## Keputusan untuk dua preview yang diuji

| Preview | Keputusan teknis | Alasan |
|---|---|---|
| Kandidat 1 | **Jangan download versi lama; render ulang** | Editorial kuat dan audio baik, tetapi subtitle tidak ada |
| Kandidat 2 | **Jangan download versi lama; render ulang** | Subtitle tidak ada dan framing terlalu ketat pada beberapa bagian |

Setelah render ulang, Kandidat 1 diperkirakan menjadi pilihan utama. Kandidat 2 tetap layak dipertahankan sebagai alternatif jika proxy baru menunjukkan framing multi-speaker yang lebih seimbang.

## Batasan evaluasi

Evaluasi ini menggunakan metadata ffprobe, pengukuran loudness, frame sampling, serta analisis visual dan audio berbasis AI. Analisis tersebut tidak menggantikan pemeriksaan manusia terhadap ejaan subtitle per kata, kepatuhan hak penggunaan, atau keputusan akhir upload ke TikTok. Approval manual tetap merupakan gate wajib campaign.

## References

[1]: https://github.com/ibank31/scrapper-engine/actions/runs/35823749241 "Successful Rolling Loud clipping workflow"

[2]: https://clipper-engine.pages.dev/ "Clipper Engine production homepage"
