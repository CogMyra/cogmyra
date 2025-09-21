#!/bin/bash
# Export CogMyra logs to CSV with timestamped filename

set -e

STAMP=$(date +"%Y%m%d-%H%M%S")
OUTFILE="$HOME/Downloads/logs-$STAMP.csv"

curl -fSL -H "x-admin-key: walnut-salsa-meteor-88" \
  -o "$OUTFILE" \
  "https://cogmyra-api.onrender.com/api/admin/export.csv"

echo "✅ Logs saved to $OUTFILE"
