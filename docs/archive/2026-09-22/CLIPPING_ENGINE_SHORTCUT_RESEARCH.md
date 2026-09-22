# Rekomendasi Shortcut untuk Clipping Engine

## Keputusan eksekutif

**Jangan mengganti scrapper-engine dengan SaaS clipping secara penuh.** Shortcut yang paling aman dan bernilai adalah menjadikan **OpusClip sebagai adapter eksternal untuk mengusulkan dan merender kandidat**, sementara scrapper-engine tetap menjadi **control plane**: membaca campaign, mengompilasi aturan, menentukan sumber yang sah, memvalidasi hasil, menyimpan audit trail, mengantrekan human approval, dan menjaga `publish_allowed=false`.

Dengan keputusan ini, pekerjaan sulit yang bersifat probabilistik—menemukan hook dari video panjang, membuat beberapa potongan, memberi caption, dan melakukan reframing—boleh didelegasikan. Namun keputusan yang bersifat kepatuhan tidak didelegasikan. **Campaign rules tetap menjadi source of truth.** Output OpusClip diperlakukan sebagai *proposal/render artifact*, bukan bukti bahwa clip sudah memenuhi campaign.

Rekomendasi ini menghindari dua kegagalan yang sama-sama mahal. Pertama, membangun ulang seluruh intelligence clipping secara lokal sebelum tahu apakah kualitas momen cukup baik. Kedua, menghubungkan SaaS langsung ke akun sosial lalu membiarkan vendor mempublikasikan hasil tanpa pemeriksaan aturan. Sistem yang disarankan mengambil jalan tengah: **delegasikan produksi kandidat, pertahankan governance di repo**.

### Pilihan utama

| Peringkat | Opsi | Nilai integrasi realistis | Peran yang disarankan | Keputusan |
|---:|---|---|---|---|
| 1 | **OpusClip** | **Tertinggi** | Proposal momen, caption, reframing, dan render melalui API; webhook mengembalikan status | **Pilot utama** |
| 2 | **Vizard** | Tinggi | Alternatif API untuk proposal dan render dengan template/Brand Kit | Pilot pembanding atau fallback |
| 3 | **Klap** | Menengah-tinggi | Adapter API sederhana untuk URL publik dan asynchronous export | Pembanding kualitas, bukan pilihan awal |
| 4 | **Descript** | Menengah | Jalur transcript-first dan AI edit untuk kasus tertentu | Fallback untuk workflow berbasis transcript |
| 5 | **Munch Studio** | Rendah untuk integrasi | UI/manual benchmarking dan platform optimization | Jangan jadikan dependency otomasi |
| 6 | **Captions** | Rendah untuk clipping terotomasi | Caption-rendering API saja atau UI manual | Jangan jadikan engine clipping |

Urutan ini **bukan ranking kualitas video menurut marketing**. Urutan ini menilai kemampuan nyata untuk terhubung ke pipeline yang sudah ada, mengembalikan status dan artefak secara programatik, menerima batasan dari campaign, serta memungkinkan scrapper-engine melakukan validasi dan approval sendiri.

## Mengapa OpusClip menjadi shortcut yang tepat

OpusClip memiliki kombinasi paling lengkap untuk eksperimen terkontrol. API-nya dapat membuat project dari URL video publik, menerima batas durasi, rentang waktu sumber, genre, kata topik, model kurasi, dan prompt kustom. API juga menyediakan webhook, daftar clip yang dapat diekspor, URL MP4, timestamp sumber, durasi, judul, kata kunci, dan representasi render/caption. Fitur tersebut cukup untuk mengurangi pekerjaan lokal tanpa memaksa sistem menyerahkan keputusan kampanye kepada vendor.[1] [2] [3] [4]

Untuk kebutuhan visual, OpusClip mendukung caption dan aspect ratio portrait, landscape, serta square. Brand template dapat diterapkan melalui ID template yang dibuat di dashboard. Reframing dan auto-reframe tersedia pada level produk, tetapi dokumentasi publik tidak membuktikan kontrol API yang deterministik untuk memilih wajah atau objek tertentu. Karena itu, hasil crop tetap harus diperiksa oleh validator dan manusia.[5] [6] [7]

Kelemahan utama OpusClip dapat diatasi dengan adapter, bukan dengan asumsi. API yang ditinjau mendokumentasikan input berbentuk URL publik, bukan multipart upload lokal yang sederhana. Scrapper-engine harus menaruh asset yang memang diizinkan campaign ke object storage/CDN sementara, lalu menyerahkan signed atau public URL sesuai persyaratan vendor. Batas upload lokal juga tidak konsisten di halaman resmi: satu halaman menyebut 10 GB, sementara dokumentasi lain menyebut 30 GB. Nilai tersebut tidak boleh dimasukkan sebagai asumsi production sebelum vendor mengonfirmasi secara tertulis.[8] [9]

OpusClip juga memiliki API social posting dan scheduling. **Fitur itu sengaja tidak dipakai dalam arsitektur awal.** Kemampuan teknis untuk publish bukan otorisasi campaign. Audio resmi yang harus dipilih melalui library platform, account rule, disclosure, watermark, dan kewajiban approval tetap berada di luar OpusClip. Sistem hanya mengambil artefak hasil render dan mengarahkannya ke review queue.

## Ranking opsi berdasarkan nilai integrasi

### 1. OpusClip — pilihan pilot utama

OpusClip adalah kandidat yang paling seimbang untuk kebutuhan scrapper-engine. Ia memiliki API clipping yang terdokumentasi, asynchronous workflow, parameter seleksi, output export, webhook, dan kontrol render. Penggunaan paling tepat adalah mengirimkan source URL yang telah lolos policy, mengirimkan topik serta rentang durasi dari `plan.json`, menunggu webhook, mengambil hasil, lalu menjalankan validator lokal.

Nilai tambah terbesarnya adalah **mengurangi kebutuhan membangun moment discovery dari nol**. Nilai tambah kedua adalah webhook, sehingga worker tidak perlu melakukan polling agresif. Nilai tambah ketiga adalah adanya data timestamp dan metadata yang dapat disimpan bersama candidate manifest.

Batasnya harus diperlakukan eksplisit. AI tetap dapat memilih momen yang lemah atau tidak lengkap. Parameter `topicKeywords` dan `customPrompt` adalah kendali seleksi, bukan jaminan setiap clip merupakan momen mandiri yang lengkap. Caption, reframing, dan template membantu render, tetapi tidak menggantikan pemeriksaan kata wajib, kata terlarang, CTA, watermark, atau kecocokan footage.

**Jalur integrasi:** `campaign plan -> asset policy check -> temporary object URL -> POST clip-project -> signed webhook -> GET exportable clips -> download artifact -> local validate -> human review`.

### 2. Vizard — alternatif paling dekat

Vizard juga menawarkan REST API yang cocok untuk pipeline eksternal. API-nya dapat menerima YouTube, Google Drive publik, atau direct downloadable URL; membuat clip berdasarkan keyword, panjang yang diinginkan, jumlah maksimum, aspect ratio, subtitle, emoji, highlight, headline, B-roll, silence removal, model, dan `templateId`. API mendukung polling atau workspace webhook serta pengambilan hasil dan publikasi.[10] [11] [12]

Vizard unggul jika campaign membutuhkan Brand Kit dan template yang konsisten. API juga mendokumentasikan batas input sampai 600 menit dan 10 GB, walaupun batas, rate limit, dan entitlement berbeda antar halaman resmi sehingga perlu konfirmasi workspace/sales.[13] [14]

Vizard berada di bawah OpusClip bukan karena kemampuannya kurang, melainkan karena **ketidakpastian operasional yang lebih besar** pada dokumentasi publik. Rate limit tercantum berbeda antara quickstart, rate-limit page, dan tabel pricing. Download URL berlaku tujuh hari. Kualitas bahasa Indonesia, SLA, dan konsistensi clip tidak dijamin. Vizard layak dijadikan A/B comparator, terutama jika template atau hasil clip lebih baik pada corpus target.

**Jalur integrasi:** sama dengan OpusClip, tetapi adapter harus menangani skema API Vizard, expiry URL tujuh hari, serta variasi rate limit dan error code.

### 3. Klap — API bersih, tetapi kontrol workflow lebih tipis

Klap menyediakan REST API dengan alur asynchronous yang jelas: membuat task, memantau task, mengambil project, lalu mengekspor hasil. API menerima URL YouTube atau direct public HTTP/HTTPS, menghasilkan beberapa short, menyediakan captions, transcript/timecode, reframing, style preset, dan `virality_score`.[15] [16] [17]

Klap cocok untuk eksperimen cepat berbasis URL. Namun Google Drive disebut sebagai integrasi mendatang, tidak ada webhook yang terdokumentasi, dan tidak ada native campaign-rule engine. Engineering harus menambahkan polling, retry, scheduling, filtering, dan callback sendiri. Dokumentasi pricing API juga lama dan tidak mempublikasikan rate limit, retention, SLA, atau subscription minimum terkini. Ada pula perbedaan base URL antara contoh lama dan dokumentasi baru yang perlu diselesaikan sebelum implementasi.

Klap sebaiknya dipakai sebagai **pembanding kualitas momen** pada pilot, bukan sebagai fondasi pertama. Ia bisa menang pada footage talking-head, tetapi uji independen menemukan boundary abrupt, topik campur, dan crop screen-content yang lemah pada tutorial.[18]

### 4. Descript — menarik untuk transcript-first, bukan shortcut clipping utama

Descript kuat untuk workflow yang menjadikan transcript sebagai pusat editing. UI-nya dapat membuat clip yang self-contained, memberi caption, mengubah layout, dan melakukan active-speaker centering. API mendukung import media, Underlord edits, transcript export, publish, polling, dan callback URL. Prompt Underlord dapat meminta highlight reel atau clip.[19] [20] [21]

Masalahnya, clip discovery melalui API lebih bersifat agent/prompt daripada endpoint clipping deterministik. YouTube juga bukan source API yang didukung; sistem harus mengubah sumber menjadi direct file URL atau upload. Dokumentasi direct upload sendiri tampak tidak konsisten antara getting-started dan endpoint reference. Lebih penting lagi, rendered media API bersifat publish-mediated, sehingga tidak sesederhana mengambil MP4 privat untuk review queue.

Descript bernilai jika corpus campaign terutama berupa podcast atau interview yang transcript-nya rapi, atau jika tim ingin menguji edit berbasis instruksi. Ia bukan pilihan shortcut utama untuk pipeline yang membutuhkan banyak candidate clip terstruktur dan ekspor privat.

### 5. Munch Studio — kualitas UI mungkin berguna, kontrak integrasi tidak ada

Munch memverifikasi alur UI untuk menganalisis video, menghasilkan clip, caption, platform optimization, coherence score, manual crop, download, dan scheduling. Coherence score menarik sebagai sinyal apakah clip dapat berdiri sendiri.[22] [23]

Namun tidak ada public API contract yang memuat endpoint ingest, job status, webhook, export, authentication, quota, atau rule interface. Pernyataan partner bahwa API/developer support tersedia bukan pengganti spesifikasi teknis yang dapat diimplementasikan dan diuji. Munch cocok sebagai alat manual untuk membandingkan kualitas, bukan sebagai dependency pada worker produksi.

### 6. Captions — bagus untuk UI dan caption API, salah scope untuk engine ini

Captions memiliki UI AI Edit dan Clips yang dapat mencari hook, membuat ranked batch, menambah caption, serta melakukan reframing speaker/action. Tetapi public Mirage API yang ditinjau hanya menyediakan video captioning dan avatar generation. API captioning menerima file lokal kecil atau video ID yang sudah ada, lalu menyediakan polling dan download. Tidak ada endpoint publik untuk AI Clips, automatic moment discovery, AI Edit, reframing, Google Drive/YouTube ingestion, atau campaign rules.[24] [25] [26]

Captions dapat dipertimbangkan kemudian sebagai **caption-rendering adapter** bila hasil caption-nya terbukti lebih baik, bukan sebagai pengganti candidate scorer dan clipping engine.

## Arsitektur hybrid yang disarankan

### Prinsip kepemilikan keputusan

Gunakan pembagian berikut:

| Area keputusan | Pemilik | Alasan |
|---|---|---|
| Campaign eligibility dan status | scrapper-engine | Campaign detail dan `plan.json` adalah source of truth |
| Sumber video yang boleh digunakan | scrapper-engine | Mencegah asset campaign lain atau sumber tidak berizin |
| Allowed/prohibited content | scrapper-engine | Vendor tidak menyediakan policy evaluator campaign yang deterministik |
| Parameter proposal | scrapper-engine | Vendor hanya menerima instruksi seleksi, bukan aturan final |
| Moment discovery dan first-pass editing | OpusClip adapter | Pekerjaan probabilistik yang menjadi shortcut |
| Render/caption/reframe | OpusClip atau local FFmpeg | Dipilih per job; output tetap harus divalidasi |
| Compliance validation | scrapper-engine | Harus dapat diaudit dan direproduksi |
| Human approval | scrapper-engine | Wajib sebelum upload atau submission |
| Posting/publication | Manusia pada fase awal | Audio resmi, account, disclosure, dan platform rules membutuhkan tindakan manual |

### Alur end-to-end

```text
Campaign detail
    -> campaign_rules.compile_plan()
    -> preflight dan source-policy gate
    -> intake asset resmi + checksum
    -> staging URL sementara bila external engine dipakai
    -> OpusClip proposal/render job
    -> signed webhook atau polling fallback
    -> ambil clip + metadata + source timestamps
    -> scrapper-engine compliance validator
    -> visual QA dan candidate deduplication
    -> review queue
    -> human ACC: approved_for_manual_post
    -> download posting package
    -> posting manual
    -> catat URL submission
```

Job state tidak boleh melompati review. Tambahkan state adapter secara eksplisit, misalnya `external_submitted`, `external_processing`, `external_ready`, `external_failed`, dan `external_expired`. Setelah artifact diterima, job harus kembali ke `validate`, lalu `review`. Tidak ada transisi dari `external_ready` langsung ke `posted`.

### Kontrak adapter minimum

Buat interface vendor-neutral agar OpusClip tidak menjadi ketergantungan yang menyebar ke seluruh kode:

```text
submit(source_url, plan, render_profile) -> external_job_id
handle_callback(event) -> normalized_job_status
poll(external_job_id) -> normalized_job_status
list_candidates(external_job_id) -> candidate_manifest[]
download(candidate) -> local_artifact
cancel(external_job_id) -> result
```

`candidate_manifest` minimal harus memuat `campaign_id`, `source_asset_id`, `source_url`, `source_start`, `source_end`, `duration`, `external_provider`, `external_job_id`, `external_clip_id`, `preview_url`, `download_url`, `transcript_or_caption`, `provider_score`, dan `provider_metadata`. Metadata vendor tidak boleh menggantikan alasan internal. Scrapper-engine tetap menambahkan `rule_matches`, `rule_failures`, `visual_warnings`, `selection_reason`, `validator_status`, dan `review_status`.

Gunakan idempotency key berbasis `campaign_id + asset_checksum + rule_hash + engine + render_profile`. Jika job diulang, adapter tidak boleh membuat duplikasi tanpa sengaja. Simpan raw request, raw response, webhook signature result, timestamp, serta expiry artifact untuk audit.

### Aturan source policy sebelum external call

Sebelum URL dikirim ke vendor, worker harus memastikan hal berikut:

1. Asset tercantum pada resource campaign atau memenuhi aturan sumber yang disimpan di `plan.json`.
2. Campaign aktif dan tidak memiliki ambiguitas kritis.
3. File sudah diunduh atau tersedia melalui jalur yang sah; login, CAPTCHA, dan permission error masuk `needs_manual_download`.
4. URL staging tidak membuka asset lebih luas dari yang diperlukan dan memiliki TTL pendek.
5. Checksum file, ukuran, durasi, dan source asset ID sudah disimpan.
6. Tidak ada private material yang dikirim ke provider tanpa keputusan data-processing yang sesuai.
7. Tidak ada parameter vendor yang menginstruksikan penggunaan sumber lain, re-upload mentah, atau konten terlarang.

OpusClip dan Vizard terutama mendokumentasikan URL yang dapat diakses provider. **Jangan mengubah resource campaign privat menjadi URL publik permanen hanya agar API menerima input.** Gunakan signed URL berumur pendek bila vendor mendukungnya; bila tidak, pekerjaan masuk jalur lokal/manual.

### Aturan output dan validator

External engine boleh mengusulkan topik, durasi, judul, caption, dan crop. Setelah hasil diterima, validator lokal harus memeriksa kembali:

- sumber asset dan kesesuaian dengan checksum yang diizinkan;
- durasi minimum/maksimum campaign;
- aspect ratio dan resolusi;
- codec, frame rate, audio, serta ukuran file;
- subtitle/caption jika diwajibkan;
- handle, CTA, hashtag, disclosure, dan kata wajib;
- prohibited content, kata terlarang, re-upload mentah, dan footage tidak relevan;
- watermark resmi dan ketiadaan watermark pihak ketiga;
- keberadaan atau kebutuhan official platform audio;
- kecocokan visual, subtitle safe area, crop wajah/objek, dan frame yang rusak;
- overlap dan duplikasi antar kandidat;
- timestamp sumber dan alasan pemilihan.

Status validator tetap tiga tingkat:

- `pass`: semua gate terukur lulus;
- `needs_review`: ada aspek visual, semantik, legal, atau policy yang tidak dapat dipastikan mesin;
- `fail`: terdapat pelanggaran terukur atau artifact tidak dapat dipakai.

`pass` bukan approval publikasi. Kandidat yang `pass` hanya boleh masuk review queue. Satu `fail` wajib menghentikan kandidat tersebut dan tidak boleh disamarkan dengan rerender otomatis yang mengubah aturan campaign.

### Rendering: external-first, local-fallback

Gunakan dua jalur render yang konsisten:

- **External-first:** OpusClip membuat candidate clip dan render awal ketika job lolos source-policy gate.
- **Local fallback:** FFmpeg, faster-whisper, dan crop lokal tetap tersedia jika vendor gagal, URL kedaluwarsa, campaign melarang staging, atau output external tidak lolos visual QA.

Local pipeline tidak perlu dihapus. Ia berfungsi sebagai fallback deterministik, alat pembanding, dan jalur untuk campaign dengan privacy atau formatting khusus. Pada pilot, jalankan local scorer dalam mode shadow pada sumber yang sama. Dengan demikian keputusan untuk memperluas external adapter didasarkan pada hasil, bukan opini.

### Publishing tetap dimatikan

Jangan memanggil endpoint social publishing/scheduling vendor pada fase pilot. `publish_allowed` harus tetap `false` di `plan.json` dan di service layer. Approval internal `approved_for_manual_post` hanya berarti manusia menyatakan artifact siap diunggah secara manual; status itu bukan persetujuan platform atau Content Rewards.

Paket manual harus memuat MP4, thumbnail, caption draft, hashtag, disclosure, SRT bila ada, checklist official audio, account/platform target, dan link sumber. Setelah manusia memposting, URL publik baru dicatat sebagai submission. Ini mempertahankan aturan yang sudah dipakai scrapper-engine dan mencegah API vendor menjadi jalur bypass.

## Pilot praktis tiga langkah

### Langkah 1 — Bangun adapter dalam shadow mode

**Tujuan:** membuktikan integrasi end-to-end tanpa mengubah keputusan produksi.

Implementasikan hanya adapter OpusClip dengan satu provider. Input adapter berasal dari `plan.json`, bukan dari prompt bebas pengguna. Pilih 3–5 sumber campaign nyata yang sudah memiliki material resmi. Staging asset dilakukan melalui object storage sementara dengan TTL pendek. Kirim parameter berikut bila tersedia di plan: `topicKeywords`, `customPrompt`, min/max duration, source time range, language, aspect ratio, dan brand template.

Adapter harus menerima webhook bertanda tangan, tetapi menyediakan polling fallback. Simpan request dan response mentah. Unduh hasil ke workspace job dan jalankan validator yang sama dengan local render. **Jangan menampilkan external result sebagai siap posting dan jangan mengaktifkan publishing.**

Kriteria keluar langkah 1:

- minimal 3 job selesai tanpa kehilangan state;
- webhook atau polling dapat memulihkan job setelah worker restart;
- artifact dan timestamp dapat diunduh sebelum expiry;
- source checksum dan campaign ID tetap terhubung;
- tidak ada request external untuk asset yang gagal source-policy gate;
- `publish_allowed` tetap `false` pada seluruh jalur.

Jika OpusClip tidak dapat menerima URL staging dengan aman, segera hentikan jalur external untuk asset itu dan gunakan local fallback. Jangan menurunkan policy agar integrasi terlihat berhasil.

### Langkah 2 — Benchmark berpasangan dan pilih pemenang

**Tujuan:** membandingkan nilai shortcut terhadap pipeline lokal pada corpus target, bukan demo vendor.

Gunakan minimal 10–20 sumber yang mewakili footage campaign: talking-head, podcast, livestream, screen/tutorial, multi-speaker, bahasa Indonesia, audio bising, dan landscape yang perlu 9:16. Untuk setiap sumber, jalankan:

1. OpusClip dengan satu prompt/parameter yang berasal dari plan.
2. Local candidate scorer dan FFmpeg pipeline dalam mode pembanding.
3. Validator yang sama.
4. Review manusia yang dibutakan dari nama provider jika memungkinkan.

Ukur **yield kandidat yang dapat dipakai**, bukan jumlah clip. KPI yang relevan adalah:

| KPI | Cara menilai | Ambang pilot yang disarankan |
|---|---|---:|
| Candidate usable rate | Kandidat yang lulus validator dan human review dibagi total kandidat | OpusClip minimal setara local pipeline atau unggul ≥20% |
| Complete-moment rate | Kandidat yang memiliki hook, konteks, dan payoff tanpa boundary rusak | ≥80% dari kandidat yang dikirim ke review |
| Compliance pass rate | Kandidat yang tidak gagal karena aturan campaign | Tidak lebih rendah dari local baseline |
| Visual accept rate | Crop, subtitle, audio, dan watermark dapat diterima | ≥80% tanpa edit besar |
| Rework rate | Kandidat yang perlu rerender atau ditolak karena kualitas | ≤30% |
| Operational success | Job yang selesai dan artifact dapat diambil sebelum expiry | ≥95% |
| Cost per usable clip | Biaya provider dibagi clip yang benar-benar dapat dipakai | Tidak melebihi batas biaya yang disetujui |

Angka tersebut adalah **gates internal pilot**, bukan klaim kemampuan vendor. Bila Indonesian footage atau screen-heavy footage menghasilkan kualitas rendah, jangan menyimpulkan dari hasil talking-head saja. Jika OpusClip gagal pada completeness tetapi local scorer menang, tetap pertahankan local path untuk jenis source tersebut.

### Langkah 3 — Aktifkan routing terbatas, bukan auto-publish

**Tujuan:** memperoleh penghematan nyata dengan risiko yang tetap terkurung.

Jika OpusClip lulus benchmark, aktifkan routing external hanya untuk campaign dan source type yang terbukti. Contohnya, OpusClip dapat dipilih untuk interview/podcast landscape berbahasa Indonesia, sedangkan tutorial screen-heavy dan material privat tetap memakai local fallback. Buat feature flag per campaign atau per source class, bukan global switch.

Setiap hasil tetap melewati urutan `external_ready -> validate -> review -> approved_for_manual_post -> downloaded -> posted_manual -> submitted`. Mulai dengan maksimal satu atau dua candidate final per source. Jangan menaikkan volume hanya karena provider dapat membuat puluhan clip; tujuan sistem adalah **beberapa kandidat yang layak**, bukan output maksimum.

Tinjau setelah satu batch produksi manual. Perluas routing hanya bila yield, compliance, latency, dan biaya tetap memenuhi gate. Endpoint social publishing vendor tetap tidak dipakai sampai ada keputusan terpisah yang mencakup OAuth scope, approval UX, audit, platform terms, dan rollback.

## Keputusan terhadap tiap opsi setelah pilot

Keputusan akhir tidak boleh didasarkan pada harga bulanan atau video demo. Gunakan aturan berikut:

- **Tetapkan OpusClip** bila ia menang pada usable rate dan operational success tanpa menurunkan compliance pass rate. OpusClip menjadi proposal/render adapter utama.
- **Tetapkan Vizard sebagai fallback** bila template/Brand Kit lebih konsisten atau Vizard unggul pada corpus tertentu. Jangan menjalankan dua provider pada semua job secara permanen; lakukan routing berbasis source class untuk mengendalikan biaya.
- **Pilih Klap hanya bila** kualitas momen terbukti lebih baik dan tim bersedia memiliki polling, retry, expiry, serta base-URL compatibility layer sendiri.
- **Pilih Descript hanya bila** transcript-first editing memberikan keuntungan nyata pada podcast/interview dan publish-mediated export dapat diterima.
- **Tolak Munch sebagai dependency** sampai partner memberikan kontrak API tertulis dengan endpoint, auth, webhook, export, quota, dan SLA.
- **Batasi Captions pada captioning** bila API caption render-nya unggul; jangan menyamakan UI Clips dengan kapabilitas public API.

## Risiko yang harus diterima secara sadar

### Risiko kualitas momen

Semua provider utama memakai AI/probabilistic selection. Tidak ada dokumentasi yang menjamin setiap clip merupakan complete moment dengan batas sempurna. Bahkan review pengguna dan pengujian independen melaporkan selection yang kadang hit-or-miss, boundary abrupt, mixed topics, atau caption error.[27] [28] Karena itu provider score, virality score, coherence score, dan prompt tidak boleh menjadi approval otomatis.

### Risiko data dan sumber

URL publik dapat memudahkan integrasi tetapi meningkatkan permukaan akses. Signed URL, TTL, checksum, penghapusan artifact setelah expiry, dan log akses harus menjadi bagian adapter. Campaign asset yang memerlukan login atau memiliki batas data processing tetap diarahkan ke local pipeline.

### Risiko quota dan harga

OpusClip memiliki processing credits, minimum 10 credits per project, concurrency, expiry project, dan quota bulanan. Vizard memiliki batas request dan upload minutes yang berbeda antar dokumen. Klap mencantumkan harga API lama tanpa SLA/rate limit yang lengkap. Jangan membuat perhitungan production hanya dari halaman pricing. Minta konfirmasi tertulis tentang API entitlement, rate limits, retention, regional processing, dan biaya overage sebelum procurement.[29] [30] [31]

### Risiko API contract

Beberapa vendor mencampurkan kemampuan UI, API, Zapier, dan partner integration. **UI feature bukan bukti API feature.** Munch tidak memiliki public developer contract; Captions memiliki API yang jauh lebih sempit daripada UI; Descript memiliki konflik dokumentasi upload; OpusClip memiliki konflik batas upload dan tier API. Adapter harus menganggap setiap kemampuan tidak tersedia sampai endpoint, auth, payload, output, dan error behavior berhasil diuji.

### Risiko publikasi tanpa sengaja

Vendor yang menyediakan social posting dapat membuat shortcut teknis terlihat seperti shortcut produk. Namun campaign memerlukan approval, account rule, official audio, disclosure, dan kemungkinan pre-post review. Semua social posting API harus disabled di konfigurasi dan ditolak di service layer selama pilot.

## Checklist keputusan sebelum production

Sistem boleh mengaktifkan OpusClip sebagai adapter terbatas hanya jika semua pernyataan berikut benar:

1. `plan.json` sudah menjadi snapshot rules yang dapat diaudit.
2. Campaign dan asset lulus source-policy gate sebelum vendor dipanggil.
3. Provider adapter memiliki idempotency, retry, webhook verification, polling fallback, dan expiry handling.
4. Candidate manifest menyimpan source timestamp, checksum, provider job ID, dan raw metadata.
5. Validator lokal memeriksa ulang allowed/prohibited content, mandatory requirements, durasi, ratio, subtitle, watermark, CTA, handle, audio, dan platform.
6. Kegagalan validator menghentikan candidate, bukan mengubah rules.
7. Human review dapat ACC, reject, atau meminta rerender dan keputusan itu tersimpan.
8. `publish_allowed=false` tetap enforced meskipun provider mengembalikan endpoint publish.
9. Posting masih manual dan official platform audio ditandai sebagai tindakan manual bila diperlukan.
10. Ada local fallback untuk source type, privacy case, atau provider outage yang tidak cocok.
11. Benchmark corpus mencakup konten Indonesia dan screen-heavy footage.
12. Procurement telah mengonfirmasi API tier, quota, retention, data processing, dan biaya aktual.

## Kesimpulan final

**Shortcut yang dipilih: OpusClip sebagai external proposal/render adapter; scrapper-engine tetap menjadi otak, penjaga aturan, dan gerbang approval.** Ini memberi keuntungan tercepat dengan perubahan arsitektur paling kecil. Integrasi tidak perlu menunggu candidate scorer lokal sempurna, tetapi juga tidak mengorbankan source policy, mandatory requirements, allowed/prohibited content, audit, human approval, atau larangan auto-publish.

Jika OpusClip gagal benchmark, jangan kembali ke trial-and-error tanpa batas. Gunakan hasil gate untuk memilih satu jalur yang jelas: Vizard sebagai adapter kedua bila kebutuhan template dan webhook lebih penting; local FFmpeg/faster-whisper sebagai fallback deterministik untuk source type yang tidak cocok; Klap hanya sebagai pembanding jika API operational gaps dapat diterima. **Tidak ada alasan untuk mengintegrasikan Munch atau Captions sebagai engine clipping terotomasi tanpa kontrak API yang lebih lengkap.**

## Referensi

[1]: https://help.opus.pro/api-reference/endpoints/create-project "OpusClip API — Create project"
[2]: https://help.opus.pro/api-reference/webhook "OpusClip API — Webhooks"
[3]: https://help.opus.pro/api-reference/endpoints/get-clips "OpusClip API — Get clips"
[4]: https://help.opus.pro/api-reference/endpoints/social-posting/overview "OpusClip API — Social posting overview"
[5]: https://www.opus.pro/api "OpusClip API product overview"
[6]: https://help.opus.pro/api-reference/brand-template "OpusClip API — Brand template"
[7]: https://help.opus.pro/docs/article/how-to-enable-face-tracking "OpusClip Help — Face tracking"
[8]: https://help.opus.pro/docs/article/video-sources-supported "OpusClip Help — Supported video sources"
[9]: https://help.opus.pro/api-reference/overview "OpusClip API — Overview and limits"
[10]: https://docs.vizard.ai/docs/introduction "Vizard API — Introduction"
[11]: https://docs.vizard.ai/docs/basic "Vizard API — Basic clipping"
[12]: https://docs.vizard.ai/docs/advanced "Vizard API — Advanced clipping"
[13]: https://docs.vizard.ai/docs/retrieve-video-clips "Vizard API — Retrieve video clips"
[14]: https://docs.vizard.ai/docs/rate-limit "Vizard API — Rate limits"
[15]: https://docs.klap.app/usecases/generate-shorts "Klap API — Generate shorts"
[16]: https://docs.klap.app/endpoints/tasks "Klap API — Tasks"
[17]: https://docs.klap.app/endpoints/exports "Klap API — Exports"
[18]: https://cybernews.com/ai-tools/klap-ai-review/ "Cybernews — Klap AI review"
[19]: https://docs.descriptapi.com/ "Descript API documentation"
[20]: https://help.descript.com/repurpose/create-clips-from-your-content "Descript Help — Create clips from content"
[21]: https://help.descript.com/api-and-mcp/api "Descript Help — API and MCP"
[22]: https://help.munchstudio.com/en/articles/8485774-what-is-coherence-score "Munch Studio Help — Coherence Score"
[23]: https://help.munchstudio.com/en/articles/8163720-what-does-munch-do-with-my-videos "Munch Studio Help — What Munch does with videos"
[24]: https://captions.ai/help/docs/api/overview "Captions API — Overview"
[25]: https://captions.ai/help/docs/api/video-captions "Captions API — Video captions"
[26]: https://captions.ai/help/api-reference/video-captions/add-captions-to-a-video "Captions API — Add captions to a video"
[27]: https://www.g2.com/products/opusclip/reviews "G2 — OpusClip reviews"
[28]: https://www.eesel.ai/blog/captions-ai-review "Eesel — Captions AI review"
[29]: https://help.opus.pro/docs/article/plans-and-credits "OpusClip Help — Plans and credits"
[30]: https://docs.vizard.ai/docs/pricing "Vizard API — Pricing"
[31]: https://docs.klap.app/pricing "Klap API — Pricing"
