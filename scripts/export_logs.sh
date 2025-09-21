#!/bin/bash
# Export CogMyra logs to CSV with timestamped filename
set -euo pipefail

: "${COGMYRA_ADMIN_KEY:?Set COGMYRA_ADMIN_KEY (export COGMYRA_ADMIN_KEY=...)}"

STAMP="$(date +"%Y%m%d-%H%M%S")"
OUTFILE="$HOME/Downloads/logs-$STAMP.csv"
TMP="$(mktemp)"
HDR="/tmp/cogmyra-export.resp.hdr"

# Use HTTP/1.1, follow redirects, fail on HTTP errors
HTTP_STATUS="$(
  curl --http1.1 -fsS --location \
    -H "x-admin-key: ${COGMYRA_ADMIN_KEY}" \
    -D "$HDR" \
    -o "$TMP" \
    -w "%{http_code}" \
    "https://cogmyra-api.onrender.com/api/admin/export.csv" \
  || true
)"

if [[ "$HTTP_STATUS" != "200" ]]; then
  echo "curl: returned HTTP $HTTP_STATUS" >&2
  sed -n '1,40p' "$HDR" >&2 || true
  rm -f "$TMP"
  echo "❌ Export failed (HTTP $HTTP_STATUS). See $HDR for response headers."
  exit 1
fi

mv "$TMP" "$OUTFILE"
chmod 600 "$OUTFILE"
echo "✅ Logs saved to $OUTFILE"
