#!/bin/sh
set -eu

env_file=${ENV_FILE:-.env}
example_file=${ENV_EXAMPLE_FILE:-.env.example}
backup_limit=${ENV_BACKUP_LIMIT:-2}

case "$backup_limit" in
    '' | *[!0-9]*)
        echo "ENV_BACKUP_LIMIT must be a positive integer" >&2
        exit 2
        ;;
esac
if [ "$backup_limit" -lt 1 ]; then
    echo "ENV_BACKUP_LIMIT must be a positive integer" >&2
    exit 2
fi

if [ ! -f "$example_file" ]; then
    echo "Environment template not found: $example_file" >&2
    exit 2
fi

if [ ! -f "$env_file" ]; then
    umask 077
    cp "$example_file" "$env_file"
    chmod 0600 "$env_file"
    echo "Created $env_file from $example_file." >&2
    echo "Fill secrets in $env_file and run deploy again." >&2
    exit 3
fi

temporary_file=$(mktemp "${env_file}.tmp.XXXXXX")
trap 'rm -f "$temporary_file"' EXIT HUP INT TERM
cp "$env_file" "$temporary_file"
chmod 0600 "$temporary_file"

added_count=0
while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
        '' | \#*) continue ;;
        *=*) ;;
        *) continue ;;
    esac

    key=${line%%=*}
    if ! printf '%s\n' "$key" | grep -Eq '^[A-Za-z_][A-Za-z0-9_]*$'; then
        continue
    fi
    if grep -q "^${key}=" "$env_file"; then
        continue
    fi

    printf '\n%s\n' "$line" >>"$temporary_file"
    added_count=$((added_count + 1))
    echo "Added environment variable: $key"
done <"$example_file"

if [ "$added_count" -eq 0 ]; then
    echo "$env_file is already synchronized with $example_file."
    exit 0
fi

backup_dir="${env_file}.backups"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_path="${backup_dir}/env_${timestamp}_$$.bak"
mkdir -p "$backup_dir"
chmod 0700 "$backup_dir"
cp "$env_file" "$backup_path"
chmod 0600 "$backup_path"

mv "$temporary_file" "$env_file"
temporary_file=

ls -1t "$backup_dir"/env_*.bak 2>/dev/null \
    | awk -v keep="$backup_limit" 'NR > keep' \
    | while IFS= read -r expired_backup; do
        rm -f "$expired_backup"
    done

echo "Synchronized $env_file: added $added_count variable(s)."
echo "Previous version: $backup_path"
