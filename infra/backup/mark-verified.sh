#!/usr/bin/env bash
# Record that a backup passed the restore drill (read by Settings, then System status).
set -euo pipefail
BACKUP_DIR=${BACKUP_DIR:-/backups}
dir="$BACKUP_DIR/${1:?backup name}"
printf '{"verified_at": "%s"}\n' "$(date -u +%FT%TZ)" > "$dir/verified.json"
