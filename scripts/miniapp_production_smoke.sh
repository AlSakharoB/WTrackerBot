#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
env_file=${ENV_FILE:-$project_dir/.env}
compose_file=${COMPOSE_FILE:-$project_dir/docker-compose.yml}

fail() {
    echo "Mini App production smoke failed: $1" >&2
    exit 2
}

setting_value() {
    awk -F= -v expected="$1" '
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

cleanup() {
    rm -rf "$work_dir"
}

[ -f "$env_file" ] || fail "environment file is missing"
[ -f "$compose_file" ] || fail "Compose file is missing"
for command in curl docker python3; do
    command -v "$command" >/dev/null 2>&1 || fail "$command is not installed"
done

public_url=$(setting_value MINIAPP_PUBLIC_URL) || \
    fail "MINIAPP_PUBLIC_URL is missing"
public_url=${public_url%/}
expected_version=$(setting_value APP_VERSION) || fail "APP_VERSION is missing"

echo "Running public DNS, TLS, redirect and port audit"
COMPOSE_FILE="$compose_file" ENV_FILE="$env_file" \
    "$script_dir/miniapp_public_audit.sh"

echo "Running production host and container audit"
COMPOSE_FILE="$compose_file" ENV_FILE="$env_file" \
    "$script_dir/miniapp_host_audit.sh"

work_dir=$(mktemp -d)
trap cleanup EXIT HUP INT TERM

root_headers="$work_dir/root.headers"
root_body="$work_dir/index.html"
root_status=$(curl --silent --show-error --max-time 15 \
    --dump-header "$root_headers" --output "$root_body" \
    --write-out '%{http_code}' "$public_url/") || \
    fail "frontend request failed"
[ "$root_status" = "200" ] || fail "frontend returned HTTP $root_status"
grep -Eiq '^content-type:[[:space:]]*text/html([;[:space:]]|$)' \
    "$root_headers" || fail "frontend Content-Type is not text/html"
grep -q '<div id="root"></div>' "$root_body" || \
    fail "frontend response is not the application shell"

route_headers="$work_dir/route.headers"
route_body="$work_dir/route.html"
route_status=$(curl --silent --show-error --max-time 15 \
    --dump-header "$route_headers" --output "$route_body" \
    --write-out '%{http_code}' "$public_url/weight") || \
    fail "direct SPA route request failed"
[ "$route_status" = "200" ] || \
    fail "direct SPA route returned HTTP $route_status"
grep -Eiq '^content-type:[[:space:]]*text/html([;[:space:]]|$)' \
    "$route_headers" || fail "direct SPA route Content-Type is not text/html"
cmp -s "$root_body" "$route_body" || \
    fail "direct SPA route did not return the application shell"

map_status=$(curl --silent --show-error --max-time 15 \
    --output /dev/null --write-out '%{http_code}' \
    "$public_url/assets/production-smoke.js.map") || \
    fail "source map policy request failed"
[ "$map_status" = "404" ] || \
    fail "source map URL returned HTTP $map_status instead of 404"
compose exec -T miniapp sh -c \
    '! find /srv -type f -name "*.map" -print -quit | grep -q .' || \
    fail "frontend container contains source maps"

release_headers="$work_dir/release.headers"
release_body="$work_dir/release.json"
release_status=$(curl --silent --show-error --max-time 15 \
    --dump-header "$release_headers" --output "$release_body" \
    --write-out '%{http_code}' "$public_url/release.json") || \
    fail "frontend release marker request failed"
[ "$release_status" = "200" ] || \
    fail "frontend release marker returned HTTP $release_status"
grep -Eiq '^content-type:[[:space:]]*application/json([;[:space:]]|$)' \
    "$release_headers" || fail "release marker Content-Type is not application/json"

frontend_identity=$(python3 -c \
    'import json,sys; p=json.load(open(sys.argv[1], encoding="utf-8")); print(str(p["version"])+"|"+str(p["commit"]))' \
    "$release_body") || fail "frontend release marker is invalid"
api_identity=$(compose exec -T web python -c \
    'from app.config import get_settings; s=get_settings(); print(f"{s.app_version}|{s.git_commit_sha}")') || \
    fail "could not read Web API release identity"
bot_identity=$(compose exec -T bot python -c \
    'from app.config import get_settings; s=get_settings(); print(f"{s.app_version}|{s.git_commit_sha}")') || \
    fail "could not read bot release identity"

[ "$frontend_identity" = "$api_identity" ] || \
    fail "frontend and Web API release identities differ"
[ "$api_identity" = "$bot_identity" ] || \
    fail "Web API and bot release identities differ"
case "$frontend_identity" in
    "$expected_version"'|'*) ;;
    *) fail "running release version does not match APP_VERSION" ;;
esac

echo "Mini App production smoke passed."
echo "Frontend, SPA routing, source maps, internal routes and release identity: valid."
