"""
Seed script — parser v4 새 결과로 DB 교체
"""
import sys, os
sys.path.insert(0, '/root/.openclaw/workspace/철수/project_3003')
sys.path.insert(0, '/root/.openclaw/workspace/디렉이/project_3003')

from database import init_db, get_db, BudgetItem
from parser_v4 import parse_all

DB_PATH = '/root/.openclaw/workspace/철수/project_3003/budget.db'

print("🗑️  기존 DB 삭제...")
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    # WAL 파일도 삭제
    for ext in ['-wal', '-shm']:
        p = DB_PATH + ext
        if os.path.exists(p):
            os.remove(p)

print("📋 파싱 시작...")
items = parse_all()

print(f"\n💾 DB 적재: {len(items):,}개 노드...")
init_db(DB_PATH)
db = get_db(DB_PATH)
try:
    for i, item in enumerate(items):
        db.add(item)
        if (i + 1) % 5000 == 0:
            db.flush()
    db.commit()
    print(f"  ✅ {len(items):,}개 저장 완료")
finally:
    db.close()

# ─── 빠른 검증 ───
db = get_db(DB_PATH)
try:
    import sqlite3
    raw = sqlite3.connect(DB_PATH)
    
    total = raw.execute("SELECT COUNT(*) FROM budget_items").fetchone()[0]
    print(f"\n🔍 검증:")
    print(f"  전체: {total:,}개")
    
    # Depth 분포
    for d in range(6):
        cnt = raw.execute("SELECT COUNT(*) FROM budget_items WHERE depth=?", (d,)).fetchone()[0]
        print(f"  depth={d}: {cnt:,}")
    
    # 부서 수
    depts = raw.execute("SELECT COUNT(DISTINCT dept) FROM budget_items WHERE depth=0 AND dept!=''").fetchone()[0]
    print(f"  부서: {depts}개")
    
    # 기획감사담당관
    g0 = raw.execute("SELECT id, budget_amount FROM budget_items WHERE dept='기획감사담당관' AND depth=0").fetchone()
    g1 = raw.execute("SELECT COUNT(*) FROM budget_items WHERE dept='기획감사담당관' AND depth=1").fetchone()[0]
    print(f"  기획감사담당관: id={g0[0]} budget={g0[1]:,} → {g1} policies")
    
    # 경제정책과
    e0 = raw.execute("SELECT id, budget_amount FROM budget_items WHERE dept='경제정책과' AND depth=0").fetchone()
    e1 = raw.execute("SELECT COUNT(*) FROM budget_items WHERE dept='경제정책과' AND depth=1").fetchone()[0]
    print(f"  경제정책과: id={e0[0]} budget={e0[1]:,} → {e1} policies")
    
    # 고아 체크 (빠르게)
    orphans = raw.execute("""
        SELECT COUNT(*) FROM budget_items b
        WHERE b.parent_id IS NOT NULL 
        AND NOT EXISTS (SELECT 1 FROM budget_items p WHERE p.id = b.parent_id)
    """).fetchone()[0]
    print(f"  고아 노드: {orphans}")
    
    # 총 예산 (depth=5 합)
    total_budget = raw.execute("SELECT SUM(budget_amount) FROM budget_items WHERE depth=5").fetchone()[0]
    print(f"  총예산(depth=5 sum): {total_budget:,}원")
    
    raw.close()
finally:
    db.close()

print("\n🏁 완료! 3003 서버 재시작 필요.")
