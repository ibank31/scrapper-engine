
# Campaign Agent Evolution Roadmap v2

**Repository:** ibank31/scrapper-engine  
**Target:** mengubah Scrapper Engine menjadi AI Campaign Agent + Clipping Agent yang memahami campaign secara menyeluruh, mengubah rules menjadi kontrak produksi yang dapat dieksekusi, memverifikasi hasilnya, dan menyisakan review manusia hanya untuk hal yang benar-benar membutuhkan manusia.  
**Strategi biaya:** free-first. Tidak ada kenaikan biaya AI sebelum ada bukti kualitas atau pendapatan yang membenarkan biaya tersebut.

> Dokumen ini adalah roadmap evolution/intelligence. docs/IMPLEMENTATION_ROADMAP.md tetap menjadi roadmap hardening pipeline/provider. Jika keduanya bersinggungan, contract keselamatan dan gate yang lebih ketat selalu menang.

---

## 0. North Star

Mesin semakin dekat ke tujuan ketika semakin banyak pekerjaan berpindah dari manusia ke mesin tanpa menurunkan kepatuhan campaign atau kualitas clip.

~~~text
Campaign mentah
  -> Evidence lengkap
  -> Campaign Brain
  -> Critic / Verifier
  -> Production Contract
  -> Material Plan
  -> Clip Strategy
  -> Render
  -> Compliance
  -> Review sederhana
  -> Buffer
  -> Outcome / Revenue
  -> Memory
  -> pembelajaran untuk campaign berikutnya
~~~

Human reviewer bukan penerjemah rules, bukan pemeriksa hashtag, dan bukan operator compliance. Human adalah quality-control terakhir.

---

## 1. Prinsip arsitektur permanen

### 1.1 Source facts adalah evidence

AI boleh menafsirkan, tetapi AI tidak boleh menghapus fakta eksplisit dari sumber.

Setiap rule penting harus bisa ditelusuri:

~~~text
rule -> evidence_id -> source -> location -> source_hash
~~~

Minimal field:

- rule_id
- type
- scope
- priority
- mandatory
- value
- source
- evidence_ids
- confidence
- interpretation_type

### 1.2 AI = reasoning, code = enforcement

AI:

- memahami bahasa;
- semantic interpretation;
- klasifikasi;
- conflict explanation;
- ambiguity resolution;
- candidate reasoning.

Kode deterministic:

- hashing;
- normalization;
- persistence;
- comparison;
- validation;
- state transition;
- caption compilation;
- retry;
- cost accounting.

### 1.3 Tidak ada silent rule loss

Jika source berisi 40 aturan lalu canonical brain berisi 38, mesin harus menyatakan kegagalan.

~~~text
RULE_COVERAGE < threshold
  -> critic
  -> reprocess
  -> jika masih gagal
  -> BLOCKED / MANUAL_REQUIRED
~~~

### 1.4 Ambiguity menjadi data

Gunakan status:

- explicit
- inferred
- conflicting
- ambiguous
- unsupported
- manual_required

Jangan diam-diam mengubah "tidak jelas" menjadi keputusan pasti.

### 1.5 Setiap keputusan punya evidence

Minimal:

~~~text
decision
reason
evidence
confidence
risk
action
~~~

---

## 2. Baseline saat roadmap dimulai

Controlled production-like E2E terakhir membuktikan:

- campaign dapat dibaca;
- material intake berjalan;
- 31 raw candidates terbentuk;
- 23 kandidat masuk candidate funnel;
- 2 output terpilih dan berhasil dirender;
- 2 output divalidasi;
- 2 preview sampai review;
- Buffer tidak dimutasi.

Namun E2E juga menemukan kegagalan intelligence:

**aturan eksplisit pada source tidak seluruhnya bertahan sampai posting package.**

Kasus Ryan Zofay menunjukkan source memiliki CTA, hashtag, dan handle platform-specific, tetapi AI-normalized rules kehilangan sebagian informasi tersebut.

Ini menjadi baseline failure CA-00 dan wajib menjadi golden regression fixture permanen.

---

## 3. North-star metrics

Roadmap tidak dianggap berhasil hanya karena test suite hijau.

### 3.1 Rule integrity

Critical Rule Preservation:

~~~text
critical_rules_preserved / critical_rules_source = 100%
~~~

Mandatory Rule Preservation:

~~~text
mandatory_rules_preserved / mandatory_rules_source = 100%
~~~

Evidence Coverage:

~~~text
>= 99% overall
100% critical + mandatory
~~~

Silent Rule Loss:

~~~text
0
~~~

### 3.2 Intelligence quality

Catat:

- source extraction recall;
- false rule creation;
- contradiction detection;
- ambiguity detection;
- campaign relevance;
- material-plan correctness;
- posting-package correctness.

### 3.3 Operational efficiency

Per campaign:

- wall-clock time;
- AI invocation count;
- cache hit rate;
- model loading time;
- media bytes;
- transcription time;
- render time;
- retry count;
- failure stage.

### 3.4 Business outcome

Saat revenue tersedia:

- clips produced;
- clips approved;
- clips published;
- clips rejected;
- rejection reason;
- views;
- reward;
- AI cost;
- compute estimate;
- net contribution.

~~~text
net contribution = revenue - attributable AI/compute/provider cost
~~~

---

## 4. Evaluation architecture

Setiap milestone wajib dievaluasi melalui 5 lapisan.

### E0 — Static contract

Validasi schema, invariants, hashes, enums, dan state transitions.

### E1 — Golden fixtures

Gunakan campaign nyata yang pernah gagal sebagai regression corpus.

### E2 — Differential evaluation

Bandingkan old pipeline vs new pipeline pada dataset yang sama.

Ukur:

- quality;
- regression;
- latency;
- AI calls;
- rule coverage.

### E3 — Controlled E2E

Jalankan website-equivalent flow. Tidak langsung provider mutation.

### E4 — Economic evaluation

Setelah revenue tersedia:

~~~text
quality gain vs incremental cost
~~~

Model mahal hanya boleh masuk jika ada alasan yang terukur.

---

## 5. Efficiency review yang wajib di setiap stage

Selain benar, setiap stage harus menjawab enam pertanyaan:

1. Apakah hasilnya benar?
2. Apakah stage ini benar-benar diperlukan?
3. Apakah stage ini melakukan pekerjaan yang sudah dilakukan stage lain?
4. Apakah hasilnya bisa di-cache?
5. Apakah AI bisa diganti deterministic code?
6. Berapa biaya runtime, bytes, model calls, dan retries?

Targetnya bukan "AI dipakai sebanyak mungkin".

Targetnya:

~~~text
minimum compute
+
minimum AI
+
maximum correctness
~~~

Jika sebuah stage tidak memberi information gain yang berarti, stage tersebut kandidat untuk dihapus, digabung, atau dijadikan conditional.

---

# 6. Roadmap milestone

## CA-00 — Evidence Contract

**Tujuan:** semua informasi campaign mentah menjadi immutable evidence.

Bangun:

- Evidence Ledger;
- source document IDs;
- URLs;
- content hashes;
- extracted text;
- source locations;
- evidence spans;
- extraction method;
- timestamps;
- source priority.

Tidak membangun model baru pada slice ini.

Acceptance:

- source fingerprint stabil;
- document-only rule dapat ditemukan;
- document changes menghasilkan fingerprint berbeda;
- mandatory rules memiliki provenance;
- Ryan Zofay CTA/hashtags/handles/duration seluruhnya dapat ditelusuri.

**Gate:** 100% critical + mandatory evidence coverage.

---

## CA-01 — Canonical Campaign Brain

**Tujuan:** evidence menjadi structured intelligence tanpa kehilangan fakta.

Domain:

~~~text
identity
objective
reward
platforms
content
production
material
posting
geography
safety
commercial
ambiguities
conflicts
evidence
confidence
~~~

Setiap rule menyimpan scope, priority, source, evidence, dan interpretation type.

Acceptance:

- critical preservation 100%;
- mandatory preservation 100%;
- zero silent loss;
- inferred value tidak otomatis menjadi mandatory.

---

## CA-02 — Campaign Critic

**Tujuan:** agent kedua membongkar kesalahan agent pertama.

Checks:

- missing rule;
- duplicate rule;
- contradiction;
- unsupported inference;
- platform scope mismatch;
- lost value;
- wrong CTA;
- wrong handle;
- wrong hashtag;
- missing material requirement.

Output:

~~~text
CRITICAL
WARNING
AMBIGUITY
INFO
~~~

Acceptance:

Golden corpus harus menemukan semua seeded rule-loss cases.

---

## CA-03 — Rule Reconciliation

**Tujuan:** menyelesaikan konflik antar source.

Hierarchy:

1. explicit current campaign instruction;
2. campaign-specific source;
3. authoritative platform/provider requirement;
4. structured campaign metadata;
5. historical memory;
6. generic model knowledge.

Historical memory tidak pernah boleh override current explicit mandatory rule.

Acceptance:

- konflik yang bisa diresolusikan -> resolved;
- konflik yang tidak aman -> manual_required;
- tidak ada silent choice.

---

## CA-04 — Production Contract Compiler

**Tujuan:** Campaign Brain menjadi execution contract.

Output:

~~~text
PRODUCTION_CONTRACT
MATERIAL_CONTRACT
CLIP_CONTRACT
POSTING_CONTRACT
COMPLIANCE_CONTRACT
~~~

Contoh:

~~~text
duration: 15-60
language: English
subtitle: required
hook: required
context: complete
forbidden: ...
platforms: ...
cta: exact
hashtags: exact
handles:
  instagram: [...]
  tiktok: [...]
~~~

Acceptance:

Setiap execution requirement punya chain:

~~~text
execution rule -> production contract -> campaign brain -> evidence
~~~

---

## CA-05 — Material Intelligence 2.0

**Tujuan:** memahami asset role, bukan sekadar menemukan URL.

Pertahankan:

- metadata-first;
- source identity;
- download budget;
- checksum;
- provenance.

Tambahkan:

- semantic asset role;
- required asset coverage;
- preferred/fallback reasoning;
- semantic duplicate detection;
- missing required asset detection.

Acceptance:

~~~text
required asset
  -> resolved
  OR
  -> explicit manual_required
~~~

Tidak ada "resolved" hanya karena URL ditemukan.

---

## CA-06 — Campaign-aware Clip Strategy

**Tujuan:** clip dipilih berdasarkan apa yang campaign bayar.

Pisahkan evidence:

~~~text
editorial_quality
campaign_relevance
rule_compliance
platform_fit
distinctness
risk
~~~

AI dipakai hanya jika semantic reasoning dibutuhkan.

Deterministic gates tetap authoritative.

Acceptance setiap final candidate memiliki:

- candidate_id;
- source_asset_id;
- transcript span;
- selection rationale;
- rule fit;
- risk;
- evidence.

---

## CA-07 — Posting Package Compiler

**Tujuan:** package dibuat dari rules, bukan dari ingatan AI.

Per platform:

~~~text
caption
handles
hashtags
disclosures
CTA
audio_policy
subtitle_delivery
native_tag_requirements
schedule_intent
~~~

AI tidak boleh membuat ulang mandatory fields setelah compiler.

Contoh Ryan Zofay harus deterministic menghasilkan platform-specific package berdasarkan evidence.

Acceptance:

- CTA preserved;
- exact required hashtags preserved;
- exact platform handles preserved;
- provenance preserved;
- unsupported native tags = manual_required;
- tidak ada invented hashtag.

---

## CA-08 — Final Campaign Compliance Gate

**Tujuan:** "MP4 valid" tidak sama dengan "campaign valid".

Gate:

~~~text
source
rules
duration
content
relevance
caption
CTA
handles
hashtags
disclosure
subtitle
audio
platform
distinctness
artifact
~~~

Hasil:

~~~text
PASS
PASS_WITH_MANUAL_STEP
BLOCKED
~~~

Review queue hanya menerima PASS atau PASS_WITH_MANUAL_STEP yang manual step-nya eksplisit.

---

## CA-09 — Indonesian Human Review Layer

**Tujuan:** evidence kompleks menjadi keputusan sederhana.

UI utama:

~~~text
✅ Durasi sesuai
✅ Caption sesuai
✅ Hashtag lengkap
✅ Mention sesuai platform
✅ Tidak ada pelanggaran
✅ Video berbeda dari clip lain

⚠️ Mesin kurang yakin pada hubungan video dengan tema campaign.
Alasan: ...
~~~

Jangan expose raw internal state sebagai pesan utama.

Acceptance:

Reviewer yang tidak memahami bahasa campaign tetap dapat:

- tahu video siap atau tidak;
- tahu exception;
- approve/reject kualitas dasar;
- tidak harus menerjemahkan rules.

---

## CA-10 — Campaign Memory

**Tujuan:** outcome historis menjadi structured memory.

Simpan:

~~~text
campaign fingerprint
rules version
material outcomes
candidate patterns
approved clips
rejected clips
rejection reasons
posting outcomes
revenue
~~~

Memory dipakai untuk retrieval, hints, ambiguity context, risk, dan cost routing.

Memory tidak boleh override current explicit rules.

Acceptance:

historical memory tidak dapat mengubah current mandatory rule.

---

## CA-11 — Self-Evaluation Loop

**Tujuan:** agent memeriksa dirinya sendiri sebelum human.

Self-check:

~~~text
source completeness
rule coverage
contradictions
material readiness
output contract
posting contract
unresolved ambiguity
confidence
~~~

Acceptance:

critical unresolved issue selalu memblokir production.

---

## CA-12 — Adaptive AI Router

**Tujuan:** free/local model menjadi default, premium hanya sebagai escalation.

Routing:

~~~text
LEVEL 0 deterministic
      ↓
LEVEL 1 local/free
      ↓
LEVEL 2 stronger free/low-cost
      ↓
LEVEL 3 premium
~~~

Trigger escalation:

- confidence rendah;
- contradiction sulit;
- high-value campaign;
- repeated previous failure;
- expected quality gain membenarkan cost.

Acceptance:

setiap escalation mempunyai reason yang tercatat.

---

## CA-13 — Cost Governor

**Tujuan:** tidak ada hidden AI cost.

Setiap AI invocation mencatat:

~~~text
provider
model
reason
input size
output size
duration
cache hit
estimated cost
fallback
~~~

Acceptance:

setiap call dapat dijelaskan dan diatribusikan ke stage.

---

## CA-14 — Economic Learning

**Tujuan:** mesin tahu kapan effort tambahan layak secara bisnis.

Gunakan:

~~~text
revenue
- provider cost
- AI cost
- compute estimate
= contribution
~~~

Bandingkan pipeline murah vs pipeline dengan escalation.

Acceptance:

model premium hanya dipakai ketika expected value positif menurut policy yang dikalibrasi dengan data.

---

# 7. Golden Campaign Corpus

Lokasi yang disarankan:

~~~text
tests/fixtures/campaigns/
~~~

Kategori:

- document-only;
- conflicting sources;
- platform-specific;
- ambiguous;
- material-heavy;
- restrictive;
- multilingual;
- no-valid-candidate;
- duplicate-heavy;
- payout-critical;
- posting-specific.

Setiap bug baru menjadi:

~~~text
fixture
+
expected result
+
regression test
+
decision log
~~~

Prinsip:

**bug yang sudah ditemukan tidak boleh ditemukan dua kali.**

---

# 8. Regression layers

## Layer 1 — Unit

Parser, normalizer, validator, selector, compiler.

## Layer 2 — Contract

Memastikan data tidak rusak antar stage.

Contoh:

~~~text
source
 -> campaign brain
 -> production contract
 -> posting package
~~~

CTA yang sama harus tetap sama.

## Layer 3 — E2E

Website-equivalent production-like flow.

## Layer 4 — Outcome

Jika revenue tersedia, korelasikan keputusan dengan hasil nyata.

---

# 9. Change protocol

Setiap perubahan mengikuti:

1. pilih satu milestone;
2. tulis hypothesis;
3. tetapkan acceptance metric;
4. tambahkan/ubah fixture;
5. implement perubahan minimal;
6. unit tests;
7. contract tests;
8. differential evaluation;
9. E2E bila relevan;
10. catat evidence;
11. update status/decision log;
12. merge;
13. stop.

Jangan memulai milestone berikutnya dalam slice yang sama.

---

# 10. E2E protocol

E2E wajib untuk perubahan pada:

- campaign interpretation;
- material intake;
- candidate funnel;
- output contract;
- rendering;
- validation;
- posting package;
- state transitions.

Tidak wajib untuk kosmetik UI murni.

E2E harus merekam:

~~~text
campaign_id
job_id
run_id
rules_hash
brain_version
production_contract_version
material counts
candidate counts
AI calls
render count
validation count
review state
manifest
new bugs
~~~

### Stop condition

Jika E2E menemukan bug baru yang valid:

~~~text
STOP
record bug
preserve evidence
do not mix unrelated fixes
~~~

---

# 11. Free-first AI policy

Default:

- deterministic code;
- local Qwen atau model lokal setara;
- cache;
- existing free API capacity;
- GitHub Actions free allocation;
- Cloudflare free-tier resources.

Tidak boleh:

- membeli API karena hype;
- memakai premium untuk regex atau exact extraction;
- mengulang AI pada fingerprint identik;
- menjalankan full analysis jika cache valid.

Premium activation harus memenuhi:

~~~text
measured failure
+
measured quality gap
+
measured campaign value
~~~

---

# 12. Model benchmark protocol

Jangan mengganti model hanya karena ada model baru.

Gunakan fixed benchmark:

~~~text
100 campaign rule cases
50 conflict cases
50 ambiguity cases
100 posting-rule cases
100 candidate relevance cases
~~~

Ukur:

- critical rule recall;
- mandatory rule recall;
- hallucination rate;
- contradiction detection;
- relevance quality;
- latency;
- memory;
- AI calls;
- cost.

Model baru hanya menang jika improvement relevan dengan target dan tidak merusak invariant.

---

# 13. Documentation protocol

Empat dokumen utama:

### STATUS.md

Current state, latest verified evidence, active milestone, blockers.

### docs/IMPLEMENTATION_ROADMAP.md

Hardening pipeline/provider.

### docs/CAMPAIGN_AGENT_ROADMAP.md

Evolution intelligence dan evaluation protocol.

### docs/DECISION_LOG.md

Mengapa keputusan arsitektur dibuat dan alternatif apa yang ditolak.

### docs/AGENT_HANDOFF.md

Snapshot operasional untuk agent berikutnya:

~~~text
current milestone
last verified commit
last E2E
known bugs
next exact slice
verification baseline
~~~

---

# 14. Branch discipline

~~~text
main
 |
 +-- feat/campaign-evidence
 +-- feat/campaign-brain
 +-- fix/rule-loss
 +-- feat/posting-compiler
~~~

Satu branch = satu bounded objective.

Setelah merge, branch yang tidak diperlukan lagi dihapus.

---

# 15. Definition of Done: "Campaign Agent pintar"

### Understanding

- memahami seluruh source;
- tidak kehilangan mandatory rules;
- memahami platform scope;
- menemukan conflict;
- menemukan ambiguity.

### Planning

- membuat production contract;
- material plan;
- clipping strategy;
- posting package.

### Verification

- self-check;
- evidence;
- block bad output;
- explain uncertainty.

### Adaptation

- menggunakan memory;
- tetap tunduk pada current rules;
- memilih model sesuai kebutuhan.

### Economics

- mengetahui kapan extra AI effort layak;
- mengukur cost;
- menghubungkan quality dengan outcome.

---

# 16. Urutan kerja aktual

Jangan mengerjakan CA-00 sampai CA-14 sekaligus.

~~~text
NOW
 |
 +-- CA-00 Evidence Contract
 |
 +-- CA-01 Campaign Brain
 |
 +-- CA-02 Campaign Critic
 |
 +-- CA-03 Rule Reconciliation
 |
 +-- CA-04 Production Contract
 |
 +-- CA-05 Material Intelligence
 |
 +-- CA-06 Clip Strategy
 |
 +-- CA-07 Posting Compiler
 |
 +-- CA-08 Compliance Gate
 |
 +-- CA-09 Human Review
 |
 +-- CA-10 Memory
 |
 +-- CA-11 Self Evaluation
 |
 +-- CA-12 AI Router
 |
 +-- CA-13 Cost Governor
 |
 +-- CA-14 Economic Learning
~~~

**Prioritas pertama: CA-00 sampai CA-04.**

Tidak ada gunanya membuat clipping semakin pintar jika Campaign Agent masih dapat kehilangan aturan campaign.

---

# 17. First implementation slice

**CA-00-A — Evidence Ledger + Ryan Zofay regression**

Scope:

- evidence representation;
- document hashing;
- rule evidence references;
- Ryan Zofay fixture;
- tests CTA/hashtags/handles/duration;
- no Buffer;
- no model replacement.

Acceptance:

~~~text
[PASS] stable source fingerprint
[PASS] document-only rule retained
[PASS] CTA retained
[PASS] hashtag retained
[PASS] platform handle retained
[PASS] provenance attached
[PASS] zero silent rule loss
[PASS] existing regression suite
~~~

Setelah CA-00-A lulus, lanjut CA-00-B. Jangan melompat langsung ke Campaign Critic.

---

# 18. Long-term operating loop

~~~text
CAMPAIGN
   ↓
EVIDENCE
   ↓
CAMPAIGN BRAIN
   ↓
CRITIC
   ↓
PRODUCTION CONTRACT
   ↓
EXECUTION
   ↓
COMPLIANCE
   ↓
HUMAN QC
   ↓
PUBLISH
   ↓
REVENUE / PERFORMANCE
   ↓
MEMORY
   ↓
BETTER DECISION
   └──────────────→ CAMPAIGN AGENT
~~~

Ukuran keberhasilan akhirnya bukan "model semakin besar".

Ukuran keberhasilannya:

**informasi semakin sedikit hilang, keputusan semakin tepat, uncertainty semakin jujur, compute semakin efisien, human work semakin kecil, dan hasil bisnis semakin baik.**

---

## Operating rule

Setiap sesi engineering di Scrapper Engine harus bisa menjawab empat kalimat:

~~~text
Apa yang sedang diperbaiki?
Bagaimana kita mengukur perbaikannya?
Bagaimana kita membuktikannya?
Apa bug berikutnya yang ditemukan?
~~~

Jika empat jawaban itu tidak jelas, sesi belum memiliki scope yang sehat.
