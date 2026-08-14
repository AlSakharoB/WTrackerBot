#!/bin/sh
set -eu

compose_file=${COMPOSE_FILE:-docker-compose.yml}

echo "Building application image"
docker compose -f "$compose_file" build backup migrate bot

echo "Starting DB -> backup/migration -> bot"
docker compose -f "$compose_file" up -d --wait

echo "Running application healthcheck"
docker compose -f "$compose_file" exec -T bot python scripts/healthcheck.py

echo "Deploy completed"
docker compose -f "$compose_file" ps
