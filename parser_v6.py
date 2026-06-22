#!/usr/bin/env python3
"""
parser_v6.py — 열 인덱스 기반 상태 머신 (민성님 명세)
- CSV (XLSX 추출본)을 읽어 첫 번째 비어있지 않은 열 인덱스로 계층 판별
- 전역 상태 변수는 시트 경계에서도 절대 초기화하지 않음
- 재원 행은 last_inserted_record에 병합
- ◎/○/- 행에서 DB INSERT
"""

import csv
import re
import sqlite3
import os
import sys

# ─── 경로 ────────────────────────────────────────────────
CSV_PATH = '/root/.openclaw/workspace/디렉이/project_3003/budget.csv'
DB_PATH = sys.argv[1] if len(sys.argv) > 1 else '/root/.openclaw/workspace/디렉이/project_3003/budget.db'

# ─── 정규식 ──────────────────────────────────────────────
SKIP_PATTERNS = [
    re.compile(r'세\s*출\s*예\s*산\s*사\s*업\s*명\s*세\s*서'),
    re.compile(r'부서[:ㆍ]'),
    re.compile(r'정책[:ㆍ]'),
    re.compile(r'단위[:ㆍ]'),
    re.compile(r'부서[ㆍ]정책[ㆍ]단위'),
    re.compile(r'^\s*-\s*\d+\s*-\s*$'),  # 페이지 번호
]
FINANCE_PREFIX_RE = re.compile(r'^(국|도|군|균|기|특)\s')
NUM_START_RE = re.compile(r'^\d{2,3}\s')       # "01 사무관리비" or "201 일반운영비"
STAGE_RE = re.compile(r'^(본예산|추경|제\d+회\s*추가경정)$')
BUGI_RE = re.compile(r'^[◎○\-]')               # 부기명
AMOUNT_CLEAN_RE = re.compile(r'[,\s원]')        # 금액 정제
PAREN_AMOUNT_RE = re.compile(r'\(([\d,]+)\)')   # 괄호 금액

# ─── DB 초기화 ───────────────────────────────────────────

def init_db(db_path):
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS budget_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER,
            dept TEXT NOT NULL DEFAULT '',
            policy TEXT NOT NULL DEFAULT '',
            unit TEXT NOT NULL DEFAULT '',
            detail TEXT NOT NULL DEFAULT '',
            item5 TEXT NOT NULL DEFAULT '',
            item6 TEXT NOT NULL DEFAULT '',
            item_code TEXT NOT NULL DEFAULT '',
            item_name TEXT NOT NULL DEFAULT '',
            calc_name TEXT NOT NULL DEFAULT '',
            budget_amount INTEGER DEFAULT 0,
            basis TEXT NOT NULL DEFAULT '',
            row_num INTEGER,
            finance_national INTEGER NOT NULL DEFAULT 0,
            finance_province INTEGER NOT NULL DEFAULT 0,
            finance_county INTEGER NOT NULL DEFAULT 0,
            finance_other INTEGER NOT NULL DEFAULT 0,
            is_total INTEGER NOT NULL DEFAULT 0,
            depth INTEGER NOT NULL DEFAULT 0,
            stage TEXT NOT NULL DEFAULT '',
            page INTEGER NOT NULL DEFAULT 0
        )
    ''')
    # 인덱스
    cur.execute('CREATE INDEX IF NOT EXISTS idx_parent ON budget_items(parent_id)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_dept ON budget_items(dept)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_depth ON budget_items(depth)')
    conn.commit()
    return conn


# ─── 유틸리티 ─────────────────────────────────────────────

def should_skip(texts):
    """row의 텍스트들 중 스킵 패턴 매칭"""
    for t in texts:
        t = (t or '').strip()
        if not t:
            continue
        for pat in SKIP_PATTERNS:
            if pat.search(t):
                return True
    return False


def clean_amount(raw: str) -> int:
    """금액 문자열 → 정수 (원)"""
    if not raw:
        return 0
    raw = raw.strip()
    # 괄호 금액 → 음수
    paren = PAREN_AMOUNT_RE.search(raw)
    if paren:
        return -int(AMOUNT_CLEAN_RE.sub('', paren.group(1)))
    # 일반 금액
    cleaned = AMOUNT_CLEAN_RE.sub('', raw)
    try:
        return int(cleaned)
    except ValueError:
        return 0


def parse_finance(raw: str):
    """재원 문자열 → (재원종류, 금액) or (None, 0)"""
    m = FINANCE_PREFIX_RE.match(raw.strip())
    if not m:
        return None, 0
    prefix = m.group(1)
    amount_str = raw[m.end():].strip()
    amount = clean_amount(amount_str)
    return prefix, amount


# ─── 상태 머신 ────────────────────────────────────────────

def parse_csv(csv_path, db_conn):
    """열 인덱스 상태 머신 메인 루프"""
    cur = db_conn.cursor()
    
    # ── 전역 상태 변수 (절대 초기화 금지) ──
    current = {
        'dept': '',
        'policy': '',
        'unit': '',
        'detail': '',
        'item5': '',
        'item6': '',
        'stage': '',
    }
    
    # 레벨별 마지막 삽입 ID (parent_id 추적용)
    last_ids = {0: None, 1: None, 2: None, 3: None, 4: None, 5: None}
    last_inserted_id = None  # 가장 최근 DB insert id
    
    # 중복 삽입 방지: 같은 레벨, 같은 이름이면 스킵
    last_inserted_at_level = {}  # level → name
    
    stats = {'rows': 0, 'skipped': 0, 'inserted': 0, 'finance': 0}
    
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = next(reader, None)  # 헤더 스킵
        
        for row in reader:
            stats['rows'] += 1
            
            if len(row) < 11:
                continue
            
            # ── 민성님 명세 열 인덱스 매핑 ──
            # idx 0 → col 2 (dept)
            # idx 1 → col 3 (policy)
            # idx 2 → col 4 (unit)
            # idx 3 → col 5 (detail)
            # idx 4 → (skip, label)
            # idx 5 → col 7 (item5: "201 일반운영비")
            # idx 6 → col 8 (item6/stage/부기명)
            # idx 7 → col 9 (calc/산출식)
            # idx 8 → col 10 (budget/재원)
            
            col_dept   = (row[2] or '').strip()
            col_policy = (row[3] or '').strip()
            col_unit   = (row[4] or '').strip()
            col_detail = (row[5] or '').strip()
            # col 6 = label (skip)
            col_item5  = (row[7] or '').strip()  # "201 일반운영비"
            col_item6  = (row[8] or '').strip()  # "01 사무관리비" / "본예산" / "◎일반수용비"
            col_calc   = (row[9] or '').strip()  # 산출식
            col_budget = (row[10] or '').strip() # 금액 or 재원
            
            # ── 스킵 검사 (col_dept 기준) ──
            if should_skip([col_dept, col_policy, col_budget]):
                stats['skipped'] += 1
                continue
            
            # ── 첫 번째 비어있지 않은 열 찾기 ──
            # 검사 순서: idx 0,1,2,3,5,6,7,8
            content_cols = [
                (0, col_dept),
                (1, col_policy),
                (2, col_unit),
                (3, col_detail),
                (5, col_item5),
                (6, col_item6),
                (7, col_calc),
                (8, col_budget),
            ]
            
            first_idx = None
            first_val = None
            for idx, val in content_cols:
                if val:
                    first_idx = idx
                    first_val = val
                    break
            
            if first_idx is None:
                continue  # 완전 빈 행
            
            # ── 열 인덱스에 따른 상태 머신 분기 ──
            
            if first_idx == 0:
                # ── 부서 변경 ──
                if col_dept != current['dept']:
                    current['dept'] = col_dept
                    current['policy'] = ''
                    current['unit'] = ''
                    current['detail'] = ''
                    current['item5'] = ''
                    current['item6'] = ''
                    last_ids = {0: None, 1: None, 2: None, 3: None, 4: None, 5: None}
                    last_inserted_at_level = {}
                    # 부서 노드 INSERT
                    budget = clean_amount(col_budget)
                    cur.execute('''
                        INSERT INTO budget_items 
                        (parent_id, dept, budget_amount, depth, page)
                        VALUES (NULL, ?, ?, 0, ?)
                    ''', (current['dept'], budget, 0))
                    last_ids[0] = cur.lastrowid
                    last_inserted_id = cur.lastrowid
                    stats['inserted'] += 1
            
            elif first_idx == 1:
                # ── 정책 변경 ──
                if col_policy != current['policy']:
                    current['policy'] = col_policy
                    current['unit'] = ''
                    current['detail'] = ''
                    current['item5'] = ''
                    current['item6'] = ''
                    for k in range(2, 6):
                        last_ids[k] = None
                    budget = clean_amount(col_budget)
                    cur.execute('''
                        INSERT INTO budget_items 
                        (parent_id, dept, policy, budget_amount, depth, page)
                        VALUES (?, ?, ?, ?, 1, ?)
                    ''', (last_ids[0], current['dept'], current['policy'], budget, 0))
                    last_ids[1] = cur.lastrowid
                    last_inserted_id = cur.lastrowid
                    stats['inserted'] += 1
            
            elif first_idx == 2:
                # ── 단위사업 변경 ──
                if col_unit != current['unit']:
                    current['unit'] = col_unit
                    current['detail'] = ''
                    current['item5'] = ''
                    current['item6'] = ''
                    for k in range(3, 6):
                        last_ids[k] = None
                    budget = clean_amount(col_budget)
                    cur.execute('''
                        INSERT INTO budget_items 
                        (parent_id, dept, policy, unit, budget_amount, depth, page)
                        VALUES (?, ?, ?, ?, ?, 2, ?)
                    ''', (last_ids[1], current['dept'], current['policy'], current['unit'], budget, 0))
                    last_ids[2] = cur.lastrowid
                    last_inserted_id = cur.lastrowid
                    stats['inserted'] += 1
            
            elif first_idx == 3:
                # ── 세부사업 변경 ──
                if col_detail != current['detail']:
                    current['detail'] = col_detail
                    current['item5'] = ''
                    current['item6'] = ''
                    for k in range(4, 6):
                        last_ids[k] = None
                    budget = clean_amount(col_budget)
                    cur.execute('''
                        INSERT INTO budget_items 
                        (parent_id, dept, policy, unit, detail, budget_amount, depth, page)
                        VALUES (?, ?, ?, ?, ?, ?, 3, ?)
                    ''', (last_ids[2], current['dept'], current['policy'], current['unit'],
                          current['detail'], budget, 0))
                    last_ids[3] = cur.lastrowid
                    last_inserted_id = cur.lastrowid
                    stats['inserted'] += 1
            
            elif first_idx == 5:
                # ── 편성목 (item5): "201 일반운영비" ──
                if col_item5 != current['item5']:
                    current['item5'] = col_item5
                    current['item6'] = ''
                    last_ids[5] = None
                    budget = clean_amount(col_budget)
                    cur.execute('''
                        INSERT INTO budget_items 
                        (parent_id, dept, policy, unit, detail, item5, budget_amount, depth, page)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 4, ?)
                    ''', (last_ids[3], current['dept'], current['policy'], current['unit'],
                          current['detail'], current['item5'], budget, 0))
                    last_ids[4] = cur.lastrowid
                    last_inserted_id = cur.lastrowid
                    stats['inserted'] += 1
            
            elif first_idx == 6:
                # ── item6 분류 (숫자시작/본예산추경/부기명) ──
                if STAGE_RE.match(col_item6):
                    # case (b): 예산구분
                    current['stage'] = col_item6
                    # stage 행 자체는 별도 INSERT 없음 (컨텍스트만 업데이트)
                    
                elif NUM_START_RE.match(col_item6):
                    # case (a): 통계목 → "01 사무관리비"
                    if col_item6 != current['item6']:
                        current['item6'] = col_item6
                        budget = clean_amount(col_budget)
                        cur.execute('''
                            INSERT INTO budget_items 
                            (parent_id, dept, policy, unit, detail, item5, item6,
                             budget_amount, depth, stage, page)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 5, ?, ?)
                        ''', (last_ids[4], current['dept'], current['policy'],
                              current['unit'], current['detail'], current['item5'],
                              current['item6'], budget, current['stage'], 0))
                        last_ids[5] = cur.lastrowid
                        last_inserted_id = cur.lastrowid
                        stats['inserted'] += 1
                        
                elif BUGI_RE.match(col_item6):
                    # case (c): 부기명 (◎, ○, -) → DB INSERT!
                    budget = clean_amount(col_budget)
                    cur.execute('''
                        INSERT INTO budget_items 
                        (parent_id, dept, policy, unit, detail, item5, item6,
                         item_name, calc_name, budget_amount, depth, stage, page)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 5, ?, ?)
                    ''', (last_ids[5], current['dept'], current['policy'],
                          current['unit'], current['detail'], current['item5'],
                          current['item6'],
                          col_item6,        # 부기명 (◎일반수용비)
                          col_calc,         # 산출식
                          budget,
                          current['stage'], 0))
                    last_inserted_id = cur.lastrowid
                    stats['inserted'] += 1
                    
                else:
                    # 그 외 → item6으로 간주
                    if col_item6 != current['item6']:
                        current['item6'] = col_item6
                        budget = clean_amount(col_budget)
                        cur.execute('''
                            INSERT INTO budget_items 
                            (parent_id, dept, policy, unit, detail, item5, item6,
                             budget_amount, depth, stage, page)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 5, ?, ?)
                        ''', (last_ids[4], current['dept'], current['policy'],
                              current['unit'], current['detail'], current['item5'],
                              current['item6'], budget, current['stage'], 0))
                        last_ids[5] = cur.lastrowid
                        last_inserted_id = cur.lastrowid
                        stats['inserted'] += 1
            
            elif first_idx == 7:
                # calc만 있는 행 → 부기명으로 처리
                budget = clean_amount(col_budget)
                cur.execute('''
                    INSERT INTO budget_items 
                    (parent_id, dept, policy, unit, detail, item5, item6,
                     item_name, calc_name, budget_amount, depth, stage, page)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 5, ?, ?)
                ''', (last_ids[5], current['dept'], current['policy'],
                      current['unit'], current['detail'], current['item5'],
                      current['item6'],
                      '', col_calc, budget,
                      current['stage'], 0))
                last_inserted_id = cur.lastrowid
                stats['inserted'] += 1
            
            elif first_idx == 8:
                # ── 재원 처리 (index 8) ──
                prefix, amount = parse_finance(col_budget)
                if prefix and last_inserted_id:
                    # last_inserted_record의 재원 정보 업데이트
                    finance_field = {
                        '국': 'finance_national',
                        '도': 'finance_province',
                        '군': 'finance_county',
                    }.get(prefix, 'finance_other')
                    cur.execute(f'''
                        UPDATE budget_items 
                        SET {finance_field} = {finance_field} + ?
                        WHERE id = ?
                    ''', (amount, last_inserted_id))
                    stats['finance'] += 1
                elif not prefix:
                    # 재원이 아닌 순수 예산 → 부기명이 없는 단독 예산 행으로 INSERT
                    budget = clean_amount(col_budget)
                    if budget > 0:
                        cur.execute('''
                            INSERT INTO budget_items 
                            (parent_id, dept, policy, unit, detail, item5, item6,
                             budget_amount, depth, stage, page)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 5, ?, ?)
                        ''', (last_ids[5], current['dept'], current['policy'],
                              current['unit'], current['detail'], current['item5'],
                              current['item6'], budget, current['stage'], 0))
                        last_inserted_id = cur.lastrowid
                        stats['inserted'] += 1
            
            # 1000행마다 커밋
            if stats['rows'] % 1000 == 0:
                db_conn.commit()
    
    db_conn.commit()
    return stats


# ─── 검증 ─────────────────────────────────────────────────

def validate(db_path, stats):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    total_nodes = cur.execute('SELECT COUNT(*) FROM budget_items').fetchone()[0]
    total_budget = cur.execute('SELECT SUM(budget_amount) FROM budget_items WHERE depth=0').fetchone()[0] or 0
    dept_count = cur.execute('SELECT COUNT(DISTINCT dept) FROM budget_items WHERE dept != ""').fetchone()[0]
    orphans = cur.execute('''
        SELECT COUNT(*) FROM budget_items b 
        WHERE b.parent_id IS NOT NULL 
        AND NOT EXISTS (SELECT 1 FROM budget_items p WHERE p.id = b.parent_id)
    ''').fetchone()[0]
    empty_dept = cur.execute('SELECT COUNT(*) FROM budget_items WHERE depth=0 AND dept=""').fetchone()[0]
    
    # depth 분포
    depth_dist = {}
    for r in cur.execute('SELECT depth, COUNT(*) FROM budget_items GROUP BY depth ORDER BY depth'):
        depth_dist[r[0]] = r[1]
    
    # 재원 총합
    finance = cur.execute('''
        SELECT SUM(finance_national), SUM(finance_province), 
               SUM(finance_county), SUM(finance_other) 
        FROM budget_items
    ''').fetchone()
    
    conn.close()
    
    print(f"\n{'='*60}")
    print(f"📊 검증 결과")
    print(f"{'='*60}")
    print(f"  총 노드:\t{total_nodes:,}")
    print(f"  부서 수:\t{dept_count}")
    print(f"  고아 노드:\t{orphans} {'✅' if orphans == 0 else '❌'}")
    print(f"  빈 dept:\t{empty_dept} {'✅' if empty_dept == 0 else '❌'}")
    print(f"  Depth 분포: {depth_dist}")
    print(f"  총 예산:\t{total_budget:,}원 ({total_budget//10000:,}만원)")
    print(f"  재원 국:\t{finance[0] or 0:,}")
    print(f"  재원 도:\t{finance[1] or 0:,}")
    print(f"  재원 군:\t{finance[2] or 0:,}")
    print(f"  재원 기타:\t{finance[3] or 0:,}")
    print(f"  재원 총합:\t{sum(f or 0 for f in finance):,}")


# ─── 메인 ─────────────────────────────────────────────────

def main():
    print(f"{'='*60}")
    print(f"📋 parser_v6.py — 열 인덱스 기반 상태 머신")
    print(f"{'='*60}")
    print(f"  CSV: {CSV_PATH}")
    print(f"  DB:  {DB_PATH}")
    
    conn = init_db(DB_PATH)
    
    try:
        stats = parse_csv(CSV_PATH, conn)
        print(f"\n  처리 행:\t{stats['rows']:,}")
        print(f"  스킵:\t{stats['skipped']:,}")
        print(f"  INSERT:\t{stats['inserted']:,}")
        print(f"  재원 UPDATE:\t{stats['finance']:,}")
        
        validate(DB_PATH, stats)
        
        db_size = os.path.getsize(DB_PATH) / 1024 / 1024
        print(f"\n  DB 크기: {db_size:.2f}MB")
        print(f"🏁 완료")
        
    finally:
        conn.close()


if __name__ == '__main__':
    main()
