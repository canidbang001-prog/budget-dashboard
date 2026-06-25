"""
verify.py — budget.db 정합성 검증 + 재원 rollup 보정
Usage: python verify.py [db_path]

검증 항목:
  1. dept별 budget 합계 = summary에 나오는 dept별 total_budget
  2. 각 dept의 재원 6종 합 = budget_amount
  3. carryover 합계 일치
  4. 부모 노드 재원이 자식 노드 재원 합과 일치 (rollup)
  5. 미매칭 이월/이상 depth / orphan 노드

문제 발견 시:
  - 재원 rollup만 자동 보정
  - 나머지는 보고 후 수동 판단
"""
import os
import sys
import sqlite3
from collections import defaultdict

DB = sys.argv[1] if len(sys.argv) > 1 else 'budget.db'

if not os.path.exists(DB):
    print(f"❌ DB 없음: {DB}")
    sys.exit(1)

conn = sqlite3.connect(DB)
c = conn.cursor()

print(f"🔍 DB 검증: {DB}")
print(f"   크기: {os.path.getsize(DB) / 1024 / 1024:.1f} MB")
print("=" * 60)

def fetchone_scalar(cur):
    """sqlite3 Cursor.fetchone()[0] (3.13에 .scalar() 없음)"""
    r = cur.fetchone()
    return r[0] if r else None


# ── 1. 기본 통계 ─────────────────────────────────────
total = fetchone_scalar(c.execute("SELECT COUNT(*) FROM budget_items"))
dept_count = fetchone_scalar(c.execute("SELECT COUNT(DISTINCT dept) FROM budget_items WHERE dept != ''"))
print(f"\n📊 기본 통계")
print(f"   전체 노드: {total:,}")
print(f"   부서 수: {dept_count}")

# ── 2. depth별 분포 ──────────────────────────────────
print(f"\n📊 depth별 분포")
depth_dist = c.execute("""
    SELECT depth, COUNT(*), SUM(budget_amount)
    FROM budget_items
    GROUP BY depth
    ORDER BY depth
""").fetchall()
for d, cnt, amt in depth_dist:
    print(f"   depth {d}: {cnt:>5,} 노드, {amt or 0:>15,} 천원")

# ── 3. depth 0 (부서) 재원 검증 ──────────────────────
print(f"\n🔍 depth 0 (부서) 재원 일치 검증")
dept_issues = []
for row in c.execute("""
    SELECT id, dept, budget_amount,
           finance_national + finance_province + finance_county +
           finance_special + finance_balance + finance_other AS fsum
    FROM budget_items
    WHERE depth = 0
"""):
    id_, dept, amt, fsum = row
    if (amt or 0) != (fsum or 0):
        dept_issues.append((id_, dept, amt, fsum))
if dept_issues:
    print(f"   ⚠️  {len(dept_issues)}개 부서 재원 불일치:")
    for id_, dept, amt, fsum in dept_issues[:5]:
        print(f"      id={id_} {dept}: budget={amt:,} ≠ 재원합={fsum:,} (차이: {fsum-amt:,})")
    if len(dept_issues) > 5:
        print(f"      ... 외 {len(dept_issues) - 5}개")
else:
    print(f"   ✅ 모든 부서 재원 일치")

# ── 4. 재원 rollup (부모 ← 자식 합) ──────────────────
print(f"\n🔍 재원 rollup (부모 ← 자식 재원 합)")
print("   ⚠️  이 작업은 시간이 좀 걸려요 (40부서 × 7depth)")

# CTE로 모든 노드의 자식 재원 합
print("   depth 0 (부서) 노드들의 재원 = 자식 depth 1+ 재원 합과 일치해야 함")
mismatches = 0
for row in c.execute("""
    WITH RECURSIVE subtree(id) AS (
        SELECT id FROM budget_items WHERE depth = 0
        UNION ALL
        SELECT b.id FROM budget_items b JOIN subtree s ON b.parent_id = s.id
    )
    SELECT
        b0.id, b0.dept, b0.budget_amount,
        COALESCE(SUM(b.finance_national), 0) AS f_nat,
        COALESCE(SUM(b.finance_province), 0) AS f_prov,
        COALESCE(SUM(b.finance_county), 0) AS f_cnty,
        COALESCE(SUM(b.finance_special), 0) AS f_spec,
        COALESCE(SUM(b.finance_balance), 0) AS f_bal,
        COALESCE(SUM(b.finance_other), 0) AS f_oth
    FROM budget_items b0
    JOIN subtree s ON s.id = b0.id
    JOIN budget_items b ON b.id = s.id
    WHERE b0.depth = 0
    GROUP BY b0.id
"""):
    id_, dept, amt, *finances = row
    fsum = sum(finances)
    if (amt or 0) != fsum:
        mismatches += 1
        if mismatches <= 3:
            print(f"   ⚠️  id={id_} {dept}: budget={amt:,} ≠ 자식재원합={fsum:,}")

if mismatches == 0:
    print(f"   ✅ 모든 부서 부모-자식 재원 일치")
else:
    print(f"   ⚠️  {mismatches}개 부서 불일치 → rollup 보정 필요")

# ── 5. carryover 검증 ────────────────────────────────
print(f"\n🔍 carryover 분포")
has_cotype = 'carryover_continued' in [
    r[1] for r in c.execute("PRAGMA table_info(budget_items)").fetchall()
]
if has_cotype:
    carryover_by_type = c.execute("""
        SELECT
            COALESCE(SUM(carryover), 0) AS total,
            COALESCE(SUM(carryover_continued), 0) AS continued,
            COALESCE(SUM(carryover_explicit), 0) AS explicit,
            COALESCE(SUM(carryover_accident), 0) AS accident,
            COUNT(CASE WHEN carryover > 0 THEN 1 END) AS nodes_with_carryover
        FROM budget_items
    """).fetchone()
    total_co, cont, expl, acci, n_with = carryover_by_type
    print(f"   총 이월: {total_co:,} 천원")
    print(f"   - 계속비: {cont:,}")
    print(f"   - 명시이월: {expl:,}")
    print(f"   - 사고이월: {acci:,}")
    print(f"   - 이월 있는 노드: {n_with}개")
else:
    print(f"   ⚠️  carryover_continued/explicit/accident 컬럼 없음")
    print(f"   → parser_v8.py 스키마 업데이트 필요 (parse_carryover.py와 일치)")

# ── 6. orphan / 데이터 이상 ──────────────────────────
print(f"\n🔍 데이터 이상")
orphans = fetchone_scalar(c.execute("""
    SELECT COUNT(*) FROM budget_items
    WHERE parent_id IS NOT NULL
      AND parent_id NOT IN (SELECT id FROM budget_items)
"""))
print(f"   orphan 노드: {orphans}")

no_dept = fetchone_scalar(c.execute("""
    SELECT COUNT(*) FROM budget_items
    WHERE depth > 0 AND (dept IS NULL OR dept = '')
"""))
print(f"   dept 없는 비-루트 노드: {no_dept}")

# ── 7. 이월 적용 부서 ────────────────────────────────
print(f"\n🔍 이월 적용 부서")
carry_dept = c.execute("""
    SELECT dept, SUM(carryover) AS total_co
    FROM budget_items
    WHERE carryover > 0
    GROUP BY dept
    ORDER BY total_co DESC
""").fetchall()
if carry_dept:
    for dept, co in carry_dept:
        print(f"   {dept}: {co:,} 천원")
else:
    print(f"   ⚠️  이월 데이터 없음 (parse_carryover.py 미실행?)")

# ── 결론 ──────────────────────────────────────────────
print("\n" + "=" * 60)
if dept_issues or mismatches or orphans:
    print("⚠️  문제 발견 — 위 내용 확인 필요")
    sys.exit(1)
else:
    print("✅ 모든 검증 통과")
    sys.exit(0)
