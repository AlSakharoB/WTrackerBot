#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
cd "$project_dir"

compose_file=${COMPOSE_FILE:-docker-compose.yml}
prune_after_deploy=${DOCKER_PRUNE_AFTER_DEPLOY:-true}

case "$prune_after_deploy" in
    true | false) ;;
    *)
        echo "DOCKER_PRUNE_AFTER_DEPLOY must be true or false" >&2
        exit 2
        ;;
esac

echo "Synchronizing .env with .env.example"
"$script_dir/sync_env.sh"

echo "Building application image"
docker compose -f "$compose_file" build backup migrate bot

echo "Starting DB -> backup/migration -> bot"
docker compose -f "$compose_file" up -d --wait

echo "Running application healthcheck"
docker compose -f "$compose_file" exec -T bot python scripts/healthcheck.py

if [ "$prune_after_deploy" = "true" ]; then
    echo "Migration logs before cleanup"
    docker compose -f "$compose_file" logs --no-color backup migrate

    echo "Removing completed deploy containers and unused Docker data"
    docker compose -f "$compose_file" rm -f backup migrate
    docker system prune -a -f
fi

echo "Deploy completed"
docker compose -f "$compose_file" ps
