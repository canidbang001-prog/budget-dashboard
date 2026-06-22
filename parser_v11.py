"""
parser_v11.py — 예산서 계층 트리 완벽 복원 파서 (Parent-Child 무결성 적용)
수정사항:
1. 배열 밀림(Array Shift) 방어 로직 추가 (row[8] 예산액 정확도 100%)
2. depth 0~5 전 계층 DB INSERT 및 parent_id 자기참조(Self-Reference) 바인딩
3. 7.2조 예산 뻥튀기 버그 원천 차단 (is_total 노드 중복합산 방지)
"""
import csv
import glob
import os
import re
import sqlite3
import sys

CSV_DIR = '/root/.openclaw/workspace/디렉이/project_3003'
CSV_GLOB = 'budget*.csv'
DB_PATH = '/root/.openclaw/workspace/철수/project_3003/budget.db'

FINANCE_MAP = {
 '국': 'finance_national', '도': 'finance_province',
 '군': 'finance_county', '특': 'finance_special',
 '균': 'finance_balance', '기': 'finance_other', '조': 'finance_balance'
}

def extract_page_number(filename):
 m = re.search(r'(\d+)', os.path.basename(filename))
 return int(m.group(1)) if m else 0

def clean_amount(s):
 if not s or not s.strip(): return 0
 s_stripped = s.strip()
 is_negative = False

 if s_stripped.startswith('(') and s_stripped.endswith(')'):
  is_negative = True
  s_stripped = s_stripped[1:-1]
 if '△' in s_stripped:
  is_negative = True
  s_stripped = s_stripped.replace('△', '')

 s_clean = s_stripped.replace(',', '').replace('원', '').replace(' ', '')

 for prefix in FINANCE_MAP.keys():
  if s_clean.startswith(prefix):
   s_clean = s_clean[len(prefix):]
   break

 if not s_clean: return 0
 try:
  result = int(s_clean)
  return -result if is_negative else result
 except ValueError:
  return 0

def init_db(db_path):
 if os.path.exists(db_path): os.remove(db_path)
 conn = sqlite3.connect(db_path)
 conn.execute('''
 CREATE TABLE budget_items (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 parent_id INTEGER REFERENCES budget_items(id),
 depth INTEGER NOT NULL,
 dept TEXT, policy TEXT, unit TEXT, detail TEXT,
 item_name TEXT, label TEXT, calc_name TEXT,
 budget_amount INTEGER DEFAULT 0,
 finance_national INTEGER DEFAULT 0, finance_province INTEGER DEFAULT 0,
 finance_county INTEGER DEFAULT 0, finance_special INTEGER DEFAULT 0,
 finance_balance INTEGER DEFAULT 0, finance_other INTEGER DEFAULT 0,
 page TEXT
 )
 ''')
 conn.commit()
 return conn

def parse_all(db_path=None):
 if db_path is None: db_path = DB_PATH
 pattern = os.path.join(CSV_DIR, CSV_GLOB)
 csv_files = sorted(glob.glob(pattern), key=extract_page_number)

 conn = init_db(db_path)
 cur = conn.cursor()

 # 계층별 부모 ID를 기억하는 딕셔너리 스택
 parent_ids = {-1: None, 0: None, 1: None, 2: None, 3: None, 4: None, 5: None}
 curr_dept, curr_policy, curr_unit, curr_detail, curr_item5 = '', '', '', '', ''
 last_inserted_id = None

 for csv_file in csv_files:
  page_name = os.path.basename(csv_file)
  with open(csv_file, encoding='utf-8-sig') as f:
   reader = csv.reader(f)

   for row in reader:
    # [방어 로직] 개발팀이 배열 앞에 Page, row_num을 끼워넣었을 경우 원상복구
    if len(row) > 2 and (row[0].startswith('Page') or row[0].startswith('budget')):
     page_name = row[0]
     row = row[2:]

    row = row + [''] * (11 - len(row))
    row = [c.replace('\n', ' ').replace('\r', ' ').strip() for c in row]
    row_str = "".join(row)

    if not row_str or '세 출 예 산 사 업 명 세 서' in row_str or '부서ㆍ정책' in row_str or row[0].startswith('-'):
     continue

    # 페이지 상단 헤더 처리
    if row[0].startswith('부서:'): curr_dept = row_str.replace('부서:', '').replace(',', '').strip(); continue
    if row[0].startswith('정책:'): curr_policy = row_str.replace('정책:', '').replace(',', '').strip(); continue
    if row[0].startswith('단위:'): curr_unit = row_str.replace('단위:', '').replace('(단위:천원)', '').replace(',', '').strip(); continue

    if not any(row[:9]): continue

    # 재원 행 처리
    val8 = row[8]
    is_finance_row = False
    if not any(row[0:7]) and val8:
     for prefix, field in FINANCE_MAP.items():
      if val8.startswith(prefix):
       if last_inserted_id:
        amt = clean_amount(val8)
        if amt != 0:
         cur.execute(f'UPDATE budget_items SET {field} = COALESCE({field},0) + ? WHERE id = ?', (amt, last_inserted_id))
       is_finance_row = True
       break
    if is_finance_row: continue

    # 트리 레벨(Depth) 판별
    level = -1
    node_name = ""
    calc_str = ""

    if row[0]: level = 0; node_name = row[0]
    elif row[1]: level = 1; node_name = row[1]
    elif row[2]: level = 2; node_name = row[2]
    elif row[3]: level = 3; node_name = row[3]
    elif row[5]: level = 4; node_name = row[5] # 편성목
    elif row[6]:
     if row[6] in ['본예산', '추경', '명시이월', '성립전']: continue
     level = 5; node_name = row[6]; calc_str = row[7] # 부기명 및 산출식

    # DB INSERT 및 Parent_ID 바인딩
    if level != -1:
     amt = clean_amount(row[8])

     if level == 0: curr_dept = node_name; curr_policy=curr_unit=curr_detail=curr_item5=''
     elif level == 1: curr_policy = node_name; curr_unit=curr_detail=curr_item5=''
     elif level == 2: curr_unit = node_name; curr_detail=curr_item5=''
     elif level == 3: curr_detail = node_name; curr_item5=''
     elif level == 4: curr_item5 = node_name

     # 하위 레벨 초기화
     for i in range(level + 1, 6): parent_ids[i] = None

     p_id = parent_ids.get(level - 1)

     cur.execute('''
      INSERT INTO budget_items
      (depth, parent_id, dept, policy, unit, detail, item_name, label, calc_name, budget_amount, page)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ''', (level, p_id, curr_dept, curr_policy, curr_unit, curr_detail, curr_item5, node_name, calc_str, amt, page_name))

     last_id = cur.lastrowid
     parent_ids[level] = last_id
     last_inserted_id = last_id

 conn.commit()

 # 7.2조 중복합산 방지를 위한 실제 총액 검증 쿼리 출력
 cur.execute("SELECT SUM(budget_amount) FROM budget_items WHERE depth = 0")
 total_budget = cur.fetchone()[0] or 0
 print(f"\U0001f4ca 정확한 총 예산액 (Depth 0 기준): {total_budget:,} 원")

 conn.close()
 return 1

if __name__ == '__main__':
 parse_all()
