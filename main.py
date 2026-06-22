#!/usr/bin/env python3
"""
FastAPI 백엔드 — 예산 대시보드 (Port 3003)
"""
import os
import sqlite3
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.requests import Request
from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "budget.db"
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = BASE_DIR / "templates"

app = FastAPI(title="홍성군 합본예산서 대시보드", version="2.0")

# 정적 파일 & 템플릿
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 직접 Jinja2 Environment 사용 (Starlette Templates 캐시 버그 회피)
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))

def render_template(name: str, context: dict) -> HTMLResponse:
    template = jinja_env.get_template(name)
    return HTMLResponse(template.render(**context))


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ─── API Endpoints ──────────────────────────────────────────

@app.get("/api/summary")
def api_summary():
    """전체 요약 정보"""
    conn = get_db()
    cur = conn.cursor()
    
    # 부서별 합계
    cur.execute("""
        SELECT dept, budget_amount, prev_amount, diff_amount,
               finance_national, finance_province, finance_county, finance_other, page
        FROM budget_items
        WHERE depth = 0 AND is_total = 1 AND dept != ''
        ORDER BY budget_amount DESC
    """)
    departments = [dict(row) for row in cur.fetchall()]
    
    total_budget = sum(d['budget_amount'] for d in departments)
    
    # 메타 정보
    cur.execute("SELECT value FROM parse_meta WHERE key='total_nodes'")
    total_nodes = int(cur.fetchone()['value'])
    
    conn.close()
    
    return {
        "total_budget": total_budget,
        "total_nodes": total_nodes,
        "department_count": len(departments),
        "departments": departments,
    }


@app.get("/api/departments")
def api_departments():
    """부서 목록"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT dept FROM budget_items
        WHERE depth = 0 AND is_total = 1 AND dept != ''
        ORDER BY budget_amount DESC
    """)
    # We need the budget too
    cur.execute("""
        SELECT dept, budget_amount FROM budget_items
        WHERE depth = 0 AND is_total = 1 AND dept != ''
        ORDER BY budget_amount DESC
    """)
    departments = [dict(row) for row in cur.fetchall()]
    conn.close()
    return departments


@app.get("/api/tree")
def api_tree(
    dept: Optional[str] = Query(None, description="부서명 필터"),
    parent_id: Optional[int] = Query(None, description="부모 노드 ID"),
    depth: Optional[int] = Query(None, description="깊이"),
    limit: int = Query(500, ge=1, le=5000),
):
    """트리 구조 데이터 조회"""
    conn = get_db()
    cur = conn.cursor()
    
    conditions = ["is_finance = 0"]  # 재원 행 제외
    params = []
    
    if dept:
        conditions.append("dept = ?")
        params.append(dept)
    
    if parent_id is not None:
        conditions.append("parent_id = ?")
        params.append(parent_id)
    
    if depth is not None:
        conditions.append("depth = ?")
        params.append(depth)
    
    where = " AND ".join(conditions)
    
    cur.execute(f"""
        SELECT id, parent_id, depth, dept, policy, unit, detail,
               item_code, item_name, calc_name,
               budget_amount, prev_amount, diff_amount,
               finance_national, finance_province, finance_county, finance_other,
               basis, page, row_num, is_total, children_count
        FROM budget_items
        WHERE {where}
        ORDER BY id
        LIMIT ?
    """, params + [limit])
    
    nodes = [dict(row) for row in cur.fetchall()]
    
    # 자식 존재 여부 확인
    node_ids = [n['id'] for n in nodes]
    if node_ids:
        placeholders = ','.join('?' * len(node_ids))
        cur.execute(f"""
            SELECT parent_id, COUNT(*) as cnt
            FROM budget_items
            WHERE parent_id IN ({placeholders}) AND is_finance = 0
            GROUP BY parent_id
        """, node_ids)
        child_counts = {row['parent_id']: row['cnt'] for row in cur.fetchall()}
        
        for node in nodes:
            node['has_children'] = child_counts.get(node['id'], 0) > 0
            node['child_count'] = child_counts.get(node['id'], 0)
    
    conn.close()
    return nodes


@app.get("/api/finance/{node_id}")
def api_finance(node_id: int):
    """특정 노드의 재원 정보 조회"""
    conn = get_db()
    cur = conn.cursor()
    
    # 해당 노드의 재원 합계
    cur.execute("""
        SELECT finance_national, finance_province, finance_county, finance_other
        FROM budget_items WHERE id = ?
    """, (node_id,))
    row = cur.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="Node not found")
    
    finance = dict(row)
    
    # 재원 상세 내역 (해당 노드 직계 자식 중 재원 노드)
    cur.execute("""
        SELECT id, budget_amount,
               CASE 
                   WHEN finance_national > 0 THEN '국비'
                   WHEN finance_province > 0 THEN '도비'
                   WHEN finance_county > 0 THEN '군비'
                   WHEN finance_other > 0 THEN '기타'
               END as source_type
        FROM budget_items
        WHERE parent_id = ? AND is_finance = 1
    """, (node_id,))
    details = [dict(row) for row in cur.fetchall()]
    
    conn.close()
    
    return {
        "node_id": node_id,
        "finance": finance,
        "details": details,
    }


@app.get("/api/search")
def api_search(
    q: str = Query(..., min_length=1, description="검색어"),
    limit: int = Query(100, ge=1, le=1000),
):
    """키워드 검색"""
    conn = get_db()
    cur = conn.cursor()
    
    like = f"%{q}%"
    cur.execute("""
        SELECT id, depth, dept, policy, unit, detail, item_name, calc_name,
               budget_amount, page
        FROM budget_items
        WHERE is_finance = 0 AND (
            dept LIKE ? OR policy LIKE ? OR unit LIKE ? OR
            detail LIKE ? OR item_name LIKE ? OR calc_name LIKE ? OR
            item_code LIKE ?
        )
        ORDER BY budget_amount DESC
        LIMIT ?
    """, (like, like, like, like, like, like, like, limit))
    
    results = [dict(row) for row in cur.fetchall()]
    conn.close()
    return results


@app.get("/api/stats")
def api_stats():
    """통계 정보"""
    conn = get_db()
    cur = conn.cursor()
    
    stats = {}
    
    # 총계
    cur.execute("""
        SELECT SUM(budget_amount) FROM budget_items 
        WHERE depth = 0 AND is_total = 1 AND dept != ''
    """)
    stats['total_budget'] = cur.fetchone()[0] or 0
    
    # 노드 수
    cur.execute("SELECT COUNT(*) FROM budget_items WHERE is_finance = 0")
    stats['total_nodes'] = cur.fetchone()[0]
    
    # 재원 행 수
    cur.execute("SELECT COUNT(*) FROM budget_items WHERE is_finance = 1")
    stats['finance_rows'] = cur.fetchone()[0]
    
    # 부서 수
    cur.execute("""
        SELECT COUNT(DISTINCT dept) FROM budget_items
        WHERE depth = 0 AND is_total = 1 AND dept != ''
    """)
    stats['department_count'] = cur.fetchone()[0]
    
    # 편성목별 합계
    cur.execute("""
        SELECT item_code, item_name, COUNT(*) as cnt, SUM(budget_amount) as total
        FROM budget_items
        WHERE depth = 5 AND item_code != '' AND is_finance = 0
        GROUP BY item_code, item_name
        ORDER BY total DESC
        LIMIT 20
    """)
    stats['top_items'] = [dict(row) for row in cur.fetchall()]
    
    conn.close()
    return stats


# ─── 페이지 라우트 ──────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def page_home(request: Request):
    """메인 대시보드"""
    return render_template("dashboard.html", {"request": request})


@app.get("/department/{dept_name:path}", response_class=HTMLResponse)
def page_department(request: Request, dept_name: str):
    """부서별 상세 페이지"""
    return render_template("department.html", {
        "request": request,
        "dept_name": dept_name,
    })


@app.get("/search", response_class=HTMLResponse)
def page_search(request: Request, q: str = ""):
    """검색 페이지"""
    return render_template("search.html", {
        "request": request,
        "query": q,
    })


# ─── 헬스체크 ───────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "db": str(DB_PATH)}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3003, log_level="info")
