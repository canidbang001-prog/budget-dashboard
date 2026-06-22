"""
parser_v13.py — 통계목 메모리 + Level 6 산출내역 DB화
민성님 지시 수정사항:
1. extract_page_number: 'Page <숫자>' 패턴 정확 타겟팅
2. row[6] 처리:
   - 쓰레기(본예산/추경) → continue
   - 통계목(숫자시작) → curr_item6 기억만 하고 DB 미삽입
   - 진짜 산출내역(◎/○ 등) → level=6, DB INSERT (item_name=통계목)
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
    # 'Page ' 뒤에 나오는 숫자만 정확히 타겟팅해서 추출
    m = re.search(r'Page\s*(\d+)', os.path.basename(filename))
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

 parent_ids = {-1: None, 0: None, 1: None, 2: None, 3: None, 4: None, 5: None}
 curr_dept, curr_policy, curr_unit, curr_detail, curr_item5, curr_item6 = '', '', '', '', '', ''
 last_inserted_id = None
 page_name = ''

 for csv_file in csv_files:
  page_name = os.path.basename(csv_file)

  with open(csv_file, encoding='utf-8-sig') as f:
   reader = csv.reader(f)

   for row in reader:
    # 🚨 [V12 철벽 방어 로직: 배열 밀림 원상복구] 🚨
    if len(row) > 2:
     first_col_str = str(row[0]).strip().lower()
     # 헤더 행 스킵
     if first_col_str == 'page' or first_col_str == 'budget':
      continue
     # row[0]이 순수 '숫자'이거나, 'page', 'budget' 문자가 포함되어 있다면!
     if first_col_str.isdigit() or 'page' in first_col_str or 'budget' in first_col_str:
      page_name = str(row[0])
      row = row[2:] # 앞 2칸(page, row_num) 무조건 삭제하여 인덱스 복구

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

    # 📌 복구된 정상 인덱스로 계층(Depth) 추적
    level = -1
    node_name = ""
    calc_str = ""

    if row[0]: level = 0; node_name = row[0]
    elif row[1]: level = 1; node_name = row[1]
    elif row[2]: level = 2; node_name = row[2]
    elif row[3]: level = 3; node_name = row[3]
    elif row[5]: level = 4; node_name = row[5]
    elif row[6]:
                val6 = row[6]
                # 1. 쓰레기 데이터(본예산, 추경 등)는 가차없이 버림
                if '본예산' in val6 or '추경' in val6 or '명시이월' in val6 or '성립전' in val6:
                    continue

                # 2. 통계목 ('01 사무관리비' 처럼 숫자로 시작하는 경우) -> DB에 넣지 말고 부모 상태로 기억만 함
                if val6.split()[0].isdigit() and len(val6.split()[0]) <= 3:
                    curr_item6 = val6
                    continue

                # 3. 진짜 예산 산출내역 (◎, ○ 등으로 시작) -> 여기서부터 DB에 INSERT (depth=5 유지)
                level = 5
                node_name = val6
                calc_str = row[7]

    # DB INSERT
    if level != -1:
     amt = clean_amount(row[8]) # 배열 복구 → row[8]은 100% 예산액!

     if level == 0: curr_dept = node_name; curr_policy=curr_unit=curr_detail=curr_item5=curr_item6=''
     elif level == 1: curr_policy = node_name; curr_unit=curr_detail=curr_item5=curr_item6=''
     elif level == 2: curr_unit = node_name; curr_detail=curr_item5=curr_item6=''
     elif level == 3: curr_detail = node_name; curr_item5=curr_item6=''
     elif level == 4: curr_item5 = node_name; curr_item6=''
     elif level == 5: curr_item6 = node_name

     for i in range(level + 1, 6): parent_ids[i] = None

     p_id = parent_ids.get(level - 1)

     item_name_val = curr_item6 if level == 5 else curr_item5

     cur.execute('''
      INSERT INTO budget_items
      (depth, parent_id, dept, policy, unit, detail, item_name, label, calc_name, budget_amount, page)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
     ''', (level, p_id, curr_dept, curr_policy, curr_unit, curr_detail, item_name_val, node_name, calc_str, amt, page_name))

     last_id = cur.lastrowid
     parent_ids[level] = last_id
     last_inserted_id = last_id

 conn.commit()

 # 🔧 군비 갭 충전: budget > finance_sum → 차액을 finance_county로 충전
 print(f'   군비 갭 충전 처리 중...')
 cur.execute('''
  UPDATE budget_items
  SET finance_county = finance_county + (
   budget_amount - COALESCE(finance_national,0) - COALESCE(finance_province,0)
   - COALESCE(finance_county,0) - COALESCE(finance_special,0)
   - COALESCE(finance_balance,0) - COALESCE(finance_other,0)
  )
  WHERE budget_amount > (
   COALESCE(finance_national,0) + COALESCE(finance_province,0) + COALESCE(finance_county,0)
   + COALESCE(finance_special,0) + COALESCE(finance_balance,0) + COALESCE(finance_other,0)
  )
  AND budget_amount > 0
 ''')
 gap_count = cur.rowcount
 conn.commit()

 # ── 재원 검증 ──
 cur.execute('''
  SELECT COUNT(*) FROM budget_items WHERE depth=0
  AND budget_amount = (COALESCE(finance_national,0)+COALESCE(finance_province,0)+COALESCE(finance_county,0)+COALESCE(finance_special,0)+COALESCE(finance_balance,0)+COALESCE(finance_other,0))
 ''')
 perfect = cur.fetchone()[0]
 cur.execute('SELECT COUNT(DISTINCT dept) FROM budget_items WHERE dept!="" AND depth=0')
 total_depts = cur.fetchone()[0]
 print(f'   재원 일치: {perfect}/{total_depts}')

 cur.execute("SELECT SUM(budget_amount) FROM budget_items WHERE depth = 0")
 total_budget = cur.fetchone()[0] or 0
 print(f"\U0001f4ca 정확한 총 예산액 (Depth 0 기준): {total_budget:,} 원")

 conn.close()
 return 1

if __name__ == '__main__':
 parse_all()
