#!/bin/bash
set -euo pipefail

BASE="https://cogmyra-api.onrender.com"
UA="cogmyra-export/discover-1.0"

# Get key from env or Keychain (trim CR/LF)
KEY="${COGMYRA_ADMIN_KEY:-}"
if [ -z "$KEY" ]; then
  RAW="$(/usr/bin/security find-generic-password -a "$USER" -s cogmyra-admin-key -w 2>/dev/null || true)"
  KEY="$(printf '%s' "$RAW" | tr -d '\r\n')"
fi
[ -n "$KEY" ] || { echo "ERROR: no admin key (env/Keychain)."; exit 2; }
printf 'Key preview: %s********%s (len=%d)\n' "${KEY:0:2}" "${KEY: -2}" "${#KEY}"

# Fetch openapi.json (unauthenticated)
OPENAPI="/tmp/cogmyra-openapi.json"
if ! /usr/bin/curl -fsS --http1.1 -H "User-Agent: $UA" "$BASE/openapi.json" -o "$OPENAPI"; then
  echo "WARN: openapi.json not available; will fall back to common guesses."
  echo '{}' > "$OPENAPI"
fi

# Extract candidate paths (bash + awk/grep only)
#  - de-escape \/ => /
CLEAN="/tmp/cogmyra-openapi.clean"
sed -e 's#\\/#/#g' "$OPENAPI" > "$CLEAN" || true

echo "Candidate API paths (filtered):"
CANDIDATES=$(grep -oE '"\/[^"]+"' "$CLEAN" | tr -d '"' | awk '
  /admin/ || /export/ || /log/ || /csv/ {print}' | sort -u)
if [ -z "$CANDIDATES" ]; then
  # Guesses if nothing found
  CANDIDATES=$(
    cat <<'EOF'
/api/admin/export.csv
/api/admin/logs.csv
/api/admin/logs/export.csv
/api/admin/logs/export
/api/export.csv
/admin/export.csv
/logs/export.csv
EOF
  )
fi
echo "$CANDIDATES" | sed 's/^/  - /'

HEADERS_VARIANTS=(
  "x-admin-key:%s"
  "X-Admin-Key:%s"
  "authorization:Bearer %s"
  "Authorization: Bearer %s"
)

HDR="/tmp/cogmyra-discover.resp.hdr"
BODY="/tmp/cogmyra-discover.resp.body"

ok=""
while read -r p; do
  [ -n "$p" ] || continue
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
    if [ "$code" = "200" ]; then
      STAMP="$(date +"%Y%m%d-%H%M%S")"
      OUT="$HOME/Downloads/logs-$STAMP.csv"
      mv "$BODY" "$OUT"
      echo "✅ Success on '$p' via header '$header'"
      echo "Saved: $OUT"
      ok="yes"
      break 2
    fi
  done
done <<< "$CANDIDATES"

if [ -z "$ok" ]; then
  echo "❌ Still failing. Showing last response headers:"
  sed -n '1,120p' "$HDR" 2>/dev/null || true
  echo "Body (first 400B, hex):"
  head -c 400 "$BODY" 2>/dev/null | od -An -t x1 -v || true
  exit 1
fi
