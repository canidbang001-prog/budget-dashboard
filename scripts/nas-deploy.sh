#!/usr/bin/env bash
# NAS auto-deploy: pull latest code from GitHub and rebuild the container
set -euo pipefail

PROJECT_DIR=/volume1/docker/hermes-agent/data/projects/합본예산서-대시보드
CONTAINER_NAME="budget-dashboard"

if [ ! -d "$PROJECT_DIR/.git" ]; then
    echo "[deploy] $PROJECT_DIR is not a Git repository"
    exit 1
fi

cd "$PROJECT_DIR"

git fetch origin
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/master)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "[deploy] already up-to-date ($LOCAL)"
    exit 0
fi

echo "[deploy] changes detected: $LOCAL -> $REMOTE"
git pull origin master

echo "[deploy] rebuilding and restarting container (zero-downtime-ish)"
if command -v docker-compose >/dev/null 2>&1; then
    docker-compose pull 2>/dev/null || true
    docker-compose up --build -d
else
    docker compose pull 2>/dev/null || true
    docker compose up --build -d
fi

sleep 3

if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[deploy] OK: http://1.11.122.94:3003"
else
    echo "[deploy] container is not running. check: docker logs $CONTAINER_NAME"
    exit 1
fi

# prune dangling images on Mondays
if [ "$(date +%u)" = "1" ]; then
    echo "[deploy] pruning dangling images..."
    docker image prune -f >/dev/null 2>&1 || true
fi
