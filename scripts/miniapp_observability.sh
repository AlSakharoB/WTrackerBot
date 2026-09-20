#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
compose_file=${COMPOSE_FILE:-$project_dir/docker-compose.yml}
since=${MINIAPP_OBSERVABILITY_SINCE:-1h}

fail() {
    echo "Mini App observability report failed: $1" >&2
    exit 2
}

compose() {
    docker compose -f "$compose_file" "$@"
}

cleanup() {
    rm -rf "$work_dir"
}

[ -f "$compose_file" ] || fail "Compose file is missing"
command -v docker >/dev/null 2>&1 || fail "Docker is not installed"
docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is unavailable"

work_dir=$(mktemp -d)
trap cleanup EXIT HUP INT TERM

echo "== Docker services and health =="
compose ps
for service in db bot web miniapp; do
    container_id=$(compose ps -q "$service")
    [ -n "$container_id" ] || fail "$service container is missing"
    health_status=$(docker inspect --format \
        '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' \
        "$container_id")
    printf '%-12s %s\n' "$service" "$health_status"
done

printf '\n== CPU and RAM ==\n'
docker stats --no-stream --format \
    'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}'

printf '\n== PostgreSQL connections ==\n'
compose exec -T db sh -c \
    'psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --no-align --tuples-only --command "SELECT count(*) AS total, count(*) FILTER (WHERE state = '\''active'\'') AS active FROM pg_stat_activity WHERE datname = current_database();"' || \
    fail "could not read aggregate PostgreSQL connection counts"

printf '\n== Root filesystem ==\n'
df -h /

printf '\n== Docker storage ==\n'
docker system df

compose logs --no-color --since "$since" web >"$work_dir/web.log" 2>&1 || \
    fail "could not read Web API logs"
compose logs --no-color --since "$since" miniapp >"$work_dir/caddy.log" 2>&1 || \
    fail "could not read Caddy logs"

printf '\n== Web API errors (correlation_id and user_id) ==\n'
awk '/ \| (ERROR|CRITICAL) \|/ || /status=5[0-9][0-9]/' \
    "$work_dir/web.log" || true

printf '\n== Open Food Facts failures (not availability failures) ==\n'
awk '/operation=external_product.lookup/ && /status=(error|timeout|5xx|429)/' \
    "$work_dir/web.log" || true

printf '\n== Caddy TLS/upstream errors (access logging is disabled) ==\n'
awk 'tolower($0) ~ /(level.?[:=].?error|tls|upstream|reverse_proxy)/' \
    "$work_dir/caddy.log" || true

printf '\nReport complete for the last %s. No request headers or initData were read.\n' \
    "$since"
