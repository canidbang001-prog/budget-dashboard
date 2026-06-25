"""
parse_carryover_all.py — 예산팀 이월 조서 (40개 부서 전체) 파싱 + DB 매칭

파일 형식:
  - .xls
  - 시트 1개 (전체 부서 통합)
  - col 0: 부서명 (이전 cell 비어있으면 같은 부서)
  - col 1: (빈)
  - col 2: 정책
  - col 3: 단위
  - col 4: 세부
  - col 5: 통계목
  - col 6: 계 (이월 총액)
  - col 11: 국비
  - col 12: 균특
  - col 13: 기금
  - col 14: 특교세
  - col 15: 도비
  - col 16: 군비
  - "부서별 소계" / "총 계" 행은 스킵

Usage:
  python parse_carryover_all.py [xls_path] [db_path]
  env: XLS_PATH, DB_PATH
"""
import os
import sys
import re
import xlrd
import sqlite3
import shutil
from datetime import datetime

# ── 인자 ──────────────────────────────────────────
XLS = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
    'XLS_PATH',
    os.path.join(os.path.dirname(__file__), '2025회계연도 명시이월 현황.xls')
)
DB = sys.argv[2] if len(sys.argv) > 2 else os.environ.get(
    'DB_PATH',
    os.path.join(os.path.dirname(__file__), 'budget.db')
)

# 파일명에서 carryover_type 자동 인식 (명시/사고/계속)
CARRYOVER_TYPE = '계속비'  # 기본
fn = os.path.basename(XLS)
if '명시' in fn:
    CARRYOVER_TYPE = '명시이월'
elif '사고' in fn:
    CARRYOVER_TYPE = '사고이월'
elif '계속비' in fn:
    CARRYOVER_TYPE = '계속비'

print(f"📋 이월 파서 v2: {os.path.basename(XLS)}")
print(f"   carryover_type: {CARRYOVER_TYPE}")
print(f"   DB: {DB}")


def norm(s):
    if not s:
        return ''
    s = str(s).strip().replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    s = s.replace('\uff08', '(').replace('\uff09', ')').replace('\u3010', '[').replace('\u3011', ']')
    return re.sub(r'\s+', ' ', s).strip()


def safe_int(v):
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def won_to_kwon(v):
    """원 → 천원 변환 (이월 조서는 원 단위, DB는 천원 단위)"""
    return round(v / 1000) if v else 0


def extract_base_policy(pol):
    pol = norm(pol)
    return re.sub(r'\s*\([^)]+\)\s*$', '', pol).strip()


def parse_xls(path):
    """부서/정책/단위/세부/통계목 + 재원 6종 추출"""
    wb = xlrd.open_workbook(path, formatting_info=False)
    ws = wb.sheet_by_index(0)

    items = []
    current_dept = ''
    skip_labels = ('총 계', '총계', '부서별 소 계', '부서별소계', '부 서 별 소 계')

    for r in range(5, ws.nrows):
        try:
            dept_cell = norm(ws.cell_value(r, 0))
            pol = norm(ws.cell_value(r, 2))
            unit = norm(ws.cell_value(r, 3))
            detail = norm(ws.cell_value(r, 4))
            stat = norm(ws.cell_value(r, 5))

            # 부서 갱신
            if dept_cell and dept_cell not in skip_labels:
                current_dept = dept_cell
            elif dept_cell in skip_labels:
                # 소계 행 — 스킵
                continue

            # 재원 (col 11~16): 국/균/기/특/도/군
            # 이월 조서는 원 단위, DB는 천원 단위 → ÷1000
            # col 10 = "다음 연도 이월 액" (사용자 확인: r4 헤더 '다 음 연 도 이 월 액')
            # col 6 = "예산액" (이게 아님!) — 이거 잘못 읽었었음
            # col 11~16 = 재원 6종 (국/균/기/특/도/군)
            carry = won_to_kwon(safe_int(ws.cell_value(r, 10)))
            nat = won_to_kwon(safe_int(ws.cell_value(r, 11)))
            bal = won_to_kwon(safe_int(ws.cell_value(r, 12)))  # 균특
            fund = won_to_kwon(safe_int(ws.cell_value(r, 13)))  # 기금
            spec = won_to_kwon(safe_int(ws.cell_value(r, 14)))  # 특교세
            prov = won_to_kwon(safe_int(ws.cell_value(r, 15)))
            cnty = won_to_kwon(safe_int(ws.cell_value(r, 16)))

            # 통계목 (col 5): 본예산 label+calc 합성 ("207-01\n연구용역비")
            # → label="207", calc="01" 추출 (Pass 9 매칭용)
            stat_raw = norm(ws.cell_value(r, 5))
            stat_match = re.match(r'^(\d{3})-(\d{2})', stat_raw)
            stat_label = stat_match.group(1) if stat_match else ''
            stat_calc = stat_match.group(2) if stat_match else ''

            # 이월사유 (col 17): 본예산 ◎ calc_name과 1:1 매칭 (Pass 8)
            carryover_reason = norm(ws.cell_value(r, 17))

            if carry == 0 and not (pol or unit or detail or stat):
                continue

            items.append({
                'dept': current_dept,
                'policy': pol,
                'unit': unit,
                'detail': detail,
                'item_name': stat,  # 통계목
                'stat_label': stat_label,  # 편성목 코드 (예: "207")
                'stat_calc': stat_calc,    # 통계목 코드 (예: "01")
                'carryover_reason': carryover_reason,  # 이월사유 (= 본예산 ◎ calc)
                'carryover': carry,
                'carryover_national': nat,
                'carryover_province': prov,
                'carryover_county': cnty,
                'carryover_special': spec,
                'carryover_balance': bal,
                'carryover_other': fund,
                'carryover_type': CARRYOVER_TYPE,
            })
        except Exception as e:
            print(f"  ⚠️ r{r} parse error: {e}")
            continue
    return items


def match_and_update(db_path, items):
    """DB에 carryover 매칭 + UPDATE"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # DB의 모든 dept 가져오기
    db_depts = [r[0] for r in cursor.execute(
        "SELECT DISTINCT dept FROM budget_items WHERE dept != ''"
    ).fetchall()]
    print(f"  DB 부서: {len(db_depts)}개")

    # dept 매핑 (엑셀의 dept_name → DB의 dept_name, 정확 일치 우선)
    # 예: "도시과" → "도시과", "홍성읍" → "홍성읍"
    # 정확 매칭이 안 되면 fuzzy

    # 매칭 후보: dept + policy + unit + detail + calc_name
    db_rows = cursor.execute("""
        SELECT id, dept, policy, unit, detail, item_name, calc_name, budget_amount, depth
        FROM budget_items
        WHERE depth >= 3
    """).fetchall()
    print(f"  DB 매칭 후보: {len(db_rows):,}개 (depth>=3)")

    # Pass 8 전용: label + calc_name까지 가져오기 (◎노드 매칭)
    db_rows_full = cursor.execute("""
        SELECT id, dept, policy, unit, detail, item_name, label, calc_name, budget_amount, depth
        FROM budget_items
        WHERE depth >= 3
    """).fetchall()

    matched = 0
    unmatched = []
    updated_ids = []

    for ex in items:
        ed = norm(ex['dept'])
        ep = extract_base_policy(ex['policy'])
        eu = norm(ex['unit'])
        edet = norm(ex['detail'])
        eitem = norm(ex['item_name'])
        eco = ex['carryover']
        cotype = ex.get('carryover_type', '이월사업')

        if eco == 0:
            continue

        fvals = [ex.get('carryover_national', 0),
                 ex.get('carryover_province', 0),
                 ex.get('carryover_county', 0),
                 ex.get('carryover_special', 0),
                 ex.get('carryover_balance', 0),
                 ex.get('carryover_other', 0)]

        set_clause = ('carryover_national = ?, carryover_province = ?, '
                      'carryover_county = ?, carryover_special = ?, '
                      'carryover_balance = ?, carryover_other = ?, '
                      'carryover = ?, status = ?')
        params = (*fvals, eco, cotype, None)

        def do_exec(candidates):
            nonlocal matched
            if len(candidates) == 1:
                cursor.execute(
                    f"UPDATE budget_items SET {set_clause} WHERE id = ?",
                    (*params[:-1], candidates[0][0])
                )
                updated_ids.append(candidates[0][0])
                matched += 1
                return True
            if len(candidates) > 1:
                # depth 7 (편성내용 ◎/○) 우선, 그 다음 depth 6 (통계목), 5 (편성목)
                def depth_rank(r):
                    d = r[8]
                    if d == 7: return 0
                    if d == 6: return 1
                    if d == 5: return 2
                    if d == 4: return 3
                    return 99
                best = sorted(candidates, key=depth_rank)[0]
                cursor.execute(
                    f"UPDATE budget_items SET {set_clause} WHERE id = ?",
                    (*params[:-1], best[0])
                )
                updated_ids.append(best[0])
                matched += 1
                return True
            return False

        # Pass 1: dept + policy + unit + detail + item (정확)
        c1 = [r for r in db_rows
              if norm(r[1]) == ed and extract_base_policy(r[2]) == ep
              and norm(r[3]) == eu and norm(r[4]) == edet
              and norm(r[5]) == eitem]
        if do_exec(c1):
            continue

        # Pass 2: dept + policy + unit + detail (item 부분 일치)
        c2 = [r for r in db_rows
              if norm(r[1]) == ed and extract_base_policy(r[2]) == ep
              and norm(r[3]) == eu and norm(r[4]) == edet]
        if c2 and eitem:
            c2 = [r for r in c2
                  if eitem in norm(r[5]) or norm(r[5]) in eitem
                  or eitem in norm(r[6]) or norm(r[6]) in eitem]
        if do_exec(c2):
            continue

        # Pass 3: dept + policy + unit (detail 부분 일치)
        c3 = [r for r in db_rows
              if norm(r[1]) == ed and extract_base_policy(r[2]) == ep
              and norm(r[3]) == eu]
        c3 = [r for r in c3
              if edet and norm(r[4])
              and (edet in norm(r[4]) or norm(r[4]) in edet)]
        if do_exec(c3):
            continue

        # Pass 4: dept + detail (loose)
        c4 = [r for r in db_rows
              if norm(r[1]) == ed and norm(r[4]) == edet]
        if do_exec(c4):
            continue

        # Pass 5: dept + partial detail
        c5 = [r for r in db_rows
              if norm(r[1]) == ed and norm(r[4])
              and edet and (edet in norm(r[4]) or norm(r[4]) in edet)]
        if do_exec(c5):
            continue

        # Pass 6: dept + unit + partial detail
        c6 = [r for r in db_rows
              if norm(r[1]) == ed and norm(r[3]) == eu
              and norm(r[4]) and edet
              and (edet in norm(r[4]) or norm(r[4]) in edet)]
        if do_exec(c6):
            continue

        # Pass 7: dept + exact detail (item 무시, 정확 일치)
        # (partial 매칭 제거: "전통시장" 같은 짧은 substring으로 다른 사업이 매칭되는 버그)
        c7 = [r for r in db_rows
              if norm(r[1]) == ed and norm(r[4]) == edet]
        if do_exec(c7):
            continue

        # Pass 8: dept + policy + unit + detail + label + calc (◎노드 매칭)
        # 이월 조서의 "통계목" (예: "207-01\n연구용역비") = 본예산 label+calc
        # 이월 조서의 "이월사유" (예: "용역 준공 미도래") = 본예산 ◎ calc_name
        # DB에 label 컬럼이 비어있어 item_name에서 추출
        # 예: item_name="207 연구개발비" → 라벨 코드 "207"
        ereason = ex.get('carryover_reason', '').strip()
        elast = ex.get('stat_label', '').strip()
        ecalc = ex.get('stat_calc', '').strip()

        if ereason or (elast and ecalc):
            c8 = []
            for r in db_rows_full:
                if norm(r[1]) != ed or extract_base_policy(r[2]) != ep:
                    continue
                if norm(r[3]) != eu or norm(r[4]) != edet:
                    continue
                # stat_label 매칭: item_name이 "207 연구개발비" 처럼 숫자로 시작
                if elast:
                    item_name = norm(r[6])
                    # item_name의 첫 단어가 elast와 일치
                    item_code = item_name.split()[0] if item_name else ''
                    if item_code != elast:
                        continue
                # stat_calc 매칭 (예: "01" = calc "01")
                if ecalc and norm(r[7]) != ecalc:
                    continue
                # carryover_reason 매칭 (◎ calc 텍스트가 일치)
                if ereason and ereason not in norm(r[7]):
                    continue
                c8.append(r)
            if do_exec(c8):
                continue

        # Pass 9: 본예산에 매칭 안 됨 → 신규 ◎ 노드 INSERT (cascade)
        # (이월 조서에 "(성립전)" 사업 = 본예산에 없는 사업 = 순수 이월)
        # dept + policy + unit + detail → cascade 매칭:
        #   d=3 (detail) 있으면 그 자식으로 ◎ INSERT
        #   없으면 d=2 (unit) 자리에 신규 detail INSERT 후 ◎ INSERT
        #   그것도 없으면 d=1 (policy) 자리에 신규 unit+detail INSERT 후 ◎ INSERT
        #   그것도 없으면 d=0 (dept) 자리에 신규 policy+unit+detail INSERT 후 ◎ INSERT

        if ed and ep:
            cur_parent_id = None
            cur_depth = 7  # 최종 ◎ 노드 d=7

            # 1) d=3 (detail) 매칭 시도
            row = cursor.execute("""
                SELECT id FROM budget_items
                WHERE dept=? AND policy=? AND unit=? AND detail=? AND depth=3
                LIMIT 1
            """, (ed, ep, eu, edet)).fetchone()

            if row:
                cur_parent_id = row[0]
            else:
                # 2) d=2 (unit) 매칭 시도, 없으면 신규 unit INSERT
                row = cursor.execute("""
                    SELECT id FROM budget_items
                    WHERE dept=? AND policy=? AND unit=? AND depth=2
                    LIMIT 1
                """, (ed, ep, eu)).fetchone()

                if row:
                    cur_parent_id = row[0]
                else:
                    # 신규 unit (d=2) INSERT
                    cursor.execute("""
                        INSERT INTO budget_items
                        (parent_id, depth, dept, policy, unit, detail,
                         budget_amount, budget_amount_raw, page, row_num, is_total, status)
                        VALUES (?, 2, ?, ?, ?, '', 0, 0, '', 0, 0, '')
                    """, (cur_parent_id, ed, ep, eu))
                    cur_parent_id = cursor.lastrowid

                # 3) d=3 (detail) 매칭 시도, 없으면 신규 detail INSERT
                row = cursor.execute("""
                    SELECT id FROM budget_items
                    WHERE parent_id=? AND detail=? AND depth=3
                    LIMIT 1
                """, (cur_parent_id, edet)).fetchone()

                if row:
                    cur_parent_id = row[0]
                else:
                    cursor.execute("""
                        INSERT INTO budget_items
                        (parent_id, depth, dept, policy, unit, detail,
                         budget_amount, budget_amount_raw, page, row_num, is_total, status)
                        VALUES (?, 3, ?, ?, ?, ?, 0, 0, '', 0, 0, '')
                    """, (cur_parent_id, ed, ep, eu, edet))
                    cur_parent_id = cursor.lastrowid

            # 4) ◎ 노드 (d=7) 신규 INSERT
            cursor.execute("""
                INSERT INTO budget_items
                (parent_id, depth, dept, policy, unit, detail, item_name, calc_name,
                 budget_amount, budget_amount_raw, page, row_num, is_total, status,
                 carryover, carryover_national, carryover_province, carryover_county,
                 carryover_special, carryover_balance, carryover_other,
                 carryover_continued, carryover_explicit, carryover_accident)
                VALUES (?, 7, ?, ?, ?, ?, ?, ?, 0, 0, '', 0, 0, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (cur_parent_id, ed, ep, eu, edet,
                  ex.get('item_name', ''), ex.get('carryover_reason', ''),
                  cotype, eco,
                  ex.get('carryover_national', 0),
                  ex.get('carryover_province', 0),
                  ex.get('carryover_county', 0),
                  ex.get('carryover_special', 0),
                  ex.get('carryover_balance', 0),
                  ex.get('carryover_other', 0),
                  eco if cotype == '계속비' else 0,
                  eco if cotype == '명시이월' else 0,
                  eco if cotype == '사고이월' else 0))
            updated_ids.append(cursor.lastrowid)
            matched += 1
            continue

        unmatched.append(ex)

    conn.commit()
    conn.close()
    return matched, unmatched, updated_ids


def main():
    if not os.path.exists(XLS):
        print(f"❌ XLS 없음: {XLS}")
        sys.exit(1)
    if not os.path.exists(DB):
        print(f"❌ DB 없음: {DB}")
        sys.exit(1)

    # 백업
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = f"{DB}.backup_carryover_{CARRYOVER_TYPE}_{ts}"
    shutil.copy2(DB, backup)
    print(f"[BACKUP] {backup}")

    # 파싱
    items = parse_xls(XLS)
    cf = sum(i['carryover'] for i in items)
    fn = sum(i['carryover_national'] for i in items)
    fp = sum(i['carryover_province'] for i in items)
    fc = sum(i['carryover_county'] for i in items)
    print(f"[PARSE] {CARRYOVER_TYPE}: {len(items)} items, sum={cf:,} (국={fn:,} 도={fp:,} 군={fc:,})")

    # 부서별 통계
    by_dept = {}
    for it in items:
        if it['carryover'] == 0:
            continue
        by_dept.setdefault(it['dept'], {'cnt': 0, 'sum': 0})
        by_dept[it['dept']]['cnt'] += 1
        by_dept[it['dept']]['sum'] += it['carryover']
    print(f"\n[DEPT] {len(by_dept)}개 부서 이월:")
    for d in sorted(by_dept.keys()):
        print(f"   {d}: {by_dept[d]['cnt']}건, {by_dept[d]['sum']:,}천원")

    # 매칭
    matched, unmatched, updated_ids = match_and_update(DB, items)
    print(f"\n{'='*60}")
    print(f"파싱: {len(items)}, 매칭: {matched}, 미매칭: {len(unmatched)}")
    print(f"업데이트: {len(set(updated_ids))} rows, 총 이월액: {cf:,}")

    if unmatched:
        print(f"\n--- 미매칭 ({len(unmatched)}) ---")
        for u in unmatched[:20]:
            print(f"  {u['dept']} | {u['detail'][:30]} | {u['item_name'][:20]} | {u['carryover']:,}")
        if len(unmatched) > 20:
            print(f"  ... 외 {len(unmatched) - 20}건")


if __name__ == '__main__':
    main()
