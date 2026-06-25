# 이월조서 사업별 분배 (Carryover Distribution to Detail Level)

> **상태**: 계획 (다음 세션부터 시작)
> **목표**: 이월 금액을 편성내용(d=7, ◎/○) 단위까지 분배
> **예상 작업 시간**: 1~2시간
> **관련 커밋**: `1eb7671` (parser_v8.py is_total=0 fix), `48400e2` (carryover 3종 컬럼)

---

## 🎯 문제 정의

### 현재 동작
이월 조서 파일 (`.xls`)의 "산출내역" (= 본예산의 ◎/○ 편성내용 단위) 정보를
`parse_carryover_all.py`가 무시하고, **편성목(d=5) 또는 세부(d=3)에 통째로 carryover를 set**.

### 결과
- 트리 펼치면 "101 인건비" 노드 budget + carryover = 4억 7,500만원 표시
- 그 아래 통계목/편성내용(◎)에는 carryover 0
- 사용자: "이월 4억 7,500만원이 인건비에 있다고 했는데 트리상에 없는데?"

### 예시 (엑셀 구조)
```
이월 조서 row:
  부서: 혁신전략담당관
  정책: 혁신전략 발굴
  단위: 친환경농정발전기획단
  세부: 친환경농정 기획 및 조정
  통계목: (없음)
  사업명/산출내역: ◎농업농촌발전기획 시간선택제임기제나급(6급상당)
  이월 금액: 4억 7,500만원

원하는 결과: 이 금액이 본예산 DB의 같은 ◎ 노드(d=7)에 들어감
```

---

## 📋 작업 명세

### 1단계: 이월 조서 파싱 확장
**대상 파일**: `parse_carryover_all.py`

- 엑셀에서 "산출내역" 컬럼 (= ◎/○ 텍스트) 추출
  - 현재: `r=5` (col F) 또는 `r=3` (col D)에서 "calc" 추출
  - 추가: `r=4` (col E) 또는 "사업명" 컬럼에서 ◎/○ 텍스트 추출
- 추출한 "산출내역"을 item['detail_calc'] = '◎...' 형태로 저장

### 2단계: match_and_update 7-pass → 8-pass 확장
**대상 함수**: `parse_carryover_all.py`의 `match_and_update()`

기존 7-pass 매칭 (dept → policy → unit → detail → item → ...):
- Pass 1: dept+policy+unit+detail+item
- Pass 2~7: 점점 완화

새로 추가:
- **Pass 8**: dept+policy+unit+detail+calc (편성내용 매칭)
  - `r[6]` (calc_name) == `eitem_calc` 매칭
  - 매칭 시 해당 노드 (편성내용, d=7) 에 carryover set
  - **부모 노드 (편성목/세부) 에는 carryover 누적 안 함** (= 편성내용에만)

### 3단계: 테스트
- `_testing/xls_carryover_sample.xlsx` 같은 샘플로 검증
- 4단계 match: dept+policy+unit+detail+calc 가 일치하면 carryover 정확히 분배
- 시각화: 페이지에서 ◎ 노드마다 "이월 X억원" 배지 표시

### 4단계: 화면 확인
**대상 파일**: `frontend/components/TreeNode.tsx`

- 현재: `carryover_continued/_explicit/_accident` 중 하나라도 > 0 이면 배지 표시
- **이미 작동 중** — match가 정밀해지면 ◎ 노드마다 자기 배지 떠야 함

### 5단계: 기존 데이터 마이그레이션
**대상 파일**: `parse_carryover_all.py` 또는 별도 스크립트

- 50개 매칭된 carryover 노드 중 depth 5/3 노드들 (현재 편성목/세부에만 set 됨)
- **재파싱 또는 carryover=0 reset 후 8-pass match_and_update로 재매칭**
- 마이그레이션 스크립트: `scripts/migrate_carryover_detail.py`

---

## 🔧 참고 파일/함수

### `parse_carryover_all.py`
```python
def parse_xls(path):
    # 추가할 코드:
    item['detail_calc'] = norm(ws.cell_value(r, ?))  # 산출내역 컬럼
    ...

def match_and_update(db_path, items):
    # Pass 8 추가:
    c8 = [r for r in db_rows
          if norm(r[1]) == ed and extract_base_policy(r[2]) == ep
          and norm(r[3]) == eu and norm(r[4]) == edet
          and norm(r[6]) == eitem_calc  # calc_name (편성내용) 매칭
             ]
    ...
```

### 엑셀 컬럼 위치 (예산팀 파일 기준)
- r=0: 부서
- r=1: (빈 칸)
- r=2: 정책
- r=3: 단위
- r=4: 세부
- r=5: 통계목
- r=6: 이월 총액 (계)
- r=7~10: 지출원인행위액 등
- r=11~16: 재원 6종
- r=17: 산출내역 (= 본예산 calc) — **새로 추출**

### 7-pass → 8-pass match 우선순위
- Pass 1~7: 기존 (dept+policy+unit+detail+item)
- **Pass 8: dept+policy+unit+detail+calc** (가장 정밀)
  - calc = ◎사업명 → 편성내용 노드 (d=7) 에 매칭
  - calc = ○사업명 → 동일

---

## 🧪 테스트 시나리오

### Test 1: 단일 사업 매칭
- 이월 조서: 부서=도시과, 단위=도로유지관리, 세부=도로정비, calc=◎차선도색유지
- 본예산 DB: 같은 dept+policy+unit+detail+calc 노드 찾아서 carryover set
- 페이지: ◎차선도도색유지 노드 옆에 "명시이월" 배지

### Test 2: 다중 사업 (같은 세부)
- 이월 조서: 세부=도로정비, calc=◎차선도색유지 + ◎포장보수 (2건)
- 본예산 DB: 2개의 ◎ 노드 각각에 carryover 분배
- 페이지: 2개 ◎ 노드마다 자기 carryover 배지

### Test 3: 매칭 실패
- 이월 조서: 사업명 = 본예산에 없는 사업
- **carryover 미적용, 로그에 unmatched 기록**

---

## ⚠️ 주의사항

1. **기존 carryover 50건은 reset 후 재매칭**
   - `UPDATE budget_items SET carryover=0, carryover_*=0, status='' WHERE carryover>0`
   - 그 다음 8-pass match_and_update 실행

2. **parser_v8.py 영향 없음**
   - parser_v8.py는 본예산만 파싱
   - carryover 분배는 parse_carryover_all.py 책임

3. **엑셀 파일 형식 차이**
   - 예산팀 파일: col 0~16 (현재 가정)
   - 다른 시트/파일은 다를 수 있음 → 동적 컬럼 탐지 필요할 수도

4. **데이터 정합성**
   - carryover 0인 ◎ 노드는 배지 안 뜸 (현재 동작 OK)
   - carryover > 0인 ◎ 노드는 배지 떠야 함 (수정 후 검증)

---

## 📝 다음 세션 시작 시 할 일

1. `docs/PLAN_CARRYOVER_DISTRIBUTION.md` 읽기 (이 문서)
2. `parse_carryover_all.py`의 `parse_xls()` 분석 (어디에 산출내역 추가할지)
3. 엑셀 파일 `2025회계연도 명시이월 현황.xls` 직접 열어서 산출내역 위치 확인
4. Pass 8 추가 + 테스트

---

## 🎯 완료 기준 (Definition of Done)

- [ ] `parse_carryover_all.py`에 Pass 8 추가
- [ ] 3개 xls (명시/사고/계속비) 재처리 시 carryover가 ◎/○ 노드에 분배됨
- [ ] 페이지에서 ◎ 노드마다 자기 carryover 배지 표시
- [ ] 매칭 실패한 항목은 logged
- [ ] 기존 50건 carryover 재매칭 (편성목/세부 → ◎/○)
- [ ] verify.py에 새 검증 추가
- [ ] GitHub Issue close

---

**작업 시작 트리거**: GitHub Issue #1 (또는 사용자가 "이월 분배 진행" 한 마디)
