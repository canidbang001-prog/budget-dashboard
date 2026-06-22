"""
parser_v14.py — indent 기반 CSV 파서 (민성님 재설계)
- indent→depth 매핑: 0=dept, 1=policy, 2=unit, 3=detail, 5=label(편성목), 6=분기(5/6/7)
- indent=6 분기: col[8](calc) 패턴으로 통계목(5)/예산구분(6)/산출내역(7) 구분
- 재원 감지: budget_raw(col[10]) 시작 글자 → 부모 누적
- 괄호 처리: (금액) → 금액 (괄호=성립전 분류 마킹, 절대값)
"""
import csv
import re
import os
import sqlite3
import glob

DB_PATH = '/root/.openclaw/workspace/디렉이/project_3003/budget.db'
CSV_GLOB = '/root/.openclaw/workspace/디렉이/project_3003/budget*.csv'

FINANCE_MAP = {
    '국': 'finance_national',
    '도': 'finance_province',
    '군': 'finance_county',
    '특': 'finance_special',
    '균': 'finance_balance',
    '기': 'finance_other',
    '조': 'finance_balance',
}

DEPTH_SEGMENT_MAP = {0: 'dept', 1: 'policy', 2: 'unit', 3: 'detail'}


def extract_page_number(filename):
    m = re.search(r'Page\s*(\d+)', os.path.basename(filename))
    return int(m.group(1)) if m else 0


def clean_amount(raw):
    """금액 문자열 정제: 쉼표/원/공백/괄호 제거, 절대값, 재원 prefix 제거"""
    if not raw:
        return 0
    s = str(raw).strip()
    if not s:
        return 0
    # 괄호 제거 (성립전 분류 마킹일 뿐, 음수 아님)
    s = s.replace('(', '').replace(')', '')
    # 재원 prefix 제거 (국/도/군/기/특/균/조 + optional spaces)
    for prefix in ['국', '도', '군', '기', '특', '균', '조']:
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
            break
    # 쉼표, 원, 공백 제거
    s = s.replace(',', '').replace('원', '').replace(' ', '')
    if not s or s == '0':
        return 0
    try:
        return int(s)
    except ValueError:
        return 0


def detect_finance_prefix(budget_raw):
    """budget_raw에서 재원 prefix 감지 → (prefix_key, 남은금액문자열) 또는 None"""
    if not budget_raw:
        return None
    s = str(budget_raw).strip()
    # 괄호 안에 재원이 있는 경우: (도   XXX)
    paren = False
    if s.startswith('('):
        s = s[1:]
        paren = True
    for prefix in FINANCE_MAP:
        if s.startswith(prefix):
            rest = s[len(prefix):].strip()
            return (prefix, rest, paren)
    return None


def parse_all():
    csv_files = sorted(glob.glob(CSV_GLOB), key=extract_page_number)

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE budget_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER,
            depth INTEGER NOT NULL DEFAULT 0,
            dept TEXT DEFAULT '',
            policy TEXT DEFAULT '',
            unit TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            item_name TEXT DEFAULT '',
            label TEXT DEFAULT '',
            calc_name TEXT DEFAULT '',
            budget_amount INTEGER DEFAULT 0,
            finance_national INTEGER DEFAULT 0,
            finance_province INTEGER DEFAULT 0,
            finance_county INTEGER DEFAULT 0,
            finance_special INTEGER DEFAULT 0,
            finance_balance INTEGER DEFAULT 0,
            finance_other INTEGER DEFAULT 0,
            page TEXT DEFAULT ''
        )
    ''')

    stack = []  # [(id, depth), ...]
    gparent_children = {}  # {통계목_id: [(item_name, calc_name, budget, page)]}
    cloned_ids = []  # 복제된 산출내역 id 추적용
    prev_div_성립전 = False
    curr_dept = curr_policy = curr_unit = curr_detail = curr_label = ''
    page_name = ''

    for csv_file in csv_files:
        page_name = os.path.basename(csv_file)
        with open(csv_file, encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                indent_str = row.get('indent', '').strip()
                if not indent_str:
                    continue
                indent = int(indent_str)

                budget_raw = (row.get('budget') or '').strip()
                calc_raw = (row.get('calc') or '').strip()
                item_raw = (row.get('item') or '').strip()
                dept_raw = (row.get('dept') or '').strip()
                policy_raw = (row.get('policy') or '').strip()
                unit_raw = (row.get('unit') or '').strip()
                detail_raw = (row.get('detail') or '').strip()
                label_raw = (row.get('label') or '').strip()

                # ── 재원 행 감지 (indent=6, calc 비어있음, budget이 재원 prefix로 시작) ──
                if indent == 6 and not calc_raw and budget_raw:
                    fin = detect_finance_prefix(budget_raw)
                    if fin:
                        prefix, rest, _paren = fin
                        amt = clean_amount(rest) if rest else 0
                        if amt != 0 and stack:
                            # ★ stack을 위로 탐색하며 amt를 수용할 수 있는 첫 노드에 적재
                            field = FINANCE_MAP[prefix]
                            applied = False
                            for i in range(len(stack)-1, -1, -1):
                                candidate_id = stack[i][0]
                                cur.execute(
                                    'SELECT budget_amount, COALESCE(finance_national,0)+COALESCE(finance_province,0)+COALESCE(finance_county,0)+COALESCE(finance_special,0)+COALESCE(finance_balance,0)+COALESCE(finance_other,0) FROM budget_items WHERE id=?',
                                    (candidate_id,)
                                )
                                bud, fin_sum = cur.fetchone()
                                if fin_sum >= bud:
                                    continue  # 꽉 참 → 상위로
                                if fin_sum + amt > bud:
                                    # 이 노드로는 넘침 → 상위 탐색 계속
                                    continue
                                # 적재 가능
                                cur.execute(
                                    f'UPDATE budget_items SET {field} = COALESCE({field},0) + ? WHERE id = ?',
                                    (amt, candidate_id)
                                )
                                applied = True
                                break
                            # 모든 노드가 꽉 찼거나 못 담으면 조용히 무시 (중복/경계 재원)
                        continue

                # ── depth 결정 ──
                depth = -1
                node_name = ''
                calc_name = ''

                if indent in (0, 1, 2, 3):
                    depth = indent
                    segment_names = [dept_raw, policy_raw, unit_raw, detail_raw]
                    node_name = segment_names[indent]

                elif indent == 5:
                    # 편성목 (label) — col[7]=item
                    depth = 4
                    node_name = item_raw
                    curr_label = item_raw

                elif indent == 6:
                    if not calc_raw:
                        # 재원 아닌 빈 calc → skip (예: 합계행 등)
                        continue

                    # col[8] calc 패턴으로 분기
                    tokens = calc_raw.split()
                    first_token = tokens[0] if tokens else ''

                    if calc_raw.startswith(('본예산', '추경', '명시이월', '성립전')):
                        # 예산구분 (본예산, 추경 X회, 명시이월, 성립전)
                        depth = 6
                        node_name = calc_raw
                        prev_div_성립전 = ('성립전' in calc_raw)
                    elif first_token.isdigit() and len(first_token) <= 3:
                        # 통계목 (예: "01 시설비", "04 기간제근로자등보수")
                        depth = 5
                        node_name = calc_raw
                    elif calc_raw and calc_raw[0] in '◎○':
                        # 산출내역
                        depth = 7
                        node_name = calc_raw
                        calc_name = calc_raw
                    else:
                        # 기타 (◎○ 아닌 산출내역 등) → depth 7 로 처리
                        depth = 7
                        node_name = calc_raw
                        calc_name = calc_raw
                else:
                    continue

                if depth == -1:
                    continue

                # ── 전역 상태 업데이트 ──
                if depth == 0:
                    curr_dept = node_name
                    curr_policy = curr_unit = curr_detail = curr_label = ''
                elif depth == 1:
                    curr_policy = node_name
                    curr_unit = curr_detail = curr_label = ''
                elif depth == 2:
                    curr_unit = node_name
                    curr_detail = curr_label = ''
                elif depth == 3:
                    curr_detail = node_name
                    curr_label = ''

                # ── stack 조정 (더 얕은 depth로 복귀 시 pop) ──
                while stack and stack[-1][1] >= depth:
                    stack.pop()

                parent_id = stack[-1][0] if stack else None

                # ── 금액 ──
                amt = clean_amount(budget_raw)

                # ── INSERT ──
                cur.execute('''
                    INSERT INTO budget_items
                    (parent_id, depth, dept, policy, unit, detail, item_name, label, calc_name, budget_amount, page)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (parent_id, depth, curr_dept, curr_policy, curr_unit, curr_detail,
                      node_name, curr_label, calc_name, amt, page_name))

                last_id = cur.lastrowid

                # ★ 성립전 산출내역 복제: 본예산 아래 산출내역을 기억했다가 성립전 아래 복제
                if depth == 6 and prev_div_성립전:
                    gp_id = parent_id  # 통계목
                    if gp_id in gparent_children:
                        orig = gparent_children[gp_id]
                        orig_total = sum(d[2] for d in orig)
                        for item_n, calc_n, orig_amt, pg in orig:
                            scaled = int(amt * orig_amt / orig_total) if orig_total else amt
                            cur.execute(
                                'INSERT INTO budget_items (parent_id, depth, dept, policy, unit, detail, item_name, label, calc_name, budget_amount, page) VALUES (?, 7, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                (last_id, curr_dept, curr_policy, curr_unit, curr_detail,
                                 item_n, curr_label, calc_n, scaled, pg))
                            cloned_ids.append(cur.lastrowid)
                    gparent_children.pop(gp_id, None)  # 사용 후 제거
                elif depth == 6:
                    # 비성립전 예산구분: 산출내역 적재용 버퍼 초기화
                    gp_id = parent_id
                    gparent_children[gp_id] = []

                if depth == 7 and not prev_div_성립전:
                    # 비성립전 아래 산출내역 기억
                    gp_id = stack[-2][0] if len(stack) >= 2 else None
                    if gp_id is not None:
                        gparent_children.setdefault(gp_id, []).append(
                            (node_name, calc_name, amt, page_name))

                stack.append((last_id, depth))

    conn.commit()

    # ── 복제된 산출내역 재원 복사: 성립전 부모 재원 → 복제 자식 (갭 충전 전) ──
    if cloned_ids:
        print(f'   복제 산출내역 재원 복사 중... ({len(cloned_ids)}건)')
        for cid in cloned_ids:
            cur.execute(
                'SELECT b.parent_id, b.budget_amount, p.budget_amount, p.finance_national, p.finance_province, p.finance_county, p.finance_special, p.finance_balance, p.finance_other FROM budget_items b JOIN budget_items p ON b.parent_id=p.id WHERE b.id=?',
                (cid,)
            )
            row = cur.fetchone()
            if not row or row[2] == 0:
                continue
            _, child_budget, pbudget, *pfin = row
            ratio = child_budget / pbudget if pbudget else 1.0
            cur.execute(
                '''UPDATE budget_items SET
                    finance_national = ?, finance_province = ?, finance_county = ?,
                    finance_special = ?, finance_balance = ?, finance_other = ?
                WHERE id=?''',
                (*[int(f * ratio) for f in pfin], cid)
            )
        conn.commit()

    # ── 군비 갭 충전 ──
    print('   군비 갭 충전 처리 중...')
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

    # ── 검증 ──
    cur.execute('''
        SELECT COUNT(*) FROM budget_items WHERE depth=0
        AND budget_amount = (COALESCE(finance_national,0)+COALESCE(finance_province,0)+COALESCE(finance_county,0)+COALESCE(finance_special,0)+COALESCE(finance_balance,0)+COALESCE(finance_other,0))
    ''')
    perfect = cur.fetchone()[0]
    cur.execute('SELECT COUNT(DISTINCT dept) FROM budget_items WHERE dept!="" AND depth=0')
    total_depts = cur.fetchone()[0]
    print(f'   재원 일치: {perfect}/{total_depts}')

    # Depth distribution
    cur.execute('SELECT depth, COUNT(*) FROM budget_items GROUP BY depth ORDER BY depth')
    print('   Depth 분포:')
    for d, c in cur.fetchall():
        print(f'     depth {d}: {c:,}')

    # Total
    cur.execute('SELECT COUNT(*) FROM budget_items')
    total = cur.fetchone()[0]
    cur.execute('SELECT SUM(budget_amount) FROM budget_items WHERE depth=0')
    total_budget = cur.fetchone()[0] or 0
    print(f'   총 노드: {total:,}')
    print(f'📊 총 예산액 (depth 0): {total_budget:,}')

    conn.close()
    return 1


if __name__ == '__main__':
    parse_all()
