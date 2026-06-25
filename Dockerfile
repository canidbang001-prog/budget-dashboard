FROM python:3.13-slim

WORKDIR /app

# 시스템 의존성 (uvloop 등 wheel 없는 경우 대비)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 의존성 먼저 복사 → 레이어 캐시 활용
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 소스
COPY . .

# uvicorn 실행
EXPOSE 3003
ENV DB_PATH=/app/budget.db
CMD ["uvicorn", "main_integrated:app", "--host", "0.0.0.0", "--port", "3003"]
