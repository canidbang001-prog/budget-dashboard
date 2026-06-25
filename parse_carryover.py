"""이월조서 파싱 + 합본예산서 DB 매칭 v5 — carryover_type + 재원 6종 추적
v5.1: 40개 부서 전체 지원 (예산팀 전체 파일)
"""
import os, re, shutil
from datetime import datetime
import xlrd, sqlite3

# 이 파일들이 우리 repo에 있으면 자동 인식
_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CARRYOVER_DIR = _HERE

# 3개 파일: 명시이월, 사고이월, 계속비이월 (각각 모든 부서 포함)
FILES = {
    '명시이월': os.path.join(_HERE, '2025회계연도 명시이월 현황.xls'),
    '사고이월': os.path.join(_HERE, '2025회계연도 사고이월 현황.xls'),
    '계속비': os.path.join(_HERE, '2025회계연도 계속비이월 현황.xls'),
}
CARRYOVER_TYPE_FILES = {
    '명시이월': os.environ.get('CARRYOVER_FILE_명시'),
    '사고이월': os.environ.get('CARRYOVER_FILE_사고'),
    '계속비': os.environ.get('CARRYOVER_FILE_계속'),
}
for k, v in CARRYOVER_TYPE_FILES.items():
    if v:
        FILES[k] = v

# DEPTS: 더 이상 제한 없음. 파일 안에 모든 부서가 있음.
DEPTS = []  # 빈 리스트 = 제한 없음 (모든 dept 매칭 시도)

DB_PATH = os.environ.get(
    'DB_PATH',
    os.path.join(_HERE, 'budget.db')
)

def norm(s):
    if not s: return ''
    s = str(s).strip().replace('\n',' ').replace('\r',' ').replace('\t',' ')
    s = s.replace('\uff08','(').replace('\uff09',')').replace('\u3010','[').replace('\u3011',']')
    return re.sub(r'\s+',' ', s).strip()

def norm_item(s):
    s = norm(s)
    return re.sub(r'^\d{3}(-\d{2})?\s*','', s).strip()

def extract_base_policy(pol):
    pol = norm(pol)
    return re.sub(r'\s*\([^)]+\)\s*$','', pol).strip()

# ─── Finance column helpers ─────────────────

def safe_int(ws, r, c):
    """Extract integer from ws cell (r,c), returning 0 on failure."""
    try: return int(float(ws.cell_value(r, c)))
    except: return 0

def read_finance(ws, r, tc):
    """Read 7 finance columns: total=tc, nat=tc+1, bal=tc+2, fund=tc+3,
       spec=tc+4, prov=tc+5, adj=tc+6, cnty=tc+7.
       Excel is in 원, DB uses 천원 → divide by 1000.
       Returns {carryover, carryover_national, ...}. other = fund + adj."""
    def won_to_kwon(v):
        return round(v / 1000)
    nat = safe_int(ws, r, tc+1)
    bal = safe_int(ws, r, tc+2)
    fund = safe_int(ws, r, tc+3)
    spec = safe_int(ws, r, tc+4)
    prov = safe_int(ws, r, tc+5)
    adj = safe_int(ws, r, tc+6)
    cnty = safe_int(ws, r, tc+7)
    total = nat + bal + fund + spec + prov + adj + cnty
    if total == 0:
        total = safe_int(ws, r, tc)  # fallback to direct total
    return {
        'carryover': won_to_kwon(total),
        'carryover_national': won_to_kwon(nat),
        'carryover_province': won_to_kwon(prov),
        'carryover_county': won_to_kwon(cnty),
        'carryover_special': won_to_kwon(spec),
        'carryover_balance': won_to_kwon(bal),
        'carryover_other': won_to_kwon(fund + adj),
    }

# ─── 엑셀 파싱 ──────────────────────────────────

def parse_myeongsi_sago(ws, dept_name):
    items = []; tc = None
    # Find total carryover column from row 2
    for c in range(ws.ncols):
        if '이월액' in str(ws.cell_value(2, c)):
            tc = c; break
    if tc is None: return items

    for r in range(5, ws.nrows):
        vals = [str(ws.cell_value(r,c)).strip() for c in range(ws.ncols)]
        pol=vals[0] if len(vals)>0 else ''
        if not pol or pol.startswith('총') or pol.startswith('합계'): continue
        unit=vals[1] if len(vals)>1 else ''; det=vals[2] if len(vals)>2 else ''
        item=vals[3] if len(vals)>3 else ''
        fin = read_finance(ws, r, tc)
        if fin['carryover'] > 0 and pol and det:
            items.append({'dept':dept_name,'policy':norm(pol),'unit':norm(unit),
                          'detail':norm(det),'item_name':norm(item), **fin})
    return items

def parse_gyesok(ws, dept_name):
    items = []; tc = None
    for c in range(ws.ncols):
        if '이월액' in str(ws.cell_value(2, c)):
            tc = c; break
    if tc is None: return items

    for r in range(5, ws.nrows):
        vals = [str(ws.cell_value(r,c)).strip() for c in range(ws.ncols)]
        pol=vals[1] if len(vals)>1 else ''; unit=vals[2] if len(vals)>2 else ''
        det=vals[3] if len(vals)>3 else ''
        if (not pol and not det) or pol.startswith('총') or pol.startswith('합계'): continue
        stat_raw=''
        for ci in (4,5):
            if ci>=len(vals): continue
            if re.match(r'^\d{3}-\d{2}',vals[ci]): stat_raw=vals[ci]; break
        if not stat_raw: stat_raw=vals[5] if len(vals)>5 and vals[5] else vals[4] if len(vals)>4 else ''
        fin = read_finance(ws, r, tc)
        if fin['carryover'] > 0 and pol and det:
            items.append({'dept':dept_name,'policy':norm(pol),'unit':norm(unit),
                          'detail':norm(det),'item_name':norm_item(stat_raw), **fin})
    return items

def parse_file(filepath, dept_name):
    wb = xlrd.open_workbook(filepath, formatting_info=False)
    all_items = []
    for si in range(len(wb.sheet_names())):
        sname = wb.sheet_names()[si]
        if '특별' in sname: continue
        ws = wb.sheet_by_index(si)
        if '계속비' in sname:
            items = parse_gyesok(ws, dept_name); ctype = '계속비'
        elif '사고' in sname:
            items = parse_myeongsi_sago(ws, dept_name); ctype = '사고이월'
        else:
            items = parse_myeongsi_sago(ws, dept_name); ctype = '명시이월'
        for i in items: i['carryover_type'] = ctype
        all_items.extend(items)
    return all_items

# ─── DB 매칭 ────────────────────────────────────

FINANCE_FIELDS = [
    'carryover', 'carryover_national', 'carryover_province', 'carryover_county',
    'carryover_special', 'carryover_balance', 'carryover_other'
]

def match_and_update(db_conn, excel_items):
    cursor = db_conn.cursor()
    # DEPTS 비어있으면 = 모든 dept 매칭 (필터 없음)
    if DEPTS:
        placeholders = ','.join('?' * len(DEPTS))
        db_rows = cursor.execute(
            f"SELECT id,dept,policy,unit,detail,item_name,calc_name,budget_amount,depth "
            f"FROM budget_items WHERE dept IN ({placeholders}) AND depth >= 3",
            DEPTS).fetchall()
    else:
        db_rows = cursor.execute(
            "SELECT id,dept,policy,unit,detail,item_name,calc_name,budget_amount,depth "
            "FROM budget_items WHERE depth >= 3"
        ).fetchall()
    matched=0; unmatched=[]; updated_ids=[]

    for ex in excel_items:
        ed,ep,eu,edet,eitem,ecarry = ex['dept'],ex['policy'],ex['unit'],ex['detail'],norm_item(ex['item_name']),ex['carryover']
        cotype = ex.get('carryover_type', '이월사업')
        fvals = [ex.get(f, 0) for f in FINANCE_FIELDS]  # 7 values
        set_clause = ', '.join(f'{f}=?' for f in FINANCE_FIELDS) + ', status=?'
        params = lambda rid: fvals + [cotype, rid]

        def do_exec(candidates):
            nonlocal matched, updated_ids
            cids = [(r[0], r[-1]) for r in candidates]  # (id, depth)
            if len(candidates) == 1:
                cursor.execute(f"UPDATE budget_items SET {set_clause} WHERE id=?", params(candidates[0][0]))
                updated_ids.append(candidates[0][0]); matched+=1
                return True
            if len(candidates) > 1:
                best = sorted(candidates, key=lambda r: (4 if r[8]==4 else 5 if r[8]==5 else 99, -r[8]))[0]
                cursor.execute(f"UPDATE budget_items SET {set_clause} WHERE id=?", params(best[0]))
                updated_ids.append(best[0]); matched+=1
                return True
            return False

        # Pass 1: exact
        c1 = [r for r in db_rows if norm(r[1])==ed and extract_base_policy(r[2])==ep and norm(r[3])==eu and norm(r[4])==edet and norm_item(r[5])==eitem]
        if do_exec(c1): continue

        # Pass 2: exact on dept/policy/unit/detail, partial item
        c2 = [r for r in db_rows if norm(r[1])==ed and extract_base_policy(r[2])==ep and norm(r[3])==eu and norm(r[4])==edet]
        if eitem:
            c2=[r for r in c2 if eitem in norm_item(r[5])or norm_item(r[5])in eitem or eitem in norm(r[6])or norm(r[6])in eitem]
        if do_exec(c2): continue

        # Pass 3: dept/policy/unit match, partial detail + partial item
        c3=[r for r in db_rows if norm(r[1])==ed and extract_base_policy(r[2])==ep and norm(r[3])==eu]; ndet=norm(edet)
        c3=[r for r in c3 if ndet and norm(r[4])and(ndet in norm(r[4])or norm(r[4])in ndet)]
        if eitem: c3=[r for r in c3 if eitem in norm_item(r[5])or norm_item(r[5])in eitem or eitem in norm(r[6])or norm(r[6])in eitem]
        if do_exec(c3): continue

        # Pass 4: dept + detail match only (loose)
        c4=[r for r in db_rows if norm(r[1])==ed and norm(r[4])==ndet]
        if eitem: c4=[r for r in c4 if eitem in norm_item(r[5])or norm_item(r[5])in eitem or eitem in norm(r[6])or norm(r[6])in eitem]
        if do_exec(c4): continue

        # Pass 5: dept + partial detail (any item match)
        c5=[r for r in db_rows if norm(r[1])==ed and norm(r[4])and ndet and(ndet in norm(r[4])or norm(r[4])in ndet)]
        if eitem: c5=[r for r in c5 if eitem in norm_item(r[5])or norm_item(r[5])in eitem or eitem in norm(r[6])or norm(r[6])in eitem]
        if do_exec(c5): continue

        # Pass 6: dept + unit match, partial detail
        c6=[r for r in db_rows if norm(r[1])==ed and norm(r[3])==eu and norm(r[4])and ndet and(ndet in norm(r[4])or norm(r[4])in ndet)]
        if do_exec(c6): continue

        # Pass 7: space-insensitive
        ndet_nosp=ndet.replace(' ','').replace('.','')
        c7=[r for r in db_rows if norm(r[1])==ed]
        c7=[r for r in c7 if norm(r[4])and ndet_nosp and(ndet_nosp in norm(r[4]).replace(' ','').replace('.','')or norm(r[4]).replace(' ','').replace('.','')in ndet_nosp)]
        if eitem: c7=[r for r in c7 if eitem in norm_item(r[5])or norm_item(r[5])in eitem or eitem in norm(r[6])or norm(r[6])in eitem]
        if do_exec(c7): continue

        unmatched.append(ex)

    db_conn.commit()
    return matched, unmatched, updated_ids

# ─── 메인 ───────────────────────────────────────

def main():
    backup_path = f'{DB_PATH}.backup_carryover_v5_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    shutil.copy2(DB_PATH, backup_path)
    print(f"[BACKUP] {backup_path}")

    all_items = []
    for dept, filepath in FILES.items():
        items = parse_file(filepath, dept)
        cf = sum(i['carryover'] for i in items)
        fn = sum(i['carryover_national'] for i in items)
        fp = sum(i['carryover_province'] for i in items)
        fc = sum(i['carryover_county'] for i in items)
        print(f"[PARSE] {dept}: {len(items)} items, sum={cf:,} (nat={fn:,} prov={fp:,} cnty={fc:,})")
        all_items.extend(items)

    print(f"\n=== Total: {len(all_items)} Excel items ===")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode = WAL")
    matched, unmatched, updated_ids = match_and_update(conn, all_items)
    conn.close()

    print(f"\n{'='*60}")
    print(f"파싱: {len(all_items)}, 매칭: {matched}, 미매칭: {len(unmatched)}")
    print(f"업데이트: {len(set(updated_ids))} rows, 총 이월액: {sum(i['carryover'] for i in all_items):,}")

    if unmatched:
        print(f"\n--- 미매칭 ({len(unmatched)}) ---")
        for u in unmatched:
            print(f"  {u['dept']} | {u['detail'][:35]} | type={u.get('carryover_type','?')} | {u['carryover']:,}")

    conn2 = sqlite3.connect(DB_PATH)
    c = conn2.execute("SELECT COUNT(*),SUM(carryover) FROM budget_items WHERE dept IN ('도시과','건설과')").fetchone()
    print(f"\n[DONE] DB: rows={c[0]}, total_carryover={c[1]:,}")

if __name__ == '__main__': main()
