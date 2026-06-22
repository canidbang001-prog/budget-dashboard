# REQUIREMENTS.md — 홍성군 합본예산서 파서 v5 (민성님 직할 명세)

> **버전:** v5.0
> **명세 작성일:** 2026-06-12
> **설계자:** 민성님
> **PM:** Director_AI
> **상태:** ⏳ Backend_Dev 개발 대기

---

## 1. 프로젝트 목표

**"홍성군 예산 족보 파서"** — 990 페이지 합본예산서 XLSX 로데이터를 CSV로 변환한 후, **가변 인덴트 상태 머신**으로 파싱하여 완벽한 계층형 트리 데이터를 SQLite DB에 적재.

---

## 2. 데이터 흐름

```
[2026 전체합본예산서.xlsx] 
  → extract_csv.py (XLSX→CSV 변환)
  → budget.csv (990개 시트, 콤마 인덴트 형식)
  → parser_v5.py (상태 머신 파서)
  → budget.db (SQLite)
  → FastAPI (API 서빙)
  → Next.js 대시보드
```

---

## 3. CSV 형식 명세 (XLSX→CSV 변환)

### 3.1 출력 컬럼 (7개)
```
page,row_num,dept,policy,unit,detail,item,calc,basis,budget,prev,diff
```

### 3.2 인덴트 표현
선행 콤마 개수 = 계층 깊이 (민성님 명세 그대로)
```csv
기획감사담당관,,,,,,,, 35,665,400       ← indent 0: 부서
,군정발전 전략 추진,,,,,,, 818,893       ← indent 1: 정책  
,,군정 종합기획 조정 및 평가,,,,,, 738,893 ← indent 2: 단위
,,,군정 종합기획 및 조정,,,,, 183,150     ← indent 3: 세부
,,,,201 일반운영비,,,, 126,050           ← indent 4: 편성목
,,,,,01 사무관리비,,, 111,050            ← indent 5: 편성목 상세
,,,,,,◎일반수용비,, 97,700               ← indent 6: 산출내역
```

### 3.3 재원 행 (ffill 절대 금지)

재원 행은 직전 subtotal 행의 자식으로 처리하되, 별도 행으로 유지:
```csv
,,,추모공원관리시설 운영,,,, 10,487,652  ← indent 3: 부서 subtotal
,,,,,,,국 2,901,000                      ← 재원 행: 부모 노드의 finance_national에 누적
,,,,,,,도 630,088                        ← 재원 행: 부모 노드의 finance_province에 누적
,,,,,,,군 6,956,564                      ← 재원 행: 부모 노드의 finance_county에 누적
```

### 3.4 시트 경계 처리
- 시트 변경 시에도 상태 머신 **리셋 금지** (pp.989~990 예시)
- 페이지 푸터 `- N -` 행은 변환 단계에서 제거
- 빈 행 제거

---

## 4. 파서 v5 상태 머신 명세

### 4.1 핵심 알고리즘

```
for each csv_line:
    indent = count_leading_commas(line)
    
    if is_recon_row(budget):
        # 재원 행 → 직전 상위 노드의 재원 dict에 흡수
        parent = stack[indent - 1]  # 바로 상위 노드
        parent.finance[recon_type] += amount
        continue
    
    if indent <= current_indent:
        # 상위 레벨로 복귀 or 동일 레벨
        stack = stack[:indent]  # 스택 트림
        parent = stack[-1]
    else:
        # 하위 레벨 진입
        parent = stack[-1]
    
    node = create_node(indent, values, parent)
    stack.append(node)
    current_indent = indent
```

### 4.2 스택 데이터 구조

```
stack = [dept_node, policy_node, unit_node, detail_node, item_node]
          depth=0     depth=1      depth=2     depth=3      depth=4

재원 행 처리:
  - budget 컬럼이 '국', '도', '군', '기', '균' 으로 시작 → 재원 행
  - stack[-1] (가장 최근 부모)의 finance 속성에 누적
```

### 4.3 노드 타입 & depth

| depth | 컬럼 | 필드 | 예시 |
|-------|------|------|------|
| 0 | A (dept) | dept | 기획감사담당관 |
| 1 | B (policy) | policy | 군정발전 전략 추진 |
| 2 | C (unit) | unit | 군정 종합기획 조정 및 평가 |
| 3 | D (detail) | detail | 군정 종합기획 및 조정 |
| 4 | E/F (item) | item_code, item_name | 201 일반운영비 |
| 5 | G (calc) | calc_name | 01 사무관리비, ◎일반수용비, ○정책기획 |

### 4.4 재원 흡수 규칙

```python
RECON_PATTERN = re.compile(r'^\s*(국|도|군|기|균)\s+([\d,]+)')

# 재원 행이면:
match = RECON_PATTERN.match(budget_raw)
if match:
    recon_type = match.group(1)  # '국','도','군','기','균'
    amount = int(match.group(2))
    parent_node = stack[-1]
    # 재원 dict에 누적
    if recon_type == '국': parent_node.finance_national += amount
    elif recon_type == '도': parent_node.finance_province += amount
    elif recon_type == '군': parent_node.finance_county += amount
    elif recon_type in ('기','균'): parent_node.finance_other += amount
```

---

## 5. 추경(변동) 데이터 분리

### 5.1 stage 필드
```
- stage='본예산' : 기본 예산 항목
- stage='추경' : 추경 변동 항목 (괄호 금액, △ 기호)
```

### 5.2 괄호 금액 파싱

```
" - 5,000 "                         → budget_amount = 0,    change_amount = -5000
"△ 3,000"                           → budget_amount = 0,    change_amount = -3000 (?)
" (  1,200 )"                       → budget_amount = 1200,  change_amount = 0 (당초)
```

### 5.3 추경 행 식별 규칙
```
- calc 컬럼에 '추경', '변동', '△' 포함 → stage='추경'
- budget 컬럼이 괄호로 감싸짐 → stage='추경'
- item 컬럼에 '변동' 포함 → stage='추경'
```

---

## 6. 최종 DB 스키마 (BudgetItem)

```sql
CREATE TABLE budget_items (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES budget_items(id),
    depth INTEGER NOT NULL,         -- 0~5
    stage TEXT DEFAULT '본예산',     -- '본예산' | '추경'
    
    -- 계층 정보
    dept TEXT,
    policy TEXT,
    unit TEXT,
    detail TEXT,
    item_code TEXT,
    item_name TEXT,
    calc_name TEXT,
    basis TEXT,
    
    -- 금액
    budget_amount INTEGER DEFAULT 0,   -- 천원 단위
    prev_amount INTEGER DEFAULT 0,     -- 전년도
    diff_amount INTEGER DEFAULT 0,     -- 증감
    
    -- 재원
    finance_national INTEGER DEFAULT 0,   -- 국비
    finance_province INTEGER DEFAULT 0,   -- 도비
    finance_county INTEGER DEFAULT 0,     -- 군비
    finance_other INTEGER DEFAULT 0,      -- 기타(기금, 균특 등)
    
    -- 추적
    page INTEGER,
    row_num INTEGER,
    is_total INTEGER DEFAULT 0           -- 1=소계 행
);
```

---

## 7. 성공 기준 (QA 검증)

| 항목 | 기준 |
|------|------|
| 고아 노드 | 0건 |
| 부서 수 | 40개 (XLSX 부서명과 일치) |
| 시트 경계면 | 990개 시트 전 구간 단절 없음 |
| 재원 오염 | ffill로 인한 재원 값 누락/중복 0건 |
| 부서 총액 | depth=0 subtotal = 책자 정산표와 원 단위 일치 |
| 추경 분리 | stage='본예산' / stage='추경' 개별 총합 검증 |
| 정책 → 단위 → 세부사업 계층 | 모든 depth에서 parent_id 연결 정상 |

---

## 8. 작업 분배

| 역할 | 담당 | 작업 |
|------|------|------|
| 📋 PM | Director_AI | 명세서, API_SPEC, 진행 관리 |
| ⚙️ Backend | Backend_Dev | parser_v5.py, XLSX→CSV 변환, DB 적재 |
| 🎨 Frontend | Frontend_Dev | stage별 대시보드 (당초/변동/최종), 재원 표시 |
| 🔍 QA | QA_Reviewer | 정합성 검증, 정산표 대조 |
