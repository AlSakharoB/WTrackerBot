#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
env_file=${ENV_FILE:-$project_dir/.env}
compose_file=${COMPOSE_FILE:-$project_dir/docker-compose.yml}
skip_system_checks=${MINIAPP_PREFLIGHT_SKIP_SYSTEM_CHECKS:-false}
minimum_free_mb=${MINIAPP_PREFLIGHT_MIN_FREE_MB:-2048}

fail() {
    echo "Mini App preflight failed: $1" >&2
    exit 2
}

case "$skip_system_checks" in
    true | false) ;;
    *) fail "MINIAPP_PREFLIGHT_SKIP_SYSTEM_CHECKS must be true or false" ;;
esac

case "$minimum_free_mb" in
    '' | *[!0-9]*) fail "MINIAPP_PREFLIGHT_MIN_FREE_MB must be a non-negative integer" ;;
esac

[ -f "$env_file" ] || fail "environment file is missing"
[ -f "$compose_file" ] || fail "Compose file is missing"

setting_count() {
    awk -v setting="$1" '
        index($0, setting "=") == 1 { count += 1 }
        END { print count + 0 }
    ' "$env_file"
}

setting_value() {
    awk -v setting="$1" '
        index($0, setting "=") == 1 {
            sub("^[^=]*=", "")
            print
            exit
        }
    ' "$env_file"
}

require_setting() {
    count=$(setting_count "$1")
    [ "$count" -eq 1 ] || fail "$1 must occur exactly once"
}

require_nonempty_setting() {
    require_setting "$1"
    [ -n "$(setting_value "$1")" ] || fail "$1 must not be empty"
}

validate_domain() {
    domain=$1
    [ "$domain" != "localhost" ] || return 1
    [ "${#domain}" -le 253 ] || return 1
    case "$domain" in
        *.*) ;;
        *) return 1 ;;
    esac
    case "$domain" in
        *[!A-Za-z0-9.-]* | .* | *. | *..* | *.-* | *-.*) return 1 ;;
    esac
    printf '%s\n' "$domain" | awk -F. '
        {
            for (part = 1; part <= NF; part += 1) {
                if (length($part) < 1 || length($part) > 63) exit 1
                if ($part !~ /^[A-Za-z0-9][A-Za-z0-9-]*[A-Za-z0-9]$/ &&
                    $part !~ /^[A-Za-z0-9]$/) exit 1
            }
        }
    ' || return 1
    printf '%s\n' "$domain" | grep -Eqv '^[0-9.]+$'
}

for required_key in \
    BOT_TOKEN \
    POSTGRES_PASSWORD \
    DATABASE_URL \
    APP_ENVIRONMENT \
    MINIAPP_ENABLED \
    MINIAPP_DOMAIN \
    MINIAPP_ACME_EMAIL \
    MINIAPP_PUBLIC_URL \
    MINIAPP_CORS_ORIGINS \
    MINIAPP_ALLOWED_TELEGRAM_IDS \
    MINIAPP_MANAGE_MENU_BUTTON \
    MINIAPP_MENU_BUTTON_TEXT
do
    require_setting "$required_key"
done

require_nonempty_setting BOT_TOKEN
require_nonempty_setting POSTGRES_PASSWORD
require_nonempty_setting DATABASE_URL

app_environment=$(setting_value APP_ENVIRONMENT)
[ "$app_environment" = "production" ] || fail "APP_ENVIRONMENT must be production"

miniapp_enabled=$(setting_value MINIAPP_ENABLED)
case "$miniapp_enabled" in
    true | false) ;;
    *) fail "MINIAPP_ENABLED must be true or false" ;;
esac

manage_menu_button=$(setting_value MINIAPP_MANAGE_MENU_BUTTON)
case "$manage_menu_button" in
    true | false) ;;
    *) fail "MINIAPP_MANAGE_MENU_BUTTON must be true or false" ;;
esac

menu_button_text=$(setting_value MINIAPP_MENU_BUTTON_TEXT)
[ -n "$(printf '%s' "$menu_button_text" | tr -d '[:space:]')" ] || \
    fail "MINIAPP_MENU_BUTTON_TEXT must not be blank"
menu_button_length=$(printf '%s' "$menu_button_text" | wc -m | tr -d '[:space:]')
[ "$menu_button_length" -le 64 ] || fail "MINIAPP_MENU_BUTTON_TEXT is too long"

allowed_ids=$(setting_value MINIAPP_ALLOWED_TELEGRAM_IDS)
if [ -n "$allowed_ids" ]; then
    printf '%s\n' "$allowed_ids" | \
        grep -Eq '^[1-9][0-9]*(,[[:space:]]*[1-9][0-9]*)*$' || \
        fail "MINIAPP_ALLOWED_TELEGRAM_IDS must contain positive comma-separated integers"
fi

acme_email=$(setting_value MINIAPP_ACME_EMAIL)
if [ -n "$acme_email" ]; then
    printf '%s\n' "$acme_email" | \
        grep -Eq '^[^[:space:]@]+@[^[:space:]@]+$' || \
        fail "MINIAPP_ACME_EMAIL must be a valid email address"
fi

if [ "$miniapp_enabled" = "true" ]; then
    miniapp_domain=$(setting_value MINIAPP_DOMAIN)
    validate_domain "$miniapp_domain" || \
        fail "MINIAPP_DOMAIN must be a public hostname without scheme, port, or path"

    expected_origin="https://$miniapp_domain"
    public_url=$(setting_value MINIAPP_PUBLIC_URL)
    [ "${public_url%/}" = "$expected_origin" ] || \
        fail "MINIAPP_PUBLIC_URL must exactly match MINIAPP_DOMAIN over HTTPS"

    cors_origins=$(setting_value MINIAPP_CORS_ORIGINS)
    [ "${cors_origins%/}" = "$expected_origin" ] || \
        fail "MINIAPP_CORS_ORIGINS must exactly match MINIAPP_PUBLIC_URL"
fi

if [ "$skip_system_checks" = "false" ]; then
    command -v docker >/dev/null 2>&1 || fail "Docker is not installed"
    docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is unavailable"
    docker compose -f "$compose_file" config --quiet >/dev/null 2>&1 || \
        fail "Docker Compose configuration is invalid"

    available_kb=$(df -Pk "$project_dir" | awk 'END { print $4 }')
    minimum_free_kb=$((minimum_free_mb * 1024))
    [ "$available_kb" -ge "$minimum_free_kb" ] || \
        fail "less than ${minimum_free_mb} MB is available for the Docker build"

    if command -v ss >/dev/null 2>&1; then
        running_services=$(
            docker compose -f "$compose_file" ps --services --status running \
                2>/dev/null || true
        )
        for public_port in 80 443; do
            if ss -H -ltn | awk -v suffix=":$public_port" \
                '$4 ~ suffix "$" { found = 1 } END { exit !found }'; then
                printf '%s\n' "$running_services" | grep -qx miniapp || \
                    fail "port $public_port is occupied by a non-project service"
            fi
        done
    fi
fi

echo "Mini App preflight passed."
echo "Environment contract: valid."
if [ "$skip_system_checks" = "false" ]; then
    echo "Docker Compose, disk space, and public ports: valid."
fi
