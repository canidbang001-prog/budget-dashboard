#!/usr/bin/env python3
"""
홍성군 합본예산서 파서 v2.0 — Raw XML Direct Parsing
=====================================================
- openpyxl 바이패스: xlsx를 unzip하여 sharedStrings.xml + sheet*.xml 직접 파싱
- Global State Machine: 페이지 경계에서도 부모 노드가 끊기지 않도록 전역 상태 유지
- 콤마 개수(선행 빈 셀 개수)로 계층 깊이 추적
- '국, 도, 군, 기' 행은 상위 노드의 재원 속성으로 바인딩

데이터 소스: /root/.openclaw/workspace/아라/2026 전체합본예산서.xlsx
출력: SQLite DB + JSON 요약
"""

import sqlite3
import json
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

# ─── 설정 ───────────────────────────────────────────────────
XLSX_PATH = "/root/.openclaw/workspace/아라/2026 전체합본예산서.xlsx"
DB_PATH = os.path.join(os.path.dirname(__file__), "budget.db")
XML_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
UNIT = 1000  # 금액 단위: 천원 → 원

# ─── 컬럼 매핑 (A=0, B=1, C=2, D=3, E=4, F=5, G=6, H=7, I=8, J=9, K=10, L=11) ───
COL_DEPT   = 0   # A: 부서명
COL_POLICY = 1   # B: 정책사업
COL_UNIT   = 2   # C: 단위사업
COL_DETAIL = 3   # D: 세부사업
COL_LABEL  = 4   # E: (헤더 라벨용)
COL_ITEM   = 5   # F: 편성목
COL_CALC   = 6   # G: 산출내역 (계층적)
COL_BASIS  = 7   # H: 산출기초
COL_BUDGET = 8   # I: 예산액(경정액)
COL_PREV   = 9   # J: 전년도예산액(기정액)
COL_DIFF   = 10  # K: 비교증감
COL_UNIT_L = 11  # L: (단위:천원)

# 재원 접두사 패턴
FINANCE_PREFIX_RE = re.compile(r'^\s*(국|도|군|기)\s')

# 편성목 코드 패턴 (예: "201 일반운영비", "301 일반보전금")
ITEM_CODE_RE = re.compile(r'^(\d{3})\s')

# 산출내역 계층 마커
CALC_LEVEL2_RE = re.compile(r'^(\d{2})\s')       # "01 사무관리비", "02 공공운영비"
CALC_CATEGORY_RE = re.compile(r'^\s*◎')           # "  ◎일반수용비"
CALC_DETAIL_RE = re.compile(r'^\s*○')              # "    ○정책기획업무추진"


@dataclass
class BudgetNode:
    """예산 트리 노드"""
    id: int = 0
    parent_id: Optional[int] = None
    depth: int = 0
    
    # 계층 정보
    dept: str = ""          # 부서명
    policy: str = ""        # 정책사업
    unit: str = ""          # 단위사업
    detail: str = ""        # 세부사업
    item_code: str = ""     # 편성목 코드 (예: "201")
    item_name: str = ""     # 편성목명 (예: "일반운영비")
    calc_name: str = ""     # 산출내역명
    
    # 금액 정보 (단위: 원)
    budget_amount: int = 0       # 예산액
    prev_amount: int = 0         # 전년도예산액
    diff_amount: int = 0         # 비교증감
    
    # 재원 정보 (하위 노드들의 합계)
    finance_national: int = 0    # 국 (국비)
    finance_province: int = 0    # 도 (도비)
    finance_county: int = 0      # 군 (군비)
    finance_other: int = 0       # 기 (기타)
    
    # 산출기초
    basis: str = ""          # 산출기초 (H열)
    
    # 메타
    page: int = 0            # 출처 페이지 번호
    row: int = 0             # 출처 행 번호
    is_total: bool = False   # 합계 행 여부
    is_finance: bool = False # 재원 행 여부
    children_count: int = 0  # 자식 노드 수

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "dept": self.dept,
            "policy": self.policy,
            "unit": self.unit,
            "detail": self.detail,
            "item_code": self.item_code,
            "item_name": self.item_name,
            "calc_name": self.calc_name,
            "budget_amount": self.budget_amount,
            "prev_amount": self.prev_amount,
            "diff_amount": self.diff_amount,
            "finance_national": self.finance_national,
            "finance_province": self.finance_province,
            "finance_county": self.finance_county,
            "finance_other": self.finance_other,
            "basis": self.basis,
            "page": self.page,
            "row": self.row,
            "is_total": self.is_total,
            "is_finance": self.is_finance,
            "children_count": self.children_count,
        }


class GlobalStateMachine:
    """전역 상태 머신 — 페이지 경계를 넘어 부모-자식 관계를 추적"""
    
    def __init__(self):
        self.dept: str = ""
        self.policy: str = ""
        self.unit: str = ""
        self.detail: str = ""
        self.item_code: str = ""
        self.item_name: str = ""
        
        # 스택 기반 계층 추적
        self.stack: List[BudgetNode] = []
        
        # 현재 페이지의 헤더 정보
        self.page_dept: str = ""
        self.page_policy: str = ""
        self.page_unit: str = ""
        
        # 통계
        self.total_budget: int = 0
        self.node_count: int = 0
    
    def reset_page_context(self):
        """새 페이지 시작 시 페이지 컨텍스트 초기화 (전역 상태는 유지)"""
        self.page_dept = ""
        self.page_policy = ""
        self.page_unit = ""
    
    def update_from_header(self, col_values: List[str]):
        """페이지 헤더(5~7행)에서 부서/정책/단위 정보 추출"""
        a_val = col_values[COL_DEPT].strip() if len(col_values) > COL_DEPT else ""
        e_val = col_values[COL_LABEL].strip() if len(col_values) > COL_LABEL else ""
        
        if a_val == "부서:" and e_val:
            self.page_dept = e_val
            self.dept = e_val
        elif a_val == "정책:" and e_val:
            self.page_policy = e_val
            self.policy = e_val
        elif a_val == "단위:" and e_val:
            self.page_unit = e_val
            self.unit = e_val
    
    def get_filled_columns(self, col_values: List[str]) -> List[int]:
        """값이 있는 컬럼 인덱스 리스트 반환"""
        return [i for i, v in enumerate(col_values) if v.strip()]
    
    def determine_depth(self, col_values: List[str]) -> int:
        """첫 번째 비어있지 않은 컬럼의 인덱스로 깊이 결정
        
        Depth mapping:
          0 (A): 부서       → dept
          1 (B): 정책       → policy
          2 (C): 단위       → unit
          3 (D): 세부사업    → detail
          5 (F): 편성목     → item
          6 (G): 산출내역   → calc
          8 (I): 재원/금액만 → finance (이 경우 depth는 현재 스택 depth + 0 유지)
        """
        for i, v in enumerate(col_values):
            if v.strip():
                if i == COL_DEPT:    # A
                    return 0
                elif i == COL_POLICY: # B
                    return 1
                elif i == COL_UNIT:   # C
                    return 2
                elif i == COL_DETAIL: # D
                    return 3
                elif i == COL_ITEM:   # F
                    return 4
                elif i == COL_CALC:   # G
                    return 5
                elif i == COL_BUDGET: # I - 재원 행일 수 있음
                    return -1  # 특수: 재원 행
        return -2  # 빈 행


class BudgetParser:
    """합본예산서 XML 파서"""
    
    def __init__(self, xlsx_path: str):
        self.xlsx_path = xlsx_path
        self.shared_strings: List[str] = []
        self.state = GlobalStateMachine()
        self.nodes: List[BudgetNode] = []
        self.errors: List[str] = []
        
        # 노드 ID 스택 (계층별 마지막 노드 ID)
        self.level_nodes: Dict[int, int] = {}  # depth → node_id
    
    def load_shared_strings(self, zf: zipfile.ZipFile):
        """공유 문자열 테이블 로드"""
        with zf.open('xl/sharedStrings.xml') as f:
            tree = ET.parse(f)
            root = tree.getroot()
            ns = {'ns': XML_NS}
            for si in root.findall('.//ns:si', ns):
                texts = si.findall('.//ns:t', ns)
                self.shared_strings.append(''.join(t.text or '' for t in texts))
        print(f"[PARSER] Shared strings loaded: {len(self.shared_strings)}")
    
    def parse_cell_value(self, cell: ET.Element) -> str:
        """셀 값 추출 (공유 문자열 참조 해결)"""
        cell_type = cell.get('t')
        value_elem = cell.find(f'{{{XML_NS}}}v')
        if value_elem is None or value_elem.text is None:
            return ""
        
        val = value_elem.text
        if cell_type == 's':  # shared string
            try:
                idx = int(val)
                if 0 <= idx < len(self.shared_strings):
                    return self.shared_strings[idx]
            except (ValueError, IndexError):
                pass
        return val
    
    def parse_row_to_columns(self, row: ET.Element) -> List[str]:
        """행을 12개 컬럼 배열로 변환 (A~L)"""
        cols = [""] * 12
        for cell in row.findall(f'{{{XML_NS}}}c'):
            ref = cell.get('r', '')
            # 컬럼 문자 추출 (예: "A1" → "A", "AB12" → "AB")
            col_letter = ''.join(c for c in ref if c.isalpha())
            col_idx = self._col_letter_to_idx(col_letter)
            if 0 <= col_idx < 12:
                cols[col_idx] = self.parse_cell_value(cell)
        return cols
    
    @staticmethod
    def _col_letter_to_idx(letter: str) -> int:
        """A=0, B=1, ..., L=11, ... 변환"""
        result = 0
        for char in letter.upper():
            result = result * 26 + (ord(char) - ord('A') + 1)
        return result - 1
    
    def parse_amount(self, text: str) -> int:
        """금액 문자열 → 원 단위 정수 변환
        
        예: "            35,665,400 " → 35665400000 (천원 → 원)
            " 도            208,321 " → 208321000 (천원 → 원)
        """
        if not text or not text.strip():
            return 0
        
        # 재원 접두사 제거
        text = FINANCE_PREFIX_RE.sub('', text).strip()
        # 쉼표, 공백 제거
        text = text.replace(',', '').replace(' ', '').replace('\n', '')
        
        try:
            amount = int(float(text))
            return amount * UNIT  # 천원 → 원
        except ValueError:
            return 0
    
    def parse_finance_source(self, col_i: str) -> tuple:
        """재원 행에서 재원 종류와 금액 추출
        
        Returns:
            (source_type, amount_in_won)
            source_type: 'national', 'province', 'county', 'other', None
        """
        text = col_i.strip()
        if not text:
            return (None, 0)
        
        if text.startswith('국'):
            return ('national', self.parse_amount(text))
        elif text.startswith('도'):
            return ('province', self.parse_amount(text))
        elif text.startswith('군'):
            return ('county', self.parse_amount(text))
        elif text.startswith('기'):
            return ('other', self.parse_amount(text))
        return (None, 0)
    
    def is_finance_row(self, col_values: List[str]) -> bool:
        """재원 행인지 확인 (I열에만 값이 있고 국/도/군/기로 시작)"""
        i_val = col_values[COL_BUDGET].strip() if len(col_values) > COL_BUDGET else ""
        if not i_val:
            return False
        # A~H 열이 모두 비어있는지 확인
        has_hierarchy_data = any(
            col_values[i].strip() 
            for i in [COL_DEPT, COL_POLICY, COL_UNIT, COL_DETAIL, COL_ITEM, COL_CALC]
        )
        if has_hierarchy_data:
            return False
        return bool(FINANCE_PREFIX_RE.match(i_val))
    
    def is_total_row(self, col_values: List[str]) -> bool:
        """합계 행인지 확인 (A열에 부서명만 있고 I열에 금액이 있는 경우)"""
        a_val = col_values[COL_DEPT].strip()
        i_val = col_values[COL_BUDGET].strip()
        if a_val and i_val:
            # 다른 계층 컬럼이 모두 비어있는지 확인
            has_other = any(
                col_values[i].strip()
                for i in [COL_POLICY, COL_UNIT, COL_DETAIL, COL_ITEM, COL_CALC]
            )
            if not has_other:
                return True
        return False
    
    def get_parent_id(self, depth: int) -> Optional[int]:
        """현재 깊이에 대한 부모 노드 ID 찾기"""
        # depth-1 레벨의 마지막 노드를 부모로
        for d in range(depth - 1, -1, -1):
            if d in self.level_nodes:
                return self.level_nodes[d]
        return None
    
    def create_node(self, col_values: List[str], page: int, row: int) -> BudgetNode:
        """행 데이터로 BudgetNode 생성"""
        depth = self.state.determine_depth(col_values)
        
        node = BudgetNode()
        node.page = page
        node.row = row
        
        # 재원 행 처리
        if depth == -1 and self.is_finance_row(col_values):
            node.is_finance = True
            # 재원은 상위 노드 깊이를 유지
            # 스택의 마지막 노드를 부모로
            if self.state.stack:
                parent = self.state.stack[-1]
                node.depth = parent.depth
                node.parent_id = parent.id
                node.dept = parent.dept
                node.policy = parent.policy
                node.unit = parent.unit
                node.detail = parent.detail
                node.item_code = parent.item_code
                node.item_name = parent.item_name
                
                # 재원 정보 추출
                source, amount = self.parse_finance_source(col_values[COL_BUDGET])
                if source == 'national':
                    node.finance_national = amount
                elif source == 'province':
                    node.finance_province = amount
                elif source == 'county':
                    node.finance_county = amount
                elif source == 'other':
                    node.finance_other = amount
                
                node.budget_amount = amount
            return node
        
        # 합계 행 처리
        if self.is_total_row(col_values):
            node.is_total = True
            depth = 0
        
        # 계층 정보 설정
        a_val = col_values[COL_DEPT].strip()
        b_val = col_values[COL_POLICY].strip()
        c_val = col_values[COL_UNIT].strip()
        d_val = col_values[COL_DETAIL].strip()
        f_val = col_values[COL_ITEM].strip()
        g_val = col_values[COL_CALC].strip()
        h_val = col_values[COL_BASIS].strip()
        i_val = col_values[COL_BUDGET].strip()
        j_val = col_values[COL_PREV].strip()
        k_val = col_values[COL_DIFF].strip()
        
        if a_val:
            if not any([b_val, c_val, d_val, f_val]):
                # 부서 합계 행
                node.dept = a_val
                node.depth = 0
                node.is_total = True
            else:
                node.dept = a_val
                self.state.dept = a_val
                node.depth = 0
        
        if b_val:
            node.policy = b_val
            self.state.policy = b_val
            if not node.dept:
                node.dept = self.state.dept
            node.depth = max(node.depth, 1)
        
        if c_val:
            node.unit = c_val
            self.state.unit = c_val
            if not node.dept:
                node.dept = self.state.dept
            if not node.policy:
                node.policy = self.state.policy
            node.depth = max(node.depth, 2)
        
        if d_val:
            node.detail = d_val
            self.state.detail = d_val
            if not node.dept:
                node.dept = self.state.dept
            if not node.policy:
                node.policy = self.state.policy
            if not node.unit:
                node.unit = self.state.unit
            node.depth = max(node.depth, 3)
        
        if f_val:
            node.depth = max(node.depth, 4)
            match = ITEM_CODE_RE.match(f_val)
            if match:
                node.item_code = match.group(1)
                node.item_name = f_val[match.end():].strip()
                self.state.item_code = node.item_code
                self.state.item_name = node.item_name
            else:
                node.item_name = f_val
            
            if not node.dept:
                node.dept = self.state.dept
            if not node.policy:
                node.policy = self.state.policy
            if not node.unit:
                node.unit = self.state.unit
            if not node.detail:
                node.detail = self.state.detail
        
        if g_val:
            node.calc_name = g_val
            node.depth = max(node.depth, 5)
            if not node.dept:
                node.dept = self.state.dept
            if not node.policy:
                node.policy = self.state.policy
            if not node.unit:
                node.unit = self.state.unit
            if not node.detail:
                node.detail = self.state.detail
            if not node.item_code:
                node.item_code = self.state.item_code
            if not node.item_name:
                node.item_name = self.state.item_name
        
        # 금액 정보
        node.budget_amount = self.parse_amount(i_val)
        node.prev_amount = self.parse_amount(j_val)
        node.diff_amount = self.parse_amount(k_val)
        
        # 산출기초
        node.basis = h_val.strip().replace('\n', ' ')
        
        # 부모 찾기
        node.parent_id = self.get_parent_id(node.depth)
        
        # 🔧 FIX: depth=0 노드의 dept가 누락되는 버그 수정
        # 합계 행 등에서 dept가 비어있으면 Global State Machine에서 상속
        if not node.dept and self.state.dept:
            node.dept = self.state.dept
        if not node.policy and self.state.policy:
            node.policy = self.state.policy
        if not node.unit and self.state.unit:
            node.unit = self.state.unit
        if not node.detail and self.state.detail:
            node.detail = self.state.detail
        
        return node
    
    def process_sheet(self, zf: zipfile.ZipFile, sheet_file: str, page_num: int):
        """단일 시트 처리"""
        self.state.reset_page_context()
        
        with zf.open(sheet_file) as f:
            tree = ET.parse(f)
            root = tree.getroot()
            ns = {'ns': XML_NS}
            rows = root.findall('.//ns:row', ns)
            
            header_phase = True  # 첫 10행은 헤더 영역
            
            for row in rows:
                row_num = int(row.get('r', 0))
                col_values = self.parse_row_to_columns(row)
                
                # 헤더 영역 처리 (1~9행)
                if row_num <= 9:
                    self.state.update_from_header(col_values)
                    continue
                
                # 빈 행 건너뛰기
                if all(not v.strip() for v in col_values):
                    continue
                
                # 페이지 번호 표시 행 건너뛰기 (예: "- 2 -")
                a_val = col_values[COL_DEPT].strip()
                if a_val and a_val.startswith('-') and '페이지' not in a_val:
                    # 페이지 번호 표시 행일 가능성
                    non_a = [v.strip() for v in col_values[1:]]
                    if all(not v for v in non_a):
                        continue
                
                # 부서헤더 행 건너뛰기 ("부서:", "정책:", "단위:")
                if a_val in ('부서:', '정책:', '단위:'):
                    self.state.update_from_header(col_values)
                    continue
                
                # 컬럼 헤더 행 건너뛰기
                if '부서ㆍ정책ㆍ단위' in a_val:
                    continue
                
                # 노드 생성
                node = self.create_node(col_values, page_num, row_num)
                
                if node.is_finance and self.state.stack:
                    # 재원 노드는 DB에 저장하지만 스택에는 쌓지 않음
                    # 대신 부모 노드의 재원 합계에 누적
                    parent = self.state.stack[-1]
                    parent.finance_national += node.finance_national
                    parent.finance_province += node.finance_province
                    parent.finance_county += node.finance_county
                    parent.finance_other += node.finance_other
                
                # 노드 저장
                node.id = len(self.nodes) + 1
                self.nodes.append(node)
                self.state.node_count += 1
                
                if not node.is_finance:
                    # 스택 관리: 현재 depth보다 깊은 노드들을 pop
                    while self.state.stack and self.state.stack[-1].depth >= node.depth:
                        popped = self.state.stack.pop()
                        popped.children_count = sum(
                            1 for n in self.nodes if n.parent_id == popped.id
                        )
                    
                    self.state.stack.append(node)
                    self.level_nodes[node.depth] = node.id
                    
                    # 상위 계층 클리어
                    for d in list(self.level_nodes.keys()):
                        if d > node.depth:
                            del self.level_nodes[d]
    
    def parse(self):
        """메인 파싱 실행"""
        print(f"[PARSER] Opening: {self.xlsx_path}")
        
        with zipfile.ZipFile(self.xlsx_path, 'r') as zf:
            # 1. 공유 문자열 로드
            self.load_shared_strings(zf)
            
            # 2. 워크북에서 시트 목록 가져오기
            with zf.open('xl/workbook.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                ns = {'ns': XML_NS}
                sheets = root.findall('.//ns:sheet', ns)
            
            print(f"[PARSER] Total sheets: {len(sheets)}")
            
            # 3. 각 시트 처리
            for idx, sheet_elem in enumerate(sheets):
                sheet_name = sheet_elem.get('name', f'Sheet{idx+1}')
                # sheetId는 1-based, sheet 파일명은 sheet{sheetId}.xml
                sheet_id = sheet_elem.get('sheetId', str(idx + 1))
                sheet_file = f'xl/worksheets/sheet{sheet_id}.xml'
                
                page_num = idx + 1
                
                if page_num % 100 == 0:
                    print(f"[PARSER] Processing page {page_num}/{len(sheets)}...")
                
                try:
                    self.process_sheet(zf, sheet_file, page_num)
                except KeyError:
                    self.errors.append(f"Sheet file not found: {sheet_file}")
                except Exception as e:
                    self.errors.append(f"Error on {sheet_name} (file: {sheet_file}): {str(e)}")
        
        print(f"[PARSER] Parsing complete: {len(self.nodes)} nodes, {len(self.errors)} errors")
        if self.errors:
            for err in self.errors[:10]:
                print(f"  ERROR: {err}")
        
        return self.nodes
    
    def save_to_db(self, db_path: str):
        """파싱 결과를 SQLite DB에 저장"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 기존 테이블 삭제
        cursor.execute("DROP TABLE IF EXISTS budget_items")
        cursor.execute("DROP TABLE IF EXISTS finance_sources")
        cursor.execute("DROP TABLE IF EXISTS parse_meta")
        
        # 예산 항목 테이블
        cursor.execute("""
            CREATE TABLE budget_items (
                id INTEGER PRIMARY KEY,
                parent_id INTEGER,
                depth INTEGER,
                dept TEXT,
                policy TEXT,
                unit TEXT,
                detail TEXT,
                item_code TEXT,
                item_name TEXT,
                calc_name TEXT,
                budget_amount INTEGER,
                prev_amount INTEGER,
                diff_amount INTEGER,
                finance_national INTEGER DEFAULT 0,
                finance_province INTEGER DEFAULT 0,
                finance_county INTEGER DEFAULT 0,
                finance_other INTEGER DEFAULT 0,
                basis TEXT,
                page INTEGER,
                row_num INTEGER,
                is_total INTEGER DEFAULT 0,
                is_finance INTEGER DEFAULT 0,
                children_count INTEGER DEFAULT 0,
                FOREIGN KEY (parent_id) REFERENCES budget_items(id)
            )
        """)
        
        # 인덱스
        cursor.execute("CREATE INDEX idx_parent ON budget_items(parent_id)")
        cursor.execute("CREATE INDEX idx_depth ON budget_items(depth)")
        cursor.execute("CREATE INDEX idx_dept ON budget_items(dept)")
        cursor.execute("CREATE INDEX idx_page ON budget_items(page)")
        cursor.execute("CREATE INDEX idx_item_code ON budget_items(item_code)")
        
        # 데이터 삽입
        for node in self.nodes:
            cursor.execute("""
                INSERT INTO budget_items (
                    id, parent_id, depth, dept, policy, unit, detail,
                    item_code, item_name, calc_name,
                    budget_amount, prev_amount, diff_amount,
                    finance_national, finance_province, finance_county, finance_other,
                    basis, page, row_num, is_total, is_finance, children_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                node.id, node.parent_id, node.depth,
                node.dept, node.policy, node.unit, node.detail,
                node.item_code, node.item_name, node.calc_name,
                node.budget_amount, node.prev_amount, node.diff_amount,
                node.finance_national, node.finance_province, node.finance_county, node.finance_other,
                node.basis, node.page, node.row,
                1 if node.is_total else 0,
                1 if node.is_finance else 0,
                node.children_count
            ))
        
        # 메타 정보
        cursor.execute("""
            CREATE TABLE parse_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("INSERT INTO parse_meta VALUES ('total_nodes', ?)", (str(len(self.nodes)),))
        cursor.execute("INSERT INTO parse_meta VALUES ('total_pages', ?)", (str(990),))
        cursor.execute("INSERT INTO parse_meta VALUES ('errors', ?)", (json.dumps(self.errors),))
        
        # 총계 계산
        total_budget = sum(n.budget_amount for n in self.nodes if n.depth == 0 and n.is_total)
        cursor.execute("INSERT INTO parse_meta VALUES ('total_budget_summary', ?)", (str(total_budget),))
        
        conn.commit()
        conn.close()
        
        print(f"[PARSER] Saved to DB: {db_path}")
        print(f"[PARSER] Total nodes: {len(self.nodes)}")
        print(f"[PARSER] Depth-0 total budget: {total_budget:,} 원")
    
    def save_json_summary(self, output_path: str):
        """요약 JSON 저장 (트리 구조)"""
        # 부서별 요약
        dept_summary = {}
        for node in self.nodes:
            if node.depth == 0 and node.is_total and node.dept:
                dept_summary[node.dept] = {
                    "dept": node.dept,
                    "budget_amount": node.budget_amount,
                    "prev_amount": node.prev_amount,
                    "diff_amount": node.diff_amount,
                    "finance_national": node.finance_national,
                    "finance_province": node.finance_province,
                    "finance_county": node.finance_county,
                    "finance_other": node.finance_other,
                    "page": node.page,
                }
        
        summary = {
            "total_nodes": len(self.nodes),
            "total_pages": 990,
            "total_budget": sum(d["budget_amount"] for d in dept_summary.values()),
            "departments": dept_summary,
            "errors": self.errors,
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        print(f"[PARSER] JSON summary saved: {output_path}")


def main():
    parser = BudgetParser(XLSX_PATH)
    nodes = parser.parse()
    parser.save_to_db(DB_PATH)
    
    json_path = os.path.join(os.path.dirname(__file__), "summary.json")
    parser.save_json_summary(json_path)
    
    print("\n[DONE] 파싱 완료!")
    print(f"  Nodes: {len(nodes)}")
    print(f"  DB: {DB_PATH}")
    print(f"  JSON: {json_path}")


if __name__ == '__main__':
    main()
