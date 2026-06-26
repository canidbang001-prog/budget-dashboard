# 다음 주 Todo (2026-06-29 ~)

## 우선순위 1: 계속비이월 누락 fix

**문제**: xls 계속비이월 15건 / 80,511,746 천원이 DB 에 전혀 반영 안 됨 (carryover_continued=0)

**예상 원인**:
- `parse_carryover.py:parse_xls` 의 carryover_type="계속비" 분기에서 컬럼 매핑 누락
- xls 의 "다 음 연 도 이 월 액" 컬럼 위치 (col 13? 14?) 와 명시이월 (col 10) 이 다름

**작업**:
1. `2025회계연도 계속비이월 현황.xls` 의 컬럼 구조 확인 (header row)
2. `parse_carryover.py:100~130` 의 carryover_type 분기에서 계속비이월 col 13/14 매핑
3. `won_to_kwon` 변환 후 15건 INSERT 되는지 verify
4. DB 의 carryover_continued 합 = 80,511,746 천원 일치 확인

**예상 시간**: 1~2시간

## 우선순위 2: UI 트리 사업 d=3 이월액 표시

**문제**: 사업 d=3 carry 컬럼이 0 이라서 UI 에서 사업 클릭 시 이월액이 안 보임. ◎이월액 노드 펼치기 전에는 0.

**작업**:
1. main_integrated.py 의 `tree` API 응답 가공 시, 사업 d=3 의 children 중 ◎이월액 노드들의 carryover 합을 `display_carryover` 필드로 추가
2. frontend TreeNode 컴포넌트에서 `display_carryover` 우선 표시 (없으면 carry 컬럼)
3. 부서 subtree 합계 (이월예산) 도 같은 방식으로 children 합 자동 계산

**예상 시간**: 2~3시간

## 우선순위 3: parse_carryover.py 매칭 로직 강화

**문제**: 6건의 carryover 사업이 "Pass 6 (dept+unit d=2)" fallback 으로만 매칭. unit 명이 약간 다르면 (예: "임업경영 기반구축" vs "임업경영 기반구") 매칭 실패.

**작업**:
1. `norm()` 함수 강화: 공백, 괄호, 조사, "및"/"등"/"·" 정규화
2. Pass 7 추가: dept+unit+detail 의 Levenshtein distance < 3 fuzzy 매칭
3. 매칭 후 자동 verify: 사업 d=3 carry + ◎이월액 들의 합 = xls 의 dept+unit+detail 의 carryover 합 자동 비교
4. mismatch 발견 시 stderr 에 alert 출력 (watchdog 종료 코드 1)

**예상 시간**: 3~4시간

## 우선순위 4: watchdog 자동 검증

**문제**: xls 변경 감지 시 자동 재빌드되지만, 매칭 실패/이중 카운트/단위 오차 자동 검증 안 됨.

**작업**:
1. `verify.py` 추가: DB 의 모든 ◎이월액 노드의 (dept, unit, detail, type) 가 xls 에 1:1 매칭되는지 자동 검증
2. `watch.sh` 가 `verify.py` 까지 실행, mismatch 발견 시 재빌드 중단 + Telegram 알림
3. CI 같은 역할

**예상 시간**: 2시간

## 우선순위 5: README 다이어그램 + docs 업데이트

**작업**:
1. `docs/WORKLOG_2026-06-26.md` 의 다이어그램을 README 에 반영
2. `docs/PLAN_CARRYOVER_DISTRIBUTION.md` 에 v22 fix 결과 추가
3. v23, v24 등 다음 fix 들을 위한 PLAN 섹션 추가

**예상 시간**: 1시간

## 백로그 (다음 달)

- 사업별 이력 추적 (전년도 대비 증감)
- CSV 다운로드 기능 (사업별 carryover 리스트)
- 사용자별 즐겨찾기 부서 저장
- 이월 사유 자동 입력 (xls 의 "이월사유" 컬럼 파싱)
- OpenAPI 자동 생성
- 통합 검색 (사업명/금액 범위)
