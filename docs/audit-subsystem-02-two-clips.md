# Audit: Two Distinct Finished Videos per Campaign

**Subsystem:** candidate selection, duplicate filtering, rendering, review outputs, and review persistence  
**Audit mode:** read-only repository audit; no production code, Buffer posts, or external state was changed  
**Conclusion:** **Two materially distinct Tier 1/Tier 2 finished videos are not guaranteed by the current implementation.** A normal successful run can produce two previews, and the documented smoke test did produce two, but the code has no campaign-level invariant requiring exactly two successful, materially distinct outputs or requiring one Tier 1 and one Tier 2 output.

## Scope and interpretation

The repository does not define a formal video-level meaning for “Tier 1” and “Tier 2.” The only explicit Tier 1 reference found is a campaign metadata flag, `EN/Tier-1`, assigned while scraping campaign text; it is not a candidate tier, render tier, or output requirement ([`modules/reward_campaign/scrape.py:69-75`](../modules/reward_campaign/scrape.py#L69-L75)). This report therefore audits the requirement in its strongest practical form: every eligible campaign should finish with two reviewable videos, the pair should be materially different, and the pair should satisfy any intended Tier 1/Tier 2 allocation. Where the intended tier definition is unavailable, that is recorded as an assumption or gap rather than inferred.

## Overall finding

The current flow is **“select up to two, render whatever succeeds, retain any non-failing preview, and mark the job ready for review.”** It is not **“produce exactly two pairwise-distinct videos, enforce their tier allocation, and block the campaign unless both pass.”** The distinction matters because the worker, validator, review queue, API, schema, and frontend all accept a variable number of previews.

The prior handoff records one successful run with `rendered_count=2`, `result_count=2`, and `preview_count=2` ([`docs/AGENT_HANDOFF.md:248-252`](../docs/AGENT_HANDOFF.md#L248-L252)). That is production evidence of one observed success, not proof of an invariant. The same implementation permits one output whenever only one candidate survives selection, rendering, or validation.

## Findings

### F-01 — The pipeline does not enforce two finished outputs per campaign (**blocker**)

**Current behavior.** The worker sets `MAX_REVIEW_CANDIDATES = 2`, but `select_distinct_candidates` returns *up to* the requested limit. The worker proceeds with one selected item if only one survives candidate collection and distinct filtering ([`worker/run_job.py:30-31`](../worker/run_job.py#L30-L31), [`worker/run_job.py:355-368`](../worker/run_job.py#L355-L368)). Rendering appends only outputs whose `clip-001.mp4` exists, then proceeds unless the list is empty; the failure guard says “two candidates” but only checks `if not all_candidates`, not `len(all_candidates) < 2` ([`worker/run_job.py:375-390`](../worker/run_job.py#L375-L390)). Validation explicitly keeps usable outputs when another candidate fails, and the worker blocks only when *all* results fail ([`worker/run_job.py:394-410`](../worker/run_job.py#L394-L410)).

The review queue emits one item or two items without asserting a count ([`modules/clipping/review_queue.py:103-158`](../modules/clipping/review_queue.py#L103-L158)). The upload loop skips blocked items and sends every remaining item; it does not require two uploads before setting the job to review ([`worker/run_job.py:415-448`](../worker/run_job.py#L415-L448)). The API accepts an arbitrary `body.previews` array and marks the job `review` using that array's length, including one item ([`cloudflare/api.js:501-508`](../cloudflare/api.js#L501-L508)).

**Impact.** A campaign can reach `review` with zero previews only through an unusual route outside the explicit all-failed/no-candidate blocks, or with one preview in the ordinary “one candidate available / one render survives / one validator passes” case. The system therefore cannot truthfully promise two finished videos per campaign.

**Target behavior.** Define a campaign output contract such as `required_finished_videos=2`. The job must remain blocked or `insufficient_outputs` unless exactly two outputs are selected, rendered, validated, uploaded, and persisted. If the campaign permits fewer than two as an explicit exception, that exception must be a stored campaign rule and visible in the review UI; it must not be an accidental consequence of list length.

### F-02 — No Tier 1/Tier 2 video allocation exists (**blocker**)

**Current behavior.** Scraping can add the string `EN/Tier-1` to campaign flags when campaign text contains tier-related language ([`modules/reward_campaign/scrape.py:69-75`](../modules/reward_campaign/scrape.py#L69-L75)). The clipping selector ranks candidate windows by a numeric score and returns non-overlapping candidates; it has no tier field or tier quota ([`core/clip_candidates.py:164-224`](../core/clip_candidates.py#L164-L224)). The worker combines candidates from sources, sorts them by score through `select_distinct_candidates`, and selects the first two; it does not require one candidate of each tier or even preserve the campaign flag into a candidate-level decision ([`worker/run_job.py:285-352`](../worker/run_job.py#L285-L352), [`worker/run_job.py:366-372`](../worker/run_job.py#L366-L372)). The semantic and production scoring paths likewise expose scores and reasons, not Tier 1/Tier 2 labels ([`core/production_policy.py:138-182`](../core/production_policy.py#L138-L182)).

**Impact.** If “Tier 1/Tier 2” means two required output classes, the current system can return two high-scoring clips from the same class, or two clips without any class assignment. If it means a campaign’s Tier 1 audience flag, that flag still does not constrain the two video outputs.

**Target behavior.** The campaign plan must define the tier taxonomy and whether the requirement is “one Tier 1 plus one Tier 2,” “two Tier 1 outputs,” or another allocation. Candidate records need a deterministic `tier` (or an explicit `tier: unknown`), and selection must satisfy the allocation before score optimization. The final manifest, validation payload, preview rows, and UI should expose the selected tier for each video.

### F-03 — Candidate distinctness is heuristic and not sufficient for “materially distinct” (**high**)

**Current behavior.** `candidates_are_near_duplicates` only treats candidates from the same `source` as overlapping duplicates. It marks same-source windows as duplicates when intersection is at least 45% of the shorter duration, or when token-set Jaccard similarity is at least 0.82 with duration difference no more than 12 seconds ([`core/clip_candidates.py:227-246`](../core/clip_candidates.py#L227-L246)). `select_distinct_candidates` then greedily retains the highest-scoring candidates until the limit ([`core/clip_candidates.py:249-258`](../core/clip_candidates.py#L249-L258)).

This leaves several material false negatives. Identical or near-identical content delivered in two different source files is never compared because different source paths immediately return `False`. Two same-source windows can share most of their narrative while falling just below the 45% overlap threshold. Token sets ignore word order and repeated counts, so the similarity test is not a robust transcript comparison. No audio fingerprint, scene fingerprint, perceptual video hash, or normalized transcript fingerprint is persisted for pairwise review.

Source-level duplicate filtering is also limited to an exact `duplicate_hash` from preflight and occurs only after the worker has already truncated the source list to `max_sources` ([`worker/run_job.py:231-255`](../worker/run_job.py#L231-L255)). Thus, duplicate assets can consume the source quota and prevent a later unique source from entering the pipeline. This is separate from candidate-window distinctness and can reduce the pool needed to obtain two genuinely different videos.

**Impact.** Two previews can be different filenames and ranks while being materially the same spoken moment, especially when the same source was mirrored or transcoded, or when two sources contain the same program segment.

**Target behavior.** Define a pairwise distinctness policy with at least: normalized transcript similarity, temporal overlap for the same source, source identity normalization, and a media fingerprint for cross-source duplicates. Distinctness should be evaluated after selection and again on final rendered artifacts. A pair that fails the threshold should be rejected or replaced before the job can enter review.

### F-04 — Technical validation is per-video only; it does not validate the pair (**high**)

**Current behavior.** `check_video` validates stream existence, 1080×1920 dimensions, H.264/AAC properties, frame rate, duration bounds, and campaign relevance for one candidate at a time ([`modules/clipping/validate.py:41-103`](../modules/clipping/validate.py#L41-L103)). The command maps each filename rank to one candidate and returns independent results ([`modules/clipping/validate.py:106-140`](../modules/clipping/validate.py#L106-L140)). There is no check for the number of results, pairwise overlap, transcript similarity, tier coverage, or materially different media. The worker treats any non-all-fail result as eligible to continue ([`worker/run_job.py:394-410`](../worker/run_job.py#L394-L410)).

**Impact.** Both videos can individually pass every technical gate while the pair is duplicate-looking, or only one can pass while the campaign is still marked ready for review.

**Target behavior.** Add a campaign-level validation result containing `expected_count`, `finished_count`, `distinctness_status`, `tier_status`, and per-pair evidence. The job should block on any failed pair invariant, not merely when every individual file fails.

### F-05 — Render outputs are deterministic per rank but do not guarantee two successful artifacts (**high**)

**Current behavior.** The worker renders each selected candidate into a temporary directory, expects `clip-001.mp4`, and copies it to `clip-001.mp4` or `clip-002.mp4` in the shared output directory ([`worker/run_job.py:375-386`](../worker/run_job.py#L375-L386)). The renderer itself creates one output per candidate rank and applies the candidate’s `start` and `duration` to ffmpeg; it does not compare outputs or enforce a pair contract ([`modules/clipping/render.py:56-82`](../modules/clipping/render.py#L56-L82)). If a render command succeeds but the expected file is absent, the worker silently omits that item and can continue with the other item; only an empty final list raises an error ([`worker/run_job.py:381-390`](../worker/run_job.py#L381-L390)).

**Impact.** Output names and 9:16 technical properties are deterministic, but count and pair distinctness are not. The final artifact naming convention should not be mistaken for proof that both outputs exist or are materially different.

**Target behavior.** Make each selected candidate a required render task. Record a render result for every expected rank, fail the campaign-level render stage if any required rank is missing, and compare final artifacts before upload. Use stable candidate IDs rather than rank alone for traceability.

### F-06 — Review persistence and UI surface a variable number of previews without a completeness warning (**medium**)

**Current behavior.** The schema defines a `previews` table with rank and status but no unique `(job_id, rank)` constraint, no expected count, no tier column, and no distinctness evidence ([`cloudflare/schema.sql:56-74`](../cloudflare/schema.sql#L56-L74)). The API inserts or replaces whatever preview list the worker sends and updates the job to `review` based on that list ([`cloudflare/api.js:501-508`](../cloudflare/api.js#L501-L508)).

The production frontend loads all previews returned by the API and labels them only as “Kandidat N”; it does not display expected-versus-actual count, tier, or pairwise distinctness status ([`web/app.js:214-233`](../web/app.js#L214-L233), [`web/app.js:289-326`](../web/app.js#L289-L326)). The demo path always fabricates two review entries, which can make the requirement appear guaranteed even though it is not representative of production behavior ([`web/app.js:132-143`](../web/app.js#L132-L143)).

**Impact.** A reviewer receives no machine-visible warning that a campaign has only one output or that both outputs belong to the same tier. Review status means “some previews exist,” not “the two-video campaign contract is complete.”

**Target behavior.** Persist campaign-level output requirements and pair evidence. Refuse or visibly flag incomplete jobs in the API and UI. Display `1/2` or `2/2`, each candidate’s tier, and a distinctness decision with the evidence used.

### F-07 — Captions do not create or prove distinctness (**low**, non-blocking)

`core/captioning.py` correctly builds captions from each candidate interval and returns cues relative to that interval ([`core/captioning.py:41-71`](../core/captioning.py#L41-L71), [`core/captioning.py:82-118`](../core/captioning.py#L82-L118)). It contains no cross-candidate logic. This is not itself a defect, but it means caption differences cannot be used as evidence that the underlying videos are materially distinct. Two duplicate windows will simply receive separately generated caption files.

## Current behavior versus target contract

| Area | Current behavior | Required target behavior |
|---|---|---|
| Count | Selects and publishes up to two; one can reach review | Exactly two finished outputs, unless an explicit campaign exception is stored |
| Tier allocation | Campaign may carry `EN/Tier-1` metadata; no clip tiers | Formal tier taxonomy, candidate labels, and enforced allocation |
| Same-source duplicate filtering | Temporal overlap and token-set heuristics | Pairwise normalized transcript plus temporal/media evidence |
| Cross-source duplicate filtering | Exact source preflight hash only; candidate duplicate check returns false across sources | Source normalization and cross-source perceptual/content fingerprints |
| Render completion | Missing one output can be silently tolerated | Every required rank must render and be verified |
| Validation | Per-file technical/relevance checks; blocks only if all fail | Pair-level count, tier, and distinctness gate |
| Persistence/UI | Arbitrary preview count; “Kandidat N” labels | Expected/actual count, tier, pair decision, and blocking status |

## Gaps and assumptions

1. **Tier semantics are undefined.** The repository contains campaign-level `EN/Tier-1` text detection but no authoritative definition of video Tier 1 or Tier 2. Product acceptance criteria must specify whether the pair is one-per-tier, two Tier 1 clips, or another allocation.
2. **“Materially distinct” has no numeric contract.** The current 45% overlap and 0.82 token similarity thresholds are implementation heuristics, not documented business requirements. They cannot be treated as acceptance criteria without calibration against labeled examples.
3. **No end-to-end invariant test exists.** The visible tests cover candidate limits, same-source duplicate filtering, captions, and per-video editorial checks, but do not test one-candidate, one-render-failure, one-validation-failure, duplicate-across-sources, or missing-tier cases ([`tests/test_candidate_limit.py:6-18`](../tests/test_candidate_limit.py#L6-L18), [`tests/test_render_quality.py:61-66`](../tests/test_render_quality.py#L61-L66), [`tests/test_worker_diagnostics.py:6-28`](../tests/test_worker_diagnostics.py#L6-L28)).
4. **Observed two-preview evidence is not a guarantee.** The documented smoke run proves the happy path reached two previews, but it does not exercise the failure paths identified above ([`docs/AGENT_HANDOFF.md:248-252`](../docs/AGENT_HANDOFF.md#L248-L252)).
5. **Tier 1 may refer to audience or campaign eligibility rather than a clip class.** If so, the requirement needs a separate mapping from campaign eligibility to the two clip-level acceptance criteria; that mapping is absent.

## Phased recommendations

### Phase 0 — Specify and instrument before changing selection

Write the acceptance contract in the campaign plan: required output count, tier allocation, duration bounds, and a measurable distinctness threshold. Add a campaign-level status vocabulary such as `insufficient_candidates`, `duplicate_pair`, `tier_allocation_failed`, `render_incomplete`, and `ready_two_clips`. Add stage metrics for selected, rendered, validated, distinct, and tier-compliant counts. Preserve the existing no-Buffer-post audit boundary while implementing and testing these checks.

### Phase 1 — Enforce the minimum invariant at the worker boundary

After distinct selection, require `len(selected) == required_finished_videos`; otherwise block with an actionable diagnostic. Require every selected render artifact to exist and pass per-video validation. After validation, require exactly two non-failing outputs before creating the review queue and uploading R2 artifacts. Do not allow the current “any non-empty list” behavior to set a job to review.

### Phase 2 — Add tier-aware selection

Define and propagate a candidate-level tier field from campaign rules and deterministic candidate evidence. Select by tier allocation first, then optimize score within each tier. If a candidate’s tier is uncertain, retain the uncertainty and block automatic completion when the campaign requires a known tier. Include tier and tier rationale in `candidates.json`, the manifest, `validation_json`, the preview rows, and the review card.

### Phase 3 — Replace heuristic-only duplicate filtering

Normalize source identity before source truncation and deduplicate all downloaded assets before applying `max_sources`. Add pairwise checks across every selected candidate, including candidates from different source paths: normalized transcript similarity, same-source temporal overlap, and a media/audio fingerprint where available. Calibrate thresholds against labeled duplicate and non-duplicate examples. Re-run the pair check on final rendered files so a successful encode cannot bypass the invariant.

### Phase 4 — Make the contract visible and regression-tested

Add schema/API fields for expected count, actual count, tier allocation, distinctness status, and evidence. Add a unique `(job_id, rank)` constraint or stable candidate ID model. Update the frontend to show `2/2`, tier labels, and a blocking explanation for incomplete or duplicate pairs. Add end-to-end tests for: one candidate; two overlapping candidates; identical content across different source files; one render missing; one validator failure; two same-tier candidates; and a valid one-Tier-1/one-Tier-2 pair.

## Final assessment

The system has a useful happy path: it can select two non-overlapping candidates, render them with deterministic rank-based filenames, validate each file, upload review artifacts, and expose them for manual review. That path is supported by the recorded smoke test. However, the requested guarantee is not implemented. The decisive blockers are the absence of a hard two-output gate and the absence of any Tier 1/Tier 2 candidate contract. Duplicate filtering and validation are local heuristics and per-file checks, so they cannot establish material pairwise distinctness.

## References

[1]: ../worker/run_job.py "Worker orchestration, selection, rendering, validation, and upload"
[2]: ../core/clip_candidates.py "Candidate scoring and near-duplicate filtering"
[3]: ../modules/clipping/render.py "Vertical clip renderer"
[4]: ../modules/clipping/validate.py "Per-video technical and editorial validator"
[5]: ../modules/clipping/review_queue.py "Review queue builder"
[6]: ../cloudflare/api.js "Preview, job, and persistence API"
[7]: ../cloudflare/schema.sql "D1 schema for jobs and previews"
[8]: ../web/app.js "Production and demo review UI"
[9]: ../core/captioning.py "Caption cue and subtitle generation"
[10]: ../modules/reward_campaign/scrape.py "Campaign metadata and Tier 1 flag extraction"
[11]: ../docs/AGENT_HANDOFF.md "Recorded production smoke-test trace"
[12]: ../tests/test_candidate_limit.py "Candidate count test"
[13]: ../tests/test_render_quality.py "Distinctness and render-quality unit tests"
[14]: ../tests/test_worker_diagnostics.py "Worker diagnostic test"

*Prepared by Manus AI from the repository state available at audit time.*
