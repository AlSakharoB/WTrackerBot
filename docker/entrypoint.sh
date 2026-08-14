#!/bin/sh
set -eu

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

rm -f /tmp/nutrition-bot-heartbeat
exec python -m app.main
