#!/bin/sh
set -eu

compose_file=${TEST_COMPOSE_FILE:-docker-compose.test.yml}

cleanup() {
    docker compose -f "$compose_file" down
}

trap cleanup EXIT HUP INT TERM

docker compose -f "$compose_file" config --quiet
docker compose -f "$compose_file" up \
    --build \
    --abort-on-container-exit \
    --exit-code-from tests
