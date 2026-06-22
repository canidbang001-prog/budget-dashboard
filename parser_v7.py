"""
parser_v7.py — 가변 인덴트 상태 머신 파서 v7 (민성님 직시)
- 모든 셀 \n → ' ' (방어 코드)
- △ 금액 → 음수 처리
- col8 분기: item6 / item_name / calc_name / stage
- 고아 강제 바인딩
"""
import csv
import os
import re
import sys

# 경로
CSV_PATH = '/root/.openclaw/workspace/디렉이/project_3003/budget.csv'
DB_PATH = '/root/.openclaw/workspace/철수/project_3003/budget.db'

sys.path.insert(0, '/root/.openclaw/workspace/철수/project_3003')
from database import get_db, BudgetItem, init_db

# ── 정규식 ──
RECON_RE = re.compile(r'^\s*(국|도|군|기|균)\s+([\d,]+)')
SOURCE_MAP = {'국': 'national', '도': 'province', '군': 'county', '기': 'other', '균': 'other'}
TRI_RE = re.compile(r'△')
AMOUNT_CLEAN = re.compile(r'[,\s원]')
CALC_PAT = re.compile(r'[\d,]+원?\s*[×*/+\-]\s*[\d,]+')
STAGE_KEYWORDS = {'본예산', '추경', '제1회 추가경정', '제2회 추가경정', '제3회 추가경정',
                  '1차 추경', '2차 추경', '3차 추경'}


def clean_cell(text: str) -> str:
    """\n → ' ', \r 제거"""
    if not text:
        return ''
    return text.replace('\n', ' ').replace('\r', '').strip()


def parse_amount(raw: str) -> int:
    """금액 문자열 → int. △ → 음수, 괄호 → 음수"""
    if not raw or not raw.strip():
        return 0
    text = clean_cell(raw)
    # △ → -
    text = TRI_RE.sub('-', text)
    # 괄호 → 음수
    if text.startswith('(') and text.endswith(')'):
        inner = text[1:-1].strip()
        # Remove commas for inner content
        inner = AMOUNT_CLEAN.sub('', inner)
        try:
            return -int(inner) if inner and inner != '-' else 0
        except ValueError:
            return 0
    # 콤마/공백/원 제거
    text = AMOUNT_CLEAN.sub('', text)
    text = text.strip()
    if text == '' or text == '-':
        return 0
    try:
        return int(text)
    except ValueError:
        return 0


def route_col8(text: str) -> dict:
    """col8(부기명/산출식) → {item6, item_name, calc_name, stage} 분기"""
    result = {'item6': '', 'item_name': '', 'calc_name': '', 'stage': ''}
    if not text:
        return result
    
    text = clean_cell(text)
    if not text:
        return result
    
    # Stage 키워드 체크
    if text in STAGE_KEYWORDS:
        result['stage'] = text
        return result
    
    # 숫자 시작 → item6 (예: "01 사무관리비")
    if text and text[0].isdigit():
        result['item6'] = text
        return result
    
    # 산출식 패턴
    m = CALC_PAT.search(text)
    if m:
        name_part = text[:m.start()].strip()
        calc_part = text[m.start():].strip()
        result['item_name'] = name_part
        result['calc_name'] = calc_part
        return result
    
    # ◎/○ 시작 → 부기명/세부명
    result['item_name'] = text
    return result


def parse_all(db_path: str = None) -> int:
    """CSV → DB 전체 파싱"""
    if db_path is None:
        db_path = DB_PATH
    
    if os.path.exists(db_path):
        os.remove(db_path)
    init_db(db_path)
    db = get_db(db_path)
    
    # ── 전역 상태 ──
    stack: list[dict] = []
    last_values = ['', '', '', '', '', '', '']  # dept, policy, unit, detail, label, item5, item6
    last_valid_parent_id = None
    
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        next(reader)  # 헤더 스킵
        
        for row in reader:
            if len(row) < 14:
                continue
            
            page = int(row[0])
            row_num = int(row[1])
            
            # 모든 셀 \n → ' ' 정리
            dept_raw = clean_cell(row[2]) if row[2] else ''
            policy_raw = clean_cell(row[3]) if row[3] else ''
            unit_raw = clean_cell(row[4]) if row[4] else ''
            detail_raw = clean_cell(row[5]) if row[5] else ''
            # label_raw = clean_cell(row[6]) if row[6] else ''  # 미사용
            item5_raw = clean_cell(row[7]) if row[7] else ''
            col8_raw = clean_cell(row[8]) if row[8] else ''
            basis_raw = clean_cell(row[9]) if row[9] else ''
            budget_raw = clean_cell(row[10]) if row[10] else ''
            prev_raw = clean_cell(row[11]) if row[11] else ''
            diff_raw = clean_cell(row[12]) if row[12] else ''
            
            try:
                indent = int(row[13].strip())
            except (ValueError, IndexError):
                continue
            
            # ── 재원 행 ──
            m = RECON_RE.match(budget_raw)
            if m:
                src = m.group(1)
                amount = int(m.group(2).replace(',', ''))
                field = SOURCE_MAP.get(src, 'other')
                if stack:
                    parent = stack[-1]
                    pi = db.query(BudgetItem).filter(BudgetItem.id == parent['id']).first()
                    if pi:
                        cur = getattr(pi, f'finance_{field}') or 0
                        setattr(pi, f'finance_{field}', cur + amount)
                        db.flush()
                continue
            
            # ── fillna: 빈 값은 last_values에서 상속 ──
            dept_val = dept_raw or last_values[0]
            policy_val = policy_raw or last_values[1]
            unit_val = unit_raw or last_values[2]
            detail_val = detail_raw or last_values[3]
            # label: skipped (last_values[4])
            item5_val = item5_raw or last_values[5]
            item6_val = ''  # will be set from col8 routing below
            
            if dept_raw:
                last_values[0] = dept_raw
            if policy_raw:
                last_values[1] = policy_raw
            if unit_raw:
                last_values[2] = unit_raw
            if detail_raw:
                last_values[3] = detail_raw
            if item5_raw:
                last_values[5] = item5_raw
            
            # ── indent → depth ──
            depth = indent if indent <= 3 else indent - 1
            
            # ── 상태 머신: 스택 트림 ──
            while stack and stack[-1]['depth'] >= depth:
                stack.pop()
            
            parent_id = stack[-1]['id'] if stack else None
            
            # ── 고아 강제 바인딩 ──
            if parent_id is None:
                if dept_raw or policy_raw or unit_raw or detail_raw or item5_raw:
                    # 유효한 값이 있고 부모가 없음 → 새 루트/부모 생성 필요
                    pass  # 정상적인 새 dept 시작
                elif last_valid_parent_id is not None:
                    parent_id = last_valid_parent_id
            
            # ── col8 라우팅 ──
            routed = route_col8(col8_raw)
            stage_val = routed['stage']
            # depth=5(calc)일 때만 col8 의미 있음
            if depth == 5 and col8_raw:
                out_item6 = routed['item6']
                out_item_name = routed['item_name']
                out_calc_name = routed['calc_name']
                if out_item6:
                    last_values[6] = out_item6
                    item6_val = out_item6
                item_name_val = out_item_name
                calc_name_val = out_calc_name
            elif depth == 4 and item5_raw:
                # depth=4: item_code = item5_raw
                item_name_val = ''
                calc_name_val = ''
            else:
                item_name_val = ''
                calc_name_val = ''
            
            # ── 금액 ──
            budget_amount = parse_amount(budget_raw)
            prev_amount = parse_amount(prev_raw)
            diff_amount = parse_amount(diff_raw)
            
            # ── 노드 생성 ──
            node = BudgetItem(
                parent_id=parent_id,
                depth=depth,
                dept=dept_val.strip(),
                policy=policy_val.strip(),
                unit=unit_val.strip(),
                detail=detail_val.strip(),
                item_code=item5_val.strip(),
                item5=item5_val.strip(),
                item6=item6_val.strip() if depth == 5 else '',
                item_name=item_name_val.strip(),
                calc_name=calc_name_val.strip(),
                stage=stage_val,
                budget_amount=budget_amount,
                finance_national=0,
                finance_province=0,
                finance_county=0,
                finance_other=0,
                basis=basis_raw.strip(),
                page=page,
                row_num=row_num,
                is_total=0,
            )
            db.add(node)
            db.flush()
            
            stack.append({'id': node.id, 'depth': depth, 'dept': dept_val.strip()})
            last_valid_parent_id = node.id
    
    # ── Post-processing: 군비 갭 충전 ──
    _fill_county_gap(db)
    
    db.commit()
    total = db.query(BudgetItem.id).count()
    db.close()
    return total


def _fill_county_gap(db) -> int:
    """budget - finance_sum → finance_county"""
    nodes = db.query(BudgetItem).all()
    updated = 0
    for node in nodes:
        fin_sum = (
            (node.finance_national or 0) +
            (node.finance_province or 0) +
            (node.finance_county or 0) +
            (node.finance_other or 0)
        )
        gap = (node.budget_amount or 0) - fin_sum
        if gap > 0:
            node.finance_county = (node.finance_county or 0) + gap
            updated += 1
    db.flush()
    return updated


if __name__ == '__main__':
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    count = parse_all(db_path)
    print(f'✅ Done: {count} rows')
