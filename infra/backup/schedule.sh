#!/usr/bin/env bash
# Runs in the backup container. Every 15 minutes: if today's backup hasn't been made and
# it's past BACKUP_TIME (local time, TZ), make it. A PC that was off at night backs up
# soon after it's switched on, instead of skipping the day.
set -uo pipefail
BACKUP_DIR=${BACKUP_DIR:-/backups}
BACKUP_TIME=${BACKUP_TIME:-03:00}
mkdir -p "$BACKUP_DIR"
echo "backups: daily after $BACKUP_TIME ($TZ), into $BACKUP_DIR"
until pg_isready -q; do sleep 5; done
while true; do
  today=$(date +%F)
  if [[ "$(date +%H:%M)" > "$BACKUP_TIME" || "$(date +%H:%M)" == "$BACKUP_TIME" ]] \
    && [ "$(cat "$BACKUP_DIR/.last-day" 2>/dev/null)" != "$today" ]; then
    if /scripts/backup.sh; then echo "$today" > "$BACKUP_DIR/.last-day"; fi
  fi
  sleep 900
done
