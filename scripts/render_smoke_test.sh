#!/usr/bin/env bash
set -euo pipefail

SERVICE_URL=${1:-}
if [[ -z "$SERVICE_URL" ]]; then
  echo "Usage: $0 https://<service-url>" >&2
  exit 1
fi

echo "Checking $SERVICE_URL/health"
TMP_RESPONSE=$(mktemp)
STATUS=$(curl -s -o "$TMP_RESPONSE" -w "%{http_code}" "$SERVICE_URL/health")
BODY=$(cat "$TMP_RESPONSE")
rm "$TMP_RESPONSE"

if [[ "$STATUS" == "200" && "$BODY" == '{"status":"ok"}' ]]; then
  echo "Render smoke test passed: $BODY"
  exit 0
fi

echo "Render smoke test failed (status: $STATUS, body: $BODY)" >&2
exit 1
