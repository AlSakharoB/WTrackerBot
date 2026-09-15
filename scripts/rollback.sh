#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
compose_file=${COMPOSE_FILE:-$project_dir/docker-compose.yml}
env_file=${ENV_FILE:-$project_dir/.env}
deploy_lock_file=${DEPLOY_LOCK_FILE:-${TMPDIR:-/tmp}/wtrackerbot-deploy.lock}
rollback_dir=
worktree_added=false
cd "$project_dir"

fail() {
    echo "Rollback failed: $*" >&2
    exit 2
}

cleanup() {
    status=$?
    trap - EXIT HUP INT TERM
    if [ "$worktree_added" = "true" ]; then
        git -C "$project_dir" worktree remove --force "$rollback_dir" >/dev/null 2>&1 \
            || true
    elif [ -n "$rollback_dir" ]; then
        rmdir "$rollback_dir" >/dev/null 2>&1 || true
    fi
    exit "$status"
}

trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

[ "$#" -eq 1 ] || fail "usage: ./scripts/rollback.sh <git-tag>"
target_tag=$1
printf '%s\n' "$target_tag" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+$' || \
    fail "target must be a semantic version tag such as v1.0.2"
target_version=${target_tag#v}

command -v flock >/dev/null 2>&1 || fail "flock is required"
exec 9>"$deploy_lock_file"
flock -n 9 || fail "another deploy or rollback is already running"
export DEPLOY_LOCK_HELD=true

[ -f "$env_file" ] || fail ".env is missing"
[ -f "$compose_file" ] || fail "Compose file is missing"
target_commit=$(git -C "$project_dir" rev-parse --verify "$target_tag^{commit}") \
    || fail "git tag does not exist"
current_commit=$(git -C "$project_dir" rev-parse --verify HEAD)
[ "$target_commit" != "$current_commit" ] || fail "target tag is already deployed source"
git -C "$project_dir" merge-base --is-ancestor "$target_commit" "$current_commit" \
    || fail "target tag is not an ancestor of the current revision"

if [ -n "$(git -C "$project_dir" status --porcelain --untracked-files=normal)" ]; then
    fail "current source contains uncommitted files"
fi

database_container=$(docker compose -f "$compose_file" ps -q db)
[ -n "$database_container" ] || fail "database container is not running"
compose_project_name=$(docker inspect --format \
    '{{ index .Config.Labels "com.docker.compose.project" }}' \
    "$database_container")
[ -n "$compose_project_name" ] || fail "Compose project name is invalid"
export COMPOSE_PROJECT_NAME=$compose_project_name

database_image=$(docker inspect --format '{{.Image}}' "$database_container")
[ -n "$database_image" ] || fail "database image is unavailable"
backup_volume=$(docker volume ls \
    --filter "label=com.docker.compose.project=$compose_project_name" \
    --filter "label=com.docker.compose.volume=postgres_backups" \
    --format '{{.Name}}')
[ -n "$backup_volume" ] || fail "database backup volume is unavailable"
[ "$(printf '%s\n' "$backup_volume" | wc -l | tr -d '[:space:]')" -eq 1 ] || \
    fail "database backup volume is ambiguous"

echo "Checking current database revision"
docker compose -f "$compose_file" exec -T web \
    python scripts/web_healthcheck.py --mode readiness

echo "Checking verified database backup marker"
docker run --rm --read-only --network none \
    --volume "$backup_volume:/backups:ro" \
    --entrypoint sh "$database_image" -ec '
marker=/backups/.last-verified
[ -s "$marker" ] || { echo "Verified backup marker is missing" >&2; exit 2; }
read -r filename expected_checksum extra <"$marker"
[ -n "$filename" ] && [ -n "$expected_checksum" ] && [ -z "${extra:-}" ] || {
    echo "Verified backup marker is invalid" >&2
    exit 2
}
case "$filename" in
    .* | */*) echo "Verified backup filename is invalid" >&2; exit 2 ;;
esac
backup_path=/backups/$filename
[ -s "$backup_path" ] || { echo "Verified backup file is missing" >&2; exit 2; }
actual_checksum=$(sha256sum "$backup_path" | cut -d " " -f 1)
[ "$actual_checksum" = "$expected_checksum" ] || {
    echo "Verified backup checksum mismatch" >&2
    exit 2
}
echo "Verified backup: $filename"
'

rollback_dir=$(mktemp -d "${TMPDIR:-/tmp}/wtrackerbot-rollback.XXXXXX")
git -C "$project_dir" worktree add --detach "$rollback_dir" "$target_commit"
worktree_added=true

for required_file in Dockerfile frontend/Dockerfile frontend/Caddyfile; do
    [ -f "$rollback_dir/$required_file" ] || \
        fail "$target_tag is not compatible with the current deployment topology"
done

if grep -q 'README.md' "$rollback_dir/Dockerfile" \
    && [ ! -f "$rollback_dir/README.md" ]; then
    printf '%s\n' "WTrackerBot rollback source for $target_tag" \
        >"$rollback_dir/README.md"
fi

# Keep the current deployment topology and TLS health endpoint while building
# application and frontend sources from the selected tag.
cp "$compose_file" "$rollback_dir/docker-compose.yml"
cp "$project_dir/frontend/Caddyfile" "$rollback_dir/frontend/Caddyfile"
ln -s "$env_file" "$rollback_dir/.env"

rollback_compose=$rollback_dir/docker-compose.yml
target_revision=$(git -C "$rollback_dir" rev-parse --short=12 HEAD)
export APP_VERSION=$target_version
export GIT_COMMIT_SHA=$target_revision

echo "Building rollback images for $target_tag ($target_revision)"
docker compose -f "$rollback_compose" build backup bot miniapp

echo "Checking target code against the current database revision"
docker compose -f "$rollback_compose" run --rm --no-deps \
    --entrypoint python migrate \
    -c 'import asyncio; from app.config import get_settings; from scripts.migrate import verify_database_revision; asyncio.run(verify_database_revision(get_settings().database_url)); print("Database revision is compatible")'

echo "Deploying compatible rollback; database schema remains unchanged"
COMPOSE_FILE="$rollback_compose" \
ENV_FILE="$env_file" \
ENV_EXAMPLE_FILE="$project_dir/.env.example" \
DEPLOY_SOURCE_DIR="$rollback_dir" \
DEPLOY_APP_VERSION="$target_version" \
DEPLOY_ALLOW_DIRTY_SOURCE=true \
DEPLOY_SKIP_BUILD=true \
DEPLOY_LOCK_HELD=true \
    "$script_dir/deploy.sh"

echo "Rollback completed: $target_tag"
