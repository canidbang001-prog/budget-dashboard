"""
extract_csv.py v2 — XLSX → CSV (민성님 인덴트 형식)
- 선행 콤마 = 인덴트 레벨
- 재원 행(국/도/군/기)은 별도 행으로 유지
- 본예산/추경 구분 없이 원본 그대로
"""
import os, re, zipfile, xml.etree.ElementTree as ET, csv

XLSX_PATH = '/root/.openclaw/workspace/아라/2026 전체합본예산서.xlsx'
CSV_PATH = '/root/.openclaw/workspace/디렉이/project_3003/budget.csv'
NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'

PAGE_FOOTER_RE = re.compile(r'^\s*-\s*\d+\s*-\s*$')

def load_ss(zf):
    root = ET.fromstring(zf.read('xl/sharedStrings.xml'))
    strings = []
    for si in root.findall(f'{{{NS}}}si'):
        t = si.find(f'{{{NS}}}t')
        if t is not None and t.text: strings.append(t.text)
        else:
            parts = []
            for r in si.findall(f'{{{NS}}}r'):
                rt = r.find(f'{{{NS}}}t')
                if rt is not None and rt.text: parts.append(rt.text)
            strings.append(''.join(parts))
    return strings

def get_val(cell, ss):
    v = cell.find(f'{{{NS}}}v')
    if v is None or v.text is None: return ''
    if cell.get('t') == 's':
        idx = int(v.text)
        return ss[idx] if 0 <= idx < len(ss) else ''
    return v.text

def extract_sheet(zf, ws_file, ss):
    ws_xml = ET.fromstring(zf.read(ws_file))
    rows = ws_xml.findall(f'{{{NS}}}sheetData/{{{NS}}}row')
    if not rows: return []
    
    page = int(re.search(r'sheet(\d+)', os.path.basename(ws_file)).group(1))
    
    # 컨텍스트 (row 5-7)
    ctx = ['', '', '']
    for row in rows:
        rn = int(row.get('r', '0'))
        if rn > 9: break
        cells = {c.get('r',''): c for c in row.findall(f'{{{NS}}}c')}
        d = cells.get(f'D{rn}')
        if d is None: continue
        v = (get_val(d, ss) or '').strip()
        if v.startswith('부서:'): ctx[0] = v.replace('부서:','').strip()
        elif v.startswith('정책:'): ctx[1] = v.replace('정책:','').strip()
        elif v.startswith('단위:'): ctx[2] = v.replace('단위:','').strip()
    
    result = []
    COLS = ['A','B','C','D','E','F','G','H','I','J','K']
    
    for row in rows:
        rn = int(row.get('r', '0'))
        if rn < 10: continue
        
        cells = {c.get('r',''): c for c in row.findall(f'{{{NS}}}c')}
        vals = []
        for col in COLS:
            ref = f'{col}{rn}'
            v = (get_val(cells[ref], ss) or '').strip().replace('\n',' ') if ref in cells else ''
            vals.append(v)
        
        # 푸터 스킵
        footers = [vals[0], vals[1], vals[8]]
        if any(PAGE_FOOTER_RE.match(f) for f in footers if f): continue
        # 완전 빈 행 스킵
        if not any(v for v in vals): continue
        
        # ─── 컨텍스트로 빈 값 채우기 (dept/policy/unit만) ───
        if not vals[0]: vals[0] = ctx[0]
        if not vals[1]: vals[1] = ctx[1]
        if not vals[2]: vals[2] = ctx[2]
        
        # ─── 인덴트 결정: 처음으로 값이 있는 컬럼 (0~6) ───
        indent = 6  # 기본: calc 레벨
        for i in range(7):  # A(0)~G(6) 스캔
            if vals[i]:
                indent = i
                break
        
        # dept/policy/unit은 컨텍스트에서 채워졌더라도 원본 값이 없으면 이전 행과 같다고 간주
        # → 원본 값 추적: 셀에 실제 값이 있었는지
        
        result.append({
            'page': page,
            'row_num': rn,
            'indent': indent,
            'vals': vals,  # A~K
            'has_original': [ref in cells for ref in [f'{c}{rn}' for c in COLS[:7]]]
        })
    
    return result


def write_csv_indent(all_rows):
    """민성님 인덴트 형식 CSV: 선행 콤마 + 값 + 나머지 콤마 + 예산"""
    with open(CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        # 헤더
        writer.writerow(['page','row_num','dept','policy','unit','detail','label',
                         'item','calc','basis','budget','prev','diff','indent'])
        
        for r in all_rows:
            vals = r['vals']
            out = [vals[0], vals[1], vals[2], vals[3], vals[4], vals[5],
                   vals[6], vals[7], vals[8], vals[9], vals[10],
                   r['indent']]
            writer.writerow([r['page'], r['row_num']] + out)
    
    print(f"  ✅ CSV: {os.path.getsize(CSV_PATH)/1024/1024:.1f}MB, {len(all_rows):,}행")


def main():
    print("📋 XLSX → CSV v2 (인덴트 포함)")
    zf = zipfile.ZipFile(XLSX_PATH)
    ss = load_ss(zf)
    
    ws_files = sorted(
        [f for f in zf.namelist() if re.match(r'xl/worksheets/sheet\d+\.xml', f)],
        key=lambda x: int(re.search(r'sheet(\d+)', x).group(1))
    )
    
    print(f"  시트 {len(ws_files)}개, 공유문자열 {len(ss)}개")
    
    all_rows = []
    for i, ws_file in enumerate(ws_files):
        rows = extract_sheet(zf, ws_file, ss)
        if rows: all_rows.extend(rows)
        if (i+1) % 100 == 0:
            print(f"  ... {i+1}/{len(ws_files)} 시트 ({len(all_rows):,} 행)")
    
    zf.close()
    print(f"  ✅ 전체 {len(all_rows):,} 행")
    
    write_csv_indent(all_rows)
    print("🏁 완료")


if __name__ == '__main__':
    main()
