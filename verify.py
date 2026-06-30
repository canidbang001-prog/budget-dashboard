"""
verify.py -- budget.db integrity verification + finance rollup check
Usage: python verify.py [db_path]
"""
import io
import os
import sys
import sqlite3
from collections import defaultdict

# Force UTF-8 stdout/stderr to prevent cp949 UnicodeEncodeError on Windows
if sys.stdout.encoding.lower() not in ('utf-8', 'utf_8'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

DB = sys.argv[1] if len(sys.argv) > 1 else 'budget.db'

if not os.path.exists(DB):
    print(f'[ERROR] DB not found: {DB}')
    sys.exit(1)

conn = sqlite3.connect(DB)
c = conn.cursor()

print(f'[INFO] Verifying DB: {DB}')
print(f'       Size: {os.path.getsize(DB) / 1024 / 1024:.1f} MB')
print('=' * 60)

def fetchone_scalar(cur):
    r = cur.fetchone()
    return r[0] if r else None

# Basic stats
total = fetchone_scalar(c.execute('SELECT COUNT(*) FROM budget_items'))
dept_count = fetchone_scalar(c.execute("SELECT COUNT(DISTINCT dept) FROM budget_items WHERE dept != ''"))
print('\n[INFO] Basic stats')
print(f'       Total nodes: {total:,}')
print(f'       Departments: {dept_count}')

# Depth distribution
print('\n[INFO] Depth distribution')
for d, cnt, amt in c.execute('SELECT depth, COUNT(*), SUM(budget_amount) FROM budget_items GROUP BY depth ORDER BY depth'):
    print(f'       depth {d}: {cnt:>5,} nodes, budget={amt or 0:>15,}')

# depth 0 finance == budget_amount
print('\n[INFO] depth 0 finance == budget_amount')
dept_issues = []
for id_, dept, amt, fsum in c.execute('''
    SELECT id, dept, budget_amount,
           finance_national + finance_province + finance_county +
           finance_special + finance_balance + finance_other AS fsum
    FROM budget_items WHERE depth = 0
'''):
    if (amt or 0) != (fsum or 0):
        dept_issues.append((id_, dept, amt, fsum))
if dept_issues:
    print(f'       [WARN] {len(dept_issues)} departments mismatch')
    for id_, dept, amt, fsum in dept_issues[:5]:
        print(f'              id={id_} {dept}: budget={amt:,} != finance_sum={fsum:,}')
else:
    print('       [OK] all departments match')

# parent-child finance rollup
print('\n[INFO] parent-child finance rollup check')
print('       this may take a while...')
mismatches = 0
for row in c.execute('''
    WITH RECURSIVE subtree(id) AS (
        SELECT id FROM budget_items WHERE depth = 0
        UNION ALL
        SELECT b.id FROM budget_items b JOIN subtree s ON b.parent_id = s.id
    )
    SELECT b0.id, b0.dept, b0.budget_amount,
        COALESCE(SUM(b.finance_national), 0),
        COALESCE(SUM(b.finance_province), 0),
        COALESCE(SUM(b.finance_county), 0),
        COALESCE(SUM(b.finance_special), 0),
        COALESCE(SUM(b.finance_balance), 0),
        COALESCE(SUM(b.finance_other), 0)
    FROM budget_items b0
    JOIN subtree s ON s.id = b0.id
    JOIN budget_items b ON b.id = s.id
    WHERE b0.depth = 0
    GROUP BY b0.id
'''):
    id_, dept, amt, *finances = row
    fsum = sum(finances)
    if (amt or 0) != fsum:
        mismatches += 1
        if mismatches <= 3:
            print(f'       [WARN] id={id_} {dept}: budget={amt:,} != child_sum={fsum:,}')
if mismatches == 0:
    print('       [OK] all departments parent-child match')
else:
    print(f'       [WARN] {mismatches} departments mismatch -> run rollup_finance.py')

# carryover
print('\n[INFO] carryover distribution')
has_cotype = 'carryover_continued' in [r[1] for r in c.execute('PRAGMA table_info(budget_items)').fetchall()]
if has_cotype:
    total, cont, expl, acci, n_with = c.execute('''
        SELECT COALESCE(SUM(carryover),0), COALESCE(SUM(carryover_continued),0),
               COALESCE(SUM(carryover_explicit),0), COALESCE(SUM(carryover_accident),0),
               COUNT(CASE WHEN carryover > 0 THEN 1 END)
        FROM budget_items
    ''').fetchone()
    print(f'       total carryover: {total:,}')
    print(f'       - continued: {cont:,}')
    print(f'       - explicit:  {expl:,}')
    print(f'       - accident:  {acci:,}')
    print(f'       - nodes:     {n_with}')
else:
    print('       [WARN] carryover type columns missing')

# orphan / no dept
print('\n[INFO] data integrity')
orphans = fetchone_scalar(c.execute('''
    SELECT COUNT(*) FROM budget_items
    WHERE parent_id IS NOT NULL AND parent_id NOT IN (SELECT id FROM budget_items)
'''))
no_dept = fetchone_scalar(c.execute('''
    SELECT COUNT(*) FROM budget_items WHERE depth > 0 AND (dept IS NULL OR dept = '')
'''))
print(f'       orphan nodes: {orphans}')
print(f'       non-root nodes without dept: {no_dept}')

# carryover by dept
print('\n[INFO] carryover by department')
for dept, co in c.execute('''
    SELECT dept, SUM(carryover) AS total_co
    FROM budget_items WHERE carryover > 0
    GROUP BY dept ORDER BY total_co DESC
'''):
    print(f'       {dept}: {co:,}')

print('\n' + '=' * 60)
if dept_issues or mismatches or orphans:
    print('[WARN] issues found')
    sys.exit(1)
else:
    print('[OK] all checks passed')
    sys.exit(0)
