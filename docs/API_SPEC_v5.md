# API_SPEC.md — Budget Dashboard v5

> **버전:** v5.0  
> **DB:** `/root/.openclaw/workspace/철수/project_3003/budget.db`  
> **Port:** 3003  
> **Base URL:** `http://localhost:3003` / `http://1.11.122.94:3003`

---

## 1. `GET /api/summary` — 전체 부서 요약

**Response:**
```json
{
  "total_budget": 915054860000,
  "dept_count": 40,
  "department_count": 40,
  "total_nodes": 22529,
  "departments": [
    {
      "dept": "기획감사담당관",
      "total_budget": 35665400000,
      "policy_count": 6,
      "finance_national": 0,
      "finance_province": 368321000,
      "finance_county": 35457079000,
      "finance_other": 0
    }
  ]
}
```

**Notes:**
- `total_budget` = 모든 depth=0 노드 budget_amount × 1000 (원 단위)
- 부서 정렬 = depth=0 노드의 id ASC (Excel 원본순)
- `policy_count` = 각 부서의 depth=1 자식 수

---

## 2. `GET /api/tree?dept={dept_name}` — 부서 트리 루트 노드

**Response:**
```json
{
  "items": [
    {
      "id": 1,
      "parent_id": null,
      "depth": 0,
      "stage": "본예산",
      "dept": "기획감사담당관",
      "policy": null,
      "unit": null,
      "detail": null,
      "item_code": null,
      "item_name": null,
      "calc_name": null,
      "budget_amount": 35665400,
      "prev_amount": 22961640,
      "diff_amount": 12703760,
      "finance_national": 0,
      "finance_province": 368321,
      "finance_county": 35457079,
      "finance_other": 0,
      "children_count": 6,
      "page": 1,
      "has_child": true
    }
  ],
  "total": 1
}
```

**Query params:**
- `dept` (required): URL-encoded 부서명
- `parent_id` (optional): 특정 노드의 자식 요청
- `depth` (optional): 특정 depth 필터

---

## 3. `GET /api/tree/children/{parent_id}` — 자식 노드 목록

**Response:**
```json
{
  "items": [
    {
      "id": 2,
      "parent_id": 1,
      "depth": 1,
      "stage": "본예산",
      "dept": "기획감사담당관",
      "policy": "군정발전 전략 추진(일반공공행정/일반행정)",
      "unit": null,
      "detail": null,
      "item_code": null,
      "item_name": null,
      "calc_name": null,
      "budget_amount": 818893,
      "prev_amount": 490910,
      "diff_amount": 327983,
      "finance_national": 0,
      "finance_province": 80000,
      "finance_county": 738893,
      "finance_other": 0,
      "children_count": 2,
      "page": 1,
      "has_child": true
    }
  ],
  "total": 6
}
```

**Optional query params:**
- `depth`: 특정 depth만 필터 (e.g., `?depth=3`)

---

## 4. `GET /api/dept/{name}` — 단일 부서 상세

**Response:**
```json
{
  "dept": "경제정책과",
  "total_budget": 26270378000,
  "finance": {
    "national": 1234567000,
    "province": 2345678000,
    "county": 22690123000,
    "other": 0
  },
  "policy_count": 8,
  "item_count": 120,
  "calc_count": 540,
  "policies": [
    {
      "id": 7678,
      "name": "지역경제 육성(산업ㆍ중소기업및에너지/산업진흥ㆍ고도화)",
      "budget_amount": 15000000,
      "children_count": 3
    }
  ]
}
```

---

## 5. Data Model: `BudgetItem`

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | PK |
| `parent_id` | int? | FK → budget_items.id |
| `depth` | int | 0=dept, 1=policy, 2=unit, 3=detail, 4=label, 5=item, 6=calc |
| `stage` | str | `본예산` | `추경` |
| `dept` | str | 부서명 |
| `policy` | str | 정책명 |
| `unit` | str | 단위명 |
| `detail` | str | 세부사업명 |
| `item_code` | str | 편성목 코드 (e.g., `201`) |
| `item_name` | str | 편성목명 (e.g., `일반운영비`) |
| `calc_name` | str | 산출내역 (e.g., `01 사무관리비`, `◎일반수용비`) |
| `basis` | str | 산출기초 |
| `budget_amount` | int | 예산액 (천원) |
| `prev_amount` | int | 전년도 (천원) |
| `diff_amount` | int | 비교증감 (천원) |
| `finance_national` | int | 국비 (천원) |
| `finance_province` | int | 도비 (천원) |
| `finance_county` | int | 군비 (천원) |
| `finance_other` | int | 기타 (기금, 균특 등) |
| `page` | int | 원본 페이지 번호 |
| `is_total` | int | 0=일반, 1=소계/합계 |

---

## 6. Frontend Mapping

### TreeNode 렌더링 (Jinja2 → Next.js)

```
depth=0: 📁 부서명 (budget_amount, 재원 breakdown)
depth=1:  ├─ 📁 정책명 (budget_amount, 재원)
depth=2:  │  ├─ 📁 단위명 (budget_amount)
depth=3:  │  │  ├─ 📁 세부사업명 (budget_amount)
depth=4:  │  │  │  ├─ 📄 편성목: 코드 + 명 (budget_amount)
depth=5:  │  │  │  │  ├─ ● calc_name (budget_amount)
depth=5:  │  │  │  │  ├─ ○ calc_name (budget_amount)
```

### 재원 표시
```
재원: 국비 xxx천원 / 도비 xxx천원 / 군비 xxx천원 / 기타 xxx천원
```
- 0원인 재원은 생략
- depth=0~1에서만 표시

### Amount 표시
- DB 저장: 천원 단위
- 프론트엔드 표시: ×1000 → 원 단위
- 천 단위 콤마 포맷
