#!/bin/sh
set -eu

case "$(basename "$0")" in
    docker)
        printf '%s\n' "$*" >>"$FAKE_DOCKER_LOG"
        if [ -n "${FAKE_DOCKER_FAIL_MATCH:-}" ]; then
            case "$*" in
                *"$FAKE_DOCKER_FAIL_MATCH"*) exit 42 ;;
            esac
        fi
        case "$*" in
            *"system df"*) echo "TYPE TOTAL ACTIVE SIZE RECLAIMABLE" ;;
            *"exec -T bot"*) echo "HEALTHY: bot" ;;
        esac
        ;;
    curl)
        printf '%s\n' "$*" >>"$FAKE_CURL_LOG"
        case "$*" in
            */api/v1/me) printf '%s' "${FAKE_API_STATUS:-503}" ;;
            */internal/readyz) printf '404' ;;
            *) printf '200' ;;
        esac
        ;;
    git)
        case "$*" in
            *" status "*) exit 0 ;;
            *"rev-parse --short=12 HEAD"*)
                printf '%s\n' "${FAKE_GIT_SHORT:-0123456789ab}"
                ;;
            *"rev-parse --verify HEAD"*)
                printf '%s\n' \
                    "${FAKE_GIT_REVISION:-0123456789abcdef0123456789abcdef01234567}"
                ;;
            *) exit 2 ;;
        esac
        ;;
    *) exit 2 ;;
esac
