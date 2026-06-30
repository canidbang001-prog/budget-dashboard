# ── Stage 1: Next.js frontend build ────────────────────────────
FROM node:24-slim AS frontend-builder

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ── Stage 2: FastAPI runtime ───────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# 시스템 의존성 (uvloop 등 wheel 없는 경우 대비)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Python 앱 소스
COPY . .

# frontend build 결과만 복사
COPY --from=frontend-builder /build/out ./frontend/out

# Windows cp949 console 인코딩 문제 방지
ENV PYTHONIOENCODING=UTF-8

# uvicorn 실행
EXPOSE 3003
ENV DB_PATH=/app/budget.db
CMD ["uvicorn", "main_integrated:app", "--host", "0.0.0.0", "--port", "3003"]
