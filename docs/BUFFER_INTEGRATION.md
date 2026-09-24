# Buffer upload integration

The review queue now includes **Upload ke Buffer**. The button loads the connected Buffer channels, lets the reviewer select one or more channels, edits the caption, and queues the video through Buffer's GraphQL API. The browser never receives the Buffer key.

## Add the Buffer secret

1. Open Buffer **Settings → API** at [publish.buffer.com/settings/api](https://publish.buffer.com/settings/api).
2. Create or copy the account API key.
3. Open the Cloudflare dashboard and select **Workers & Pages → clipper-engine → Settings → Variables and Secrets → Production**.
4. Add a secret named `BUFFER_API_KEY` and paste the key as its value. Do not put it in `web/config.js`, Git, or frontend JavaScript.
5. Redeploy the Pages project so the new secret is available to the Pages Function.

The backend also accepts an optional non-secret variable named `BUFFER_PUBLIC_MEDIA_BASE_URL`. Leave it empty for the default stable URL `https://clipper-engine.pages.dev/media/...`. Set it only if the R2 bucket is exposed through a permanent public custom domain. Buffer requires a direct, public, stable HTTPS media URL; the existing signed `/api/files` URLs must not be sent to Buffer because they expire.

## How it works

The backend queries Buffer organizations and channels through `GET /api/buffer/channels`. The upload action calls `createPost` with `schedulingType: automatic`, `mode: addToQueue`, and the selected channel IDs. Each attempt is recorded in D1 in `buffer_uploads`, including the Buffer post ID or the error returned by Buffer.

The action remains behind the existing review authorization (`REVIEW_TOKEN`, when configured) and shows a browser confirmation before sending. Uploading to Buffer schedules content in Buffer; it does not immediately publish outside Buffer's configured queue rules.

## Required deployment settings

| Name | Type | Required | Purpose |
| --- | --- | ---: | --- |
| `BUFFER_API_KEY` | Secret | Yes | Server-side Buffer account API key. |
| `BUFFER_PUBLIC_MEDIA_BASE_URL` | Variable | No | Permanent public base URL for media; defaults to the Pages `/media/` route. |
| `REVIEW_TOKEN` | Secret | Recommended | Protects review and Buffer actions from unauthorised callers. |

Buffer documentation: [Authentication](https://developers.buffer.com/guides/authentication.html), [Posts & Scheduling](https://developers.buffer.com/guides/posts-and-scheduling.html), and [Hosting Media](https://developers.buffer.com/guides/hosting-media.html).
