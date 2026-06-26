#!/bin/bash
# watch.sh v2 — watchfiles (inotify) + docker build + restart
# 우리 컨테이너(hermes-app) 안에서 실행. docker.sock 통해 호스트 도커 조작.
# .py 변경 감지 → image 재빌드 → 컨테이너 재시작
# 평균 반영 시간: 빌드 시간 = 5~10초 (watchfiles는 inotify 기반이라 감지 즉시)

set -e
WATCH_DIR="${WATCH_DIR:-/opt/data/projects/합본예산서-대시보드}"
HOST_DATA_DIR="/volume1/docker/hermes-agent/data/projects/합본예산서-대시보드"
IMAGE_NAME="budget-dashboard:latest"
CONTAINER_NAME="budget-dashboard"

echo "[watch] 시작: $WATCH_DIR 감시 중..."

cd "$WATCH_DIR"
exec .venv/bin/watchfiles \
    --ignore-paths .venv \
    --ignore-paths __pycache__ \
    --ignore-paths .git \
    --filter python \
    "bash -c '
        echo \"[watch] \$(date +%H:%M:%S) 변경 감지 → 빌드\"
        cd $WATCH_DIR
        if docker build -t $IMAGE_NAME . > /tmp/rebuild.log 2>&1; then
            docker rm -f $CONTAINER_NAME 2>/dev/null || true
            docker run -d --name $CONTAINER_NAME --restart unless-stopped --network host \
                -v $HOST_DATA_DIR/budget.db:/app/budget.db \
                -v $HOST_DATA_DIR/summary.json:/app/summary.json:ro \
                -v $HOST_DATA_DIR/budget.csv:/app/budget.csv:ro \
                $IMAGE_NAME > /dev/null
            echo \"[watch] ✅ 반영 완료: http://1.11.122.94:3003\"
        else
            echo \"[watch] ❌ 빌드 실패:\"
            tail -20 /tmp/rebuild.log
        fi
    '" "$WATCH_DIR"
