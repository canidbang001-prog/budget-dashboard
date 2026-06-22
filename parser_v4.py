"""
합본예산서 Parser v4.1 — 트리 빌더 수정
- 원본 컬럼 존재 여부로 depth 결정 (fillna 값 아닌 원본 기준)
- fillna는 context(dept/policy/unit) 추적용으로만 사용
"""
import os, re, zipfile, xml.etree.ElementTree as ET
from typing import Optional
from database import BudgetItem

XLSX_PATH = '/root/.openclaw/workspace/아라/2026 전체합본예산서.xlsx'
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
FINANCE_RE = re.compile(r'^\s*(국|도|군|기)\s+([\d,]+)')
PAGE_FOOTER_RE = re.compile(r'^\s*-\s*\d+\s*-\s*$')


def load_shared_strings(zf):
    root = ET.fromstring(zf.read('xl/sharedStrings.xml'))
    strings = []
    for si in root.findall(f'{{{NS}}}si'):
        t = si.find(f'{{{NS}}}t')
        if t is not None and t.text:
            strings.append(t.text)
        else:
            strings.append(''.join(rt.text or '' for r in si.findall(f'{{{NS}}}r') for rt in r.findall(f'{{{NS}}}t') if rt.text))
    return strings


def get_cell_value(cell, ss):
    v = cell.find(f'{{{NS}}}v')
    if v is None or v.text is None:
        return None
    t = cell.get('t')
    if t == 's':
        idx = int(v.text)
        return ss[idx] if 0 <= idx < len(ss) else None
    return v.text


def parse_single_sheet(zf, ws_file, ss):
    ws_xml = ET.fromstring(zf.read(ws_file))
    rows = ws_xml.findall(f'{{{NS}}}sheetData/{{{NS}}}row')
    if not rows:
        return []
    
    page = int(os.path.basename(ws_file).replace('sheet','').replace('.xml',''))
    
    # 시트 컨텍스트 추출 (row 5-7)
    ctx_dept = ''
    ctx_policy = ''
    ctx_unit = ''
    for row in rows:
        rn = int(row.get('r', '0'))
        if rn > 9:
            break
        cells = {c.get('r', ''): c for c in row.findall(f'{{{NS}}}c')}
        d_cell = cells.get(f'D{rn}')
        if d_cell is None:
            continue
        val = (get_cell_value(d_cell, ss) or '').strip()
        if val.startswith('부서:'):
            ctx_dept = val.replace('부서:', '').strip()
        elif val.startswith('정책:'):
            ctx_policy = val.replace('정책:', '').strip()
        elif val.startswith('단위:'):
            ctx_unit = val.replace('단위:', '').strip()
    
    data_rows = []
    for row in rows:
        rn = int(row.get('r', '0'))
        if rn < 10:
            continue
        
        cells = {}
        for c in row.findall(f'{{{NS}}}c'):
            cells[c.get('r', '')] = c
        
        def cv(col_letter):
            ref = f'{col_letter}{rn}'
            if ref in cells:
                return (get_cell_value(cells[ref], ss) or '').strip()
            return ''
        
        raw_dept = cv('A')
        raw_policy = cv('B')
        raw_unit = cv('C')
        raw_detail = cv('D')
        raw_label = cv('E')
        raw_item = cv('F')
        raw_calc = cv('G')
        raw_basis = cv('H')
        raw_budget = cv('I')
        raw_prev = cv('J')
        raw_diff = cv('K')
        
        data_rows.append({
            'page': page,
            'row_num': rn,
            # 원본 값 (fillna 이전)
            'dept': raw_dept,
            'policy': raw_policy,
            'unit': raw_unit,
            'detail': raw_detail,
            'label': raw_label,
            'item': raw_item,
            'calc': raw_calc,
            'basis': raw_basis,
            'budget_raw': raw_budget,
            'prev_raw': raw_prev,
            'diff_raw': raw_diff,
            # 시트 컨텍스트 (row 5-7)
            'ctx_dept': ctx_dept,
            'ctx_policy': ctx_policy,
            'ctx_unit': ctx_unit,
            # 원본 값 존재 여부 (depth 결정용)
            'has_dept': bool(raw_dept),
            'has_policy': bool(raw_policy),
            'has_unit': bool(raw_unit),
            'has_detail': bool(raw_detail),
            'has_item': bool(raw_item),
            'has_calc': bool(raw_calc),
        })
    
    return data_rows


def parse_amount(text):
    if not text:
        return 0
    try:
        return int(text.replace(',', '').replace('\n', '').strip())
    except ValueError:
        return 0


def is_finance_row(row):
    m = FINANCE_RE.match(row['budget_raw'])
    if m:
        return m.group(1)
    return None


def is_footer(val):
    return bool(PAGE_FOOTER_RE.match(val)) if val else False


def merge_all_sheets():
    zf = zipfile.ZipFile(XLSX_PATH)
    ss = load_shared_strings(zf)
    
    ws_files = sorted(
        [f for f in zf.namelist() if re.match(r'xl/worksheets/sheet\d+\.xml', f)],
        key=lambda x: int(re.search(r'sheet(\d+)', x).group(1))
    )
    
    print(f"  시트 {len(ws_files)}개, 공유문자열 {len(ss)}개")
    
    all_rows = []
    for i, ws_file in enumerate(ws_files):
        rows = parse_single_sheet(zf, ws_file, ss)
        if rows:
            all_rows.extend(rows)
        if (i + 1) % 100 == 0:
            print(f"  ... {i+1}/{len(ws_files)} ({len(all_rows):,} 행)")
    
    zf.close()
    print(f"  ✅ 전체 {len(all_rows):,} 행 통합")
    return all_rows


def clean_and_fillna(rows):
    print(f"  정제: {len(rows):,}행")
    
    cleaned = []
    for row in rows:
        if is_footer(row['dept']) or is_footer(row['policy']) or is_footer(row['budget_raw']):
            continue
        
        # 시트 컨텍스트 반영 (빈 dept/policy/unit 채움)
        if not row['dept']:
            row['dept'] = row['ctx_dept']
            row['has_dept'] = False  # 원본 아님
        if not row['policy']:
            row['policy'] = row['ctx_policy']
            row['has_policy'] = False
        if not row['unit']:
            row['unit'] = row['ctx_unit']
            row['has_unit'] = False
        
        # 완전 빈 행 제거
        if not any([row['dept'], row['policy'], row['unit'], row['detail'], 
                    row['item'], row['calc'], row['budget_raw']]):
            continue
        
        cleaned.append(row)
    
    print(f"    → {len(cleaned):,}행")
    
    # 전역 forward-fill (dept/policy/unit/detail/item)
    last = {'dept':'','policy':'','unit':'','detail':'','item':''}
    for row in cleaned:
        for k in ['dept','policy','unit','detail','item']:
            if row[k]:
                last[k] = row[k]
            else:
                row[k] = last[k]
    
    print(f"  전역 fillna 완료")
    return cleaned


def build_tree(rows):
    print(f"  트리 변환: {len(rows):,}행")
    
    items = []
    id_counter = [0]
    
    # 스택: 마지막 노드 id (depth 0~5)
    stack = [None] * 6
    stack_nodes = [None] * 6
    
    # 마지막으로 본 dept/policy/unit/detail/item 값
    last_vals = [''] * 6
    
    for row in rows:
        budget_amount = parse_amount(row['budget_raw'])
        prev_amount = parse_amount(row['prev_raw'])
        diff_amount = parse_amount(row['diff_raw'])
        
        # ─── 재원 행 처리 ───
        fin_type = is_finance_row(row)
        if fin_type:
            idx_map = {'국': 0, '도': 1, '군': 2, '기': 3}
            target = idx_map.get(fin_type, 0)
            # 가장 가까운 non-None 부모 찾기
            for s_idx in range(5, -1, -1):
                if stack_nodes[s_idx] is not None:
                    node = stack_nodes[s_idx]
                    amounts = [node.finance_national, node.finance_province,
                               node.finance_county, node.finance_other]
                    amounts[target] += budget_amount
                    node.finance_national = amounts[0]
                    node.finance_province = amounts[1]
                    node.finance_county = amounts[2]
                    node.finance_other = amounts[3]
                    break
            continue
        
        # ─── depth 결정 (원본 컬럼 존재 여부 기준) ───
        # has_* 필드는 fillna 이전 원본 값 기준
        depth = 5  # 기본
        if row['has_calc']:
            depth = 5
        elif row['has_item']:
            depth = 4
        elif row['has_detail']:
            depth = 3
        elif row['has_unit']:
            depth = 2
        elif row['has_policy']:
            depth = 1
        elif row['has_dept']:
            depth = 0
        else:
            continue  # 순수 fillna 행 (재원 아니면 skip)
        
        # ─── 부모 ID 찾기 ───
        parent_id = None
        for p_idx in range(depth - 1, -1, -1):
            if stack[p_idx] is not None:
                parent_id = stack[p_idx]
                break
        
        # ─── 노드 생성 ───
        id_counter[0] += 1
        node = BudgetItem()
        node.id = id_counter[0]
        node.parent_id = parent_id
        node.depth = depth
        node.dept = row['dept']
        node.policy = row['policy'] if depth >= 1 else ''
        node.unit = row['unit'] if depth >= 2 else ''
        node.detail = row['detail'] if depth >= 3 else ''
        
        # 편성목 파싱
        item_raw = row['item']
        item_code = ''
        item_name = ''
        if item_raw:
            parts = item_raw.split(None, 1)
            item_code = parts[0] if parts else ''
            item_name = parts[1] if len(parts) > 1 else item_raw
        
        node.item_code = item_code if depth >= 4 else ''
        node.item_name = item_name if depth >= 4 else ''
        node.calc_name = row['calc'] if depth >= 5 else ''
        node.basis = row['basis']
        node.budget_amount = budget_amount
        node.prev_amount = prev_amount
        node.diff_amount = diff_amount
        node.page = row['page']
        node.row_num = row['row_num']
        node.is_total = 0
        node.finance_national = 0
        node.finance_province = 0
        node.finance_county = 0
        node.finance_other = 0
        
        items.append(node)
        
        # 스택 업데이트
        stack[depth] = node.id
        stack_nodes[depth] = node
        for clr in range(depth + 1, 6):
            stack[clr] = None
            stack_nodes[clr] = None
    
    print(f"  ✅ {len(items):,}개 노드")
    return items


def parse_all():
    print("📋 Parser v4.1 — 원본 컬럼 기반 depth")
    print("  [1/3] 시트 통합...")
    all_rows = merge_all_sheets()
    print("  [2/3] 정제 + 전역 fillna...")
    cleaned = clean_and_fillna(all_rows)
    print("  [3/3] 트리 변환...")
    items = build_tree(cleaned)
    return items


if __name__ == '__main__':
    items = parse_all()
    # 통계
    from collections import Counter
    dc = Counter(i.depth for i in items)
    for d in sorted(dc):
        print(f"  depth={d}: {dc[d]:,}")
    print(f"  TOTAL: {len(items):,}")
