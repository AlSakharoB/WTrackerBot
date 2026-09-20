#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
env_file=${ENV_FILE:-$project_dir/.env}
minimum_certificate_seconds=${MINIAPP_CERTIFICATE_MIN_SECONDS:-604800}

fail() {
    echo "Mini App public audit failed: $1" >&2
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

cleanup() {
    rm -f "$headers_file" "$tls_file" "$certificate_file"
}

[ -f "$env_file" ] || fail "environment file is missing"
for command in dig curl openssl python3; do
    command -v "$command" >/dev/null 2>&1 || fail "$command is not installed"
done

case "$minimum_certificate_seconds" in
    '' | *[!0-9]*) fail "MINIAPP_CERTIFICATE_MIN_SECONDS must be an integer" ;;
esac

domain=$(setting_value MINIAPP_DOMAIN) || fail "MINIAPP_DOMAIN is missing"
public_url=$(setting_value MINIAPP_PUBLIC_URL) || fail "MINIAPP_PUBLIC_URL is missing"
public_url=${public_url%/}
expected_ipv4=$(setting_value MINIAPP_EXPECTED_IPV4) || \
    fail "MINIAPP_EXPECTED_IPV4 is missing"
expected_ipv6=$(setting_value MINIAPP_EXPECTED_IPV6 2>/dev/null || true)
ssh_port=$(setting_value MINIAPP_SSH_PORT 2>/dev/null || printf '22\n')
miniapp_enabled=$(setting_value MINIAPP_ENABLED) || \
    fail "MINIAPP_ENABLED is missing"

[ -n "$expected_ipv4" ] || fail "MINIAPP_EXPECTED_IPV4 must not be empty"
[ "$public_url" = "https://$domain" ] || \
    fail "MINIAPP_PUBLIC_URL must be the HTTPS origin for MINIAPP_DOMAIN"
case "$domain" in
    localhost | *.example.com) fail "MINIAPP_DOMAIN is still a placeholder" ;;
esac

a_records=$(dig +short "$domain" A | awk 'NF { print }' | sort -u)
[ "$a_records" = "$expected_ipv4" ] || \
    fail "DNS A record does not exactly match MINIAPP_EXPECTED_IPV4"

cname_records=$(dig +short "$domain" CNAME | awk 'NF { print }')
[ -z "$cname_records" ] || fail "conflicting DNS CNAME record exists"

aaaa_records=$(dig +short "$domain" AAAA | awk 'NF { print }' | sort -u)
if [ -n "$expected_ipv6" ]; then
    [ "$aaaa_records" = "$expected_ipv6" ] || \
        fail "DNS AAAA record does not exactly match MINIAPP_EXPECTED_IPV6"
else
    [ -z "$aaaa_records" ] || \
        fail "DNS AAAA exists while MINIAPP_EXPECTED_IPV6 is empty"
fi

headers_file=$(mktemp)
tls_file=$(mktemp)
certificate_file=$(mktemp)
trap cleanup EXIT HUP INT TERM

http_status=$(curl --silent --show-error --max-time 15 \
    --dump-header "$headers_file" --output /dev/null --write-out '%{http_code}' \
    "http://$domain/") || fail "HTTP redirect request failed"
case "$http_status" in
    301 | 302 | 307 | 308) ;;
    *) fail "HTTP endpoint did not redirect to HTTPS" ;;
esac
grep -Eiq "^location:[[:space:]]*https://$domain/?[[:space:]]*$" "$headers_file" || \
    fail "HTTP redirect location does not match the HTTPS origin"

frontend_status=$(curl --silent --show-error --max-time 15 \
    --dump-header "$headers_file" --output /dev/null --write-out '%{http_code}' \
    "$public_url/") || fail "HTTPS frontend request failed"
[ "$frontend_status" = "200" ] || \
    fail "HTTPS frontend returned HTTP $frontend_status"
grep -Eiq '^strict-transport-security:' "$headers_file" || \
    fail "HTTPS response is missing Strict-Transport-Security"

api_status=$(curl --silent --show-error --max-time 15 \
    --output /dev/null --write-out '%{http_code}' "$public_url/api/v1/me") || \
    fail "public API request failed"
if [ "$miniapp_enabled" = "true" ]; then
    expected_api_status=401
else
    expected_api_status=503
fi
[ "$api_status" = "$expected_api_status" ] || \
    fail "public API returned HTTP $api_status instead of $expected_api_status"

internal_status=$(curl --silent --show-error --max-time 15 \
    --output /dev/null --write-out '%{http_code}' "$public_url/internal/readyz") || \
    fail "public internal endpoint request failed"
[ "$internal_status" = "404" ] || \
    fail "public internal endpoint returned HTTP $internal_status"

openssl s_client -connect "$domain:443" -servername "$domain" \
    -verify_hostname "$domain" -verify_return_error -showcerts \
    </dev/null >"$tls_file" 2>&1 || fail "TLS chain or hostname validation failed"
awk '
    /-----BEGIN CERTIFICATE-----/ { certificate = 1 }
    certificate { print }
    /-----END CERTIFICATE-----/ { exit }
' "$tls_file" >"$certificate_file"
grep -q 'BEGIN CERTIFICATE' "$certificate_file" || \
    fail "server leaf certificate was not returned"
openssl x509 -in "$certificate_file" -noout \
    -checkend "$minimum_certificate_seconds" >/dev/null || \
    fail "TLS certificate expires too soon"

python3 "$script_dir/miniapp_external_ports.py" \
    --host "$expected_ipv4" --ssh-port "$ssh_port" || \
    fail "external TCP port policy failed"
if [ -n "$expected_ipv6" ]; then
    python3 "$script_dir/miniapp_external_ports.py" \
        --host "$expected_ipv6" --ssh-port "$ssh_port" || \
        fail "external IPv6 TCP port policy failed"
fi

echo "TLS certificate:"
openssl x509 -in "$certificate_file" -noout -subject -issuer -dates \
    -fingerprint -sha256 -ext subjectAltName
echo "Mini App public audit passed."
echo "DNS, redirect, TLS, routes, headers, and external TCP ports: valid."
