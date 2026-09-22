# P0 Research Decisions

## Scope

P0 closes the production loop from campaign selection to preview review and approval. The control plane is Cloudflare Pages/Worker/D1. R2 stores private media. GitHub Actions performs FFmpeg and CPU video processing.

## Decisions

- D1 is the source of truth for jobs, revisions, state transitions, ownership, and audit events.
- R2 objects are immutable per job/revision and are never addressed by a raw client-supplied key.
- Preview access is issued by an authenticated server endpoint after ownership/status checks. Short-lived presigned GET URLs are the default; Worker streaming remains the option for per-request revocation or custom-domain access.
- Approval is bound to the current revision and render hash. A later rerender invalidates the earlier approval.
- The minimum state path is `queued -> processing -> review -> approved_for_manual_post`, with `blocked`, `error`, `cancel_requested`, `cancelled`, and `changes_requested` recovery paths.
- GitHub Actions is at-least-once execution. D1 idempotency and job ownership checks are required; workflow retries must not duplicate previews or overwrite newer revisions.
- R2 must stay private. CORS is browser policy, not authentication. Presigned URLs are bearer tokens and must not be logged or persisted in analytics.
- The preview baseline is 1080x1920, 9:16, H.264/AAC, `setsar=1`, `yuv420p`, `+faststart`, deterministic crop fallback, subtitle safe area, and explicit validator output.
- Automated checks are prechecks. Human approval remains the final decision before manual upload.

## Sources

- https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- https://developers.cloudflare.com/r2/buckets/cors/
- https://developers.cloudflare.com/r2/buckets/public-buckets/
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://developers.cloudflare.com/r2/buckets/object-lifecycles/
- https://developers.cloudflare.com/d1/tutorials/build-an-api-to-access-d1/
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://docs.github.com/rest/actions/workflows
- https://docs.github.com/en/rest/actions/workflow-runs
- https://docs.github.com/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs
- https://docs.github.com/actions/reference/workflow-syntax-for-github-actions
- https://docs.github.com/en/actions/reference/limits
- https://ffmpeg.org/ffmpeg-filters.html
- https://ffmpeg.org/ffmpeg-codecs.html
- https://developers.google.com/edge/mediapipe/solutions/vision/face_detector/python
- https://docs.aws.amazon.com/step-functions/latest/dg/tutorial-human-approval.html
- https://www.w3.org/WAI/WCAG22/Understanding/captions-prerecorded.html

## P0 acceptance target

A user can select an analyzed clipping campaign, start one idempotent job, watch stage/progress, open a secure preview, see validation/checklist information, approve or request changes, and download the approved manual-post package. A duplicate click, stale callback, old revision, expired preview URL, or unauthorized user cannot mutate or read another user's job.
