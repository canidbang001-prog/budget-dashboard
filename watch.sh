#!/bin/bash
# watch.sh — .py 변경 감지 → 재빌드 + 재시작
# 우리 컨테이너(hermes-app) 안에서 실행됨. docker.sock 통해 호스트 도커 조작.
#
# mount source는 host path를 사용해야 함 (컨테이너 path X)
# 우리 컨테이너의 /opt/data는 host의 /volume1/docker/hermes-agent/data에 bind mount

set -e
WATCH_DIR="${WATCH_DIR:-/opt/data/projects/합본예산서-대시보드}"
HOST_DATA_DIR="/volume1/docker/hermes-agent/data/projects/합본예산서-대시보드"
IMAGE_NAME="budget-dashboard:latest"
CONTAINER_NAME="budget-dashboard"

echo "[watch] 시작: $WATCH_DIR 감시 중..."
echo "[watch] host path: $HOST_DATA_DIR"

LAST_HASH=""

while true; do
    # .py 파일 해시 계산 (.venv/__pycache__ 제외)
    CURRENT_HASH=$(find "$WATCH_DIR" -name "*.py" \
        -not -path "*/.venv/*" \
        -not -path "*/__pycache__/*" \
        -exec md5sum {} \; 2>/dev/null | md5sum | awk '{print $1}')

    if [ "$CURRENT_HASH" != "$LAST_HASH" ] && [ -n "$LAST_HASH" ]; then
        echo "[watch] $(date '+%H:%M:%S') .py 변경 감지 → 재빌드 시작"
        cd "$WATCH_DIR"
        if docker build -t "$IMAGE_NAME" . > /tmp/rebuild.log 2>&1; then
            echo "[watch] 빌드 성공 → 컨테이너 재시작"
            docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
            docker run -d \
                --name "$CONTAINER_NAME" \
                --restart unless-stopped \
                --network host \
                -v "$HOST_DATA_DIR/budget.db:/app/budget.db:ro" \
                -v "$HOST_DATA_DIR/summary.json:/app/summary.json:ro" \
                -v "$HOST_DATA_DIR/budget.csv:/app/budget.csv:ro" \
                "$IMAGE_NAME" > /dev/null
            echo "[watch] ✅ 반영 완료: http://1.11.122.94:3003 (또는 192.168.0.28:3003)"
        else
            echo "[watch] ❌ 빌드 실패:"
            tail -20 /tmp/rebuild.log
        fi
    fi
    LAST_HASH="$CURRENT_HASH"
    sleep 3
done
