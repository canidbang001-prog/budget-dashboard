#!/bin/bash
# update.sh — xlsx → csv → DB → 재원 rollup → 이월 적용 (한방 실행)
# Usage: ./update.sh [xlsx_path]
#   - xlsx_path 미지정 시 repo 내 "2026 전체합본예산서.xlsx" 사용
#   - 결과: budget.csv → budget.db → 검증
#
# 주의: parse_carryover_all.py는 3개 .xls (명시/사고/계속비) 모두 처리
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
.venv/bin/python -c "
import sqlite3, sys
DB = '$DB'
conn = sqlite3.connect(DB)
c = conn.cursor()
cols = [r[1] for r in c.execute('PRAGMA table_info(budget_items)').fetchall()]
for col in ('carryover_continued', 'carryover_explicit', 'carryover_accident'):
    if col not in cols:
        c.execute(f'ALTER TABLE budget_items ADD COLUMN {col} INTEGER DEFAULT 0')
        print(f'  컬럼 추가: {col}')
c.execute('''
    UPDATE budget_items
    SET carryover_continued = CASE WHEN status='계속비' THEN carryover ELSE 0 END,
        carryover_explicit = CASE WHEN status='명시이월' THEN carryover ELSE 0 END,
        carryover_accident = CASE WHEN status='사고이월' THEN carryover ELSE 0 END
    WHERE status IN ('계속비', '명시이월', '사고이월')
''')
n = c.rowcount
conn.commit()
print(f'  carryover 3종 동기화: {n}개')
conn.close()
"

# 5) 이월 적용 (3개 .xls: 명시/사고/계속비)
echo ""
echo "▶ 4단계: 이월 적용"
for XLS in "2025회계연도 명시이월 현황.xls" \
           "2025회계연도 사고이월 현황.xls" \
           "2025회계연도 계속비이월 현황.xls"; do
    if [ -f "$XLS" ]; then
        .venv/bin/python parse_carryover_all.py "$XLS" "$DB" || echo "  ⚠️ $XLS 처리 실패 (계속)"
    else
        echo "  ⚠️ $XLS 파일 없음 (skip)"
    fi
done

# 6) 검증
echo ""
echo "▶ 5단계: 검증"
.venv/bin/python verify.py "$DB"

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
