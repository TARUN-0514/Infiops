#!/usr/bin/env bash
# Restore a backup into a database.
#   restore.sh <backup|latest> <database> [--uploads]
# Checks the checksums first. Restoring into the live database (PGDATABASE) needs
# CONFIRM=yes and the api and worker stopped. --uploads also replaces the uploads folder.
set -euo pipefail

BACKUP_DIR=${BACKUP_DIR:-/backups}
UPLOADS_DIR=${UPLOADS_DIR:-/uploads}
name=${1:?backup name or latest}
target=${2:?target database}
with_uploads=${3:-}

if [ "$name" = latest ]; then
  name=$(ls -1d "$BACKUP_DIR"/2*/ 2>/dev/null | sort | tail -n1 | xargs -r basename)
  [ -n "$name" ] || { echo "no backups in $BACKUP_DIR" >&2; exit 1; }
fi
dir="$BACKUP_DIR/$name"
[ -f "$dir/manifest.json" ] || { echo "no backup called $name" >&2; exit 1; }

if [ "$target" = "${PGDATABASE}" ] && [ "${CONFIRM:-}" != yes ]; then
  echo "Restoring over the live database $target replaces everything in it." >&2
  echo "Stop the api and worker, then run again with CONFIRM=yes." >&2
  exit 2
fi

(cd "$dir" && for f in db.dump uploads.tar.gz; do
  want=$(grep -o "\"$f\": \"[0-9a-f]*\"" manifest.json | cut -d'"' -f4)
  have=$(sha256sum "$f" | cut -d' ' -f1)
  [ "$want" = "$have" ] || { echo "checksum mismatch for $f: backup is damaged" >&2; exit 3; }
done)

dropdb --if-exists "$target"
createdb "$target"
pg_restore --no-owner --no-privileges --exit-on-error -d "$target" "$dir/db.dump"

if [ "$with_uploads" = --uploads ]; then
  find "$UPLOADS_DIR" -mindepth 1 -delete
  tar -C "$UPLOADS_DIR" -xzf "$dir/uploads.tar.gz"
fi
echo "$name"
