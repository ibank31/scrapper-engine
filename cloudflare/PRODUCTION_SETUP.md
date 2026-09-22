# Production setup runbook

## Current resources

The active Cloudflare Pages project is `clipper-engine` at `https://clipper-engine.pages.dev`. It is connected to the `ibank31/scrapper-engine` repository on the `main` branch. The production function is bound to D1 database `clipper-engine` (`ee8299d2-84e5-433b-b02f-553dcd4aea73`) and R2 bucket `clipper-engine-previews`.

The P0 review schema has been applied to production. The `previews` table now includes `review_reason`, `reviewed_by`, and `reviewed_at`; `preview_events` and its index exist.

The Pages production function must also have `GITHUB_ACTIONS_TOKEN` configured as a secret. It is used only by `POST /api/jobs/:id/run` to dispatch the repository workflow with the selected `job_id`. Without it, jobs remain queued and the API returns `github_dispatch_not_configured` with HTTP 503. Use a fine-scoped GitHub token that can dispatch workflows in `ibank31/scrapper-engine`; never put this token in the repository or frontend.

## Required secrets

These values must be stored as Cloudflare Pages production secrets, never in GitHub, `web/config.js`, the repository, or logs:

```text
PREVIEW_SIGNING_SECRET  random high-entropy value used to sign short-lived preview URLs
REVIEW_TOKEN            random high-entropy value used to authorize review mutations until Access is enabled
GITHUB_ACTIONS_TOKEN    fine-scoped GitHub token used only to dispatch clipper-worker.yml
```

Recommended setup with Wrangler after installing it or running it through `npx`:

```bash
npx wrangler pages secret put PREVIEW_SIGNING_SECRET --project-name clipper-engine
npx wrangler pages secret put REVIEW_TOKEN --project-name clipper-engine
npx wrangler pages secret put GITHUB_ACTIONS_TOKEN --project-name clipper-engine
```

When prompted, paste different random values. Do not reuse the Google OAuth client secret, GitHub token, or Worker token. The signing secret is not recoverable after creation; generate a replacement and re-deploy if it is lost.

## GitHub Actions secrets

The existing worker workflow expects these repository secrets:

```text
CLIPPER_API_URL=https://clipper-engine.pages.dev
CLIPPER_WORKER_TOKEN=<same value as the Worker upload/status token>
GOOGLE_DRIVE_REFRESH_TOKEN=<Google OAuth refresh token>
GOOGLE_OAUTH_CLIENT_ID=<Google OAuth client ID>
GOOGLE_OAUTH_CLIENT_SECRET=<Google OAuth client secret>
```

The Google values must remain GitHub secrets. They must never be copied into this document or the Pages frontend.

## Smoke test

After the Pages deployment finishes and the secrets are configured:

```bash
scripts/verify_production.sh https://clipper-engine.pages.dev
```

The script checks the homepage and the campaign API only. A real review test must use a preview created by the worker and verify that an URL without a valid signature returns HTTP 403, a fresh URL plays with Range requests, and a review action creates an event in D1.

## Deployment safety

Do not make the R2 bucket public. Do not expose raw R2 object keys to the browser. The preview URL endpoint maps a preview ID to its server-side object key and signs a short-lived URL when `PREVIEW_SIGNING_SECRET` is present. Keep the legacy unsigned fallback disabled in production by setting the secret before real media is processed.

The Pages project currently deploys automatically from `main`. Code changes are reversible with a Git revert or a Pages deployment rollback. Secret rotation is an account-security change and should be performed deliberately; rotating `REVIEW_TOKEN` invalidates existing review requests, while rotating `PREVIEW_SIGNING_SECRET` invalidates previously issued preview URLs.
