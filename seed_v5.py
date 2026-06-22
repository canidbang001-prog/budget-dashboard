"""
seed_v5.py — parser_v8 호출 → budget.db 생성
"""
import sys
sys.path.insert(0, '/root/.openclaw/workspace/디렉이/project_3003')

from parser_v8 import parse_all

if __name__ == '__main__':
    count = parse_all()
    print(f'seed_v5: {count} rows written to budget.db')
