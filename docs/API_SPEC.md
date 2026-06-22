# API 명세서 — 합본예산서 웹 조회 시스템

**버전:** 2.0
**호스트:** Port 3003

---

## 1. GET /api/summary

전체 요약 정보 (부서별 합계, 총 예산액)

**Response (200):**
```json
{
  "total_budget": 915054860000,
  "total_nodes": 37958,
  "department_count": 40,
  "departments": [
    {
      "dept": "가정행복과",
      "budget_amount": 167968344000,
      "prev_amount": ...,
      "diff_amount": ...,
      "finance_national": 0,
      "finance_province": 510000000,
      "finance_county": 91389707000,
      "finance_other": 0,
      "page": 264
    }
  ]
}
```

---

## 2. GET /api/tree

트리 구조 데이터 조회. 필터 없이 호출 시 전체 부서 반환.

**Parameters:**
| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| dept | string | N | 부서명 필터 |
| parent_id | int | N | 부모 노드 ID (자식만 조회) |
| depth | int | N | 깊이 필터 (0~5) |
| limit | int | N | 최대 결과 수 (기본 500, 최대 5000) |

**Response (200):**
```json
[
  {
    "id": 1,
    "parent_id": null,
    "depth": 0,
    "dept": "기획감사담당관",
    "policy": null,
    "unit": null,
    "detail": null,
    "item_code": "",
    "item_name": "",
    "calc_name": "",
    "budget_amount": 35665400000,
    "prev_amount": 22961640000,
    "diff_amount": 12703760000,
    "finance_national": 208321000,
    "finance_province": 0,
    "finance_county": 35457079000,
    "finance_other": 0,
    "basis": "",
    "page": 1,
    "row_num": 10,
    "is_total": 1,
    "children_count": 0,
    "has_children": true,
    "child_count": 5
  }
]
```

---

## 3. GET /api/departments

부서 목록 (예산액 기준 내림차순)

**Response (200):**
```json
[
  { "dept": "가정행복과", "budget_amount": 167968344000 },
  { "dept": "농업정책과", "budget_amount": 82737929000 }
]
```

---

## 4. GET /api/finance/{node_id}

특정 노드의 재원 상세 정보

**Path Parameters:**
| 파라미터 | 타입 | 설명 |
|----------|------|------|
| node_id | int | 조회할 노드 ID |

**Response (200):**
```json
{
  "node_id": 1,
  "finance": {
    "finance_national": 208321000,
    "finance_province": 0,
    "finance_county": 35457079000,
    "finance_other": 0
  },
  "details": [
    { "id": 2, "budget_amount": 208321000, "source_type": "국비" },
    { "id": 3, "budget_amount": 35457079000, "source_type": "군비" }
  ]
}
```

---

## 5. GET /api/search

키워드 검색 (부서명, 정책, 단위, 세부, 편성목, 산출내역)

**Parameters:**
| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| q | string | Y | 검색어 |
| limit | int | N | 최대 결과 수 (기본 100) |

**Response (200):**
```json
[
  {
    "id": 23,
    "depth": 5,
    "dept": "기획감사담당관",
    "policy": "군정발전 전략 추진",
    "unit": "군정 종합기획 조정 및 평가",
    "detail": "군정 종합기획 및 조정",
    "item_name": "일반운영비",
    "calc_name": "○군정백서 제작(정책성과 자료집)",
    "budget_amount": 40000000,
    "page": 1
  }
]
```

---

## 6. GET /api/stats

통계 정보

**Response (200):**
```json
{
  "total_budget": 915054860000,
  "total_nodes": 23208,
  "finance_rows": 14750,
  "department_count": 40,
  "top_items": [
    { "item_code": "301", "item_name": "일반보전금", "cnt": 1234, "total": 698991644000 }
  ]
}
```

---

## 7. GET /health

헬스체크

**Response (200):**
```json
{ "status": "ok", "db": "/root/.../budget.db" }
```
