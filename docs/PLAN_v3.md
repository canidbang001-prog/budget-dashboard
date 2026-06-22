# 📋 1단계 실행 계획서 — 합본예산서 파싱 & 대시보드 v3.0

**작성자:** 디렉이 (Director_AI)
**버전:** 3.0
**상태:** ⏳ 아라 승인 대기

---

## 1. 개요

홍성군 2026년도 전체합본예산서(990페이지)를 파싱하여 구조화된 DB로 적재하고,
Next.js 기반의 드릴다운 대시보드로 시각화하는 데이터 파이프라인 중심 웹 애플리케이션.

---

## 2. 아키텍처

```
┌─────────────────────┐     ┌──────────────────────────────┐
│  합본예산서.xlsx     │     │  Backend (FastAPI :3003)      │
│  (990 pages)        │────▶│  ┌────────┐  ┌───────────┐  │
└─────────────────────┘     │  │ Parser │─▶│ SQLite DB │  │
                             │  └────────┘  └───────────┘  │
                             │         │                    │
                             │         ▼                    │
                             │  ┌─────────────┐            │
                             │  │ REST API    │            │
                             │  │ /api/tree   │            │
                             │  │ /api/search │            │
                             │  │ /api/stats  │            │
                             │  └──────┬──────┘            │
                             └─────────┼───────────────────┘
                                       │ JSON
                             ┌─────────▼───────────────────┐
                             │  Frontend (Next.js :3000)    │
                             │  React + Tailwind CSS        │
                             │  ┌────────────────────────┐  │
                             │  │ Drill-down Accordion   │  │
                             │  │ Dept Summary Cards     │  │
                             │  │ Search Interface       │  │
                             │  └────────────────────────┘  │
                             └─────────────────────────────┘
```

---

## 3. 기술 스택

| 계층 | 기술 | 사유 |
|------|------|------|
| **벡엔드 파서** | Python Raw XML (openpyxl 바이패스) | xlsx 호환성, 정밀 계층 추적 |
| **벡엔드 API** | FastAPI | 비동기 처리, 자동 Swagger 문서화, Pydantic 검증 |
| **DB (MVP)** | SQLite | 무설정, 빠른 프로토타이핑, 파일 기반 경량화 |
| **프론트엔드** | Next.js 14 + React 18 + Tailwind CSS 3 | 컴포넌트 기반 Drill-down, SSR 최적화 |
| **QA** | Python pytest | 자동화 정합성 검증 |

---

## 4. 데이터 파싱 전략

### 4.1 컬럼 매핑

| 컬럼 | 내용 | 파싱 |
|------|------|:----:|
| A | 부서명 | ✅ |
| B | 정책사업 | ✅ |
| C | 단위사업 | ✅ |
| D | 세부사업 | ✅ |
| E | (헤더 라벨) | ❌ |
| F | 편성목 | ✅ |
| G | 산출내역 | ✅ |
| H | 산출기초 | ✅ |
| I | 예산액(경정액) | ✅ |
| J | 전년도예산액 | ❌ 제외 |
| K | 비교증감 | ❌ 제외 |
| L | (단위:천원) | ❌ |

### 4.2 계층 구조 (5 Depth)

```
Depth 0: 부서      (A열)  예: 기획감사담당관
Depth 1: 정책      (B열)  예: 군정발전 전략 추진
Depth 2: 단위      (C열)  예: 군정 종합기획 조정 및 평가
Depth 3: 세부      (D열)  예: 군정 종합기획 및 조정
Depth 4: 편성목    (F열)  예: 201 일반운영비
Depth 5: 산출내역  (G열)  예: ○정책기획업무추진 기본수용비
```

### 4.3 Global State Machine
- 페이지 경계에서 부모 노드가 끊기지 않도록 **전역 스택 기반 상태 유지**
- 선행 빈 셀 개수로 Depth 추적
- 국/도/군/기 재원 행은 **상위 노드의 재원 속성으로만 저장** (별도 노드 생성 X, DB 컬럼에만 누적)

### 4.4 제외 대상
- J열(전년도예산액), K열(비교증감) → **파싱에서 완전히 제외**
- 페이지 번호 표시 행 (`- 2 -`, `- 3 -` 등)
- 빈 행

---

## 5. DB 스키마

```sql
CREATE TABLE budget_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id INTEGER REFERENCES budget_items(id),
    depth INTEGER NOT NULL,           -- 0~5
    dept TEXT NOT NULL,               -- 부서명
    policy TEXT,                      -- 정책사업
    unit TEXT,                        -- 단위사업
    detail TEXT,                      -- 세부사업
    item_code TEXT,                   -- 편성목 코드 ("201")
    item_name TEXT,                   -- 편성목명 ("일반운영비")
    calc_name TEXT,                   -- 산출내역명
    budget_amount INTEGER NOT NULL,   -- 예산액 (원)
    finance_national INTEGER DEFAULT 0,  -- 국비
    finance_province INTEGER DEFAULT 0,  -- 도비
    finance_county INTEGER DEFAULT 0,    -- 군비
    finance_other INTEGER DEFAULT 0,     -- 기타
    basis TEXT,                       -- 산출기초 (H열)
    page INTEGER,                     -- 출처 페이지
    row_num INTEGER,                  -- 출처 행번호
    is_total INTEGER DEFAULT 0        -- 합계행 여부
);
```

---

## 6. API 명세 (FastAPI)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/summary` | 전체 요약 (총 예산, 부서별 합계) |
| GET | `/api/tree?dept=&parent_id=&depth=` | 트리 노드 조회 |
| GET | `/api/search?q=` | 키워드 검색 |
| GET | `/api/stats` | 통계 정보 |

※ 모든 응답은 JSON. CORS 설정으로 Next.js 프론트엔드의 cross-origin 요청 허용.

---

## 7. 프론트엔드 (Next.js) 화면 설계

### 7.1 페이지 구성

| 라우트 | 컴포넌트 | 설명 |
|--------|----------|------|
| `/` | `DashboardPage` | 2컬럼: 부서목록 + 트리뷰 |
| `/dept/[name]` | `DepartmentPage` | 부서별 상세 트리 |
| `/search?q=` | `SearchPage` | 검색 결과 |

### 7.2 UI 컴포넌트 트리

```
Layout
├── TopBar (검색바 포함)
├── DashboardPage
│   ├── SummaryCards (총 예산, 부서 수, 노드 수)
│   ├── DeptListPanel (좌측: 부서 목록 + 재원 태그)
│   └── TreePanel (우측: Drill-down 아코디언)
│       ├── TreeNode (재귀적)
│       │   ├── ExpandToggle (▶/▼)
│       │   ├── NodeName
│       │   ├── BudgetAmount
│       │   └── FinanceTags (국/도/군/기)
│       └── TreeControls (전체 펼치기/접기)
└── SearchPage
    ├── SearchInput
    └── ResultTable
```

---

## 8. 팀별 R&R

### ⚙️ Backend_Dev
| 작업 | 산출물 |
|------|--------|
| `parser.py` — Raw XML 파서 (J/K열 제외, 재원 누적 방식) | `/project_3003/parser.py` |
| `models.py` — Pydantic 스키마 | `/project_3003/models.py` |
| `database.py` — SQLite + SQLAlchemy 세션 | `/project_3003/database.py` |
| `main.py` — FastAPI 앱 + CORS + API 엔드포인트 | `/project_3003/main.py` |

### 🎨 Frontend_Dev
| 작업 | 산출물 |
|------|--------|
| Next.js 프로젝트 초기화 (Tailwind) | `/project_3003/frontend/` |
| `DashboardPage` — 부서목록 + 트리뷰 | `app/page.tsx` |
| `TreeNode` — 재귀적 드릴다운 컴포넌트 | `components/TreeNode.tsx` |
| `DeptListPanel` — 부서 목록 사이드바 | `components/DeptListPanel.tsx` |
| `SearchPage` — 검색 인터페이스 | `app/search/page.tsx` |
| API 연동 (fetch → FastAPI :3003) | `lib/api.ts` |

### 🔍 QA_Reviewer
| 작업 | 산출물 |
|------|--------|
| 파싱 정합성 검증 (원본 총계 대조) | `test_qa.py` |
| API 응답 스키마 검증 | `test_api.py` |
| 크로스 페이지 연속성 검증 | `test_integrity.py` |
| 프론트엔드 E2E (서버 연동) | 수동 테스트 |

---

## 9. 작업 순서 (의존성)

```
Phase 1: Backend_Dev → parser.py + DB 구축
    ↓ (API 스펙 확정)
Phase 2: Frontend_Dev + Backend_Dev 병렬
    ├── Backend_Dev → FastAPI 서버
    └── Frontend_Dev → Next.js 프로젝트
    ↓ (통합)
Phase 3: QA_Reviewer → 전수 검증
    ↓
Phase 4: 배포 및 최종 보고
```

---

## 10. 승인 요청

아라님, 위 계획을 검토하시고 승인해주시면 즉시 팀에 업무를 할당하겠습니다.

**핵심 변경사항 (v2 → v3):**
- ✅ 프론트엔드: Jinja2 → **Next.js / React + Tailwind CSS** (Frontend_Dev 전담)
- ✅ 전년도예산액(J열), 비교증감(K열) **완전 제외**
- ✅ 재원 행: 별도 노드 생성 → **상위 노드 컬럼에 누적** (DB 정규화)
- ✅ PM은 계획/조율만, 코딩 직접 하지 않음
