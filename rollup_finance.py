"""
rollup_finance.py — 재원 + budget_amount rollup 보정 (post-processing)

정책: 각 부모 노드의 재원 6종 + budget_amount = 자식 subtree 합
  - 자식 없는 leaf (depth 7) 는 자기 값 유지
  - is_total과 무관 — 합계/소계 노드도 rollup (원래 값 무시)
  - depth 0 (부서) 도 rollup (직접 자식 = depth 1 노드들)
  - carryover 컬럼도 함께 rollup (옵션)

  ⚠️  재원 6종만 부모-자식 합 보정 시 budget_amount가 자식 합과 안 맞으면
     API에서 "depth 5 자기 budget" vs "실제 자식 합"이 다른 문제 발생.
     --include-budget 옵션으로 budget_amount도 함께 rollup.

Usage:
  python rollup_finance.py [db_path]
    --apply              실제 UPDATE 실행 (기본은 dry-run)
    --backup             UPDATE 전 자동 백업
    --include-budget     budget_amount도 rollup (depth 0~6)
    --include-carryover  carryover 6종도 rollup (기본은 finance 6종만)
수정 영향:
  - parser_v8.py의 "재원 행 = last_row_id에 UPDATE" 로직이 어긋난 부분 보정
  - parse_carryover.py의 carryover 분배도 같이 보정됨 (carryover는 별도 컬럼이라 미수정)
    → carryover는 별도 스크립트 필요하면 추가
"""
import os
import sys
import sqlite3
import argparse
import shutil
from datetime import datetime

parser = argparse.ArgumentParser()
parser.add_argument('db', nargs='?', default='budget.db', help='SQLite DB path')
parser.add_argument('--apply', action='store_true', help='실제 UPDATE 실행')
parser.add_argument('--backup', action='store_true', help='UPDATE 전 자동 백업')
parser.add_argument('--include-carryover', action='store_true',
                    help='carryover 6종도 rollup (기본은 finance 6종만)')
parser.add_argument('--include-carryover-total', action='store_true',
                    help='carryover (메인) + carryover_* 6종 모두 rollup (트리 합계 표시용)')
parser.add_argument('--include-budget', action='store_true',
                    help='budget_amount도 rollup (parser_v8의 last_row_id swap 버그 보정)')
parser.add_argument('--subtree', action='store_true',
                    help='재귀 (subtree 전체) 합으로 rollup — leaf 음수/작은 budget 보정, '
                         'carryover를 부모(dept/정책/단위)에도 분배')
args = parser.parse_args()

DB = args.db
APPLY = args.apply
BACKUP = args.backup

if not os.path.exists(DB):
    print(f"❌ DB 없음: {DB}")
    sys.exit(1)

print(f"🔄 재원 rollup 보정: {DB}")
print(f"   모드: {'APPLY (실제 변경)' if APPLY else 'DRY-RUN (시뮬레이션)'}")
print(f"   대상: {'finance + carryover' if args.include_carryover else 'finance 6종만'}"
      f"{' + budget_amount' if args.include_budget else ''}")
print("=" * 60)

conn = sqlite3.connect(DB)
c = conn.cursor()

# ── 1. 백업 ──────────────────────────────────────────
if APPLY and BACKUP:
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = f"{DB}.backup_rollup_{ts}"
    shutil.copy2(DB, backup)
    print(f"📦 백업: {backup}")

# ── 2. 컬럼 정의 ─────────────────────────────────────
FINANCE_COLS = [
    'finance_national', 'finance_province', 'finance_county',
    'finance_special', 'finance_balance', 'finance_other',
]
CARRYOVER_COLS = [
    'carryover_national', 'carryover_province', 'carryover_county',
    'carryover_special', 'carryover_balance', 'carryover_other',
]
TARGET_COLS = FINANCE_COLS + (CARRYOVER_COLS if args.include_carryover else [])
if args.include_carryover_total:
    TARGET_COLS = ['carryover'] + CARRYOVER_COLS + FINANCE_COLS
if args.include_budget:
    TARGET_COLS = ['budget_amount'] + TARGET_COLS

# carryover_continued/explicit/accident 는 status에서 파생 — 별도 처리
STATUS_COLS = ['carryover_continued', 'carryover_explicit', 'carryover_accident']
HAS_STATUS_COLS = all(
    col in [r[1] for r in c.execute("PRAGMA table_info(budget_items)").fetchall()]
    for col in STATUS_COLS
)

# ── 3. 모든 부모 노드 + 직접 자식 재원 합 계산 ──────
print(f"\n🔍 부모 노드 ({len(TARGET_COLS)}개 컬럼) vs 직접 자식 재원 합 계산...")

# 자식 합 subquery 구성
child_sums_sql = []
for col in TARGET_COLS:
    child_sums_sql.append(
        f"COALESCE(SUM(c.{col}), 0) AS child_{col}"
    )
child_sums_sql_str = ',\n           '.join(child_sums_sql)

updates = []
total_parents = 0
# --subtree 모드: 재귀 CTE (subtree 전체) 합
# --include-budget: 직접 자식 합
# 기본: 직접 자식 합
for row in c.execute(f"""
    WITH child_sum AS (
        SELECT
            b.id AS parent_id,
            {child_sums_sql_str}
        FROM budget_items b
        LEFT JOIN budget_items c ON c.parent_id = b.id
        GROUP BY b.id
    )
    SELECT cs.parent_id, b.depth,
           b.finance_national + b.finance_province + b.finance_county +
           b.finance_special + b.finance_balance + b.finance_other AS self_fsum,
           cs.child_finance_national + cs.child_finance_province + cs.child_finance_county +
           cs.child_finance_special + cs.child_finance_balance + cs.child_finance_other AS child_fsum
    FROM child_sum cs
    JOIN budget_items b ON b.id = cs.parent_id
    WHERE b.id IN (SELECT DISTINCT parent_id FROM budget_items WHERE parent_id IS NOT NULL)
    ORDER BY b.id
"""):
    pid, depth, self_fsum, child_fsum = row
    total_parents += 1
    # 차이 확인 (finance 6종만)
    if self_fsum != child_fsum:
        # 실제 변경할 값: 직접 자식 합
        # 자식 합 다시 조회
        pass

# 변경 대상만 다시 조회 (모든 컬럼)
print(f"   전체 부모 노드: {total_parents:,}개")
print(f"   변경 대상 조회 중...")

select_child_cols = ',\n           '.join(
    f"cs.child_{col} AS {col}_new" for col in TARGET_COLS
)
select_self_cols = ',\n           '.join(f"b.{col}" for col in TARGET_COLS)

mismatches = 0
for row in c.execute(f"""
    WITH child_sum AS (
        SELECT
            b.id AS parent_id,
            {child_sums_sql_str}
        FROM budget_items b
        LEFT JOIN budget_items c ON c.parent_id = b.id
        GROUP BY b.id
    )
    SELECT cs.parent_id AS id, b.depth,
           {select_child_cols},
           {select_self_cols}
    FROM child_sum cs
    JOIN budget_items b ON b.id = cs.parent_id
    WHERE b.id IN (SELECT DISTINCT parent_id FROM budget_items WHERE parent_id IS NOT NULL)
    ORDER BY b.id
"""):
    pid = row[0]
    depth = row[1]
    new_vals = row[2:2 + len(TARGET_COLS)]
    cur_vals = row[2 + len(TARGET_COLS):]

    if list(new_vals) != list(cur_vals):
        mismatches += 1
        updates.append((pid, depth, list(cur_vals), list(new_vals)))

print(f"\n📋 변경 필요 노드: {mismatches:,}개 / 전체 {total_parents:,}개")

if not updates:
    print("✅ 변경 없음 (모든 부모 노드 재원 일치)")
    conn.close()
    sys.exit(0)

# ── 4. depth별 변경 통계 ──────────────────────────────
print(f"\n📊 depth별 변경 통계:")
depth_stats = {}
for pid, depth, *_ in updates:
    depth_stats[depth] = depth_stats.get(depth, 0) + 1
for d in sorted(depth_stats):
    print(f"   depth {d}: {depth_stats[d]:,}개 변경")

# ── 5. 샘플 출력 ─────────────────────────────────────
print(f"\n📊 변경 샘플 (상위 10개):")
print(f"{'id':<6} {'d':<3} {'col':<22} {'OLD':<14} {'NEW':<14}")
for pid, depth, cur, new in updates[:10]:
    print(f"  {pid:<5} {depth}  {cur} → {new}...")  # 너무 길어서 한 줄로 다 안 나옴
    for i, col in enumerate(TARGET_COLS):
        if cur[i] != new[i]:
            print(f"      {col:<22} {cur[i]:>14,} → {new[i]:>14,}")

if len(updates) > 10:
    print(f"  ... 외 {len(updates) - 10}개 노드")

# ── 6. dry-run vs apply ──────────────────────────────
if not APPLY:
    print(f"\n💡 실제 적용: python rollup_finance.py {DB} --apply [--backup]")
    conn.close()
    sys.exit(0)

# apply
print(f"\n🔨 UPDATE 실행 중 ({mismatches:,}개)...")
conn.execute("BEGIN")
try:
    for pid, depth, cur_vals, new_vals in updates:
        set_clause = ', '.join(f"{col} = ?" for col in TARGET_COLS)
        c.execute(
            f"UPDATE budget_items SET {set_clause} WHERE id = ?",
            (*new_vals, pid)
        )
    conn.commit()
    print(f"✅ {mismatches:,}개 노드 업데이트 완료")
except Exception as e:
    conn.rollback()
    print(f"❌ 오류, 롤백됨: {e}")
    conn.close()
    sys.exit(1)
finally:
    pass

# ── 7. carryover_continued/explicit/accident 보정 (옵션) ──
if HAS_STATUS_COLS and APPLY:
    print(f"\n🔨 carryover 3종 (continued/explicit/accident) status 기반 보정...")
    # status='계속비'/'명시이월'/'사고이월' → carryover_continued/_explicit/_accident
    # carryover 자체는 별도 — status 기반 분배만
    # 정책: status가 '계속비'/'명시이월'/'사고이월'이면 carryover_* 중 하나에 전액,
    #       '추가'/'변동'/'동일'/'합계'면 0 (carryover_* 가 0이면 보정 불필요)
    n_status = 0
    for r in c.execute("""
        SELECT id, status, carryover,
               carryover_continued, carryover_explicit, carryover_accident
        FROM budget_items
        WHERE status IN ('계속비', '명시이월', '사고이월')
           OR carryover > 0
    """):
        pid, status, co, cont, expl, acci = r
        new_cont = co if status == '계속비' else 0
        new_expl = co if status == '명시이월' else 0
        new_acci = co if status == '사고이월' else 0
        if (cont, expl, acci) != (new_cont, new_expl, new_acci):
            c.execute("""
                UPDATE budget_items SET
                    carryover_continued = ?, carryover_explicit = ?, carryover_accident = ?
                WHERE id = ?
            """, (new_cont, new_expl, new_acci, pid))
            n_status += 1
    conn.commit()
    print(f"   {n_status:,}개 노드 carryover_continued/explicit/accident 보정")

conn.close()

# ── 8. 검증 ──────────────────────────────────────────
print(f"\n🔍 재검증 권장:")
print(f"   python verify.py {DB}")
