#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-https://clipper-engine.pages.dev}"

printf '%s\n' "== Clipper Engine production verification =="
printf 'Base URL: %s\n' "$BASE_URL"

status=$(curl -sS -o /tmp/clipper-home.html -w '%{http_code}' "$BASE_URL/")
if [ "$status" != "200" ]; then
  echo "Homepage failed with HTTP $status" >&2
  exit 1
fi

grep -q "Clipper Engine" /tmp/clipper-home.html || {
  echo "Homepage does not contain the expected application title" >&2
  exit 1
}
printf '%s\n' "Homepage: OK"

api_status=$(curl -sS -o /tmp/clipper-campaigns.json -w '%{http_code}' "$BASE_URL/api/campaigns")
if [ "$api_status" != "200" ]; then
  echo "Campaign API failed with HTTP $api_status" >&2
  cat /tmp/clipper-campaigns.json >&2 || true
  exit 1
fi

python3 - <<'PY'
import json
with open('/tmp/clipper-campaigns.json', encoding='utf-8') as handle:
    payload = json.load(handle)
if not isinstance(payload.get('campaigns'), list):
    raise SystemExit('Campaign API response has no campaigns array')
print(f"Campaign API: OK ({len(payload['campaigns'])} campaigns)")
PY

rm -f /tmp/clipper-home.html /tmp/clipper-campaigns.json
printf '%s\n' "Production smoke test passed."
