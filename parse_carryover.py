"""
parse_carryover.py — 이월 조서 → DB에 ◎이월액 가상 노드 INSERT

설계 원칙:
- 이월 조서 = 본예산에 별도 (사업명 다를 수 있음, "성립전" 등)
- 매칭은 통계목(d=6)까지만 = 본예산 트리 따라 들어가서 매칭
- ◎이월액 노드 (d=7) = 통계목의 자식으로 INSERT
  - parent_id = 매칭된 통계목 (d=6) 의 id
  - dept/policy/unit/detail = 이월 조서 값
  - calc_name = "◎이월액"
  - budget_amount = carryover (다음 연도 이월 액, col 10)
  - carryover_6종 = col 11~16
  - status = '명시이월' / '사고이월' / '계속비'
  - carryover_3종 (continued/explicit/acident) = status 기반

매칭 실패 시:
- 본예산에 통계목 자체가 없음 → dept("이월사업") 에 depth=4 단위 노드 INSERT
  - 그 밑에 ◎이월액 노드 INSERT (depth=7)
  - "이월사업" dept = 본예산 매칭 안 된 이월 모음

엑셀 컬럼 매핑 (carryover_type별 분기 — 명시/사고 vs 계속비 양식 상이):

명시이월 / 사고이월 (동일 양식):
- 0: 조직 (dept)
- 2: 정책 (policy) | 3: 단위 (unit) | 4: 세부 (detail) | 5: 통계목
- 10: 다음 연도 이월 액 (carryover 본값)
- 11~16: 국비/균특/기금/특교세/도비/군비 (재원 6종)
- 17: 이월사유 (carryover_reason)

계속비이월 (별도 양식):
- 0: 조직 | 2: 정책 | 3: 단위 | 4: 세부 | 5: 통계목
- 6: 예산계상액 | 7: 전년도이월액 | 9: 계 | 10: 지출금액 | 11: 금후지출소요액
- 12: 잔액
- 13: 다음연도 이월액 (carryover 본값)
- 14~18: 국비/균특/기금/특교세/도비 (재원 5종 — 군비 없음)
- 사유 컬럼 없음

사용법: python parse_carryover.py <이월조서.xls> [이월조서2.xls ...]
DB = ./budget.db (default)
"""
import re
import sqlite3
import sys
import xlrd
from collections import defaultdict


# ── 공통 INSERT 헬퍼 ──────────────────────────────────────────
# 27 컬럼 × 27 값 정합을 한 곳에서 보장 (복붙 INSERT 3종 통합)
_CARRYOVER_INSERT_SQL = """
    INSERT INTO budget_items
    (parent_id, depth, dept, policy, unit, detail, label, item_code,
     item_name, calc_name, basis, budget_amount, budget_amount_raw,
     page, row_num, is_total, status,
     carryover, carryover_national, carryover_province, carryover_county,
     carryover_special, carryover_balance, carryover_other,
     carryover_continued, carryover_explicit, carryover_accident)
    VALUES (?, 7, ?, ?, ?, ?, '', '',
            ?, '◎이월액', ?, ?, ?,
            ?, 0, 1, ?,
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?)
"""


def _insert_carryover_node(c, parent_id, ex, eco, carryover_type):
    """◎이월액 (d=7) 노드 INSERT — 27 컬럼 × 27 값 정합 (단일 진실 공급원).

    Args:
        c: sqlite3 cursor
        parent_id: 부모 calc (d=6) 노드 id
        ex: parse_xls() items dict (carryover, 6col, carryover_type 등 포함)
        eco: ex["carryover"] (천원 단위 이월액 본값)
        carryover_type: '명시이월' | '사고이월' | '계속비'

    Returns: INSERT된 row id
    """
    c.execute(_CARRYOVER_INSERT_SQL, (
        parent_id,
        ex["dept"], ex["policy"], ex["unit"], ex["detail"],
        ex["calc_name"],                              # item_name
        ex.get("carryover_reason", ""),               # basis
        eco,                                          # budget_amount = 이월액 (트리에 금액 표시, d=0 subtree 보정에서 d=7 제외로 중복 방지)
        eco,                                          # budget_amount_raw
        ex.get("page", ""),                           # page
        carryover_type,                               # status
        eco,                                          # carryover (= ex["carryover"])
        ex["carryover_national"], ex["carryover_province"], ex["carryover_county"],
        ex["carryover_special"], ex["carryover_balance"], ex["carryover_other"],
        eco if carryover_type == "계속비" else 0,
        eco if carryover_type == "명시이월" else 0,
        eco if carryover_type == "사고이월" else 0,
    ))
    return c.lastrowid


def ensure_carryover_columns(c):
    """carryover_continued/explicit/accident 컬럼 없으면 ALTER TABLE 추가.

    parser_v8 schema엔 3종 컬럼이 없어서 INSERT silent fail 회피.
    """
    cols = [r[1] for r in c.execute("PRAGMA table_info(budget_items)").fetchall()]
    for col in ("carryover_continued", "carryover_explicit", "carryover_accident"):
        if col not in cols:
            c.execute(f"ALTER TABLE budget_items ADD COLUMN {col} INTEGER DEFAULT 0")
            print(f"  컬럼 추가: {col}")


def norm(s):
    """공백/특수문자 정규화"""
    if s is None:
        return ""
    return str(s).strip().replace("\n", " ").replace("\r", "")


def won_to_kwon(v):
    """원 → 천원"""
    return round(v / 1000)


def safe_int(v):
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def extract_stat_calc(stat_raw):
    """통계목 "207-01\n연구용역비" → calc_name "01 연구용역비" + label_code "207" """
    if not stat_raw:
        return "", ""
    # 숫자-숫자 패턴 추출
    m = re.match(r"^(\d{3})-(\d{2})\s*(.*)", norm(stat_raw))
    if m:
        return m.group(2) + " " + m.group(3).strip(), m.group(1)
    return norm(stat_raw), ""


def parse_xls(path, carryover_type):
    """이월 조서 1개 파싱 → list of dict"""
    wb = xlrd.open_workbook(path, formatting_info=False)
    ws = wb.sheet_by_index(0)
    items = []
    current_dept = ""
    current_policy = ""
    current_unit = ""
    current_detail = ""

    for r in range(8, ws.nrows):  # r8+ = 실제 사업 (r5=헤더, r6=총계, r7=부서별소계)
        try:
            # 부서 (col 0)
            dept_cell = norm(ws.cell_value(r, 0))
            if dept_cell and "총계" not in dept_cell and "소계" not in dept_cell and not dept_cell.startswith("부서"):
                current_dept = dept_cell

            # 정책 (col 2) — 비어있으면 직전 값
            pol_cell = norm(ws.cell_value(r, 2))
            if pol_cell:
                current_policy = pol_cell

            # 단위 (col 3) — 비어있으면 직전 값
            unit_cell = norm(ws.cell_value(r, 3))
            if unit_cell:
                current_unit = unit_cell

            # 세부 (col 4) — 비어있으면 직전 값
            detail_cell = norm(ws.cell_value(r, 4))
            if detail_cell:
                current_detail = detail_cell

            # 통계목 (col 5) 비어있으면 skip
            stat_raw = norm(ws.cell_value(r, 5))
            if not stat_raw:
                continue

            # 컬럼 매핑 — 명시/사고이월 vs 계속비 양식 상이
            if carryover_type == "계속비":
                # 계속비: 이월액 col 13, 재원 col 14~18 (국/균/기/특/도, 군비 없음), 사유 없음
                carry_col = 13
                nat = won_to_kwon(safe_int(ws.cell_value(r, 14)))
                bal = won_to_kwon(safe_int(ws.cell_value(r, 15)))   # 균특
                fund = won_to_kwon(safe_int(ws.cell_value(r, 16)))  # 기금
                spec = won_to_kwon(safe_int(ws.cell_value(r, 17))) # 특교세
                prov = won_to_kwon(safe_int(ws.cell_value(r, 18)))  # 도비
                cnty = 0  # 군비 없음
                reason_col = None
            else:
                # 명시/사고: 이월액 col 10, 재원 col 11~16 (국/균/기/특/도/군), 사유 col 17
                carry_col = 10
                nat = won_to_kwon(safe_int(ws.cell_value(r, 11)))
                bal = won_to_kwon(safe_int(ws.cell_value(r, 12)))   # 균특
                fund = won_to_kwon(safe_int(ws.cell_value(r, 13)))  # 기금
                spec = won_to_kwon(safe_int(ws.cell_value(r, 14)))  # 특교세
                prov = won_to_kwon(safe_int(ws.cell_value(r, 15)))
                cnty = won_to_kwon(safe_int(ws.cell_value(r, 16)))
                reason_col = 17

            # 다음 연도 이월 액
            carry = won_to_kwon(safe_int(ws.cell_value(r, carry_col)))
            if carry == 0:
                continue

            # calc_name + label_code 추출
            calc_name, label_code = extract_stat_calc(stat_raw)

            items.append({
                "dept": current_dept,
                "policy": current_policy,
                "unit": current_unit,
                "detail": current_detail,
                "calc_name": calc_name,
                "label_code": label_code,
                "carryover": carry,
                "carryover_national": nat,
                "carryover_province": prov,
                "carryover_county": cnty,
                "carryover_special": spec,
                "carryover_balance": bal,
                "carryover_other": fund,
                "carryover_type": carryover_type,
                "carryover_reason": norm(ws.cell_value(r, reason_col)) if reason_col is not None else "",
                "page": str(r),
            })
        except Exception as e:
            print(f"  ⚠️ r{r} parse error: {e}")
            continue
    return items


def create_new_tree(c, ex, carryover_type, eco):
    """
    매칭 실패한 이월 사업 = 본예산에 신규 트리 생성
    (dept + policy + unit + detail + label + item + calc + ◎이월액)

    Returns: ◎이월액 노드의 id (성공) / None (실패)
    """
    ed = norm(ex["dept"])
    ep = norm(ex["policy"])
    eu = norm(ex["unit"])
    edet = norm(ex["detail"])
    label_code = ex.get("label_code", "").strip()
    calc_name = ex.get("calc_name", "").strip()

    if not ed:
        return None

    try:
        # dept (d=0)
        row = c.execute("SELECT id FROM budget_items WHERE depth=0 AND dept=? LIMIT 1", (ed,)).fetchone()
        if row:
            dept_id = row[0]
        else:
            c.execute("INSERT INTO budget_items (parent_id, depth, dept, policy, unit, detail, budget_amount, is_total) VALUES (NULL, 0, ?, '', '', '', 0, 1)", (ed,))
            dept_id = c.lastrowid

        # policy (d=1)
        if ep:
            row = c.execute("SELECT id FROM budget_items WHERE depth=1 AND dept=? AND policy=? LIMIT 1", (ed, ep)).fetchone()
            if row:
                pol_id = row[0]
            else:
                c.execute("INSERT INTO budget_items (parent_id, depth, dept, policy, unit, detail, budget_amount, is_total) VALUES (?, 1, ?, ?, '', '', 0, 1)", (dept_id, ed, ep))
                pol_id = c.lastrowid
        else:
            pol_id = dept_id

        # unit (d=2)
        if eu:
            row = c.execute("SELECT id FROM budget_items WHERE depth=2 AND dept=? AND policy=? AND unit=? LIMIT 1", (ed, ep, eu)).fetchone()
            if row:
                unit_id = row[0]
            else:
                c.execute("INSERT INTO budget_items (parent_id, depth, dept, policy, unit, detail, budget_amount, is_total) VALUES (?, 2, ?, ?, ?, '', 0, 1)", (pol_id, ed, ep, eu))
                unit_id = c.lastrowid
        else:
            unit_id = pol_id

        # detail (d=3)
        if edet:
            row = c.execute("SELECT id FROM budget_items WHERE depth=3 AND dept=? AND unit=? AND detail=? LIMIT 1", (ed, eu, edet)).fetchone()
            if row:
                det_id = row[0]
            else:
                c.execute("INSERT INTO budget_items (parent_id, depth, dept, policy, unit, detail, budget_amount, is_total) VALUES (?, 3, ?, ?, ?, ?, 0, 1)", (unit_id, ed, ep, eu, edet))
                det_id = c.lastrowid
        else:
            det_id = unit_id

        # label (d=4) + item (d=5) — col 5 통계목의 label_code 추출
        if label_code:
            row = c.execute("SELECT id FROM budget_items WHERE depth=4 AND dept=? AND detail=? AND label=? LIMIT 1", (ed, edet, label_code)).fetchone()
            if row:
                lbl_id = row[0]
            else:
                c.execute("INSERT INTO budget_items (parent_id, depth, dept, policy, unit, detail, label, item_code, item_name, calc_name, budget_amount, is_total) VALUES (?, 4, ?, ?, ?, ?, ?, '', '', '', 0, 1)", (det_id, ed, ep, eu, edet, label_code))
                lbl_id = c.lastrowid

            # item_name = 본예산 패턴과 일치: 편성목명(calc_name) 사용.
            item_name = calc_name or f"{label_code} (편성목)"
            row = c.execute("SELECT id FROM budget_items WHERE depth=5 AND dept=? AND detail=? AND item_code=? LIMIT 1", (ed, edet, label_code)).fetchone()
            if row:
                item_id = row[0]
            else:
                c.execute("INSERT INTO budget_items (parent_id, depth, dept, policy, unit, detail, label, item_code, item_name, calc_name, budget_amount, is_total) VALUES (?, 5, ?, ?, ?, ?, ?, ?, ?, '', 0, 1)", (lbl_id, ed, ep, eu, edet, label_code, label_code, item_name))
                item_id = c.lastrowid
        else:
            item_id = det_id

        # calc (d=6) — 통계목
        if calc_name:
            row = c.execute("SELECT id FROM budget_items WHERE depth=6 AND dept=? AND detail=? AND calc_name=? LIMIT 1", (ed, edet, calc_name)).fetchone()
            print(f"  [DBG] calc SELECT: dept={ed} detail={edet} calc_name={calc_name} → {row}")
            if row:
                calc_id = row[0]
            else:
                c.execute("INSERT INTO budget_items (parent_id, depth, dept, policy, unit, detail, label, item_code, item_name, calc_name, budget_amount, is_total) VALUES (?, 6, ?, ?, ?, ?, '', '', '', ?, 0, 1)", (item_id, ed, ep, eu, edet, calc_name))
                calc_id = c.lastrowid
                print(f"  [DBG] calc INSERT → calc_id={calc_id}")
        else:
            calc_id = item_id

        # ◎이월액 (d=7) INSERT — 공통 헬퍼 사용 (27 컬럼 × 27 값 정합)
        return _insert_carryover_node(c, calc_id, ex, eco, carryover_type)
    except Exception as e:
        print(f"  ⚠️ 신규 트리 생성 실패 ({ex['dept']} {ex['unit']} {ex['detail']}): {e}")
        return None


def create_new_tree_under(c, ex, carryover_type, eco, parent_id):
    """
    매칭된 부모 (d=2 unit 또는 d=3 detail) 의 dept/policy/unit/dept를 따르고
    그 밑에 detail/label/item/calc/◎이월액 신규 생성.

    Returns: ◎이월액 노드의 id (성공) / None (실패)
    """
    label_code = ex.get("label_code", "").strip()
    calc_name = ex.get("calc_name", "").strip()
    edet = norm(ex["detail"])

    if not parent_id:
        return None

    try:
        # parent의 depth 확인
        parent_row = c.execute(
            "SELECT depth, dept, policy, unit, detail FROM budget_items WHERE id = ?",
            (parent_id,),
        ).fetchone()
        if not parent_row:
            return None
        parent_depth, p_dept, p_policy, p_unit, p_detail = parent_row

        # 사용자 의도: 이월 조서 unit/detail 우선 (매칭된 부모의 것보다)
        # unit은 이월 조서 값 사용 (친환경농정발전기획단)
        eu = norm(ex["unit"]) or p_unit
        # policy는 매칭된 부모의 것 (괄호 포함)
        ep = p_policy
        ed = p_dept

        # d=2 unit 밑 → d=3 detail 신규 생성
        # d=3 detail 밑 → d=4 label 신규 생성
        if parent_depth == 2 and edet:
            # detail (d=3) 신규
            row = c.execute("""
                SELECT id FROM budget_items
                WHERE depth=3 AND dept=? AND unit=? AND detail=?
                LIMIT 1
            """, (ed, eu, edet)).fetchone()
            if row:
                det_id = row[0]
            else:
                c.execute("""
                    INSERT INTO budget_items
                    (parent_id, depth, dept, policy, unit, detail, budget_amount, is_total)
                    VALUES (?, 3, ?, ?, ?, ?, 0, 1)
                """, (parent_id, ed, ep, eu, edet))
                det_id = c.lastrowid
        elif parent_depth == 3:
            det_id = parent_id
        else:
            return None

        # label (d=4) + item (d=5) + calc (d=6) 신규 생성
        if label_code:
            row = c.execute("""
                SELECT id FROM budget_items
                WHERE depth=4 AND dept=? AND detail=? AND label=?
                LIMIT 1
            """, (ed, edet, label_code)).fetchone()
            if row:
                lbl_id = row[0]
            else:
                c.execute("""
                    INSERT INTO budget_items
                    (parent_id, depth, dept, policy, unit, detail, label, item_code,
                     item_name, calc_name, budget_amount, is_total)
                    VALUES (?, 4, ?, ?, ?, ?, ?, '', '', '', 0, 1)
                """, (det_id, ed, ep, eu, edet, label_code))
                lbl_id = c.lastrowid

            # item_name = 본예산 패턴과 일치: 편성목명(calc_name) 사용.
            # 예: "01 연구용역비". 기존 f"{label_code} (편성목)" 은 본예산 item_name 과 불일치.
            item_name = calc_name or f"{label_code} (편성목)"
            row = c.execute("""
                SELECT id FROM budget_items
                WHERE depth=5 AND dept=? AND detail=? AND item_code=?
                LIMIT 1
            """, (ed, edet, label_code)).fetchone()
            if row:
                item_id = row[0]
            else:
                c.execute("""
                    INSERT INTO budget_items
                    (parent_id, depth, dept, policy, unit, detail, label, item_code,
                     item_name, calc_name, budget_amount, is_total)
                    VALUES (?, 5, ?, ?, ?, ?, ?, ?, ?, '', 0, 1)
                """, (lbl_id, ed, ep, eu, edet, label_code, label_code, item_name))
                item_id = c.lastrowid
        else:
            item_id = det_id

        if calc_name:
            row = c.execute("""
                SELECT id FROM budget_items
                WHERE depth=6 AND dept=? AND detail=? AND calc_name=?
                LIMIT 1
            """, (ed, edet, calc_name)).fetchone()
            if row:
                calc_id = row[0]
            else:
                c.execute("""
                    INSERT INTO budget_items
                    (parent_id, depth, dept, policy, unit, detail, label, item_code,
                     item_name, calc_name, budget_amount, is_total)
                    VALUES (?, 6, ?, ?, ?, ?, '', '', '', ?, 0, 1)
                """, (item_id, ed, ep, eu, edet, calc_name))
                calc_id = c.lastrowid
        else:
            calc_id = item_id

        # ◎이월액 (d=7) INSERT — 공통 헬퍼 사용 (27 컬럼 × 27 값 정합)
        return _insert_carryover_node(c, calc_id, ex, eco, carryover_type)
    except Exception as e:
        print(f"  ⚠️ create_new_tree_under 실패 ({ex['dept']} {ex['unit']} {ex['detail']}): {e}")
        return None


def match_and_insert(db_path, items, carryover_type):
    """
    매칭 → ◎이월액 노드 INSERT

    Pass 1: dept+policy+unit+detail 정확 → ◎이월액 INSERT
    Pass 2: dept+policy_prefix+unit+detail 정확 → ◎이월액 INSERT
    Pass 3: 매칭 실패 → 본예산에 신규 트리 생성 (dept~◎이월액)
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 매칭 후보: dept+policy+unit+detail 까지 정확 매칭 → d=3 (세부) 가장 깊은 것
    # 그 밑에 ◎이월액 노드 INSERT
    db_rows = c.execute("""
        SELECT id, dept, policy, unit, detail, depth, parent_id
        FROM budget_items
        WHERE depth IN (3, 4, 5, 6) AND (calc_name IS NULL OR calc_name != '◎이월액')
    """).fetchall()
    print(f"  DB 매칭 후보 (d=3~6): {len(db_rows):,}개")

    # dept별로 index
    dept_index = defaultdict(list)
    for r in db_rows:
        dept_index[norm(r[1])].append(r)

    matched = 0
    unmatched = []

    # dept='' row 처리: 직전 items의 dept 기억 → 빈 dept 채우기 (todo 3 — 61건 해결)
    # 이월조서 엑셀에서 col 0이 빈 row = 같은 부서의 연속 row.
    last_dept = ""

    for ex in items:
        ed = norm(ex["dept"])
        # dept 빈 row → 직전 dept 사용
        if not ed and last_dept:
            ed = last_dept
            ex["dept"] = last_dept  # 원본 dict 갱신 (create_new_tree/_under 등에서 사용)
        if ed:
            last_dept = ed

        ep = norm(ex["policy"])
        eu = norm(ex["unit"])
        edet = norm(ex["detail"])
        ecalc = norm(ex["calc_name"])
        eco = ex["carryover"]

        if eco == 0:
            continue

        # Pass 1: dept+policy+unit+detail 정확
        cands = [
            r for r in db_rows
            if norm(r[1]) == ed and norm(r[2]) == ep
            and norm(r[3]) == eu and norm(r[4]) == edet
        ]
        if cands:
            print(f"  [DBG1] ed={ed} ep={ep} eu={eu} edet={edet} → cands={[(r[0], r[1], r[2], r[3], r[4]) for r in cands]}")
        # Pass 2
        if not cands and len(ep) >= 3:
            cands = [
                r for r in db_rows
                if norm(r[1]) == ed and (ep in norm(r[2]) or norm(r[2]).startswith(ep))
                and norm(r[3]) == eu and norm(r[4]) == edet
            ]
            if cands:
                print(f"  [DEBUG] Pass 2 매칭: → cands={[r[0] for r in cands]}")

        # Pass 2.5: 이월조서 정책 괄호 suffix 무시 — ep_stem = ep.split()[0] 매칭
        # 예: 이월조서 "혁신전략 발굴" vs 본예산 "혁신전략 발굴(산업ㆍ중소기업및에너지/산업진흥ㆍ고도화)"
        if not cands and len(ep) >= 3:
            ep_stem = ep.split()[0] if ep.split() else ep
            cands = [
                r for r in db_rows
                if norm(r[1]) == ed and norm(r[3]) == eu and norm(r[4]) == edet
                and norm(r[2]).split() and norm(r[2]).split()[0] == ep_stem
            ]
            if cands:
                print(f"  [DEBUG] Pass 2.5 stem 매칭: stem={ep_stem} → cands={[r[0] for r in cands]}")

        # Pass 3 제거 — detail substring 느슨 매칭 (Pass 5와 동일 이유)
        # Pass 4 제거 — dept+unit만 매칭 (정책/세부 무시)도 "농촌 에너지" 같은
        # 본예산에 없는 사업이 매칭되어 같은 부모에 잘못 들어감
        # Pass 1~2 정확 매칭 안 되면 create_new_tree()로 신규 트리 생성

        # Pass 5 제거 — detail substring 느슨해서 "농촌 에너지" 같은
        # 본예산에 없는 사업이 같은 부모에 잘못 매칭됨

        # Pass 6: dept+unit 정확 (unit 노드 = d=2) — 상위 매칭
        # 사용자 의도: 신규 트리는 "상위 트리 매칭된 부모" 밑에 생성
        if not cands and ed and eu:
            cands = [
                r for r in db_rows
                if norm(r[1]) == ed and norm(r[3]) == eu and r[5] == 2
            ]
        # Pass 6 fallback: dept만 (d=2) — 다 모를 때
        if not cands and ed:
            cands = [r for r in db_rows if norm(r[1]) == ed and r[5] == 2]

        if not cands:
            # 매칭 실패 (dept도 없음) → 본예산에 통째로 신규 트리 생성
            parent_id = create_new_tree(c, ex, carryover_type, eco)
            if parent_id:
                matched += 1
                continue
            else:
                unmatched.append(ex)
                continue

        # 가장 깊은 (depth 큰) 노드 = ◎이월액 노드 parent
        cands.sort(key=lambda r: -r[5])  # depth 내림차순
        parent_id = cands[0][0]
        parent_depth = cands[0][5]

        # Pass 6 매칭 (d=2 unit) 또는 dept+detail (d=3) 만 있을 때
        # = "상위 트리 매칭, 사업은 신규" → 그 밑에 신규 트리 생성
        # cands 가 [unit] 또는 [detail] 또는 둘 다일 때 (본예산 사업 일치 0~1개)
        if parent_depth in (2, 3):
            # 매칭된 부모 (unit/detail) 의 dept/policy/unit/detail 를 따르고
            # 그 밑에 detail/label/item/calc/◎이월액 신규 생성
            # cands에 본예산 사업 (d=3 또는 d=4~6) 있으면 자기 사업을 사용
            # cands에 단위(d=2)만 있으면 = 본예산에 사업 없음 → 신규 트리
            use_existing = any(r[5] >= 4 for r in cands)  # d=4~6 사업 있음
            if not use_existing:
                parent_id = create_new_tree_under(c, ex, carryover_type, eco, parent_id)
                if parent_id:
                    matched += 1
                    continue
                else:
                    unmatched.append(ex)
                    continue

        # ◎이월액 노드 INSERT — 공통 헬퍼 사용 (27 컬럼 × 27 값 정합)
        try:
            _insert_carryover_node(c, parent_id, ex, eco, carryover_type)
            matched += 1
        except Exception as e:
            unmatched.append(ex)
            print(f"  ⚠️ INSERT 실패 ({ex['dept']} {ex['unit']} {ex['calc_name']}): {e}")

    conn.commit()
    conn.close()
    return matched, unmatched


def main():
    if len(sys.argv) < 2:
        print("사용법: python parse_carryover.py <이월조서.xls> [이월조서2.xls ...]")
        print("       DB: ./budget.db (default)")
        sys.exit(1)

    DB = "budget.db"
    if sys.argv[-1].endswith(".db"):
        DB = sys.argv[-1]
        files = sys.argv[1:-1]
    else:
        files = sys.argv[1:]

    # 매핑: 파일명 → carryover_type
    type_map = {
        "명시이월": "명시이월",
        "사고이월": "사고이월",
        "계속비": "계속비",
    }

    for f in files:
        # 파일명에서 carryover_type 추출
        carryover_type = "이월사업"
        for key, val in type_map.items():
            if key in f:
                carryover_type = val
                break

        print(f"\n📋 {f}")
        print(f"   carryover_type: {carryover_type}")

        # 기존 ◎이월액 노드 중 이 type 인 것 삭제 (재실행 가능)
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        ensure_carryover_columns(c)  # schema self-healing (3종 컬럼 보장)
        n_del = c.execute("""
            DELETE FROM budget_items
            WHERE calc_name = '◎이월액' AND status = ?
        """, (carryover_type,)).rowcount
        conn.commit()
        conn.close()
        if n_del > 0:
            print(f"   기존 ◎이월액 ({carryover_type}) 노드 삭제: {n_del}개")

        # 파싱
        items = parse_xls(f, carryover_type)
        print(f"   파싱: {len(items)}건")

        if not items:
            continue

        # 매칭 + INSERT
        matched, unmatched = match_and_insert(DB, items, carryover_type)
        print(f"   매칭: {matched}, 미매칭: {len(unmatched)}")

        if unmatched:
            print(f"   --- 미매칭 ({len(unmatched)}) ---")
            for ex in unmatched[:5]:
                print(f"     {ex['dept']} | {ex['unit']} | {ex['detail']} | {ex['calc_name']} | {ex['carryover']:,}원")

    # 최종 carryover 합
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    r = c.execute("""
        SELECT status, COUNT(*), SUM(carryover)
        FROM budget_items WHERE calc_name = '◎이월액'
        GROUP BY status
    """).fetchall()
    print("\n=== ◎이월액 status 분포 ===")
    for s, cnt, amt in r:
        print(f"  {s}: {cnt}개, {amt:,}천원 ({amt/100000:.1f}억원)")

    r = c.execute("""
        SELECT depth, COUNT(*), SUM(carryover)
        FROM budget_items WHERE carryover > 0
        GROUP BY depth
    """).fetchall()
    print("\n=== carryover > 0 depth 분포 ===")
    for d, cnt, amt in r:
        print(f"  d={d}: {cnt}개, {amt:,}천원")
    conn.close()


if __name__ == "__main__":
    main()
