#!/usr/bin/env bash
# Restore drill: prove the latest backup (or the one named) can be restored.
#   scripts/restore-drill.sh [backup-name]
# Restores it into a scratch database (nexus_restore_check), checks the row counts,
# schema revision and that encrypted values decrypt with your key, marks the backup as
# verified (Settings, then System status), and drops the scratch database. Your live data
# is not touched. Run it monthly.
set -euo pipefail
cd "$(dirname "$0")/.."
name=${1:-latest}
check=nexus_restore_check
cleanup() { docker compose exec -T backup dropdb --if-exists "$check" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "Restoring $name into $check…"
name=$(docker compose exec -T backup /scripts/restore.sh "$name" "$check" | tail -n1)
echo "Checking $name…"
docker compose run --rm --no-deps -T api python -m app.cli restore-check \
  --database "$check" --backup "$name"
docker compose exec -T backup /scripts/mark-verified.sh "$name"
echo "Restore drill passed for $name."
