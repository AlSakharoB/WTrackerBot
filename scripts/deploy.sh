#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
cd "$project_dir"
source_dir=${DEPLOY_SOURCE_DIR:-$project_dir}
compose_file=${COMPOSE_FILE:-$project_dir/docker-compose.yml}
env_file=${ENV_FILE:-$project_dir/.env}
deploy_lock_file=${DEPLOY_LOCK_FILE:-${TMPDIR:-/tmp}/wtrackerbot-deploy.lock}
prune_after_deploy=${DOCKER_PRUNE_AFTER_DEPLOY:-true}
skip_build=${DEPLOY_SKIP_BUILD:-false}
allow_dirty_source=${DEPLOY_ALLOW_DIRTY_SOURCE:-false}
lock_held=${DEPLOY_LOCK_HELD:-false}
diagnostics_enabled=false
cleanup_started=false

fail() {
    echo "Mini App deploy failed: $*" >&2
    exit 2
}

validate_boolean() {
    value=$1
    name=$2
    case "$value" in
        true | false) ;;
        *) fail "$name must be true or false" ;;
    esac
}

setting_value() {
    key=$1
    awk -F= -v expected="$key" '
        $1 == expected {
            sub(/^[^=]*=/, "")
            print
            found = 1
        }
        END { if (!found) exit 1 }
    ' "$env_file"
}

compose() {
    docker compose -f "$compose_file" "$@"
}

show_storage() {
    echo "Docker and root filesystem usage:"
    docker system df
    df -h /
}

show_failure_diagnostics() {
    if [ "$cleanup_started" = "true" ]; then
        echo "Deploy smoke tests passed, but Docker cleanup did not finish." >&2
    else
        echo "Deploy did not complete; cleanup was not started." >&2
    fi
    if [ "$diagnostics_enabled" = "true" ]; then
        compose ps -a >&2 || true
        compose logs --no-color --tail=200 db backup migrate bot web miniapp >&2 || true
    fi
}

on_exit() {
    status=$?
    trap - EXIT HUP INT TERM
    if [ "$status" -ne 0 ]; then
        show_failure_diagnostics
    fi
    exit "$status"
}

trap on_exit EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

validate_boolean "$prune_after_deploy" DOCKER_PRUNE_AFTER_DEPLOY
validate_boolean "$skip_build" DEPLOY_SKIP_BUILD
validate_boolean "$allow_dirty_source" DEPLOY_ALLOW_DIRTY_SOURCE
validate_boolean "$lock_held" DEPLOY_LOCK_HELD

command -v flock >/dev/null 2>&1 || fail "flock is required"
if [ "$lock_held" = "false" ]; then
    exec 9>"$deploy_lock_file"
    flock -n 9 || fail "another deploy or rollback is already running"
    export DEPLOY_LOCK_HELD=true
else
    flock -n 9 >/dev/null 2>&1 || fail "inherited deploy lock is unavailable"
fi

command -v git >/dev/null 2>&1 || fail "git is required"
[ -d "$source_dir" ] || fail "deployment source directory is missing"
[ -f "$compose_file" ] || fail "Compose file is missing"

if [ "$allow_dirty_source" = "false" ] \
    && [ -n "$(git -C "$source_dir" status --porcelain --untracked-files=normal)" ]; then
    fail "deployment source contains uncommitted files"
fi

echo "Synchronizing .env with .env.example"
ENV_FILE="$env_file" "$script_dir/sync_env.sh"

echo "Running production preflight"
COMPOSE_FILE="$compose_file" ENV_FILE="$env_file" \
    "$script_dir/miniapp_preflight.sh"
diagnostics_enabled=true

revision=$(git -C "$source_dir" rev-parse --verify HEAD)
short_revision=$(git -C "$source_dir" rev-parse --short=12 HEAD)
app_version=${DEPLOY_APP_VERSION:-$(setting_value APP_VERSION)}
case "$app_version" in
    '' | *[!A-Za-z0-9._-]*) fail "APP_VERSION is not a valid image tag component" ;;
esac
export APP_VERSION=$app_version
export GIT_COMMIT_SHA=$short_revision

echo "Deploying APP_VERSION=$APP_VERSION GIT_COMMIT_SHA=$GIT_COMMIT_SHA"
echo "Git revision: $revision"
show_storage

if [ "$skip_build" = "false" ]; then
    echo "Building backup, application and Mini App images"
    compose build backup bot miniapp
else
    echo "Using images prepared by rollback preflight"
fi

echo "Starting DB -> backup/migration -> bot + web -> miniapp"
compose up -d --no-build --wait

echo "Checking long-running services"
compose exec -T bot python scripts/healthcheck.py
compose exec -T web python scripts/web_healthcheck.py --mode readiness
compose exec -T miniapp \
    curl --fail --silent --show-error --max-time 3 \
    --output /dev/null http://127.0.0.1:2019/healthz

miniapp_enabled=$(setting_value MINIAPP_ENABLED)
miniapp_domain=$(setting_value MINIAPP_DOMAIN)
public_url=$(setting_value MINIAPP_PUBLIC_URL)
public_url=${public_url%/}

case "$miniapp_domain" in
    localhost | *.example.com) public_smoke=false ;;
    *)
        if [ "$public_url" = "https://$miniapp_domain" ]; then
            public_smoke=true
        else
            public_smoke=false
        fi
        ;;
esac

if [ "$public_smoke" = "true" ]; then
    command -v curl >/dev/null 2>&1 || fail "curl is required for HTTPS smoke tests"
    echo "Checking HTTPS frontend and API routing"
    frontend_status=$(curl --silent --show-error --max-time 15 --noproxy '*' \
        --resolve "$miniapp_domain:443:127.0.0.1" \
        --output /dev/null --write-out '%{http_code}' "$public_url/") || \
        fail "HTTPS frontend request failed"
    [ "$frontend_status" = "200" ] || \
        fail "HTTPS frontend returned HTTP $frontend_status"

    api_status=$(curl --silent --show-error --max-time 15 --noproxy '*' \
        --resolve "$miniapp_domain:443:127.0.0.1" \
        --output /dev/null --write-out '%{http_code}' "$public_url/api/v1/me") || \
        fail "public API request failed"
    if [ "$miniapp_enabled" = "true" ]; then
        expected_api_status=401
    else
        expected_api_status=503
    fi
    [ "$api_status" = "$expected_api_status" ] || \
        fail "public API routing returned HTTP $api_status"

    internal_status=$(curl --silent --show-error --max-time 15 --noproxy '*' \
        --resolve "$miniapp_domain:443:127.0.0.1" \
        --output /dev/null --write-out '%{http_code}' \
        "$public_url/internal/readyz") || \
        fail "public internal endpoint request failed"
    [ "$internal_status" = "404" ] || \
        fail "public internal endpoint returned HTTP $internal_status"

    if [ "$miniapp_enabled" = "true" ]; then
        echo "Checking production host and Caddy storage"
        COMPOSE_FILE="$compose_file" ENV_FILE="$env_file" \
            "$script_dir/miniapp_host_audit.sh"
    fi
else
    [ "$miniapp_enabled" = "false" ] || \
        fail "HTTPS smoke test cannot be skipped while Mini App is enabled"
    echo "Skipping public HTTPS smoke while Mini App uses a disabled placeholder URL"
fi

echo "Smoke tests passed"

if [ "$prune_after_deploy" = "true" ]; then
    cleanup_started=true
    echo "Migration logs before cleanup"
    compose logs --no-color backup migrate

    echo "Removing completed deployment containers"
    compose rm -f backup migrate

    echo "Removing unused images and build cache"
    docker image prune -a -f
    docker builder prune -a -f
else
    echo "Docker cleanup is disabled for this deployment"
fi

show_storage
echo "Deploy completed: APP_VERSION=$APP_VERSION GIT_COMMIT_SHA=$GIT_COMMIT_SHA"
compose ps
