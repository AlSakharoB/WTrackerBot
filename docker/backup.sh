#!/bin/sh
set -eu

backup_dir=${MIGRATION_BACKUP_DIR:-/backups}
marker=${MIGRATION_BACKUP_MARKER:-/backups/.last-verified}
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
database_name=$(printf '%s' "${PGDATABASE:-database}" | tr -c 'A-Za-z0-9_.-' '_')
filename="${database_name}_${timestamp}.dump"
temporary_path="${backup_dir}/.${filename}.tmp"
backup_path="${backup_dir}/${filename}"
marker_temporary_path="${marker}.tmp"

mkdir -p "$backup_dir"
rm -f "$temporary_path" "$marker_temporary_path"

pg_dump --format=custom --no-password --file="$temporary_path"
test -s "$temporary_path"
pg_restore --list "$temporary_path" >/dev/null
mv "$temporary_path" "$backup_path"

checksum=$(sha256sum "$backup_path" | cut -d ' ' -f 1)
printf '%s %s\n' "$filename" "$checksum" >"$marker_temporary_path"
mv "$marker_temporary_path" "$marker"
chmod 0444 "$backup_path" "$marker"

printf 'Verified PostgreSQL 16 backup: %s\n' "$filename"
