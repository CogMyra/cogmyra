#!/bin/bash
set -euo pipefail
KEY="$(/usr/bin/security find-generic-password -a "$USER" -s cogmyra-admin-key -w 2>/dev/null | tr -d $'\r\n')"
: "${KEY:?no key in login Keychain (service=cogmyra-admin-key)}"
export COGMYRA_ADMIN_KEY="$KEY"
exec "$HOME/cogmyra-dev/scripts/export_logs.sh"
