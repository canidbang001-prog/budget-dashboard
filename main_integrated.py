"""
FastAPI 통합 서버 — 합본예산서 API + 인증 게이트 + 정적 파일 (Port 3003)
"""
import os
import sys
from http.cookies import SimpleCookie
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.types import ASGIApp, Scope, Receive, Send
from sqlalchemy import func
from database import get_db, BudgetItem
from models import (
    BudgetItemOut, TreeItem, SummaryOut, SummaryDept,
    StatsOut, SearchResult, TreeResponse, HealthOut,
)
from auth import create_session_token, verify_session_token, DASHBOARD_PASSWORD, COOKIE_NAME, SESSION_MAX_AGE

DB_PATH = os.path.join(os.path.dirname(__file__), 'budget.db')

app = FastAPI(
    title='합본예산서 API',
    description='2026년도 전체 합본예산서 데이터 조회 API v14',
    version='1.1.0',
)

# ── 인증 미들웨어 ──────────────────────────────────────────────

AUTH_WHITELIST = {
    '/login', '/api/auth/login', '/health', '/docs', '/openapi.json',
    '/favicon.ico',
}
AUTH_WHITELIST_PREFIXES = ('/static/', '/_next/',)

class AuthMiddleware:
    """순수 ASGI 미들웨어 — BaseHTTPMiddleware StaticFiles 충돌 방지"""
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # 화이트리스트 경로는 인증 우회
        if path in AUTH_WHITELIST or path.startswith(AUTH_WHITELIST_PREFIXES):
            await self.app(scope, receive, send)
            return

        # 쿠키 파싱 (ASGI headers → SimpleCookie)
        headers = dict(scope.get("headers", []))
        cookie_header = headers.get(b"cookie", b"").decode("latin-1", errors="ignore")
        cookies = SimpleCookie()
        cookies.load(cookie_header)
        token = cookies.get(COOKIE_NAME)
        token_val = token.value if token else None

        if token_val and verify_session_token(token_val):
            await self.app(scope, receive, send)
            return

        # 비로그인 → /login 리다이렉트 (Raw ASGI)
        await send({
            "type": "http.response.start",
            "status": 302,
            "headers": [
                (b"location", b"/login"),
                (b"content-length", b"0"),
            ],
        })
        await send({"type": "http.response.body", "body": b""})

app.add_middleware(AuthMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 인증 라우트 ────────────────────────────────────────────────

LOGIN_HTML = """\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>합본예산서 대시보드 · 로그인</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       background:#f0f2f5;display:flex;align-items:center;justify-content:center;
       min-height:100vh}
  .card{background:#fff;border-radius:12px;padding:40px 36px;width:360px;
        box-shadow:0 2px 12px rgba(0,0,0,.08)}
  h2{text-align:center;color:#1a365d;margin-bottom:8px;font-size:20px}
  p.sub{text-align:center;color:#718096;font-size:13px;margin-bottom:28px}
  label{display:block;font-size:13px;color:#4a5568;margin-bottom:6px;font-weight:600}
  input[type=password]{width:100%;padding:10px 12px;border:1px solid #e2e8f0;
    border-radius:8px;font-size:15px;outline:none;transition:border .2s}
  input[type=password]:focus{border-color:#4299e1;box-shadow:0 0 0 3px rgba(66,153,225,.15)}
  button{width:100%;padding:12px;background:#2b6cb0;color:#fff;border:none;
    border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;margin-top:20px;
    transition:background .15s}
  button:hover{background:#2c5282}
  .error{color:#e53e3e;font-size:13px;text-align:center;margin-top:14px;display:none}
  .error.show{display:block}
</style>
</head>
<body>
<div class="card">
  <h2>🏛 합본예산서 대시보드</h2>
  <p class="sub">비밀번호를 입력하여 접속하세요</p>
  <form id="loginForm" method="post" action="/api/auth/login">
    <label for="password">비밀번호</label>
    <input type="password" id="password" name="password" placeholder="비밀번호 입력" autofocus required>
    <button type="submit">로그인</button>
    <p class="error" id="errorMsg"></p>
  </form>
</div>
<script>
const form = document.getElementById('loginForm');
const errorEl = document.getElementById('errorMsg');
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  errorEl.classList.remove('show');
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({password: document.getElementById('password').value}),
  });
  const data = await res.json();
  if (res.ok) { window.location.href = '/'; }
  else { errorEl.textContent = data.message || '오류가 발생했습니다'; errorEl.classList.add('show'); }
});
</script>
</body>
</html>"""



def _patch_tree_marks(tree_items):
    """d=6에 ◎, d=7에 ○ 접두사 붙이기 (◎이월액 제외)"""
    for ti in tree_items:
        if ti.calc_name and ti.calc_name != '◎이월액':
            if ti.depth == 6 and not ti.calc_name.startswith('◎'):
                ti.calc_name = '◎' + ti.calc_name
            elif ti.depth == 7 and not ti.calc_name.startswith('○'):
                ti.calc_name = '○' + ti.calc_name
    return tree_items

@app.get('/login', response_class=HTMLResponse, include_in_schema=False)
def login_page():
    return HTMLResponse(content=LOGIN_HTML)


@app.post('/api/auth/login', include_in_schema=False)
async def api_auth_login(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {'status': 'error', 'message': '잘못된 요청입니다'},
            status_code=400,
        )
    password = body.get('password', '')
    if password != DASHBOARD_PASSWORD:
        return JSONResponse(
            {'status': 'error', 'message': '비밀번호가 일치하지 않습니다'},
            status_code=401,
        )
    token = create_session_token()
    resp = JSONResponse({'status': 'ok'})
    resp.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=False,
        samesite='lax',
        path='/',
    )
    return resp


# ── API 라우트 ──────────────────────────────────────────────────

@app.get('/health', response_model=HealthOut)
def health():
    db_size = 0.0
    if os.path.exists(DB_PATH):
        db_size = os.path.getsize(DB_PATH) / (1024 * 1024)
    return HealthOut(status='ok', db_path=DB_PATH, db_size_mb=round(db_size, 2))


@app.get('/api/summary', response_model=SummaryOut)
def api_summary():
    db = get_db(DB_PATH)
    try:
        total_nodes = db.query(func.count(BudgetItem.id)).scalar() or 0
        # carryover 합계: ◎이월액 노드들의 carryover_explicit/accident/continued 만 사용
        # (사업 d=3 의 6col 은 0 reset — 이중 카운트 회피, source of truth 는 ◎이월액 노드)
        total_carryover = db.query(func.coalesce(
            func.sum(
                BudgetItem.carryover_explicit
                + BudgetItem.carryover_continued
                + BudgetItem.carryover_accident
            ), 0
        )).filter(
            BudgetItem.calc_name == '◎이월액',
        ).scalar() or 0
        dept_rows = db.query(
            BudgetItem.dept,
            func.sum(BudgetItem.budget_amount).label('total_budget'),
            func.sum(BudgetItem.budget_original).label('budget_original'),
            func.sum(BudgetItem.budget_modified).label('budget_modified'),
            func.sum(BudgetItem.finance_national).label('finance_national'),
            func.sum(BudgetItem.finance_province).label('finance_province'),
            func.sum(BudgetItem.finance_county).label('finance_county'),
            func.sum(BudgetItem.finance_special).label('finance_special'),
            func.sum(BudgetItem.finance_balance).label('finance_balance'),
            func.sum(BudgetItem.finance_other).label('finance_other'),
        ).filter(BudgetItem.depth == 0).group_by(BudgetItem.dept).order_by(
            func.min(BudgetItem.id)
        ).all()

        departments = []
        grand_total = 0
        for d in dept_rows:
            policy_count = db.query(func.count(func.distinct(BudgetItem.policy))).filter(
                BudgetItem.dept == d.dept, BudgetItem.depth == 1, BudgetItem.policy != ''
            ).scalar() or 0
            unit_count = db.query(func.count(func.distinct(BudgetItem.unit))).filter(
                BudgetItem.dept == d.dept, BudgetItem.depth == 2, BudgetItem.unit != ''
            ).scalar() or 0
            # carryover 집계는 ◎이월액 노드들의 carryover_explicit/accident/continued 만 사용
            # (사업 d=3 의 6col 은 0 reset — source of truth 는 ◎이월액 노드)
            co_agg = db.query(
                func.coalesce(func.sum(BudgetItem.carryover_explicit), 0),
                func.coalesce(func.sum(BudgetItem.carryover_continued), 0),
                func.coalesce(func.sum(BudgetItem.carryover_accident), 0),
                func.coalesce(func.sum(BudgetItem.carryover_national), 0),
                func.coalesce(func.sum(BudgetItem.carryover_province), 0),
                func.coalesce(func.sum(BudgetItem.carryover_county), 0),
                func.coalesce(func.sum(BudgetItem.carryover_special), 0),
                func.coalesce(func.sum(BudgetItem.carryover_balance), 0),
                func.coalesce(func.sum(BudgetItem.carryover_other), 0),
            ).filter(
                BudgetItem.dept == d.dept,
                BudgetItem.calc_name == '◎이월액',
            ).first()

            dept_co_total = (co_agg[0] or 0) + (co_agg[1] or 0) + (co_agg[2] or 0)

            departments.append(SummaryDept(
                dept=d.dept, total_budget=d.total_budget or 0,
                budget_original=d.budget_original or 0,
                budget_modified=d.budget_modified or 0,
                carryover=dept_co_total,
                carryover_national=co_agg[0],
                carryover_province=co_agg[1],
                carryover_county=co_agg[2],
                carryover_special=co_agg[3],
                carryover_balance=co_agg[4],
                carryover_other=co_agg[5],
                finance_national=d.finance_national or 0,
                finance_province=d.finance_province or 0,
                finance_county=d.finance_county or 0,
                finance_special=d.finance_special or 0,
                finance_balance=d.finance_balance or 0,
                finance_other=d.finance_other or 0,
                policy_count=policy_count, unit_count=unit_count,
            ))
            grand_total += d.total_budget or 0

        return SummaryOut(
            total_budget=grand_total, dept_count=len(departments),
            total_carryover=total_carryover, total_combined=total_carryover + grand_total,
            department_count=len(departments), total_nodes=total_nodes,
            departments=departments,
        )
    finally:
        db.close()


def _patch_dept_carryover(db, tree_items: list[TreeItem]):
    """For every node, aggregate carryover from its entire subtree.

    carryover 단일 컬럼은 의미 모호 (raw 또는 중복) → 6컬럼(천원) 합으로 통일.
    carryover_continued/explicit/accident 도 동일하게.
    """
    cache = {}
    for ti in tree_items:
        if ti.id in cache:
            co = cache[ti.id]
        else:
            # RECURSIVE CTE: all descendants of ti.id
            # carryover 합계 = ◎이월액 노드들의 carryover_explicit/continued/accident 만 사용
            # (사업 d=3 의 6col carryover_county 는 명시이월 row 1건과 매칭되지만, 같은 값이 ◎이월액 d=6 에도 박혀있어 이중 카운트 회피)
            from sqlalchemy import text
            sql = text('''
                WITH RECURSIVE subtree(id) AS (
                    SELECT :root
                    UNION ALL
                    SELECT b.id FROM budget_items b JOIN subtree s ON b.parent_id = s.id
                )
                SELECT
                    COALESCE(SUM(
                        CASE WHEN b.calc_name='◎이월액' THEN
                            COALESCE(b.carryover_national, 0)
                            + COALESCE(b.carryover_province, 0)
                            + COALESCE(b.carryover_county, 0)
                            + COALESCE(b.carryover_special, 0)
                            + COALESCE(b.carryover_balance, 0)
                            + COALESCE(b.carryover_other, 0)
                            + COALESCE(b.carryover_explicit, 0)
                            + COALESCE(b.carryover_continued, 0)
                            + COALESCE(b.carryover_accident, 0)
                          ELSE 0 END
                    ), 0) AS total_carryover,
                    COALESCE(SUM(CASE WHEN b.calc_name='◎이월액' THEN b.carryover_national ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN b.calc_name='◎이월액' THEN b.carryover_province ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN b.calc_name='◎이월액' THEN b.carryover_county ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN b.calc_name='◎이월액' THEN b.carryover_special ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN b.calc_name='◎이월액' THEN b.carryover_balance ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN b.calc_name='◎이월액' THEN b.carryover_other ELSE 0 END), 0),
                    COALESCE(SUM(b.carryover_continued), 0),
                    COALESCE(SUM(b.carryover_explicit), 0),
                    COALESCE(SUM(b.carryover_accident), 0)
                FROM budget_items b
                WHERE b.id IN (SELECT id FROM subtree)
            ''')
            row = db.execute(sql, {'root': ti.id}).fetchone()
            cache[ti.id] = row
            co = row
        ti.carryover = co[0]
        ti.carryover_national = co[1]
        ti.carryover_province = co[2]
        ti.carryover_county = co[3]
        ti.carryover_special = co[4]
        ti.carryover_balance = co[5]
        ti.carryover_other = co[6]
        ti.carryover_continued = co[7]
        ti.carryover_explicit = co[8]
        ti.carryover_accident = co[9]


@app.get('/api/tree', response_model=TreeResponse)
def api_tree(
    dept: str = Query(None), parent_id: int = Query(None),
    depth: int = Query(None), limit: int = Query(200),
):
    db = get_db(DB_PATH)
    try:
        q = db.query(BudgetItem)
        if dept: q = q.filter(BudgetItem.dept == dept)
        if parent_id is not None: q = q.filter(BudgetItem.parent_id == parent_id)
        if depth is not None: q = q.filter(BudgetItem.depth == depth)
        if parent_id is None and depth is None: q = q.filter(BudgetItem.depth == 0)
        q = q.order_by(BudgetItem.id).limit(limit)
        items = q.all()
        tree_items = [TreeItem.model_validate(i) for i in items]
        tree_items = _patch_tree_marks(tree_items)
        # Patch depth-0 carryover from department-wide aggregation
        _patch_dept_carryover(db, tree_items)
        return TreeResponse(
            items=tree_items,
            total=len(tree_items),
        )
    finally:
        db.close()


@app.get('/api/tree/children/{item_id}', response_model=TreeResponse)
def api_tree_children(item_id: int, limit: int = Query(200)):
    db = get_db(DB_PATH)
    try:
        children = db.query(BudgetItem).filter(
            BudgetItem.parent_id == item_id
        ).order_by(BudgetItem.id).limit(limit).all()
        tree_items = [TreeItem.model_validate(c) for c in children]
        tree_items = _patch_tree_marks(tree_items)
        # Patch depth-0 carryover from department-wide aggregation
        _patch_dept_carryover(db, tree_items)
        return TreeResponse(
            items=tree_items,
            total=len(tree_items),
        )
    finally:
        db.close()


@app.get('/api/search', response_model=SearchResult)
def api_search(q: str = Query(...), limit: int = Query(200)):
    db = get_db(DB_PATH)
    try:
        pattern = f'%{q}%'
        items = db.query(BudgetItem).filter(
            (BudgetItem.dept.like(pattern)) | (BudgetItem.policy.like(pattern)) |
            (BudgetItem.unit.like(pattern)) | (BudgetItem.detail.like(pattern)) |
            (BudgetItem.item_name.like(pattern)) | (BudgetItem.label.like(pattern)) |
            (BudgetItem.calc_name.like(pattern))
        ).order_by(BudgetItem.dept, BudgetItem.id).limit(limit).all()
        total = db.query(func.count(BudgetItem.id)).filter(
            (BudgetItem.dept.like(pattern)) | (BudgetItem.policy.like(pattern)) |
            (BudgetItem.unit.like(pattern)) | (BudgetItem.detail.like(pattern)) |
            (BudgetItem.item_name.like(pattern)) | (BudgetItem.label.like(pattern)) |
            (BudgetItem.calc_name.like(pattern))
        ).scalar() or 0
        return SearchResult(
            items=[BudgetItemOut.model_validate(i) for i in items],
            total_found=total,
        )
    finally:
        db.close()


@app.get('/api/stats', response_model=StatsOut)
def api_stats():
    db = get_db(DB_PATH)
    try:
        return StatsOut(
            total_rows=db.query(func.count(BudgetItem.id)).scalar() or 0,
            total_dept=db.query(func.count(func.distinct(BudgetItem.dept))).filter(BudgetItem.dept != '').scalar() or 0,
            total_policy=db.query(func.count(func.distinct(BudgetItem.policy))).filter(BudgetItem.policy != '').scalar() or 0,
            total_unit=db.query(func.count(func.distinct(BudgetItem.unit))).filter(BudgetItem.unit != '').scalar() or 0,
            total_detail=db.query(func.count(func.distinct(BudgetItem.detail))).filter(BudgetItem.detail != '').scalar() or 0,
            total_item_name=db.query(func.count(func.distinct(BudgetItem.item_name))).filter(BudgetItem.item_name != '').scalar() or 0,
            total_label=db.query(func.count(func.distinct(BudgetItem.label))).filter(BudgetItem.label != '').scalar() or 0,
            total_budget=db.query(func.sum(BudgetItem.budget_amount)).scalar() or 0,
            finance_national=db.query(func.sum(BudgetItem.finance_national)).scalar() or 0,
            finance_province=db.query(func.sum(BudgetItem.finance_province)).scalar() or 0,
            finance_county=db.query(func.sum(BudgetItem.finance_county)).scalar() or 0,
            finance_special=db.query(func.sum(BudgetItem.finance_special)).scalar() or 0,
            finance_balance=db.query(func.sum(BudgetItem.finance_balance)).scalar() or 0,
            finance_other=db.query(func.sum(BudgetItem.finance_other)).scalar() or 0,
        )
    finally:
        db.close()


@app.get('/api/item/{item_id}', response_model=BudgetItemOut)
def api_item(item_id: int):
    db = get_db(DB_PATH)
    try:
        item = db.query(BudgetItem).filter(BudgetItem.id == item_id).first()
        if not item: raise HTTPException(status_code=404, detail='Item not found')
        return BudgetItemOut.model_validate(item)
    finally:
        db.close()


# ── 정적 파일 (Next.js 대시보드) ─────────────────────────────────

static_dir = os.path.join(os.path.dirname(__file__), 'frontend', 'out')
if os.path.isdir(static_dir):
    app.mount('/', StaticFiles(directory=static_dir, html=True), name='frontend')

if __name__ == '__main__':
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3003
    uvicorn.run(app, host='0.0.0.0', port=port)
