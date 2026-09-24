# Panduan Penempatan dan Gaya Subtitle Short-Form

**Status:** Implemented baseline for the clipping renderer  
**Canvas master:** 1080 × 1920 px, rasio 9:16

## Kesimpulan desain

Tidak ada satu koordinat aman yang berlaku permanen untuk semua video organik di TikTok, Instagram Reels, dan YouTube Shorts. Elemen UI berubah berdasarkan aplikasi, perangkat, bahasa, format iklan, CTA, dan konfigurasi platform. Karena itu, renderer menggunakan **safe-zone fallback lintas platform** dan tetap harus menyediakan pemeriksaan preview pada platform tujuan.

Fallback saat ini menempatkan subtitle sebagai blok dua baris di area lower-middle. Blok tersebut dijaga agar tidak menyentuh rail interaksi kanan atau area metadata bawah. Pada canvas 1080 × 1920, target kerja yang konservatif adalah sekitar **x=108–960** dan **y=269–1248**. Batas ini merupakan keputusan engineering yang menggabungkan guardrail iklan Meta, zona UI iklan Shorts, dan panduan subtitle vertikal BBC; batas ini bukan klaim bahwa semua tampilan organik selalu menggunakan koordinat yang sama [1] [2] [3] [4].

Subtitle menggunakan satu atau dua baris sebagai default. Tiga baris hanya digunakan jika pemenggalan alami tidak mungkin dilakukan dan hasilnya sudah diperiksa terhadap wajah, produk, teks sumber, serta UI aplikasi. Cue dipotong menjadi unit pendek agar penonton dapat membaca tanpa menghentikan video.

## Perbandingan safe zone platform

| Platform | Fakta yang relatif kuat | Baseline produksi yang disarankan |
|---|---|---|
| TikTok | TikTok merekomendasikan format 9:16 dan menjelaskan bahwa safe zone berubah menurut orientasi, panjang caption iklan, anchor, serta interactive add-on. TikTok tidak menjanjikan satu peta piksel universal. | Gunakan master 1080 × 1920. Mulai dengan area kritis x=60–960 dan y=108–1600 sebagai heuristik, lalu gunakan safe-zone file dan preview TikTok untuk format yang sebenarnya. Subtitle tetap lower-middle dan jangan masuk ke rail kanan atau area caption bawah. |
| Instagram Reels | Meta memberi guardrail iklan sekitar 14% kosong di atas, 35% di bawah, dan 6% pada masing-masing sisi. Untuk 1080 × 1920, ini kira-kira x=65–1015 dan y=269–1248. Meta juga memperingatkan agar disclaimer Reels menyisakan bagian bawah 40%. | Untuk konten yang mungkin di-boost atau dijadikan iklan, perlakukan x=65–1015 dan y=269–1248 sebagai batas kritis. Letakkan subtitle di lower-middle dengan batas bawah sekitar y=1150–1230. |
| YouTube Shorts | Panduan iklan Google menyebut zona UI sekitar 10% atas, 25% bawah, dan 10% kanan. Ini adalah proxy untuk iklan Shorts, bukan janji koordinat universal untuk Short organik. | Hindari y=0–192, y=1440–1920, dan x=972–1080. Targetkan subtitle pada y sekitar 60–72% dengan batas bawah tidak lebih rendah dari sekitar y=1248. |

Panduan BBC untuk subtitle video vertikal menyarankan area tengah sekitar 75% secara vertikal dan 90% secara horizontal. Panduan tersebut juga mengizinkan sampai tiga baris untuk video vertikal, tetapi praktik produksi ini memilih satu atau dua baris sebagai default karena lebih ringan dan lebih aman terhadap UI [4].

## Palet global, ukuran, dan posisi terbaru

Tidak dibuat tiga jenis video per platform. Semua campaign menggunakan satu master 9:16 dan satu style subtitle global. Palet violet-cyan sebelumnya diganti karena masih terasa kurang tegas. Renderer global sekarang menggunakan teks cyan terang dengan stroke deep-violet:

| Peran | Warna | Fungsi |
|---|---|---|
| Base caption | `#66EBFF` | Cyan terang untuk body caption. |
| Outline | `#2F1424` | Deep violet gelap sebagai stroke tegas. |
| Emphasis | `#FFA7E9` | Magenta-lavender terang untuk kata penting dan payoff. |
| Optional backing | `#21103D` dengan opacity tinggi | Panel atau pill ketika footage terlalu ramai. |

Ukuran font global dinaikkan menjadi 50 pada canvas 1080 × 1920. Posisi diturunkan sekitar 50 px dari versi sebelumnya agar tidak terasa terlalu tinggi, tetapi tetap berada di lower-middle dan tidak masuk ke UI bawah. Font memakai sans-serif bold dengan stroke gelap 3 px. Hue tidak boleh menjadi satu-satunya pembawa makna. Kata emphasis tetap diberi bold sehingga pesan tidak hilang dalam grayscale. Kontras minimum yang dijadikan target adalah 4.5:1 untuk teks biasa dan 3:1 hanya untuk teks yang benar-benar memenuhi kriteria large text [5] [6].

## Aturan kata penekanan

Renderer menandai paling banyak dua kata per cue agar penekanan tidak berubah menjadi noise visual. Kata yang diprioritaskan meliputi kata yang membawa energi atau payoff, misalnya **free**, **insane**, **huge**, **viral**, **never**, **back**, **hit**, **wow**, dan **yes**. Angka, nominal uang, serta bentuk seperti `2K`, `$500`, dan `20%` juga dapat diberi penekanan.

Penekanan hanya dipakai pada unit semantik terkecil yang penting. Seluruh kalimat tidak diberi warna amber. Kata emphasis disinkronkan dengan ucapan, tetap terbaca tanpa warna, dan tidak menggunakan flicker cepat. Jika cue berisi banyak kata menarik, sistem tetap membatasi aksen agar hierarki visual tidak runtuh.

Kata-kata tersebut adalah baseline heuristik global, bukan konfigurasi khusus Backyard Breaks. Semua campaign yang melewati renderer yang sama akan mendapatkan style, ukuran, dan emphasis ini. Tahap berikutnya dapat menambahkan daftar istilah per campaign atau memilih emphasis berdasarkan struktur kalimat, angka, tanda seru, dan payoff kandidat.

## Pencegahan preview duplikat

Pipeline sebelumnya mengambil dua kandidat dengan skor tertinggi setelah setiap duration band, tetapi hanya menghapus duplikat dengan start dan end yang persis sama. Akibatnya, dua window yang sangat overlap dapat tampil sebagai dua preview walaupun secara visual hampir sama. Pipeline global sekarang membandingkan source asset, rasio overlap waktu, dan kemiripan token transcript. Kandidat kedua dibuang jika overlap-nya minimal 45% dari window yang lebih pendek atau kemiripan teksnya sangat tinggi dengan durasi yang hampir sama. Dengan begitu, dua preview yang dikirim ke review queue harus mewakili bagian video yang berbeda.

## Verifikasi yang wajib dilakukan

Preview akhir harus diperiksa pada aplikasi target, bukan hanya pada timeline renderer. Pemeriksaan perlu mencakup perangkat Android dan iOS, caption pendek dan panjang, footage terang dan gelap, tampilan grayscale, kondisi sound-off, serta collision dengan wajah, produk, teks sumber, rail kanan, CTA, dan metadata bawah.

Untuk aksesibilitas, subtitle sebaiknya tetap disediakan melalui fitur caption platform jika workflow publikasi mendukungnya. Burned-in subtitle membantu penonton yang menonton tanpa suara, tetapi tidak menggantikan kontrol pengguna atas ukuran, bahasa, dan tampilan caption platform [5] [7].

## Referensi

[1]: https://ads.tiktok.com/resources/help/article/tiktok-auction-in-feed-ads?redirected=1 "TikTok Business Help Center — Auction In-Feed Ads"
[2]: https://www.facebook.com/business/ads-guide/update/image/instagram-reels "Meta for Business — Instagram Reels ad safe zone"
[3]: https://business.google.com/us/ad-solutions/youtube-ads/shorts-ads/ "Google Business — YouTube Shorts ads creative requirements"
[4]: https://www.bbc.co.uk/accessibility/forproducts/guides/subtitles/ "BBC Accessibility — Subtitle Guidelines"
[5]: https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html "W3C WAI — Understanding Contrast (Minimum)"
[6]: https://www.w3.org/WAI/WCAG21/Understanding/use-of-color.html "W3C WAI — Understanding Use of Color"
[7]: https://www.w3.org/WAI/media/av/captions/ "W3C WAI — Captions and Subtitles"
[8]: https://partnerhelp.netflixstudios.com/hc/en-us/articles/215758617-Timed-Text-Style-Guide-General-Requirements "Netflix Partner Help — Timed Text Style Guide"
[9]: https://www.ucop.edu/electronic-accessibility/standards-and-best-practices/ecourse-accessibility-checklist/captioning-best-practices.html "University of California — Captioning Best Practices"
[10]: https://pmc.ncbi.nlm.nih.gov/articles/PMC9185210/ "Chen and Muhamad — Impact of Color and Polarity on Visual Resolution"
