#!/bin/bash
set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
BASE="https://cogmyra-api.onrender.com"
PATHS=( "/api/admin/export.csv" "/api/admin/export" )
HEADERS_VARIANTS=(
  "x-admin-key:%s"
  "X-Admin-Key:%s"
  "authorization:Bearer %s"
  "Authorization: Bearer %s"
)
UA="cogmyra-export/diag-1.0"

# ── Key (from env or Keychain) ───────────────────────────────────────────────
KEY="${COGMYRA_ADMIN_KEY:-}"
if [ -z "$KEY" ]; then
  RAW="$(
    /usr/bin/security find-generic-password -a "$USER" -s cogmyra-admin-key -w 2>/dev/null || true
  )"
  KEY="$(printf '%s' "$RAW" | tr -d '\r\n')"
fi
if [ -z "$KEY" ]; then
  echo "ERROR: no admin key in env or Keychain." >&2
  exit 2
fi

printf 'Key preview: %s********%s (len=%d)\n' "${KEY:0:2}" "${KEY: -2}" "${#KEY}"

# ── Work files ───────────────────────────────────────────────────────────────
HDR="/tmp/cogmyra-diag.resp.hdr"
BODY="/tmp/cogmyra-diag.resp.body"
STATUS="/tmp/cogmyra-diag.status"

rm -f "$HDR" "$BODY" "$STATUS"

# ── Try matrix ────────────────────────────────────────────────────────────────
ok=""
for p in "${PATHS[@]}"; do
  for fmt in "${HEADERS_VARIANTS[@]}"; do
    header=$(printf "$fmt" "$KEY")
    echo "→ Trying $BASE$p with header: $header"

    code=$(/usr/bin/curl -fsS --http1.1 --location \
      -H "$header" \
      -H "Accept: text/csv" \
      -H "User-Agent: $UA" \
      -D "$HDR" -w "%{http_code}" \
      -o "$BODY" \
      "$BASE$p" \
      || true)

    echo "  HTTP $code"
    echo "$code" > "$STATUS"

    if [ "$code" = "200" ]; then
      # If endpoint is JSON with CSV bytes, fine; if /export (no .csv) still returns csv, great.
      STAMP="$(date +"%Y%m%d-%H%M%S")"
      OUT="$HOME/Downloads/logs-$STAMP.csv"
      mv "$BODY" "$OUT"
      echo "✅ Success via '$header' on '$p'"
      echo "Saved: $OUT"
      ok="yes"
      break 2
    fi
  done
done

if [ -z "$ok" ]; then
  echo "❌ All attempts failed."
  echo "Status: $(cat "$STATUS" 2>/dev/null || echo '?')"
  echo "--- Response headers ---"
  sed -n '1,80p' "$HDR" 2>/dev/null || true
  echo "--- Response body (first 400B, hex) ---"
  head -c 400 "$BODY" 2>/dev/null | od -An -t x1 -v || true
  exit 1
fi
