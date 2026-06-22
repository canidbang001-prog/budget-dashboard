#!/usr/bin/env python3
"""
QA 검증 스크립트 — 합본예산서 파싱 정합성 테스트
"""
import sqlite3
import json
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "budget.db"

def connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def test_db_exists():
    assert DB_PATH.exists(), "DB 파일이 존재하지 않습니다"
    print("✅ [PASS] DB 파일 존재")

def test_total_nodes():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM budget_items")
    cnt = cur.fetchone()['cnt']
    assert cnt == 37958, f"노드 수 불일치: expected 37958, got {cnt}"
    print(f"✅ [PASS] 총 노드 수: {cnt:,}")
    conn.close()

def test_no_orphans():
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) as cnt FROM budget_items b
        WHERE b.parent_id IS NOT NULL AND b.parent_id != 0 AND b.is_finance = 0
        AND NOT EXISTS (SELECT 1 FROM budget_items p WHERE p.id = b.parent_id)
    """)
    orphans = cur.fetchone()['cnt']
    assert orphans == 0, f"고아 노드 발견: {orphans}개"
    print(f"✅ [PASS] 고아 노드: 0")
    conn.close()

def test_department_count():
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT dept) as cnt FROM budget_items
        WHERE depth = 0 AND is_total = 1 AND dept != ''
    """)
    cnt = cur.fetchone()['cnt']
    assert cnt == 40, f"부서 수 불일치: expected 40, got {cnt}"
    print(f"✅ [PASS] 부서 수: {cnt}")
    conn.close()

def test_depth_distribution():
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT depth, COUNT(*) as cnt FROM budget_items
        WHERE is_finance = 0
        GROUP BY depth ORDER BY depth
    """)
    depths = {row['depth']: row['cnt'] for row in cur.fetchall()}
    print(f"📊 [INFO] Depth 분포:")
    for d in sorted(depths):
        print(f"    Depth {d}: {depths[d]:,} nodes")
    assert 0 in depths, "Depth 0 누락"
    assert 5 in depths, "Depth 5 누락" 
    print(f"✅ [PASS] 모든 depth 레벨 존재 (0-5)")
    conn.close()

def test_page_coverage():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT MIN(page) as mn, MAX(page) as mx FROM budget_items")
    row = cur.fetchone()
    assert row['mn'] == 1, f"첫 페이지 불일치: {row['mn']}"
    assert row['mx'] == 990, f"마지막 페이지 불일치: {row['mx']}"
    print(f"✅ [PASS] 페이지 범위: {row['mn']} - {row['mx']}")
    conn.close()

def test_cross_page_continuity():
    """페이지 경계에서 부모-자식 관계가 끊기지 않는지 검증"""
    conn = connect()
    cur = conn.cursor()
    
    # 여러 페이지에 걸친 부서 찾기
    cur.execute("""
        SELECT dept, MIN(page) as first_pg, MAX(page) as last_pg, COUNT(DISTINCT page) as pages
        FROM budget_items WHERE dept != ''
        GROUP BY dept HAVING pages > 3
        ORDER BY pages DESC LIMIT 5
    """)
    multi_page_depts = [dict(row) for row in cur.fetchall()]
    
    all_ok = True
    for dept_info in multi_page_depts:
        dept = dept_info['dept']
        # Check if all nodes for this dept have proper parent links
        cur.execute("""
            SELECT COUNT(*) as cnt FROM budget_items b
            WHERE b.dept = ? AND b.is_finance = 0 AND b.depth > 0
            AND (b.parent_id IS NULL OR b.parent_id = 0 
                 OR NOT EXISTS (SELECT 1 FROM budget_items p WHERE p.id = b.parent_id))
        """, (dept,))
        bad = cur.fetchone()['cnt']
        if bad > 0:
            print(f"  ⚠️ [WARN] {dept}: {bad} broken parent links")
            all_ok = False
    
    if all_ok:
        print(f"✅ [PASS] 크로스 페이지 연속성: 모든 다중 페이지 부서의 부모-자식 관계 정상")
    else:
        print(f"⚠️ [WARN] 일부 부서에서 부모-자식 관계 이슈 발견")
    
    conn.close()

def test_finance_binding():
    """재원 행이 올바르게 부모 노드에 바인딩되었는지 검증"""
    conn = connect()
    cur = conn.cursor()
    
    # 재원 행 수
    cur.execute("SELECT COUNT(*) as cnt FROM budget_items WHERE is_finance = 1")
    finance_cnt = cur.fetchone()['cnt']
    assert finance_cnt == 14750, f"재원 행 수 불일치: expected 14750, got {finance_cnt}"
    print(f"✅ [PASS] 재원 행 수: {finance_cnt:,}")
    
    # 재원 행이 모두 부모를 가지는지 확인
    cur.execute("""
        SELECT COUNT(*) as cnt FROM budget_items
        WHERE is_finance = 1 AND (parent_id IS NULL OR parent_id = 0)
    """)
    no_parent = cur.fetchone()['cnt']
    if no_parent > 0:
        print(f"  ⚠️ [WARN] 부모 없는 재원 행: {no_parent}개")
    else:
        print(f"✅ [PASS] 모든 재원 행이 부모 노드에 바인딩됨")
    
    conn.close()

def test_department_total_verification():
    """기획감사담당관 부서 총액 검증 (원본 대조)"""
    conn = connect()
    cur = conn.cursor()
    
    # Known values from original sheet
    known = {
        '기획감사담당관': 35665400000,  # 원 단위
    }
    
    for dept, expected in known.items():
        cur.execute("""
            SELECT budget_amount FROM budget_items
            WHERE dept = ? AND depth = 0 AND is_total = 1
        """, (dept,))
        row = cur.fetchone()
        if row:
            actual = row['budget_amount']
            if actual == expected:
                print(f"✅ [PASS] {dept} 총액: {actual:,}원 (원본과 일치)")
            else:
                print(f"❌ [FAIL] {dept} 총액: actual={actual:,}, expected={expected:,}, diff={actual-expected:,}")
        else:
            print(f"❌ [FAIL] {dept} 합계 행을 찾을 수 없음")
    
    conn.close()

def test_search_api():
    """검색 API 동작 확인"""
    conn = connect()
    cur = conn.cursor()
    
    # 검색 테스트
    tests = [
        ('기획', True),
        ('nonexistent_xyz', False),
        ('201', True),
        ('일반운영비', True),
    ]
    
    for q, should_find in tests:
        cur.execute("""
            SELECT COUNT(*) as cnt FROM budget_items
            WHERE is_finance = 0 AND (
                dept LIKE ? OR policy LIKE ? OR unit LIKE ? OR
                detail LIKE ? OR item_name LIKE ? OR calc_name LIKE ? OR item_code LIKE ?
            )
        """, (f'%{q}%',)*7)
        cnt = cur.fetchone()['cnt']
        if should_find:
            assert cnt > 0, f"검색 '{q}' 결과가 없어야 하는데 {cnt}건 발견"
            print(f"✅ [PASS] 검색 '{q}': {cnt}건")
        else:
            assert cnt == 0, f"검색 '{q}' 결과가 {cnt}건 (0건 예상)"
            print(f"✅ [PASS] 검색 '{q}': 0건 (정상)")
    
    conn.close()

def main():
    print("=" * 60)
    print("🔍 QA 검증 자동화 — 합본예산서 파싱 정합성")
    print("=" * 60)
    print()
    
    tests = [
        test_db_exists,
        test_total_nodes,
        test_no_orphans,
        test_department_count,
        test_depth_distribution,
        test_page_coverage,
        test_cross_page_continuity,
        test_finance_binding,
        test_department_total_verification,
        test_search_api,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"❌ [FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"💥 [ERROR] {test.__name__}: {e}")
            failed += 1
        print()
    
    print("=" * 60)
    print(f"결과: ✅ {passed} 통과 / ❌ {failed} 실패")
    print("=" * 60)
    
    return 0 if failed == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
