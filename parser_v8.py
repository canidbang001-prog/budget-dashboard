"""
parser_v8.py — 민성님 지시 초경량 2-Pass 파서 v8.1 (긴급 수정)
수정사항 (2026-06-12):
  1. 파일 읽기 순서 Numeric Sort 강제 (glob + re page number)
  2. 트리 계층 하향식 초기화 (Downward Reset) 명시적 적용
  3. 에러 Silent Drop 금지 — CAST FAIL 경고 출력 + 괄호(감액) 처리
Phase 1: CSV clean (trim col 0-10, \n→space)
Phase 2: 인덱스 기반 계층 트리 + 재원 바인딩
"""
import csv
import glob
import os
import re
import sqlite3
import sys
import traceback

CSV_DIR = os.environ.get(
    'CSV_DIR',
    os.path.join(os.path.dirname(os.path.abspath(__file__)))
)
CSV_GLOB = os.environ.get('CSV_GLOB', 'budget*.csv')
DB_PATH = os.environ.get(
    'DB_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'budget.db')
)

FINANCE_MAP = {
    '국': 'finance_national',
    '도': 'finance_province',
    '군': 'finance_county',
    '특': 'finance_special',
    '균': 'finance_balance',
    '기': 'finance_other',
    '조': 'finance_balance',  # 조정교부금 → 균특
}


def extract_page_number(filename):
    m = re.search(r'(\d+)', os.path.basename(filename))
    return int(m.group(1)) if m else 0


def clean_amount(s, row_num=0, page='?'):
    """쉼표, '원', 공백, △, 괄호(감액) 제거 → int"""
    if not s or not s.strip():
        return 0
    original = s
    is_negative = False
    s_stripped = s.strip()
    if s_stripped.startswith('(') and s_stripped.endswith(')'):
        is_negative = True
        s = s_stripped[1:-1]
    s = s.replace(',', '').replace('원', '').replace(' ', '').strip()
    if not s:
        return 0
    if '△' in s:
        is_negative = True
        s = s.replace('△', '')
    for prefix in ('국', '도', '군', '특', '균', '기', '조'):
        if s.startswith(prefix):
            val = s[len(prefix):]
            try:
                result = int(val) if val else 0
                return -result if is_negative else result
            except ValueError:
                print(f'  ⚠️ [CAST FAIL] Page {page} Row {row_num}: 재원 변환 실패 — "{original}"')
                return 0
    try:
        result = int(s) if s else 0
        return -result if is_negative else result
    except ValueError:
        print(f'  ⚠️ [CAST FAIL] Page {page} Row {row_num}: int 변환 실패 — "{original}"')
        return 0


def init_db(db_path):
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('''
        CREATE TABLE budget_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER REFERENCES budget_items(id),
            depth INTEGER NOT NULL DEFAULT 0,
            dept TEXT DEFAULT '',
            policy TEXT DEFAULT '',
            unit TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            label TEXT DEFAULT '',
            item_code TEXT DEFAULT '',
            item_name TEXT DEFAULT '',
            calc_name TEXT DEFAULT '',
            basis TEXT DEFAULT '',
            budget_amount INTEGER DEFAULT 0,
            budget_amount_raw TEXT DEFAULT '',
            budget_original INTEGER DEFAULT 0,
            budget_modified INTEGER DEFAULT 0,
            carryover INTEGER DEFAULT 0,
            carryover_national INTEGER DEFAULT 0,
            carryover_province INTEGER DEFAULT 0,
            carryover_county INTEGER DEFAULT 0,
            carryover_special INTEGER DEFAULT 0,
            carryover_balance INTEGER DEFAULT 0,
            carryover_other INTEGER DEFAULT 0,
            status TEXT DEFAULT '',
            summary_text TEXT DEFAULT '',
            prev_amount INTEGER DEFAULT 0,
            diff_amount INTEGER DEFAULT 0,
            finance_national INTEGER DEFAULT 0,
            finance_province INTEGER DEFAULT 0,
            finance_county INTEGER DEFAULT 0,
            finance_special INTEGER DEFAULT 0,
            finance_balance INTEGER DEFAULT 0,
            finance_other INTEGER DEFAULT 0,
            page TEXT DEFAULT '',
            row_num INTEGER DEFAULT 0,
            is_total INTEGER DEFAULT 0,
            children_count INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    return conn


def parse_all(db_path=None):
    if db_path is None:
        db_path = DB_PATH

    # ── 수정 #1: Numeric Sort ──
    pattern = os.path.join(CSV_DIR, CSV_GLOB)
    csv_files = sorted(glob.glob(pattern), key=extract_page_number)
    if not csv_files:
        print(f'❌ No CSV files: {pattern}')
        return 0
    print(f'  📂 {len(csv_files)} file(s): {[os.path.basename(f) for f in csv_files]}')

    rows_clean = []
    total_raw = 0
    for csv_file in csv_files:
        page_name = os.path.basename(csv_file)
        with open(csv_file, encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                row = row[:11]
                row = [c.replace('\n', ' ').replace('\r', ' ') for c in row]
                rows_clean.append((page_name, row))
                total_raw += 1

    print(f'  Phase 1: {total_raw} rows cleaned')

    conn = init_db(db_path)
    cur = conn.cursor()

    # ── 수정 #2: 전역 상태 (Downward Reset) ──
    current_dept = ''
    current_policy = ''
    current_unit = ''
    current_detail = ''
    current_label = ''

    last_dept_id = None
    last_policy_id = None
    last_unit_id = None
    last_detail_id = None
    last_label_id = None
    last_item_id = None
    last_subitem_id = None
    last_row_id = None

    dept_count = 0
    total_inserted = 0
    total_finance = 0
    errors = 0

    for page_name, row in rows_clean:
        try:
            row_num = int(row[1]) if row[1] else 0
            dept = row[2].strip()
            policy = row[3].strip()
            unit = row[4].strip()
            detail = row[5].strip()
            label = row[6].strip()
            item_col = row[7].strip()
            calc = row[8].strip()
            basis = row[9].strip()
            budget_raw = row[10].strip()

            # ── 수정 #3: clean_amount with cast warning ──
            budget_amount = clean_amount(budget_raw, row_num, page_name)
            budget_amount_raw = budget_raw

            # ── 재원 행 검출 ──
            is_finance = False
            if not dept and not policy and not unit and not detail and not label and not item_col:
                if budget_raw and isinstance(budget_amount, int) and budget_amount != 0:
                    for key, field in FINANCE_MAP.items():
                        if budget_raw.lstrip().startswith(key):
                            if last_row_id is not None:
                                cur.execute(
                                    f'UPDATE budget_items SET {field} = COALESCE({field},0) + ? WHERE id = ?',
                                    (budget_amount, last_row_id)
                                )
                                total_finance += 1
                            is_finance = True
                            break
            if is_finance:
                continue

            # ── 계층 갱신 + Downward Reset (#2) ──
            # dept 변경 → 모든 하위 초기화
            if dept:
                current_dept = dept
                current_policy = ''
                current_unit = ''
                current_detail = ''
                current_label = ''
                cur.execute(
                    'INSERT INTO budget_items (parent_id, depth, dept, budget_amount, budget_amount_raw, page, row_num, is_total) VALUES (?,?,?,?,?,?,?,?)',
                    (None, 0, dept, budget_amount, budget_amount_raw, page_name, row_num, 1)
                )
                last_dept_id = cur.lastrowid
                last_row_id = last_dept_id
                last_policy_id = None
                last_unit_id = None
                last_detail_id = None
                last_label_id = None
                last_item_id = None
                last_subitem_id = None
                dept_count += 1
                total_inserted += 1
                continue

            # policy 변경 → unit/detail/label 초기화
            if policy:
                current_policy = policy
                current_unit = ''
                current_detail = ''
                current_label = ''
                cur.execute(
                    'INSERT INTO budget_items (parent_id, depth, dept, policy, budget_amount, budget_amount_raw, page, row_num, is_total) VALUES (?,?,?,?,?,?,?,?,?)',
                    (last_dept_id, 1, current_dept, policy, budget_amount, budget_amount_raw, page_name, row_num, 1)
                )
                last_policy_id = cur.lastrowid
                last_row_id = last_policy_id
                last_unit_id = None
                last_detail_id = None
                last_label_id = None
                last_item_id = None
                last_subitem_id = None
                total_inserted += 1
                continue

            # unit 변경 → detail/label 초기화
            if unit:
                current_unit = unit
                current_detail = ''
                current_label = ''
                parent_id = last_policy_id or last_dept_id
                cur.execute(
                    'INSERT INTO budget_items (parent_id, depth, dept, policy, unit, budget_amount, budget_amount_raw, page, row_num, is_total) VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (parent_id, 2, current_dept, current_policy, unit, budget_amount, budget_amount_raw, page_name, row_num, 1)
                )
                last_unit_id = cur.lastrowid
                last_row_id = last_unit_id
                last_detail_id = None
                last_label_id = None
                last_item_id = None
                last_subitem_id = None
                total_inserted += 1
                continue

            # detail 변경 → label 초기화
            if detail:
                current_detail = detail
                current_label = ''
                parent_id = last_unit_id or last_policy_id or last_dept_id
                cur.execute(
                    'INSERT INTO budget_items (parent_id, depth, dept, policy, unit, detail, budget_amount, budget_amount_raw, page, row_num, is_total) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (parent_id, 3, current_dept, current_policy, current_unit, detail, budget_amount, budget_amount_raw, page_name, row_num, 1)
                )
                last_detail_id = cur.lastrowid
                last_row_id = last_detail_id
                last_label_id = None
                last_item_id = None
                last_subitem_id = None
                total_inserted += 1
                continue

            # label → 하위 초기화 없음 (최종 계층 헤더)
            if label:
                current_label = label
                parent_id = last_detail_id or last_unit_id or last_policy_id or last_dept_id
                item_code = ''
                parts = label.split()
                if parts and parts[0].isdigit():
                    item_code = parts[0]
                cur.execute(
                    'INSERT INTO budget_items (parent_id, depth, dept, policy, unit, detail, label, item_code, budget_amount, budget_amount_raw, page, row_num, is_total) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (parent_id, 4, current_dept, current_policy, current_unit, current_detail, label, item_code, budget_amount, budget_amount_raw, page_name, row_num, 1)
                )
                last_label_id = cur.lastrowid
                last_row_id = last_label_id
                total_inserted += 1
                continue

            # item/calc 노드 → depth 5/6/7 based on pattern
            if item_col or calc:
                fallback = last_label_id or last_detail_id or last_unit_id or last_policy_id or last_dept_id
                item_code = ''
                if current_label:
                    parts = current_label.split()
                    if parts and parts[0].isdigit():
                        item_code = parts[0]

                # 편성목: item_col starts with \d{3}\s → depth=5
                if item_col and re.match(r'^\d{3}\s', item_col):
                    cur.execute(
                        '''INSERT INTO budget_items
                           (parent_id, depth, dept, policy, unit, detail, label, item_code, item_name, calc_name, basis, budget_amount, budget_amount_raw, page, row_num, is_total)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (fallback, 5, current_dept, current_policy, current_unit, current_detail,
                         current_label, item_code, item_col, calc, basis, budget_amount, budget_amount_raw, page_name, row_num, 0)
                    )
                    last_item_id = cur.lastrowid
                    last_row_id = last_item_id
                    last_subitem_id = None
                    total_inserted += 1
                    continue

                # 통계목: calc starts with \d{2}\s → depth=6
                if calc and re.match(r'^\d{2}\s', calc):
                    parent_id = last_item_id or fallback
                    cur.execute(
                        '''INSERT INTO budget_items
                           (parent_id, depth, dept, policy, unit, detail, label, item_code, item_name, calc_name, basis, budget_amount, budget_amount_raw, page, row_num, is_total)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (parent_id, 6, current_dept, current_policy, current_unit, current_detail,
                         current_label, item_code, item_col, calc, basis, budget_amount, budget_amount_raw, page_name, row_num, 0)
                    )
                    last_subitem_id = cur.lastrowid
                    last_row_id = last_subitem_id
                    total_inserted += 1
                    continue

                # 편성내용: calc starts with ◎ or ○ → depth=7
                if calc and (calc.startswith('◎') or calc.startswith('○')):
                    parent_id = last_subitem_id or last_item_id or fallback
                    cur.execute(
                        '''INSERT INTO budget_items
                           (parent_id, depth, dept, policy, unit, detail, label, item_code, item_name, calc_name, basis, budget_amount, budget_amount_raw, page, row_num, is_total)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (parent_id, 7, current_dept, current_policy, current_unit, current_detail,
                         current_label, item_code, item_col, calc, basis, budget_amount, budget_amount_raw, page_name, row_num, 0)
                    )
                    last_row_id = cur.lastrowid
                    total_inserted += 1
                    continue

                # 본예산: skip
                if calc == '본예산':
                    continue

                # 기타: depth=5
                cur.execute(
                    '''INSERT INTO budget_items
                       (parent_id, depth, dept, policy, unit, detail, label, item_code, item_name, calc_name, basis, budget_amount, budget_amount_raw, page, row_num, is_total)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (fallback, 5, current_dept, current_policy, current_unit, current_detail,
                     current_label, item_code, item_col, calc, basis, budget_amount, budget_amount_raw, page_name, row_num, 0)
                )
                last_row_id = cur.lastrowid
                total_inserted += 1
                continue

        except Exception as e:
            errors += 1
            if errors <= 20:
                print(f'  ❌ [ERROR] Page {page_name} Row {row[1] if len(row)>1 else "?"}: {str(e)[:120]}')
            continue

    # ── 군비 갭 충전 ──
    print(f'  Processing county gap fill...')
    cur.execute('''
        UPDATE budget_items
        SET finance_county = finance_county + (
            budget_amount - COALESCE(finance_national,0) - COALESCE(finance_province,0)
            - COALESCE(finance_county,0) - COALESCE(finance_special,0)
            - COALESCE(finance_balance,0) - COALESCE(finance_other,0)
        )
        WHERE budget_amount > (
            COALESCE(finance_national,0) + COALESCE(finance_province,0) + COALESCE(finance_county,0)
            + COALESCE(finance_special,0) + COALESCE(finance_balance,0) + COALESCE(finance_other,0)
        )
        AND budget_amount > 0
    ''')
    gap_count = cur.rowcount

    conn.commit()

    cur.execute('SELECT COUNT(*) FROM budget_items')
    total = cur.fetchone()[0]
    cur.execute('SELECT COUNT(DISTINCT dept) FROM budget_items WHERE dept != ""')
    depts = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM budget_items WHERE parent_id IS NOT NULL AND parent_id NOT IN (SELECT id FROM budget_items)')
    orphans = cur.fetchone()[0]
    cur.execute('SELECT SUM(budget_amount) FROM budget_items WHERE depth=0 AND is_total=1')
    total_budget = cur.fetchone()[0] or 0

    conn.close()

    print(f'  Phase 2: {total} nodes, {depts} depts, {dept_count} dept entries')
    print(f'  Finance rows: {total_finance}, County gap fill: {gap_count}')
    print(f'  Orphans: {orphans}, Errors: {errors}, Total budget: {total_budget:,}')

    return total


if __name__ == '__main__':
    # CLI: parser_v8.py [db_path]
    # env: DB_PATH, CSV_DIR, CSV_GLOB
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    if db_path:
        DB_PATH = db_path
    count = parse_all(DB_PATH)
    print(f'✅ Done: {count} rows')
