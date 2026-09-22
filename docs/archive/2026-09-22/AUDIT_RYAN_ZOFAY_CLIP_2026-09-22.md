# Audit Ryan Zofay Clipping Campaign 01

## Kesimpulan

Preview pertama berhasil melewati pipeline teknis, tetapi belum layak dianggap sebagai clip matang. Durasi akhirnya adalah **5,42 detik** dengan durasi stream video **5,37 detik**. Penyebabnya bukan batas durasi campaign. Campaign tidak menetapkan `min_duration_seconds` atau `max_duration_seconds`. Penyebabnya adalah sumber media yang dipilih hanya menyediakan sekitar satu potongan ucapan pendek, sedangkan selector sebelumnya mengizinkan fallback hingga tiga detik dan tidak memeriksa apakah momen memiliki hook, konteks, serta payoff yang lengkap.

Dengan demikian, sistem lama mencampurkan dua keputusan yang seharusnya dipisahkan. **Kepatuhan terhadap rules** menjawab apakah output melanggar syarat campaign. **Kelayakan editorial** menjawab apakah output cukup utuh dan menarik untuk diposting. Preview ini relatif patuh terhadap format teknis dasar, tetapi gagal pada kelayakan editorial.

## Bukti preview nyata

Preview yang masuk ke review memiliki format H.264 vertical 1080×1920, audio AAC 48 kHz, dan durasi 5,42 detik. Transkripsi langsung terhadap file menghasilkan dua bagian berikut:

> “They're gonna be the ones to help guide you and, and kind of cross that bridge with you—”
>
> “to become that future.”

Analisis multimodal menemukan bahwa video dimulai di tengah kalimat, memperlihatkan monitor dan ruangan sebelum subjek terlihat jelas, kemudian berhenti segera setelah frasa “that future”. Tidak ada hook pembuka, konteks tentang siapa “they” itu, atau payoff yang menjelaskan masa depan yang dimaksud. Audio dapat dipahami, tetapi terdengar seperti audio ruangan dari ponsel, bukan feed langsung podcast. Caption tidak dibakar ke video.

## Mengapa durasinya hanya 5 detik

Alur yang terjadi pada run berhasil adalah sebagai berikut. Intake mengunduh lima file dan memilih tiga sumber video. Whisper berhasil mentranskripsi masing-masing sumber. Dua sumber menghasilkan kandidat setelah adaptive short-form fallback, sedangkan satu sumber tidak menghasilkan kandidat. Kandidat yang dipilih memiliki rentang sekitar lima detik karena rentang transkrip yang tersedia hanya mencakup dua segmen pendek. Renderer kemudian memotong tepat pada rentang kandidat tersebut.

Pipeline tidak memperpanjang rentang ke kalimat sebelum atau sesudahnya karena segmen tambahan memang tidak tersedia dalam transkrip sumber tersebut. Pipeline juga belum memiliki quality gate yang menolak kandidat yang dimulai dengan konjungsi atau pronomina tanpa antecedent, serta kandidat yang berakhir tanpa tanda penyelesaian ucapan. Fallback tiga detik menyelesaikan kegagalan teknis `candidates: 0`, tetapi secara editorial membuka jalan bagi preview yang terlalu pendek dan menggantung.

## Campaign rules sebagai source of truth

| Rule campaign | Nilai aktual | Dampak pada preview | Keputusan enforcement |
|---|---|---|---|
| Source policy | Provided clips | Sumber dari Drive dipakai | Pertahankan; jangan memakai sumber yang tidak disediakan campaign |
| Allowed content | Ryan’s best moments | Kandidat harus benar-benar menampilkan momen Ryan yang layak | Tandai kandidat ambigu untuk review manusia |
| Topic terms | business, author, speaker, podcast host, personal development | Transcript preview tidak memuat kecocokan literal | Jangan auto-block; tandai `uncertain` dan minta verifikasi manusia |
| Aspect ratio | Tidak ditentukan | Sistem menghasilkan 9:16 sebagai format platform default | 9:16 tetap digunakan sebagai default teknis, bukan klaim rule campaign |
| Minimum duration | Tidak ditentukan | Tidak ada pelanggaran durasi formal | Terapkan quality floor editorial terpisah, bukan campaign rule |
| Maximum duration | Tidak ditentukan | Tidak ada pelanggaran durasi formal | Batasi hanya untuk kualitas platform, bukan compliance campaign |
| Subtitle | Tidak wajib; style `none` | Preview tanpa subtitle | Secara rules benar; subtitle boleh menjadi enhancement, bukan kewajiban |
| Watermark | Tidak wajib | Tidak ada watermark campaign | Benar |
| Third-party watermark | Diizinkan | Tidak ada watermark terdeteksi dalam metadata | Tidak ada konflik |
| Official audio | Tidak wajib | Audio sumber dipertahankan | Benar, tetapi kualitas audio tetap harus direview |
| CTA, handles, hashtags | Tidak diwajibkan | Tidak ditambahkan | Benar |
| Mandatory requirement | Include demographic information | Belum dipenuhi dan definisinya tidak tersedia | Harus menjadi checklist wajib sebelum approval; jangan mengarang isi |
| Publish policy | Human approval required | Preview berhenti di `pending_review` | Benar |

## Temuan rules yang paling penting

Campaign memiliki satu requirement wajib: **“Include demographic information.”** AI juga menandainya sebagai ambiguity karena tidak menjelaskan apakah informasi demografis harus berupa target audience, caption disclosure, atau metadata posting. Pipeline lama tidak memasukkan requirement ini ke checklist review dan caption draft. Itu adalah gap kepatuhan yang lebih serius daripada durasi lima detik. Sistem harus menahan approval atau setidaknya menampilkan requirement tersebut secara eksplisit sampai definisinya dikonfirmasi.

Sebaliknya, subtitle bukan pelanggaran pada campaign ini karena `subtitle_required` bernilai `false`. Rekomendasi umum platform tidak boleh mengalahkan source of truth campaign. Subtitle dapat ditawarkan sebagai versi quality enhancement, tetapi tidak boleh dinyatakan sebagai kewajiban rules.

## Keputusan produk yang disarankan

Pipeline perlu menggunakan dua gate berbeda. Gate pertama memeriksa compliance terhadap rules campaign. Gate kedua memeriksa kelayakan editorial. Kandidat yang tidak cocok secara literal tetapi tidak menunjukkan topik yang bertentangan boleh masuk review dengan status `uncertain`. Kandidat yang lebih pendek dari quality floor, dimulai di tengah pikiran, atau berakhir tanpa payoff harus ditandai `editorial_fail` dan tidak boleh dikirim sebagai preview matang.

Untuk campaign ini, output ideal seharusnya berasal dari sumber podcast yang memiliki percakapan lebih panjang atau dari file yang benar-benar berisi potongan Ryan yang selesai. Menggabungkan potongan video pendek yang tidak berkesinambungan untuk memaksa durasi lebih panjang akan berisiko melanggar konteks dan rules “Ryan’s best moments”. Sistem lebih baik menolak sumber yang tidak memadai dengan alasan yang jelas daripada mengirim clip lima detik yang tampak seperti hasil gagal.

## Perubahan implementasi berikutnya

Perubahan berikut perlu diprioritaskan sebelum job kedua dijalankan. Pertama, masukkan seluruh mandatory requirements dari `source_of_truth` ke checklist review dan status approval. Kedua, tambahkan editorial quality gate untuk minimum durasi, kalimat pembuka, penyelesaian ucapan, dan payoff. Ketiga, simpan alasan penolakan sumber agar dashboard menjelaskan bahwa masalahnya adalah **asset tidak cukup panjang atau tidak memiliki momen utuh**, bukan kegagalan teknis worker. Keempat, pertahankan aturan bahwa publish tetap mustahil sebelum human approval dan requirement demographic information diselesaikan.

## Referensi

[1]: https://clipper-engine.pages.dev "Clipper Engine production dashboard"
[2]: https://github.com/ibank31/scrapper-engine/actions/runs/35706198906 "Successful clipping workflow run"
[3]: https://github.com/ibank31/scrapper-engine "Scrapper Engine source repository"
