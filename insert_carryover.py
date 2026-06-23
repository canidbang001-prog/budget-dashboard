"""
순수 이월사업 DB 삽입 — 미매칭 7건
"""
import re, shutil
from datetime import datetime
import sqlite3

DB_PATH = '/root/.openclaw/workspace/디렉이/project_3003/budget.db'

def norm(s):
    if not s: return ''
    s = str(s).strip()
    s = s.replace('\n',' ').replace('\r',' ').replace('\t',' ')
    s = s.replace('\uff08','(').replace('\uff09',')').replace('\u3010','[').replace('\u3011',']')
    return re.sub(r'\s+',' ', s).strip()

def nosp(s):
    return norm(s).replace(' ','')

def extract_base_policy(pol):
    pol = norm(pol)
    return re.sub(r'\s*\([^)]+\)\s*$','', pol).strip()

unmatched = [
    {'dept':'도시과','policy':'지역계획 및 도시개발','unit':'도시가로망조성',
     'detail':'광천중~천주교성당 앞 도시계획도로 개설','item_name':'시설비및부대비','carryover':461536,
     'carryover_national':0,'carryover_province':214159,'carryover_county':247377,
     'carryover_special':0,'carryover_balance':0,'carryover_other':0,
     'carryover_type':'명시이월'},
    {'dept':'도시과','policy':'도시재생 활성화','unit':'도시재생 활성화계획 수립',
     'detail':'도시재생활성화계획 수립','item_name':'연구개발비','carryover':34000,
     'carryover_national':0,'carryover_province':0,'carryover_county':34000,
     'carryover_special':0,'carryover_balance':0,'carryover_other':0,
     '_unit_override':'도시재생 활성화','carryover_type':'사고이월'},
    {'dept':'도시과','policy':'지역계획 및 도시개발','unit':'도시가로망조성',
     'detail':'광천읍 광천역사 중심거리 진입도로 개설','item_name':'시설비','carryover':58570,
     'carryover_national':0,'carryover_province':0,'carryover_county':58570,
     'carryover_special':0,'carryover_balance':0,'carryover_other':0,
     'carryover_type':'계속비'},
    {'dept':'건설과','policy':'농촌 기반조성','unit':'기반조성 일반',
     'detail':'노후위험저수지 시설보강사업(도비보조)','item_name':'시설비및부대비','carryover':327863,
     'carryover_national':0,'carryover_province':98359,'carryover_county':229504,
     'carryover_special':0,'carryover_balance':0,'carryover_other':0,
     'carryover_type':'명시이월'},
    {'dept':'건설과','policy':'도로시설 관리','unit':'도로 선형개량',
     'detail':'군도4호 위험도로 구조개선(전환사업)','item_name':'시설비 및 부대비','carryover':84840,
     'carryover_national':0,'carryover_province':0,'carryover_county':84840,
     'carryover_special':0,'carryover_balance':0,'carryover_other':0,
     '_unit_override':'도로 일반','carryover_type':'사고이월'},
    {'dept':'건설과','policy':'도로시설 관리','unit':'도로일반',
     'detail':'군도4호(택리교) 보수보강공사','item_name':'시설비 및 부대비','carryover':475600,
     'carryover_national':0,'carryover_province':0,'carryover_county':271778,
     'carryover_special':203822,'carryover_balance':0,'carryover_other':0,
     '_unit_override':'도로 일반','carryover_type':'사고이월'},
    {'dept':'건설과','policy':'도로시설 관리','unit':'도로일반',
     'detail':'재해복구사업','item_name':'시설비 및 부대비','carryover':655785,
     'carryover_national':446726,'carryover_province':0,'carryover_county':0,
     'carryover_special':209060,'carryover_balance':0,'carryover_other':0,
     '_unit_override':'도로 일반','carryover_type':'사고이월'},
]

# Backup
backup_path = f'{DB_PATH}.backup_insert_carryover_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
shutil.copy2(DB_PATH, backup_path)
print(f"[BACKUP] {backup_path}")

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys = OFF")

results = []

for item in unmatched:
    ed = item['dept']
    ep = item['policy']
    eu = item.get('_unit_override', item['unit'])
    edet = item['detail']
    carry = item['carryover']
    
    print(f"\n{'='*60}")
    print(f"처리: {ed}/{edet[:40]}")
    
    # 1. Check if detail already exists
    existing = conn.execute(
        "SELECT id FROM budget_items WHERE dept=? AND detail=?",
        (ed, edet)
    ).fetchall()
    if existing:
        print(f"  [SKIP] 이미 존재: id={existing[0][0]}")
        results.append((edet, '-', carry, 'SKIP', '-'))
        continue
    
    # 2. Find unit node
    # Try exact match first
    unit_candidates = conn.execute(
        "SELECT id, depth, dept, policy, unit FROM budget_items WHERE dept=? AND depth=2 AND unit=?",
        (ed, eu)
    ).fetchall()
    unit_candidates = [c for c in unit_candidates if extract_base_policy(c[3]) == ep]
    
    if not unit_candidates:
        # Fuzzy: space-insensitive
        unit_candidates = conn.execute(
            "SELECT id, depth, dept, policy, unit FROM budget_items WHERE dept=? AND depth=2",
            (ed,)
        ).fetchall()
        unit_candidates = [
            c for c in unit_candidates
            if extract_base_policy(c[3]) == ep and nosp(c[4]) == nosp(eu)
        ]
    
    if not unit_candidates:
        # Any unit under this dept+policy
        unit_candidates = conn.execute(
            "SELECT id, depth, dept, policy, unit FROM budget_items WHERE dept=? AND depth=2",
            (ed,)
        ).fetchall()
        unit_candidates = [c for c in unit_candidates if extract_base_policy(c[3]) == ep]
    
    if not unit_candidates:
        print(f"  [FAIL] 단위사업을 찾을 수 없음: {ed}/{ep}/{eu}")
        results.append((edet, '-', carry, 'FAIL', '-'))
        continue
    
    # Pick the best unit (prefer the one with most detail children = most active)
    best_unit = unit_candidates[0]
    if len(unit_candidates) > 1:
        print(f"  {len(unit_candidates)} units found, using id={best_unit[0]} '{best_unit[4][:30]}'")
    
    unit_id = best_unit[0]
    unit_depth = best_unit[1]
    unit_dept = best_unit[2]
    unit_policy = best_unit[3]
    unit_name = best_unit[4]
    
    # 3. Get max id for new row
    new_id = conn.execute("SELECT MAX(id) FROM budget_items").fetchone()[0] + 1
    new_depth = unit_depth + 1  # depth 3
    
    # 4. INSERT — use real item_name, status from carryover_type, + carryover finance
    real_item_name = item.get('item_name', '')
    cotype = item.get('carryover_type', '이월사업')
    conn.execute("""
        INSERT INTO budget_items (id, parent_id, depth, dept, policy, unit, detail,
            item_name, budget_amount, carryover, carryover_national, carryover_province,
            carryover_county, carryover_special, carryover_balance, carryover_other,
            budget_original, budget_modified, status, summary_text,
            finance_national, finance_province, finance_county,
            finance_special, finance_balance, finance_other, page,
            calc_name, label)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, '이월조서 순수이월 사업', 0, 0, 0, 0, 0, 0, '', '', '')
    """, (new_id, unit_id, new_depth, unit_dept, unit_policy, unit_name, edet,
           real_item_name, carry,
           item.get('carryover_national', 0), item.get('carryover_province', 0),
           item.get('carryover_county', 0), item.get('carryover_special', 0),
           item.get('carryover_balance', 0), item.get('carryover_other', 0),
           cotype))
    
    conn.commit()
    print(f"  [INSERT] id={new_id} parent={unit_id} depth={new_depth} carryover={carry:,}")
    print(f"    unit: {unit_name[:50]}")
    print(f"    item_name: {real_item_name}")
    results.append((edet, unit_name[:30], carry, 'INSERTED', real_item_name))

# Verification
print(f"\n{'='*60}")
print("=== 결과 ===")
print(f"{'사업명':<45s} {'단위사업':<25s} {'이월액':>15s} {'결과':<10s} {'item_name':<20s}")
print("-"*120)
for row in results:
    det, unit, carry, status = row[:4]
    item_n = row[4] if len(row) > 4 else '-'
    print(f"{det[:43]:<45s} {unit[:23]:<25s} {carry:>15,} {status:<10s} {item_n:<20s}")

# Verify total carryover
total = conn.execute("SELECT SUM(carryover) FROM budget_items WHERE dept IN ('도시과','건설과')").fetchone()[0]
print(f"\n도시과+건설과 carryover 합계: {total:,}")

conn.close()
print(f"\n[DONE] Backup: {backup_path}")
