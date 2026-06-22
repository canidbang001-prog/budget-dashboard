# 요구사항 정의서 — 홍성군 합본예산서 1단계 파싱 및 대시보드

**작성자:** 디렉이 (Director_AI)
**버전:** 2.0 (2026-06-12)
**상태:** ✅ 1단계 배포 완료

---

## 1. 프로젝트 개요
홍성군 2026년도 전체합본예산서(990페이지, 160,549개 공유문자열)를 구조화된 DB로 파싱하고,
계층형 드릴다운 대시보드를 통해 웹에서 조회 가능하게 하는 시스템.

**데이터 소스:** `/root/.openclaw/workspace/아라/2026 전체합본예산서.xlsx`
**호스팅:** Port 3003

---

## 2. 핵심 기술 스택

| 계층 | 기술 | 비고 |
|------|------|------|
| 파서 | Python Raw XML (openpyxl 바이패스) | xlsx 스타일 호환성 이슈 회피 |
| DB | SQLite | 경량 로컬 DB |
| 백엔드 | Python FastAPI | REST API + Jinja2 SSR |
| 프론트엔드 | Jinja2 Templates + Vanilla JS | 드릴다운 아코디언 |
| 검증 | Python 테스트 스크립트 | 10개 항목 자동화 |

---

## 3. 파싱 로직 상세

### 3.1 계층 구조 (6 Depth)
```
Depth 0: 부서 (A열)     예: 기획감사담당관
Depth 1: 정책 (B열)     예: 군정발전 전략 추진
Depth 2: 단위 (C열)     예: 군정 종합기획 조정 및 평가
Depth 3: 세부 (D열)     예: 군정 종합기획 및 조정
Depth 4: 편성목 (F열)   예: 201 일반운영비
Depth 5: 산출내역 (G열) 예: 01 사무관리비 → ◎일반수용비 → ○정책기획업무추진
```

### 3.2 Global State Machine
- 페이지 경계를 넘어도 부모 노드가 끊기지 않도록 **전역 상태 유지**
- 각 시트의 헤더(5~7행)에서 부서/정책/단위 정보를 읽어 컨텍스트 설정
- 이전 페이지의 상태를 다음 페이지로 자연스럽게 이어받음

### 3.3 콤마 개수 기반 깊이 추적
- 각 행에서 첫 번째 비어있지 않은 컬럼(A~G)의 인덱스로 계층 깊이 결정
- A: 0, B: 1, C: 2, D: 3, F: 4, G: 5

### 3.4 재원 행 처리
- '국', '도', '군', '기'로 시작하는 행(I열)은 **독립된 사업이 아닌 상위 노드의 재원 속성**으로 바인딩
- 재원 노드는 DB에 저장되지만, 상위 노드의 `finance_national/province/county/other` 필드에 누적

---

## 4. DB 스키마

```sql
CREATE TABLE budget_items (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER,
    depth INTEGER,             -- 0~5
    dept TEXT,                 -- 부서명
    policy TEXT,               -- 정책사업
    unit TEXT,                 -- 단위사업
    detail TEXT,               -- 세부사업
    item_code TEXT,            -- 편성목 코드 (예: "201")
    item_name TEXT,            -- 편성목명
    calc_name TEXT,            -- 산출내역명
    budget_amount INTEGER,     -- 예산액 (원)
    prev_amount INTEGER,       -- 전년도예산액
    diff_amount INTEGER,       -- 비교증감
    finance_national INTEGER,  -- 국비
    finance_province INTEGER,  -- 도비
    finance_county INTEGER,    -- 군비
    finance_other INTEGER,     -- 기타
    basis TEXT,                -- 산출기초
    page INTEGER,              -- 출처 페이지
    row_num INTEGER,           -- 출처 행번호
    is_total INTEGER,          -- 합계행 여부
    is_finance INTEGER,        -- 재원행 여부
    children_count INTEGER     -- 자식 노드 수
);
```

---

## 5. 데이터 현황 (1단계 완료)

| 지표 | 값 |
|------|-----|
| 총 노드 수 | 37,958 |
| 일반 노드 | 23,208 |
| 재원 노드 | 14,750 |
| 부서 수 | 40 |
| 페이지 수 | 990 |
| 총 예산액 | 915,054,860,000원 (약 9,150억원) |
| 고아 노드 | 0 |
| Depth 범위 | 0~5 (6단계) |
| 파싱 오류 | 0건 |

---

## 6. API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/summary` | 전체 요약 (부서별 합계, 총 예산) |
| GET | `/api/departments` | 부서 목록 |
| GET | `/api/tree?dept=&parent_id=&depth=&limit=` | 트리 데이터 조회 |
| GET | `/api/finance/{node_id}` | 노드별 재원 정보 |
| GET | `/api/search?q=&limit=` | 키워드 검색 |
| GET | `/api/stats` | 통계 정보 |
| GET | `/health` | 서버 상태 |

### 페이지
| 경로 | 설명 |
|------|------|
| `/` | 메인 대시보드 (2컬럼: 부서목록 + 트리뷰) |
| `/department/{name}` | 부서별 상세 트리 |
| `/search?q=` | 검색 페이지 |

---

## 7. 성공 기준 달성 여부

| 항목 | 목표 | 결과 |
|------|------|------|
| **정확성** | 모든 사업 누락 없이 DB 적재 | ✅ 37,958개 노드, 0 오류 |
| **유연성** | 페이지 경계 부모-자식 관계 유지 | ✅ 0개 고아 노드, 크로스페이지 연속성 검증 |
| **재원 바인딩** | 국/도/군/기 행 상위 노드 연결 | ✅ 14,750개 재원 행 모두 부모 바인딩 |
| **원본 총계 일치** | 기획감사담당관 원본 대조 | ✅ 35,665,400,000원 정확 일치 |
| **검증** | QA 자동화 10개 테스트 | ✅ 10/10 통과 |
