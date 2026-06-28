#!/usr/bin/env python3
"""parser_v14.py — 합본예산서 xlsx 직접 파싱 → SQLite DB 트리 구축.

컬럼 → depth 매핑:
  A → d=0 (부서)   B → d=1 (정책)   C → d=2 (단위)
  D → d=3 (세부)   F → d=4 (통계목)  G → d=5~7 (편성목/◎/○)
  I → 예산액(천원)  H → 산출기준     J → 전년도  K → 증감
"""
import zipfile, xml.etree.ElementTree as ET, sqlite3, re, sys, os
from collections import defaultdict

XLSX = "2026 전체합본예산서.xlsx"
DB = sys.argv[1] if len(sys.argv) > 1 else "budget.db"
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def get_cell_val(row, col_letter, shared):
    """XML row에서 특정 컬럼의 셀 값 추출."""
    for c in row.findall('s:c', NS):
        ref = c.get('r')
        col = ''.join(ch for ch in ref if ch.isalpha())
        if col == col_letter:
            t = c.get('t')
            v = c.find('s:v', NS)
            if v is not None:
                if t == 's':
                    return shared[int(v.text)] if int(v.text) < len(shared) else v.text
                return v.text
    return ''


def parse_amount(s):
    if not s:
        return 0
    s = s.strip().replace('(', '').replace(')', '').replace(',', '').replace(' ', '').replace('△', '-')
    for p in ['도', '군', '국', '균', '기', '특']:
        s = s.replace(p, '')
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def load_shared_strings(z):
    ss_xml = z.read('xl/sharedStrings.xml')
    root = ET.fromstring(ss_xml)
    shared = []
    for si in root.findall('s:si', NS):
        texts = si.findall('.//s:t', NS)
        shared.append(''.join(t.text or '' for t in texts))
    return shared


def parse_sheet(z, shared, sheet_num):
    """시트 1개 파싱 → (dept, policy, unit, data_rows)"""
    try:
        sx = z.read(f'xl/worksheets/sheet{sheet_num}.xml')
    except KeyError:
        return None
    root = ET.fromstring(sx)
    rows = root.findall('.//s:sheetData/s:row', NS)
    if not rows:
        return None

    def get_cell(row, col_letter):
        for c in row.findall('s:c', NS):
            ref = c.get('r')
            col = ''.join(ch for ch in ref if ch.isalpha())
            if col == col_letter:
                t = c.get('t')
                v = c.find('s:v', NS)
                if v is not None:
                    if t == 's':
                        return shared[int(v.text)] if int(v.text) < len(shared) else v.text
                    return v.text
        return ''

    # 헤더에서 부서/정책/단위 추출 (r1~r9)
    dept = policy = unit = ''
    header_row = 9
    for row in rows[:12]:
        r = int(row.get('r'))
        a = get_cell(row, 'A').strip()
        e = get_cell(row, 'E').strip()
        if a == '부서:':
            dept = e
            header_row = r + 2
        elif a == '정책:':
            policy = e
            header_row = r + 2
        elif a == '단위:':
            unit = e
            header_row = r + 2
        i_val = get_cell(row, 'I')
        if '경정액' in i_val or '예산액' in i_val:
            header_row = r

    if not dept:
        return None

    # 데이터 row 파싱
    data_rows = []
    for row in rows:
        r = int(row.get('r'))
        if r <= header_row:
            continue
        a = get_cell(row, 'A').strip()
        b = get_cell(row, 'B').strip()
        c = get_cell(row, 'C').strip()
        d = get_cell(row, 'D').strip()
        f = get_cell(row, 'F').strip()
        g = get_cell(row, 'G').strip()
        h = get_cell(row, 'H').strip()
        i_val = get_cell(row, 'I').strip()
        j_val = get_cell(row, 'J').strip()

        if a.startswith('-') and a.endswith('-'):
            continue
        if not any([a, b, c, d, f, g]) and not i_val:
            continue

        fin_match = re.match(r'^(도|군|국|균|기|특)', i_val)
        is_finance = bool(fin_match) and not any([a, b, c, d, f, g])

        budget = parse_amount(i_val) if i_val else 0
        prev_year = parse_amount(j_val) if j_val else 0

        finance = {'national': 0, 'province': 0, 'county': 0, 'special': 0, 'balance': 0, 'other': 0}
        if is_finance:
            fin_type = fin_match.group(1)
            fin_map = {'국': 'national', '도': 'province', '군': 'county',
                       '특': 'special', '균': 'balance', '기': 'other'}
            finance[fin_map[fin_type]] = budget

        # depth 결정 (컬럼 기준)
        depth = None
        name = ''
        label_code = ''
        item_code = ''
        if a and a != '세 출 예 산 사 업 명 세 서':
            depth = 0; name = a
        elif b:
            depth = 1; name = b
        elif c:
            depth = 2; name = c
        elif d:
            depth = 3; name = d
        elif f:
            m = re.match(r'^(\d{3})\s+(.+)', f)
            if m:
                label_code = m.group(1)
                name = m.group(2)
            else:
                name = f
            depth = 4
        elif g:
            if g.startswith('◎'):
                depth = 6; name = g[1:].strip()
            elif g.startswith('○'):
                depth = 7; name = g[1:].strip()
            elif g == '본예산':
                depth = None
            elif re.match(r'^\d{2}\s', g) or re.match(r'^\d{2}$', g):
                m = re.match(r'^(\d{2})\s*(.+)', g)
                if m:
                    item_code = m.group(1)
                    name = m.group(2)
                else:
                    name = g
                depth = 5
            else:
                depth = 5; name = g
        elif is_finance:
            depth = None
        elif i_val:
            depth = None

        data_rows.append({
            'depth': depth,
            'name': name,
            'label_code': label_code,
            'item_code': item_code,
            'budget': budget if not is_finance else 0,
            'prev_year': prev_year,
            'is_finance': is_finance,
            'finance': finance,
            'basis': h,
            'raw': i_val,
            'row_num': r,
        })

    return {'dept': dept, 'policy': policy, 'unit': unit, 'rows': data_rows}


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    print(f"📊 parser_v14 — {XLSX} → {DB}")
    z = zipfile.ZipFile(XLSX)
    shared = load_shared_strings(z)
    print(f"   sharedStrings: {len(shared):,}개")

    # DB 재구축
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS budget_items")
    c.execute("""
        CREATE TABLE budget_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER,
            depth INTEGER,
            dept TEXT DEFAULT '', policy TEXT DEFAULT '', unit TEXT DEFAULT '',
            detail TEXT DEFAULT '', label TEXT DEFAULT '', item_code TEXT DEFAULT '',
            item_name TEXT DEFAULT '', calc_name TEXT DEFAULT '',
            basis TEXT DEFAULT '', budget_amount INTEGER DEFAULT 0,
            budget_amount_raw TEXT, budget_original INTEGER DEFAULT 0,
            budget_modified INTEGER DEFAULT 0, page TEXT DEFAULT '', row_num INTEGER DEFAULT 0,
            is_total INTEGER DEFAULT 0, status TEXT DEFAULT '',
            summary_text TEXT DEFAULT '', prev_amount INTEGER DEFAULT 0,
            diff_amount INTEGER DEFAULT 0, children_count INTEGER DEFAULT 0,
            finance_national INTEGER DEFAULT 0, finance_province INTEGER DEFAULT 0,
            finance_county INTEGER DEFAULT 0, finance_special INTEGER DEFAULT 0,
            finance_balance INTEGER DEFAULT 0, finance_other INTEGER DEFAULT 0,
            carryover INTEGER DEFAULT 0,
            carryover_national INTEGER DEFAULT 0, carryover_province INTEGER DEFAULT 0,
            carryover_county INTEGER DEFAULT 0, carryover_special INTEGER DEFAULT 0,
            carryover_balance INTEGER DEFAULT 0, carryover_other INTEGER DEFAULT 0,
            carryover_continued INTEGER DEFAULT 0, carryover_explicit INTEGER DEFAULT 0,
            carryover_accident INTEGER DEFAULT 0
        )
    """)
    conn.commit()

    # 트리 노드 캐시: depth-aware key → id
    node_cache = {}
    total_inserted = 0
    depth_counts = defaultdict(int)

    _ZERO_FIN = {'national': 0, 'province': 0, 'county': 0, 'special': 0, 'balance': 0, 'other': 0}

    def get_or_create(dept, policy, unit, detail, label, item_code, item_name, calc_name,
                      depth, budget, finance, basis, page, row_num):
        if finance is None or finance == {}:
            finance = _ZERO_FIN

        # depth-aware key: 해당 depth까지의 필드만 key에 포함
        if depth == 0:
            key = (dept, '', '', '', '', '', '', '')
        elif depth == 1:
            key = (dept, policy or '', '', '', '', '', '', '')
        elif depth == 2:
            key = (dept, policy or '', unit or '', '', '', '', '', '')
        elif depth == 3:
            key = (dept, policy or '', unit or '', detail or '', '', '', '', '')
        elif depth == 4:
            key = (dept, policy or '', unit or '', detail or '', label or '', '', '', '')
        elif depth == 5:
            key = (dept, policy or '', unit or '', detail or '', label or '',
                   item_code or '', item_name or '', '')
        elif depth == 6:
            key = (dept, policy or '', unit or '', detail or '', label or '',
                   item_code or '', item_name or '', calc_name or '')
        else:  # depth == 7
            key = (dept, policy or '', unit or '', detail or '', label or '',
                   item_code or '', item_name or '', calc_name or '', name_id or '')

        if key in node_cache:
            nid = node_cache[key]
            c.execute("UPDATE budget_items SET budget_amount = budget_amount + ? WHERE id = ?",
                      (budget, nid))
            if finance:
                c.execute("""UPDATE budget_items SET
                    finance_national = finance_national + ?,
                    finance_province = finance_province + ?,
                    finance_county = finance_county + ?,
                    finance_special = finance_special + ?,
                    finance_balance = finance_balance + ?,
                    finance_other = finance_other + ?
                    WHERE id = ?""",
                    (finance['national'], finance['province'], finance['county'],
                     finance['special'], finance['balance'], finance['other'], nid))
            return nid

        # parent_id 찾기 (재귀)
        parent_id = None
        if depth == 0:
            parent_id = None
        elif depth == 1:
            parent_id = get_or_create(dept, '', '', '', '', '', '', '', 0, 0, {}, '', page, 0)
        elif depth == 2:
            parent_id = get_or_create(dept, policy, '', '', '', '', '', '', 1, 0, {}, '', page, 0)
        elif depth == 3:
            parent_id = get_or_create(dept, policy, unit, '', '', '', '', '', 2, 0, {}, '', page, 0)
        elif depth == 4:
            parent_id = get_or_create(dept, policy, unit, detail, '', '', '', '', 3, 0, {}, '', page, 0)
        elif depth == 5:
            parent_id = get_or_create(dept, policy, unit, detail, label, '', '', '', 4, 0, {}, '', page, 0)
        elif depth == 6:
            parent_id = get_or_create(dept, policy, unit, detail, label, item_code, item_name, '', 5, 0, {}, '', page, 0)
        elif depth == 7:
            parent_id = get_or_create(dept, policy, unit, detail, label, item_code, item_name, calc_name,
                                      6, 0, {}, '', page, 0)

        c.execute("""
            INSERT INTO budget_items (parent_id, depth, dept, policy, unit, detail, label,
                item_code, item_name, calc_name, basis, budget_amount, budget_amount_raw,
                page, row_num, is_total, status,
                finance_national, finance_province, finance_county,
                finance_special, finance_balance, finance_other)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, '', ?, ?, ?, ?, ?, ?)
        """, (parent_id, depth, dept, policy or '', unit or '', detail or '', label or '',
              item_code or '', item_name or '', calc_name or '', basis or '', budget,
              str(budget) if budget else '', str(page) if page else '', row_num or 0,
              finance['national'], finance['province'], finance['county'],
              finance['special'], finance['balance'], finance['other']))
        nid = c.lastrowid
        node_cache[key] = nid
        return nid

    # 990개 시트 파싱
    for sheet_num in range(1, 991):
        result = parse_sheet(z, shared, sheet_num)
        if not result:
            continue
        dept = result['dept']
        policy = result['policy']
        unit = result['unit']
        page = sheet_num

        # 트리 노드 추적 — 각 depth의 현재 값
        cur_detail = ''
        cur_label = ''
        cur_item_code = ''
        cur_item_name = ''
        cur_calc_name = ''
        name_id = ''  # d=7 산출내역 고유 식별용

        last_node_id = None

        for row in result['rows']:
            # 재원 행 → 직전 노드에 재원 누적
            if row['is_finance']:
                if last_node_id:
                    c.execute("""UPDATE budget_items SET
                        finance_national = finance_national + ?,
                        finance_province = finance_province + ?,
                        finance_county = finance_county + ?,
                        finance_special = finance_special + ?,
                        finance_balance = finance_balance + ?,
                        finance_other = finance_other + ?
                        WHERE id = ?""",
                        (row['finance']['national'], row['finance']['province'],
                         row['finance']['county'], row['finance']['special'],
                         row['finance']['balance'], row['finance']['other'], last_node_id))
                continue

            if row['depth'] is None:
                continue

            d = row['depth']
            name = row['name']
            if not name:
                continue

            # 현재 depth의 값 업데이트
            if d == 3:
                cur_detail = name
                cur_label = ''; cur_item_code = ''; cur_item_name = ''; cur_calc_name = ''; name_id = ''
            elif d == 4:
                cur_label = name
                cur_item_code = ''; cur_item_name = ''; cur_calc_name = ''; name_id = ''
            elif d == 5:
                cur_item_code = row['item_code']
                cur_item_name = name
                cur_calc_name = ''; name_id = ''
            elif d == 6:
                cur_calc_name = name
                name_id = ''
            elif d == 7:
                # 산출내역 — 고유 식별자로 row_num + name 사용
                name_id = f"{row['row_num']}_{name}"

            # 노드 생성/조회
            # d=6: calc_name만 설정, item_name은 상위(d=5) 값 유지
            # d=7: calc_name 유지(d=6 값), name으로 산출내역명 저장
            nid = get_or_create(
                dept, policy, unit, cur_detail, cur_label,
                cur_item_code,
                cur_item_name if d <= 5 else '',
                cur_calc_name if d >= 6 else '',
                d, row['budget'], row['finance'], row['basis'],
                page, row['row_num']
            )
            last_node_id = nid
            total_inserted += 1
            depth_counts[d] += 1

        if sheet_num % 100 == 0:
            conn.commit()
            print(f"   ... sheet {sheet_num}/990 처리 중 ({dept})")

    conn.commit()
    z.close()

    # === 후처리 ===

    # 1. 부서별 직접 예산액 + 재원 추출 (첫 시트만)
    z2 = zipfile.ZipFile(XLSX)
    dept_data = {}
    for i in range(1, 991):
        try:
            sx = z2.read(f'xl/worksheets/sheet{i}.xml')
        except KeyError:
            continue
        root = ET.fromstring(sx)
        rows = root.findall('.//s:sheetData/s:row', NS)
        dept = ''
        header_row = 9
        for row in rows[:12]:
            r = int(row.get('r'))
            a = get_cell_val(row, 'A', shared).strip()
            e = get_cell_val(row, 'E', shared).strip()
            if a == '부서:':
                dept = e
                header_row = r + 2
            iv = get_cell_val(row, 'I', shared)
            if '경정액' in iv or '예산액' in iv:
                header_row = r
        if not dept or dept in dept_data:
            continue
        d = {'budget': 0, 'national': 0, 'province': 0, 'county': 0, 'special': 0, 'balance': 0, 'other': 0}
        found = False
        for row in rows:
            r = int(row.get('r'))
            if r <= header_row:
                continue
            a = get_cell_val(row, 'A', shared).strip()
            b = get_cell_val(row, 'B', shared).strip()
            iv = get_cell_val(row, 'I', shared).strip()
            if not iv:
                continue
            fin_match = re.match(r'^(도|군|국|균|기|특)', iv)
            if a == dept and not found:
                d['budget'] = parse_amount(iv)
                found = True
                continue
            if found and fin_match and not b:
                fin_map = {'국': 'national', '도': 'province', '군': 'county',
                           '특': 'special', '균': 'balance', '기': 'other'}
                d[fin_map[fin_match.group(1)]] += parse_amount(iv)
            elif b:
                break
        dept_data[dept] = d
    z2.close()

    # 2. d=0 중복 제거 — budget_amount가 가장 큰 1개만 남기고 자식 이동
    for dept in dept_data:
        rows = c.execute('SELECT id FROM budget_items WHERE depth=0 AND dept=? ORDER BY budget_amount DESC',
                         (dept,)).fetchall()
        if len(rows) > 1:
            keep_id = rows[0][0]
            for r in rows[1:]:
                c.execute('UPDATE budget_items SET parent_id=? WHERE parent_id=?', (keep_id, r[0]))
                c.execute('DELETE FROM budget_items WHERE id=?', (r[0],))
    conn.commit()

    # 3. d=1~6 중복 제거 (같은 dept+policy+unit+...+calc_name 조합)
    for d in range(1, 7):
        dupes = c.execute(f'''
            SELECT GROUP_CONCAT(id) as ids, COUNT(*) as cnt
            FROM budget_items WHERE depth = {d}
            GROUP BY dept, policy, unit, detail, label, item_code, item_name, calc_name
            HAVING cnt > 1
        ''').fetchall()
        for row in dupes:
            ids = row[0].split(',')
            keep_id = int(ids[0])
            for old_id in ids[1:]:
                c.execute('UPDATE budget_items SET parent_id=? WHERE parent_id=?', (keep_id, int(old_id)))
                c.execute('DELETE FROM budget_items WHERE id=?', (int(old_id),))
        conn.commit()

    # 4. 남은 고아 노드 연쇄 삭제
    while True:
        c.execute('''DELETE FROM budget_items WHERE parent_id IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM budget_items p WHERE p.id = budget_items.parent_id)''')
        n = c.rowcount
        conn.commit()
        if n == 0:
            break

    # 5. d=0에 예산액 + 재원 직접 박기
    for dept, d in dept_data.items():
        c.execute('''UPDATE budget_items SET
            budget_amount=?, budget_original=?,
            finance_national=?, finance_province=?, finance_county=?,
            finance_special=?, finance_balance=?, finance_other=?
            WHERE depth=0 AND dept=?''',
            (d['budget'], d['budget'],
             d['national'], d['province'], d['county'],
             d['special'], d['balance'], d['other'], dept))
    conn.commit()

    # 6. rollup — leaf → root (d=7 → d=1)
    #    d=6(◎)는 자식 d=7(○)의 합
    #    d=5(편성목)는 자식 d=6(◎)의 합
    #    d=4(통계목)는 자식 d=5(편성목)의 합
    #    ... d=1(정책)은 자식 d=2(단위)의 합
    for d in range(6, 0, -1):
        c.execute(f'DROP TABLE IF EXISTS tmp_rollup_{d}')
        c.execute(f'''CREATE TEMP TABLE tmp_rollup_{d} AS
            SELECT parent_id, SUM(budget_amount) as ba,
                   SUM(finance_national) as fn, SUM(finance_province) as fp,
                   SUM(finance_county) as fc, SUM(finance_special) as fs,
                   SUM(finance_balance) as fb, SUM(finance_other) as fo
            FROM budget_items WHERE depth = {d+1} GROUP BY parent_id''')
        c.execute(f'''UPDATE budget_items SET
            budget_amount = COALESCE((SELECT ba FROM tmp_rollup_{d} WHERE tmp_rollup_{d}.parent_id = budget_items.id), budget_amount),
            finance_national = COALESCE((SELECT fn FROM tmp_rollup_{d} WHERE tmp_rollup_{d}.parent_id = budget_items.id), 0),
            finance_province = COALESCE((SELECT fp FROM tmp_rollup_{d} WHERE tmp_rollup_{d}.parent_id = budget_items.id), 0),
            finance_county = COALESCE((SELECT fc FROM tmp_rollup_{d} WHERE tmp_rollup_{d}.parent_id = budget_items.id), 0),
            finance_special = COALESCE((SELECT fs FROM tmp_rollup_{d} WHERE tmp_rollup_{d}.parent_id = budget_items.id), 0),
            finance_balance = COALESCE((SELECT fb FROM tmp_rollup_{d} WHERE tmp_rollup_{d}.parent_id = budget_items.id), 0),
            finance_other = COALESCE((SELECT fo FROM tmp_rollup_{d} WHERE tmp_rollup_{d}.parent_id = budget_items.id), 0)
            WHERE depth = {d} AND EXISTS (SELECT 1 FROM budget_items child WHERE child.parent_id = budget_items.id)''')
        c.execute(f'DROP TABLE tmp_rollup_{d}')
        conn.commit()

    # 7. d=0 budget_amount는 직접 값 유지 (rollup 안 덮어쓰기)
    for dept, d in dept_data.items():
        c.execute('UPDATE budget_items SET budget_amount=?, budget_original=? WHERE depth=0 AND dept=?',
                  (d['budget'], d['budget'], dept))
    conn.commit()

    # 8. children_count 계산
    c.execute('''UPDATE budget_items SET children_count = (
        SELECT COUNT(*) FROM budget_items child WHERE child.parent_id = budget_items.id
    )''')
    conn.commit()

    # 9. NULL 정리
    c.execute("UPDATE budget_items SET page='' WHERE page IS NULL")
    c.execute("UPDATE budget_items SET summary_text='' WHERE summary_text IS NULL")
    c.execute("UPDATE budget_items SET calc_name='' WHERE calc_name IS NULL")
    conn.commit()
    c.execute('PRAGMA wal_checkpoint(FULL)')

    # 통계
    print(f"\n{'='*60}")
    print(f"✅ 파싱 완료: {total_inserted:,}개 노드 INSERT")
    r = c.execute("SELECT COUNT(*) FROM budget_items").fetchone()
    print(f"   총 노드: {r[0]:,}개")
    for d in range(8):
        r = c.execute(f"SELECT COUNT(*) FROM budget_items WHERE depth={d}").fetchone()
        if r[0]:
            print(f"     d={d}: {r[0]:,}개")
    r = c.execute("SELECT SUM(budget_amount) FROM budget_items WHERE depth=0").fetchone()
    print(f"   d=0 예산액 합: {r[0]:,}천원 ({r[0]/100000:.1f}억)" if r[0] else "   d=0 예산액: 0")
    r = c.execute("SELECT COUNT(DISTINCT dept) FROM budget_items WHERE depth=0").fetchone()
    print(f"   부서 수: {r[0]}개")
    r = c.execute("""SELECT COUNT(*) FROM budget_items WHERE parent_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM budget_items p WHERE p.id = budget_items.parent_id)""").fetchone()
    print(f"   고아 노드: {r[0]}개")
    # d=6 ◎ 노드 확인
    r = c.execute("SELECT COUNT(*) FROM budget_items WHERE depth=6 AND calc_name != ''").fetchone()
    print(f"   d=6 (◎산출부기명): {r[0]:,}개")
    conn.close()


if __name__ == '__main__':
    main()
