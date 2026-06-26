#!/bin/bash
# update.sh — xlsx → csv → DB → 재원 rollup → 이월 적용 (한방 실행)
# Usage: ./update.sh [xlsx_path]
#   - xlsx_path 미지정 시 repo 내 "2026 전체합본예산서.xlsx" 사용
#   - 결과: budget.csv → budget.db → 검증
#
# 주의: parse_carryover.py는 3개 .xls (명시/사고/계속비) 모두 처리
#       각 .xls가 repo에 있어야 함

set -e
cd "$(dirname "$0")"

XLSX="${1:-2026 전체합본예산서.xlsx}"
DB="budget.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  합본예산서 DB 업데이트"
echo "  시각: $TIMESTAMP"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1) 백업
if [ -f "$DB" ]; then
    mkdir -p .backups
    cp "$DB" ".backups/budget_${TIMESTAMP}.db"
    echo "📦 백업: .backups/budget_${TIMESTAMP}.db"
fi

# 1.5) 프론트엔드 빌드 (선택, frontend/out 없으면)
if [ -d frontend ] && [ ! -d frontend/out ]; then
    echo ""
    echo "▶ 1.5단계: frontend 빌드 (next build)"
    cd frontend
    if [ ! -d node_modules ]; then
        npm install --include=dev --no-audit --no-fund
    fi
    npm run build
    cd ..
fi

# 2) xlsx → csv
echo ""
echo "▶ 1단계: xlsx → csv"
.venv/bin/python extract_csv.py "$XLSX"

# 3) csv → db
echo ""
echo "▶ 2단계: csv → db"
.venv/bin/python parser_v8.py "$DB"

# 4) 재원 rollup 보정 (parser 버그 보정)
echo ""
echo "▶ 3단계: 재원 rollup 보정"
.venv/bin/python rollup_finance.py "$DB" --apply --include-budget --include-carryover

# 4.5) carryover_continued/explicit/accident 컬럼 동기화 (status 기반)
#      컬럼 없으면 추가
# (이 로직은 6.5단계에서 carryover 중복 제거 + 함께 처리됨. 여기서는 컬럼 추가만)

# 5) 이월 적용 (3개 .xls: 명시/사고/계속비) — ◎이월액 노드 INSERT
echo ""
echo "▶ 4단계: 이월 적용"
.venv/bin/python parse_carryover.py "2025회계연도 명시이월 현황.xls" \
                                       "2025회계연도 사고이월 현황.xls" \
                                       "2025회계연도 계속비이월 현황.xls" "$DB" 2>&1 | tail -10

# 6) 검증
echo ""
echo "▶ 5단계: 검증"
.venv/bin/python verify.py "$DB"

# 6.5) carryover 3종 + budget 음수 → 0 보정 + dept d=0 subtree 보정
.venv/bin/python -c "
import sqlite3
DB = '$DB'
conn = sqlite3.connect(DB)
c = conn.cursor()

# carryover 3종 컬럼 없으면 추가
cols = [r[1] for r in c.execute('PRAGMA table_info(budget_items)').fetchall()]
for col in ('carryover_continued', 'carryover_explicit', 'carryover_accident'):
    if col not in cols:
        c.execute(f'ALTER TABLE budget_items ADD COLUMN {col} INTEGER DEFAULT 0')
        print(f'  컬럼 추가: {col}')

# budget 음수 노드 → 0으로 clamp
n_neg = c.execute('UPDATE budget_items SET budget_amount = 0 WHERE budget_amount < 0').rowcount
print(f'  budget 음수 → 0 보정: {n_neg}개')

# carryover 중복 set 방지: d<=6 노드 carryover = 0
# (carryover는 가장 깊은 ◎/○ 노드 d=7에만)
n_dup = c.execute('''
    UPDATE budget_items SET
        carryover = 0,
        carryover_national = 0, carryover_province = 0, carryover_county = 0,
        carryover_special = 0, carryover_balance = 0, carryover_other = 0,
        carryover_continued = 0, carryover_explicit = 0, carryover_accident = 0,
        status = ''
    WHERE depth <= 6 AND carryover > 0
''').rowcount
print(f'  carryover 중복 제거 (d<=6): {n_dup}개')

# dept d=0 subtree 보정 (dept의 실제 총예산 = 자식 subtree budget 합)
# (페이지에서 dept 노드의 budget이 '총예산'으로 표시되어야 함)
# carryover는 d=7에만 유지 (dept d=0에 분배 안 함 → 중복 방지)
c.execute('DROP TABLE IF EXISTS tmp_subtree')
c.execute('''
    CREATE TEMP TABLE tmp_subtree AS
    WITH RECURSIVE sub(id, anc, ba) AS (
        SELECT id, id, budget_amount FROM budget_items WHERE depth=0
        UNION ALL
        SELECT b.id, s.anc, b.budget_amount
        FROM budget_items b JOIN sub s ON b.parent_id=s.id
    )
    SELECT s.anc AS dept_id, SUM(s.ba) AS sub_ba
    FROM sub s
    WHERE s.id != s.anc
    GROUP BY s.anc
''')
n_sub = c.execute('''
    UPDATE budget_items
    SET budget_amount = (SELECT sub_ba FROM tmp_subtree WHERE dept_id = budget_items.id)
    WHERE depth = 0
''').rowcount
c.execute('DROP TABLE tmp_subtree')
conn.commit()
print(f'  dept d=0 subtree 보정 (budget만): {n_sub}개')

# carryover_3종 status 동기화 (d=0~7 모두)
n_sync = c.execute('''
    UPDATE budget_items SET
        carryover_continued = CASE WHEN status='계속비' THEN carryover ELSE 0 END,
        carryover_explicit = CASE WHEN status='명시이월' THEN carryover ELSE 0 END,
        carryover_accident = CASE WHEN status='사고이월' THEN carryover ELSE 0 END
    WHERE status IN ('계속비', '명시이월', '사고이월')
''').rowcount
conn.commit()
print(f'  carryover_3종 status 동기화: {n_sync}개')
conn.close()
"

# 6.5) WAL checkpoint (컨테이너가 최신 데이터 볼 수 있도록)
.venv/bin/python -c "
import sqlite3
conn = sqlite3.connect('$DB')
c = conn.cursor()
c.execute('PRAGMA wal_checkpoint(FULL)')
print('WAL checkpoint:', c.fetchone())
conn.close()
"

# 7) 컨테이너 재시작
echo ""
echo "▶ 6단계: 컨테이너 재시작"
if docker ps -a --format '{{.Names}}' | grep -q '^budget-dashboard$'; then
    docker restart budget-dashboard
    sleep 3
    echo "  ✅ budget-dashboard 재시작 완료"
else
    echo "  ⚠️ budget-dashboard 컨테이너 없음"
fi

echo ""
echo "✅ 완료! DB: $DB"
echo "   페이지: http://1.11.122.94:3003"
