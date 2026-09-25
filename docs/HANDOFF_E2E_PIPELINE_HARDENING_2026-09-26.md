# HANDOFF — SCRAPPER ENGINE E2E PIPELINE HARDENING

**Date:** 2026-09-26  
**Repository:** `ibank31/scrapper-engine`  
**Branch:** `hardening/e2e-pipeline-contracts`  
**Production branch:** `main`  
**Cloudflare Pages:** `clipper-engine`

## 1. Objective

The project goal is not merely to generate one video successfully. Scrapper Engine is intended to become a reliable asset-production engine for additional income.

The required end-to-end chain is:

```
CAMPAIGN
  -> CAMPAIGN INGESTION
  -> MATERIAL / REFERENCE DISCOVERY
  -> SOURCE CLASSIFICATION
  -> SOURCE ACCESS PREFLIGHT
  -> ASSET MANIFEST
  -> DOWNLOAD / ACQUISITION
  -> MEDIA VALIDATION
  -> CONTENT ANALYSIS
  -> OPPORTUNITY / CLIP DISCOVERY
  -> AI RANKING
  -> TOP CANDIDATE SELECTION
  -> VIDEO GENERATION
  -> QUALITY CONTROL
  -> STORAGE / PREVIEW
  -> DELIVERY
  -> HISTORY / METRICS
```

Every stage must have explicit input, output, state, error reason, and recovery behavior.

Do not optimize only the rendering/video stage. Correctness and reliability of the whole pipeline come first.

## 2. Current production context

- Repository: `ibank31/scrapper-engine`
- Branch used for production: `main`
- Cloudflare Pages project: `clipper-engine`
- Worker pipeline is executed through GitHub Actions.
- D1 is the control plane.
- R2 stores previews/output artifacts.
- Current production pipeline already contains substantial work for bounded downloads, disk safety, candidate generation, semantic ranking, early stopping, and dispatch recovery.

## 3. Important recent production failures

These failures motivated this hardening work:

### Yomi
- A previous run filled the GitHub Actions disk while downloading Google Drive material.
- Partial files were subsequently mistaken for usable media.
- Later Yomi runs could discover/transcribe sources but still produce zero usable candidates.
- A generic UI message such as `Sumber video campaign belum tersedia` did not expose the exact source-level reason.

### Jo Koy
- A production run reached the worker timeout without producing a mature asset.

### Dardan
Campaign:
`ad3ee67d-37c4-418a-83f9-206eb5ae08f8`

The campaign plan contains a Google Doc reference and text such as:

`Music video: Dardan - Erinnerung (Official Video)`

The text is a named media reference, not a URL.

The current intake logic extracts explicit URLs, Drive sources, YouTube sources, etc., but previously had no controlled resolver for named media references.

## 4. Architectural lesson

Do not confuse:

- discovery of explicit URLs
- resolution of named references
- verification of source access
- download
- validation of a real media file

They are separate states.

Likewise, a campaign brief can contain:

- primary source footage
- source collections
- official source references
- examples/inspiration
- lyrics
- documents
- tools
- symbolic assets such as `brandAsset`

A TikTok example must not automatically become source footage.

A named official video must not automatically become a source merely because a search engine returns a similarly named result.

## 5. Work already started on this branch

### A. `core/media_validation.py`

Added cheap media validation before expensive analysis.

It uses `ffprobe` and checks:

- file exists
- file size > 0
- supported video extension
- real video stream
- audio stream
- duration
- video codec
- audio codec
- width/height
- container

Output is structured and includes an `issues` array.

The intended gate is:

`downloaded -> media_validation -> usable_for_analysis`

A downloaded filename must never be treated as proof that the asset is valid.

### B. `core/material_references.py`

Added reference extraction/classification.

It supports:

- explicit URL extraction
- line/context evidence
- named media reference extraction
- source/reference classification
- symbolic reference detection
- controlled YouTube metadata search for named video references

Current classifications include:

- `PRIMARY_SOURCE`
- `PRIMARY_SOURCE_CANDIDATE`
- `REFERENCE_ONLY`
- `AMBIGUOUS_REFERENCE`
- unresolved named references

Named YouTube resolution is metadata-only. It does not download the candidate automatically.

Verification currently considers title similarity and an `official` hint. It should be strengthened during integration where campaign/brand/channel evidence is available.

## 6. Current branch state

The branch contains the two new modules above.

The branch is **NOT production-ready**.

Do not merge into `main` yet.

Do not dispatch a production campaign merely to test these changes.

## 7. Required next implementation

### Step 1 — Integrate reference classification into intake

Modify:

`modules/reward_campaign/intake.py`

The current intake already handles:

- Google Docs
- Google Sheets
- Drive folders
- Drive files
- YouTube videos
- YouTube collections
- direct media URLs
- bounded downloads
- fair source queueing
- asset manifest generation

Integrate `core/material_references.py` without removing existing capabilities.

For Google Docs:

1. Save the document text.
2. Extract explicit URLs.
3. Extract named media references.
4. Classify references.
5. Keep reference-only URLs auditable but do not download them as primary footage.
6. For a primary named video reference, attempt controlled metadata resolution.
7. Only promote a search result to a source candidate when deterministic verification passes.
8. Otherwise mark it `UNRESOLVED_REFERENCE`.

Do not silently discard unresolved references.

### Step 2 — Resolve symbolic assets safely

For values such as:

`brandAsset`

look for an existing campaign asset/resource mapping first.

If a mapping exists:
- resolve it to the actual asset.

If no mapping exists:
- mark `UNRESOLVED_SYMBOLIC_ASSET`.

Never invent a URL.

### Step 3 — Build a complete asset preflight

The intake manifest must clearly expose:

- references discovered
- explicit URLs discovered
- named references discovered
- primary sources
- reference-only sources
- unresolved references
- inaccessible sources
- video assets discovered
- accessible video assets
- download attempts
- successful downloads
- failed downloads
- deferred assets
- valid media assets
- invalid media assets
- total downloaded bytes
- final `READY_FOR_PROCESSING` count

Desired conceptual report:

```
ASSET PREFLIGHT

References discovered: 7
Primary video sources: 3
Reference/example sources: 4

Video assets discovered: 23
Accessible: 21
Inaccessible: 2

Downloaded: 8
Download failed: 1
Deferred: 14

Media validation:
  valid: 7
  invalid: 1

READY FOR PROCESSING: 7
```

Exact numbers are examples only.

### Step 4 — Add a hard media gate

Before Whisper or expensive semantic analysis:

```
READY_FOR_PROCESSING > 0
```

must be true.

If zero:
- stop cleanly
- do not download Whisper
- do not transcribe
- do not run expensive semantic analysis
- return structured source-level diagnostics

### Step 5 — Propagate stage state

Every stage should eventually have:

- stage name
- status
- started_at
- ended_at
- error_code
- error_detail
- metrics

Use existing D1/job stage infrastructure rather than inventing a parallel tracking system.

### Step 6 — Improve job diagnostics

Replace generic errors such as:

`Sumber video campaign belum tersedia`

with structured diagnostics that can answer:

- What references were found?
- Which were primary sources?
- Which were examples?
- Which were unresolved?
- Which sources were inaccessible?
- Which assets downloaded?
- Which failed?
- Which files failed media validation?
- Why was processing blocked?

The user-facing UI may still show a concise message, but the underlying job state must retain the full diagnostic payload.

## 8. Testing requirements

Add unit tests for at least:

### Material references
- explicit YouTube URL
- explicit Drive URL
- direct media URL
- TikTok example/reference
- named `Music video: Dardan - Erinnerung (Official Video)`
- ambiguous named reference
- `brandAsset`
- unknown symbolic asset

### Named YouTube resolver
Mock `yt-dlp` metadata output.

Test:
- valid title match
- weak title match
- official-reference mismatch
- no result
- yt-dlp failure
- malformed JSON

Do not perform live YouTube searches in unit tests.

### Media validation
Mock/fixture:
- valid video with audio
- video without audio
- corrupted file
- empty file
- unsupported extension
- too-short media

### Intake
Test a Google Doc containing:
- one primary named video
- explicit source URL
- two example URLs
- one symbolic asset

Expected behavior:
- primary source candidates are separate from examples
- named reference is resolved or explicitly unresolved
- no reference is silently lost
- manifest contains source-level evidence

## 9. Regression requirements

Do not break existing behavior for:

- Google Drive recursive discovery
- Drive shortcuts
- YouTube playlist/channel expansion
- download byte budget
- download asset budget
- disk safety margin
- fair queue
- source deduplication
- early stopping
- global semantic ranking
- dispatch recovery
- D1 job state
- R2 preview flow
- output contract
- human review gate

## 10. Production safety

Until tests pass:

- do not merge into `main`
- do not trigger production campaign runs
- do not delete existing production data
- do not alter secrets
- do not print secret values
- do not introduce paid APIs as a shortcut

The project is intended to remain free-first.

## 11. Definition of done for this hardening phase

This phase is complete only when:

1. Tests pass.
2. Intake produces a complete auditable material/source manifest.
3. Named references are resolved or explicitly marked unresolved.
4. Examples are not mistaken for primary footage.
5. Symbolic assets are resolved through real mappings or marked unresolved.
6. Downloaded files pass real media validation.
7. Expensive analysis cannot start with zero valid video assets.
8. Job diagnostics expose exact failure causes.
9. Existing production optimizations still pass regression tests.
10. A controlled end-to-end test can demonstrate:

```
campaign
 -> material
 -> discovery
 -> classification
 -> access
 -> acquisition
 -> validation
 -> analysis
 -> candidate
 -> ranking
 -> render
 -> QC
 -> R2
```

Only after that should the changes be considered for production.

## 12. Do not repeat the old workflow

Do NOT:

- keep trying random campaigns
- optimize Whisper before asset acquisition is proven
- treat a URL as proof of accessibility
- treat a downloaded filename as proof of valid media
- treat every link in a brief as footage
- blindly download every reference/example
- silently discard unresolved references
- add paid APIs just to make a test pass
- rewrite working downstream systems unnecessarily
- redo the entire project audit from zero

Continue from this handoff and work forward.

## 13. Immediate next task

The next agent should:

1. Inspect the current branch.
2. Integrate `core/material_references.py` into `modules/reward_campaign/intake.py`.
3. Integrate `core/media_validation.py` into the intake/worker boundary.
4. Produce structured asset-preflight data.
5. Add the required unit tests.
6. Run the full test suite.
7. Review the diff for regressions.
8. Only then prepare a controlled E2E test plan.

Do not claim the engine is production-ready until the E2E chain has actually been demonstrated.

## 2026-09-26 continuation update

Additional hardening completed after the initial handoff:

- `_resolve_symbolic_asset()` now resolves symbolic references only from explicit campaign-plan mappings and otherwise emits `UNRESOLVED_SYMBOLIC_ASSET`.
- Google Doc symbolic references now enter the auditable reference manifest with resolution status and mapping evidence.
- Worker no longer falls back to scanning raw workspace video files when a modern `asset_manifest` is present. This prevents an invalid/unvalidated file from bypassing the media-validation gate.
- Zero-ready-source diagnostics now propagate the structured `asset_preflight` metrics into the job error/stage telemetry.
- Added regression coverage for mapped, normalized, and unresolved symbolic assets.

Latest commits on branch:
- `b78b28cbbdd30774122fce2100fccaf76a2a51ae` — safe symbolic asset resolution
- `7d0caae76b5d1133e47237f9239655167d46851d` — enforce validated asset manifest at worker gate
- `5d93611e086bd4beb22bcd58650bda684b28d148` — symbolic asset regression tests

CI still needs to be observed on PR #12. The branch remains non-production until deterministic CI and controlled real-asset E2E are proven.
