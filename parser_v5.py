"""
parser_v5.py — 가변 인덴트 상태 머신 파서 (민성님 v5 명세)
- CSV 스트리밍 (indent 컬럼 기반)
- stack 트림 기반 상태 머신
- 전역 fillna (last_values)
- 재원 행 → 직계 부모 finance_* 누적
- Post-processing: 군비 갭 충전
"""
import csv
import os
import re
import sys
from collections import defaultdict

# 경로
CSV_PATH = '/root/.openclaw/workspace/디렉이/project_3003/budget.csv'
DB_PATH = '/root/.openclaw/workspace/철수/project_3003/budget.db'

sys.path.insert(0, '/root/.openclaw/workspace/철수/project_3003')

from database import get_db, BudgetItem, init_db

# ── 재원 행 정규식 ──
RECON_RE = re.compile(r'^\s*(국|도|군|기|균)\s+([\d,]+)')
SOURCE_MAP = {'국': 'national', '도': 'province', '군': 'county', '기': 'other', '균': 'other'}


def parse_amount(raw: str) -> int:
    """금액 문자열 → 정수"""
    if not raw:
        return 0
    cleaned = raw.replace(',', '').replace('\n', '').strip()
    # △ 표시 → 음수 (절대값)
    if cleaned.startswith('△'):
        cleaned = cleaned[1:].strip()
        try:
            return -int(cleaned)
        except ValueError:
            return 0
    # 괄호 → 음수
    if cleaned.startswith('(') and cleaned.endswith(')'):
        cleaned = cleaned[1:-1].strip()
        try:
            return -int(cleaned) if cleaned else 0
        except ValueError:
            return 0
    try:
        return int(cleaned)
    except ValueError:
        return 0


def parse_all(db_path: str = None) -> int:
    """CSV → DB 전체 파싱"""
    if db_path is None:
        db_path = DB_PATH
    
    if os.path.exists(db_path):
        os.remove(db_path)
    init_db(db_path)
    db = get_db(db_path)
    
    # ── 전역 상태 ──
    stack: list[dict] = []       # [{id, depth}]
    last_values = ['', '', '', '', '', '', '']  # dept, policy, unit, detail, label, item, calc
    
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        next(reader)  # 헤더 스킵
        
        for row in reader:
            page = int(row[0])
            row_num = int(row[1])
            dept_raw = row[2]
            policy_raw = row[3]
            unit_raw = row[4]
            detail_raw = row[5]
            # label_raw = row[6]  # 사용 안 함
            item_raw = row[7]
            calc_raw = row[8]
            basis_raw = row[9]
            budget_raw = row[10]
            prev_raw = row[11]
            diff_raw = row[12]
            indent = int(row[13].strip())
            
            # ── 재원 행 ──
            m = RECON_RE.match(budget_raw.strip() if budget_raw else '')
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
            item_val = item_raw or last_values[5]  # last_values[4] = label (skip)
            calc_val = calc_raw or last_values[6]
            basis_val = (basis_raw or '').strip()
            
            # depth=0 (부서) 노드: 비부서 필드 fillna 금지 + last_values 초기화 (이전 부서 잔재 오염 차단)
            if indent == 0:
                policy_val = policy_raw or ''
                unit_val = unit_raw or ''
                detail_val = detail_raw or ''
                item_val = item_raw or ''
                calc_val = calc_raw or ''
                last_values[1] = last_values[2] = last_values[3] = last_values[5] = last_values[6] = ''
            
            # update last_values
            if dept_raw:
                last_values[0] = dept_raw
            if policy_raw:
                last_values[1] = policy_raw
            if unit_raw:
                last_values[2] = unit_raw
            if detail_raw:
                last_values[3] = detail_raw
            if item_raw:
                last_values[5] = item_raw
            if calc_raw:
                last_values[6] = calc_raw
            
            # ── indent → depth 매핑 (0~5) ──
            # indent: 0=dept, 1=policy, 2=unit, 3=detail, 4=label(미사용), 5=item, 6=calc
            # depth:  0=dept, 1=policy, 2=unit, 3=detail, 4=item, 5=calc
            depth = indent if indent <= 3 else indent - 1  # 5→4, 6→5
            
            # ── 상태 머신: 스택 트림 ──
            while stack and stack[-1]['depth'] >= depth:
                stack.pop()
            parent_id = stack[-1]['id'] if stack else None
            
            # ── 금액 파싱 ──
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
                item_code=item_val.strip(),
                item_name=calc_val.strip() if depth == 5 else item_val.strip(),
                calc_name=calc_val.strip(),
                budget_amount=budget_amount,
                basis=basis_val,
                page=page,
                row_num=row_num,
                is_total=0,
                # prev/diff 저장용 임시 필드
                finance_national=0,
                finance_province=0,
                finance_county=0,
                finance_other=0,
            )
            db.add(node)
            db.flush()
            
            stack.append({'id': node.id, 'depth': depth, 'dept': dept_val.strip()})
    
    # ── Post-processing: 군비 갭 충전 ──
    _fill_county_gap(db)
    
    db.commit()
    
    total_rows = db.query(BudgetItem.id).count()
    db.close()
    return total_rows


def _fill_county_gap(db) -> int:
    """budget - finance_sum 갭 → finance_county 자동 충전"""
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
