#!/bin/bash
# Export CogMyra logs to CSV with timestamped filename

set -euo pipefail

: "${COGMYRA_ADMIN_KEY:?Set COGMYRA_ADMIN_KEY in your shell (export COGMYRA_ADMIN_KEY=...)}"

STAMP=$(date +"%Y%m%d-%H%M%S")
OUTFILE="$HOME/Downloads/logs-$STAMP.csv"
TMPFILE="$(mktemp)"

# -f: fail on HTTP error, -S: show error, -s: silent otherwise, --location: follow redirects
curl -fsS --location \
  -H "x-admin-key: ${COGMYRA_ADMIN_KEY}" \
  "https://cogmyra-api.onrender.com/api/admin/export.csv" \
  -o "$TMPFILE"

mv "$TMPFILE" "$OUTFILE"
echo "✅ Logs saved to $OUTFILE"
