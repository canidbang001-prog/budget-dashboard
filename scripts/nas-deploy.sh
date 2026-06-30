#!/usr/bin/env bash
# NAS에서 GitHub 최신 코드를 받아 Docker 컨테이너를 재시작합니다.
# NAS의 Synology DSM Tasks 또는 crontab에서 1분마다 실행하도록 등록하세요.

set -e

# 실제 프로젝트 경로로 수정하세요.
# 예: /volume1/docker/hermes-agent/data/projects/홍성예산/budget-dashboard
PROJECT_DIR="/volume1/docker/hermes-agent/data/projects/예산대시보드/홍성군예산대시보드"
CONTAINER_NAME="budget-dashboard"

if [ ! -d "$PROJECT_DIR/.git" ]; then
    echo "[deploy] $PROJECT_DIR 가 Git 저장소가 아닙니다. 경로를 확인하세요."
    exit 1
fi

cd "$PROJECT_DIR"

# GitHub에서 최신 상태 확인
# REMOTE_URL은 .git/config 의 origin 에 등록되어 있어야 합니다.
git fetch origin

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/master)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "[deploy] 이미 최신입니다. ($LOCAL)"
    exit 0
fi

echo "[deploy] 변경 감지. GitHub에서 pull: $LOCAL -> $REMOTE"
git pull origin master

echo "[deploy] Docker 이미지 재빌드 & 컨테이너 재시작"
if command -v docker-compose &> /dev/null; then
    docker-compose down
    docker-compose up --build -d
elif command -v docker &> /dev/null; then
    docker compose down
    docker compose up --build -d
else
    echo "[deploy] docker 명령어를 찾을 수 없습니다."
    exit 1
fi

if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[deploy] 완료: http://1.11.122.94:3003"
else
    echo "[deploy] 컨테이너가 떠 있지 않습니다. 로그 확인: docker logs $CONTAINER_NAME"
fi
