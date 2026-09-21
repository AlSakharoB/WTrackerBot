#!/bin/sh
set -eu

case "$(basename "$0")" in
    pg_dump)
        output=""
        for argument in "$@"; do
            case "$argument" in
                --file=*) output=${argument#--file=} ;;
            esac
        done
        test -n "$output"
        printf 'verified custom dump' >"$output"
        ;;
    pg_restore)
        exit 0
        ;;
    date)
        printf '20260920T120000Z\n'
        ;;
    *)
        printf 'Unsupported fake command: %s\n' "$0" >&2
        exit 2
        ;;
esac
