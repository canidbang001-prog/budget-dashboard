# 합본예산서 대시보드 (Hongseong County Budget Dashboard)

2026 홍성군 합본예산서 + 이월 조서 통합 조회 대시보드 (FastAPI + Next.js)

운영 서버: `http://1.11.122.94:3003` (LAN: `http://192.168.0.28:3003`)

## 빠른 시작

```bash
./update.sh
# → extract → parse → rollup → carryover → verify
# → 컨테이너 자동 재빌드 (~5초)
# → 페이지: http://1.11.122.94:3003  (비번: 1234!)
```

## 파이프라인 구조

```
[2026 전체합본예산서.xlsx]    [2025 이월 .xls × 3]
        │                            │
        ▼                            ▼
  extract_csv.py              parse_carryover.py
        │                            │ (Pass 1~6: dept+unit+detail+사업 d=3 매칭)
        ▼                            │ (미매칭 → create_new_tree 신규 트리)
   budget.csv                  ◎이월액 d=6/d=7
        │                            │
        ▼                            ▼
   parser_v8.py ───────┐   carryover 컬럼 + carryover_explicit/accident
        │              │
        ▼              ▼
   budget.db ◄── rollup_finance.py (post-processing)
        │              │
        └──────►──────┘
                │
                ▼
        FastAPI (3003)
                │
                ▼
        Next.js 15 + TypeScript → 웹페이지
```

## 스크립트

| 파일 | 용도 |
|---|---|
| `extract_csv.py` | xlsx → CSV (민성님 인덴트 형식) |
| `parser_v8.py` | CSV → DB (8단계 트리) |
| `rollup_finance.py` | 재원 rollup 보정 |
| `parse_carryover.py` | 이월 조서 40부서 매칭 + ◎이월액 d=6/d=7 INSERT |
| `update.sh` | 한방 실행 (extract→parse→rollup→carryover→verify) |
| `verify.py` | DB 정합성 검증 |
| `main_integrated.py` | FastAPI 서버 (3003) |
| `auth.py` | 비번 게이트 (itsdangerous) |
| `frontend/` | Next.js 15 + TypeScript |
| `watch.sh` | watchdog (inotify 기반, ~5초 재빌드) |

## 이월 carryover 트리 구조 (2026-06-26, v22)

```
본예산 사업 d=3 (carry 컬럼)
    ├─ 본예산 통계목 d=4~d=6
    │     └─ ◎이월액 d=6/d=7  ← 이월 조서에서 매칭된 노드
    │           ├─ carryover_explicit (명시이월)
    │           ├─ carryover_continued (계속비이월)
    │           └─ carryover_accident (사고이월)
    └─ 사업 d=3 자체의 carry 컬럼
          └─ xls 명시이월 row 1건 = 1:1 (선택적)
```

**xls 101행 ↔ DB ◎이월액 101개 1:1 매칭 검증 완료 (v22).**

## Carryover Fix 역사 (v15~v22)

| 버전 | 변경 |
|---|---|
| v15 | carryover 단위 1000배 mismatch (d=4 21개 사업 ×1000, 농촌에너지 ×10) |
| v16 | `total_carryover` 가 carry 컬럼 (raw, 원) 사용 → 6col 천원 합계 (사업단위) 로 fix. UI 이월예산 42.7조 → 232억 |
| v17 | d=4 (편성목) carryover 컬럼 ÷ 1000 (raw 원 → 천원) |
| v18 | `_patch_dept_carryover` 가 carryover 컬럼(raw) → 6컬럼 천원 합으로 변경 |
| v19 | 6col carryover d=1~d=7 5 level 중복 제거 |
| v20 | 사업 20690 (농촌 에너지) carryover 760,000 → 76,000 천원 (10배 ÷) |
| v21 | `parse_carryover.py` INSERT 에 carryover 컬럼 placeholder 추가 |
| **v22** | **사업 d=3 carry 컬럼 정합성 1:1 매칭 (◎이월액 101/101)** |

## env/CLI 옵션

대부분 스크립트가 CLI/env로 경로 오버라이드 가능:
```bash
XLSX_PATH=/path/to/xlsx .venv/bin/python extract_csv.py
CSV_DIR=/path/to/csv .venv/bin/python parser_v8.py
DB_PATH=/path/to/db .venv/bin/python rollup_finance.py --apply
XLS_PATH=/path/to/xls .venv/bin/python parse_carryover.py
```

## 요구사항

- Python 3.13+
- xlsx (4.5MB, 합본예산서 원본) — repo에 없음
- xls × 3 (이월 조서) — repo에 없음
- Docker (FastAPI 서빙용)
- xlsx 원본은 NAS `/volume1/.../합본예산서-대시보드/` 에 두면 자동 인식

## 관련 문서

- [`docs/WORKLOG_2026-06-26.md`](docs/WORKLOG_2026-06-26.md) — v22 carryover 정합성 fix 작업 일지
- [`docs/TODO_NEXT_WEEK.md`](docs/TODO_NEXT_WEEK.md) — 다음 주 우선순위 todo (계속비이월 fix, UI 개선 등)

## 작업 일지 (2026-06-26)

### v22 carryover 정합성 fix

- **문제**: 6개 사업 d=3 의 carryover 컬럼이 잘못된 값, 9개 사업의 carry 컬럼 0 미반영, 1건 사업 d=3 누락
- **fix**:
  - 6개 사업 d=3 carryover_accident = xls 값 (안전관리/회계/문화유산/도시/교통)
  - 9개 사업 d=3 carry 컬럼 0 reset (◎이월액 노드와 이중 카운트 방지)
  - id=447 (홍보전산) carry 0 reset (이월조서에 dept 자체 없음)
  - id=18798 (혁신전략 권역개발) 사업 d=3 + carryover_accident=22,000 신규
  - 3건 1천원 단위 미세 fix (반올림)
- **검증**: xls 101개 이월행 ↔ DB ◎이월액 101개 1:1 매칭
  - 명시이월: 46건 / 22,926,197 천원
  - 사고이월: 55건 / 13,580,974 천원
  - 계속비이월: 0건 (xls 데이터 없음)

### Hermes 컨테이너 설정

- `HERMES_WRITE_SAFE_ROOT=` (빈 값) — `/tmp/` 임시 검증 스크립트 write 허용
- `build_write_denied_paths` 가드 (.ssh/.aws/.env 등)는 환경변수와 무관하게 영구 차단 유지
