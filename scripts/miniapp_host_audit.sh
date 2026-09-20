#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
env_file=${ENV_FILE:-$project_dir/.env}
compose_file=${COMPOSE_FILE:-$project_dir/docker-compose.yml}
restart_caddy=${MINIAPP_AUDIT_RESTART_CADDY:-false}

fail() {
    echo "Mini App host audit failed: $1" >&2
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

has_public_tcp_listener() {
    ss -H -ltn "( sport = :$1 )" | awk '
        $4 !~ /^127\./ && $4 !~ /^\[::1\]:/ && $4 !~ /^::1:/ {
            found = 1
        }
        END { exit !found }
    '
}

has_public_udp_listener() {
    ss -H -lun "( sport = :$1 )" | awk '
        $4 !~ /^127\./ && $4 !~ /^\[::1\]:/ && $4 !~ /^::1:/ {
            found = 1
        }
        END { exit !found }
    '
}

check_caddy_storage() {
    compose exec -T miniapp sh -c \
        'test -d /data/caddy/certificates && test -n "$(find /data/caddy/certificates -type f -print -quit)"' \
        >/dev/null 2>&1 || fail "Caddy certificate storage is empty"
}

wait_for_caddy() {
    attempts=0
    while [ "$attempts" -lt 15 ]; do
        if compose exec -T miniapp \
            curl --fail --silent --max-time 3 --output /dev/null \
            http://127.0.0.1:2019/healthz 2>/dev/null; then
            return 0
        fi
        attempts=$((attempts + 1))
        sleep 2
    done
    return 1
}

case "$restart_caddy" in
    true | false) ;;
    *) fail "MINIAPP_AUDIT_RESTART_CADDY must be true or false" ;;
esac

[ -f "$env_file" ] || fail "environment file is missing"
[ -f "$compose_file" ] || fail "Compose file is missing"
command -v docker >/dev/null 2>&1 || fail "Docker is not installed"
command -v ss >/dev/null 2>&1 || fail "ss is not installed"
command -v timedatectl >/dev/null 2>&1 || fail "timedatectl is not installed"

miniapp_enabled=$(setting_value MINIAPP_ENABLED) || \
    fail "MINIAPP_ENABLED is missing"
[ "$miniapp_enabled" = "true" ] || fail "MINIAPP_ENABLED must be true"

ssh_port=$(setting_value MINIAPP_SSH_PORT 2>/dev/null || printf '22\n')
case "$ssh_port" in
    '' | *[!0-9]*) fail "MINIAPP_SSH_PORT must be an integer" ;;
esac
[ "$ssh_port" -ge 1 ] && [ "$ssh_port" -le 65535 ] || \
    fail "MINIAPP_SSH_PORT must be between 1 and 65535"

ntp_status=$(timedatectl show --property=NTPSynchronized --value 2>/dev/null || true)
[ "$ntp_status" = "yes" ] || fail "system clock is not NTP-synchronized"

for required_port in "$ssh_port" 80 443; do
    has_public_tcp_listener "$required_port" || \
        fail "required public TCP port $required_port is not listening"
done

for private_port in 5432 8080 5173 5174; do
    if has_public_tcp_listener "$private_port"; then
        fail "private TCP port $private_port is publicly listening"
    fi
done

if has_public_udp_listener 443; then
    echo "HTTP/3 listener: UDP 443 is available."
else
    echo "HTTP/3 listener: UDP 443 is not available (optional)."
fi

compose config --quiet >/dev/null 2>&1 || fail "Docker Compose configuration is invalid"
running_services=$(compose ps --services --status running)
for required_service in db bot web miniapp; do
    printf '%s\n' "$running_services" | grep -qx "$required_service" || \
        fail "required service is not running: $required_service"
done

compose exec -T bot python scripts/healthcheck.py >/dev/null || \
    fail "bot healthcheck failed"
compose exec -T web python scripts/web_healthcheck.py --mode readiness >/dev/null || \
    fail "Web API readiness failed"
wait_for_caddy || fail "Caddy healthcheck failed"
check_caddy_storage

if [ "$restart_caddy" = "true" ]; then
    echo "Restarting Caddy to verify persistent certificate storage."
    compose restart miniapp >/dev/null
    wait_for_caddy || fail "Caddy did not recover after restart"
    check_caddy_storage
fi

echo "Mini App host audit passed."
echo "NTP, listeners, services, readiness, and Caddy storage: valid."
