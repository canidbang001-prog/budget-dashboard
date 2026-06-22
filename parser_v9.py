"""
parser_v9.py — 예산서 계층 트리 완벽 복원 파서 (오류 수정판)
수정사항:
1. row[1] 캐스팅 자폭 에러 원천 제거 (인덱스 구조 전면 재배치)
2. 페이지 상단 헤더(부서/정책/단위) 상태 머신 상속 완벽 구현
3. 상위 노드 변경 시 하위 노드 Downward Reset 적용
4. 재원(국,도,군 등) 금액 완벽 분리 및 부모 노드 바인딩
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
 '국': 'finance_national',
 '도': 'finance_province',
 '군': 'finance_county',
 '특': 'finance_special',
 '균': 'finance_balance',
 '기': 'finance_other',
 '조': 'finance_balance',
}

def extract_page_number(filename):
 m = re.search(r'(\d+)', os.path.basename(filename))
 return int(m.group(1)) if m else 0

def clean_amount(s):
 """금액 클렌징: 쉼표, 원, 공백, △, 괄호 제거 후 int 반환"""
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

 # 국, 도, 군 등 재원 글자가 붙어있으면 제거
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
 depth INTEGER NOT NULL,
 dept TEXT, policy TEXT, unit TEXT, detail TEXT,
 item_code TEXT, item_name TEXT, calc_name TEXT, basis TEXT,
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

 # 전역 상태 변수 (페이지가 넘어가도 유지됨)
 curr_dept, curr_policy, curr_unit, curr_detail = '', '', '', ''
 curr_item5, curr_item6 = '', ''
 last_row_id = None
 inserted_count = 0

 for csv_file in csv_files:
  page_name = os.path.basename(csv_file)
  with open(csv_file, encoding='utf-8-sig') as f:
   reader = csv.reader(f)

   for row_idx, row in enumerate(reader):
    # 11개 컬럼 미만이면 빈칸으로 채움
    row = row + [''] * (11 - len(row))
    row = [c.replace('\n', ' ').replace('\r', ' ').strip() for c in row]
    row_str = "".join(row)

    # 1. 불필요한 행 스킵
    if '세 출 예 산 사 업 명 세 서' in row_str or '부서ㆍ정책' in row_str or '- ' in row[0]:
     continue

    # 2. 페이지 상단 헤더 처리 (Context 유지)
    if row[0].startswith('부서:'):
     curr_dept = row_str.replace('부서:', '').replace(',', '').strip()
     continue
    if row[0].startswith('정책:'):
     curr_policy = row_str.replace('정책:', '').replace(',', '').strip()
     continue
    if row[0].startswith('단위:'):
     curr_unit = row_str.replace('단위:', '').replace('(단위:천원)', '').replace(',', '').strip()
     continue

    # 데이터가 비어있으면 스킵
    if not any(row[:9]):
     continue

    # 3. 재원 처리 (독립된 행으로 '도', '군' 등이 나온 경우)
    val8 = row[8].strip()
    is_finance_row = False
    if not any(row[0:7]) and val8:
     for prefix, field in FINANCE_MAP.items():
      if val8.startswith(prefix):
       if last_row_id:
        amt = clean_amount(val8)
        cur.execute(f'UPDATE budget_items SET {field} = COALESCE({field},0) + ? WHERE id = ?', (amt, last_row_id))
       is_finance_row = True
       break
    if is_finance_row:
     continue

    # 4. 계층 추적 (인덱스 기반 하향식 초기화)
    # row[0]: 부서, row[1]: 정책, row[2]: 단위, row[3]: 세부사업
    # row[5]: 편성목, row[6]: 통계목/부기명, row[7]: 산출식, row[8]: 예산액
    if row[0]:
     curr_dept = row[0]
     curr_policy, curr_unit, curr_detail, curr_item5, curr_item6 = '', '', '', '', ''
    elif row[1]:
     curr_policy = row[1]
     curr_unit, curr_detail, curr_item5, curr_item6 = '', '', '', ''
    elif row[2]:
     curr_unit = row[2]
     curr_detail, curr_item5, curr_item6 = '', '', ''
    elif row[3]:
     curr_detail = row[3]
     curr_item5, curr_item6 = '', ''
    elif row[5]:
     curr_item5 = row[5]
     curr_item6 = ''

    if row[6]:
     val6 = row[6]
     if val6.split()[0].isdigit(): # 통계목 (예: 01 사무관리비)
      curr_item6 = val6
     elif val6 in ['본예산', '추경', '명시이월']:
      continue
     else: # 실제 부기명 (◎, ○ 등) -> DB 저장 트리거
      calc_name = row[7]
      amt = clean_amount(row[8])

      cur.execute('''
       INSERT INTO budget_items
       (depth, dept, policy, unit, detail, item_code, item_name, calc_name, budget_amount, page)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ''', (6, curr_dept, curr_policy, curr_unit, curr_detail, curr_item5, val6, calc_name, amt, page_name))

      last_row_id = cur.lastrowid
      inserted_count += 1

 conn.commit()
 conn.close()
 return inserted_count

if __name__ == '__main__':
 db_path = sys.argv[1] if len(sys.argv) > 1 else None
 count = parse_all(db_path)
 print(f'✅ 성공적으로 파싱 완료: {count}건의 예산 항목이 DB에 적재되었습니다.')
