#!/usr/bin/env bash
# One backup of NEXUS: the database (pg_dump custom format), the uploads folder, and a
# manifest with checksums and the exact row count of every table. The counts are taken in
# the same snapshot as the dump, so a restore can be checked against them exactly.
#
# The encryption key (NEXUS_ENCRYPTION_KEY) is NOT in the backup. Keep a copy of it
# somewhere safe and separate (a password manager): without it, finance, health, journal
# and account tokens in a backup can't be read.
#
# Env: PGHOST PGUSER PGPASSWORD PGDATABASE, BACKUP_DIR (/backups), UPLOADS_DIR (/uploads),
#      BACKUP_KEEP (14 backups kept).
set -euo pipefail

BACKUP_DIR=${BACKUP_DIR:-/backups}
UPLOADS_DIR=${UPLOADS_DIR:-/uploads}
KEEP=${BACKUP_KEEP:-14}
stamp=$(date -u +%Y%m%dT%H%M%SZ)
work="$BACKUP_DIR/.partial-$stamp"
out="$BACKUP_DIR/$stamp"

fail() {
  local msg="$1"
  printf '{"at": "%s", "error": "%s"}\n' "$(date -u +%FT%TZ)" "${msg//\"/\'}" \
    > "$BACKUP_DIR/last-error.json"
  rm -rf "$work"
  echo "backup failed: $msg" >&2
  exit 1
}
trap 'fail "step failed near line $LINENO"' ERR

mkdir -p "$work"
started=$(date +%s)

# Hold one repeatable-read transaction open, export its snapshot, count rows in it, and
# have pg_dump use the same snapshot.
mkfifo "$work/ctl"
psql -X -q -A -t -v ON_ERROR_STOP=1 < "$work/ctl" > "$work/session.out" 2> "$work/session.err" &
session=$!
exec 3> "$work/ctl"
echo "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SELECT pg_export_snapshot();" >&3
for _ in $(seq 100); do [ -s "$work/session.out" ] && break; sleep 0.1; done
snapshot=$(head -n1 "$work/session.out")
[ -n "$snapshot" ] || fail "could not open a snapshot: $(cat "$work/session.err")"

cat >&3 <<'SQL'
SELECT coalesce(json_object_agg(t.table_name, (xpath('/row/c/text()', query_to_xml(
  format('SELECT count(*) AS c FROM public.%I', t.table_name), false, true, '')))[1]::text::bigint
  ORDER BY t.table_name), '{}')
FROM information_schema.tables t
WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE';
SQL

pg_dump -Fc --no-owner --no-privileges --snapshot="$snapshot" -f "$work/db.dump" \
  || fail "pg_dump failed"

for _ in $(seq 600); do [ "$(wc -l < "$work/session.out")" -ge 2 ] && break; sleep 0.1; done
counts=$(sed -n 2p "$work/session.out")
echo "COMMIT;" >&3
exec 3>&-
wait "$session" || true
[ -n "$counts" ] || fail "could not count rows: $(cat "$work/session.err")"
revision=$(psql -X -A -t -c "SELECT version_num FROM alembic_version" 2>/dev/null || echo "")

if [ -d "$UPLOADS_DIR" ]; then
  tar -C "$UPLOADS_DIR" -czf "$work/uploads.tar.gz" . || fail "archiving uploads failed"
else
  tar -czf "$work/uploads.tar.gz" -T /dev/null
fi
rm -f "$work/ctl" "$work/session.out" "$work/session.err"

db_sha=$(sha256sum "$work/db.dump" | cut -d' ' -f1)
up_sha=$(sha256sum "$work/uploads.tar.gz" | cut -d' ' -f1)
bytes=$(( $(stat -c %s "$work/db.dump") + $(stat -c %s "$work/uploads.tar.gz") ))
cat > "$work/manifest.json" <<JSON
{
  "version": 1,
  "created_at": "$(date -u +%FT%TZ)",
  "database": "${PGDATABASE}",
  "alembic_revision": "${revision}",
  "seconds": $(( $(date +%s) - started )),
  "size_mb": $(awk "BEGIN { printf \"%.1f\", $bytes / 1048576 }"),
  "files": {"db.dump": "$db_sha", "uploads.tar.gz": "$up_sha"},
  "counts": $counts
}
JSON

mv "$work" "$out"
rm -f "$BACKUP_DIR/last-error.json"

# Keep the newest $KEEP backups.
ls -1d "$BACKUP_DIR"/2*/ 2>/dev/null | sort | head -n -"$KEEP" | xargs -r rm -rf
echo "backup ok: $out"
