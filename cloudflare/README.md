# Cloudflare deployment plan

## Architecture

Cloudflare Pages hosts the static dashboard in `web/`. A Cloudflare Worker hosts the small JSON API in `cloudflare/api.js`. D1 stores campaign metadata, jobs, and preview metadata. R2 stores rendered MP4 files and thumbnails. The Python worker runs outside Cloudflare because FFmpeg and faster-whisper are not suitable for Cloudflare Workers' free 10 ms CPU and 128 MB memory limits.

The UI is intentionally in demo mode until the Worker URL is configured. Set `web/config.js` to:

```js
window.CLIPPER_CONFIG = {
  API_BASE_URL: "https://your-api.your-subdomain.workers.dev",
  DEMO_MODE: false
};
```

## Free-first boundaries

The exact storage, retention, query, and upload guardrails are documented in [`FREE_COST_POLICY.md`](./FREE_COST_POLICY.md). Read and apply that policy before creating production bindings.

Cloudflare Pages Free supports static deployments and has a 25 MiB individual asset limit, so MP4 files must not be committed to Pages. Put videos and thumbnails in R2 and expose only short-lived or protected download URLs through the API. R2 currently includes 10 GB-month storage, 1 million Class A operations, 10 million Class B operations, and free egress on the standard free tier. Check current billing before storing a large library.

Cloudflare Workers Free is suitable for a light API, not video rendering. The current limit is 100,000 requests per day, 10 ms CPU per request, and 128 MB memory. Cloudflare Queues can be used later for job notifications, but its free tier has a 10,000 operations/day allowance and 24-hour retention. The actual heavy job remains on the local Python worker.

## Initial setup

1. Create a Pages project from the `web/` directory. The site can be deployed through Git integration so pushes to GitHub create automatic deployments.
2. Create a D1 database and apply `schema.sql`.
3. Create an R2 standard bucket for `clips`.
4. Deploy the Worker API and bind D1 as `DB` and R2 as `CLIPS`.
5. Set a random `WORKER_TOKEN` secret for local worker status updates. Do not commit it.
6. Put the public API URL in `web/config.js` and set `DEMO_MODE: false`.
7. Protect the Pages site and Worker with Cloudflare Access before using private campaign or video data.

Because the user only has a phone, the Python worker must not be assumed to run locally. The planned worker is a GitHub Actions standard runner from the public `ibank31/scrapper-engine` repository. It will run the existing pipeline, upload MP4 and thumbnails to R2, insert preview rows, and PATCH job progress with `x-worker-token`. See [`PHONE_ONLY_ARCHITECTURE.md`](./PHONE_ONLY_ARCHITECTURE.md). It must never receive or store Cloudflare credentials in the repository.

## API contract

- `GET /api/campaigns` — campaign list for the dashboard.
- `GET /api/campaigns/:id` — campaign detail and compiled plan.
- `POST /api/campaigns/:id/jobs` — create a queued clipping job.
- `GET /api/jobs/:id` — job status.
- `GET /api/jobs/:id/previews` — preview metadata and protected URLs.
- `PATCH /api/jobs/:id` — worker-only status update.

The current API is intentionally small. Authentication and R2 signed URL issuance must be completed before public deployment.
