# 합본예산서 대시보드 (Hongseong County Budget Dashboard)

2026 홍성군 합본예산서 + 이월 조서 통합 조회 대시보드 (FastAPI + Next.js)

## 빠른 시작

```bash
# 1. DB 업데이트 (xlsx + 이월 .xls → DB)
./update.sh

# 2. 컨테이너 자동 재시작됨. 페이지:
#    http://1.11.122.94:3003  (비번: 1234!)
```

## 파이프라인 구조

```
[2026 전체합본예산서.xlsx]    [2025 이월 .xls × 3]
        │                            │
        ▼                            ▼
  extract_csv.py              parse_carryover_all.py
        │                            │
        ▼                            │
   budget.csv                     carryover 컬럼
        │                            │
        ▼                            │
   parser_v8.py ───────┐             │
        │              │             │
        ▼              │             │
   budget.db (re)      │             │
        │              ▼             │
        │       rollup_finance.py ◄──┘
        │              │   (parser_v8의 last_row_id 버그 보정)
        │              ▼
        └──────► budget.db (최종)
                       │
                       ▼
              FastAPI (3003)
                       │
                       ▼
              Next.js (정적 export) → 웹페이지
```

## 스크립트

| 파일 | 용도 |
|---|---|
| `extract_csv.py` | xlsx → CSV (민성님 인덴트 형식) |
| `parser_v8.py` | CSV → DB (8단계 트리) |
| `rollup_finance.py` | 재원 rollup 보정 (post-processing) |
| `parse_carryover_all.py` | 이월 조서 40부서 매칭 |
| `update.sh` | 한방 실행 (extract→parse→rollup→carryover→verify) |
| `verify.py` | DB 정합성 검증 |
| `main_integrated.py` | FastAPI 서버 (3003) |
| `auth.py` | 비번 게이트 (itsdangerous) |
| `frontend/` | Next.js 15 + TypeScript |
| `watch.sh` | watchdog (inotify 기반, ~5초 재빌드) |

## env/CLI 옵션

대부분 스크립트가 CLI/env로 경로 오버라이드 가능:
```bash
XLSX_PATH=/path/to/xlsx .venv/bin/python extract_csv.py
CSV_DIR=/path/to/csv .venv/bin/python parser_v8.py
DB_PATH=/path/to/db .venv/bin/python rollup_finance.py --apply
XLS_PATH=/path/to/xls .venv/bin/python parse_carryover_all.py
```

## 요구사항

- Python 3.13+
- xlsx (4.5MB, 합본예산서 원본) — repo에 없음 (너 PC에서 받기)
- xls × 3 (이월 조서) — repo에 없음
- Docker (FastAPI 서빙용)
- xlsx 원본은 NAS `/volume1/.../합본예산서-대시보드/` 에 두면 자동 인식
