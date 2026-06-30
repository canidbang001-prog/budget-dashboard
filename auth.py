

def create_session_token() -> str:
    """세션 토큰 생성 (1시간짜리 서명)."""
    return _serializer.dumps({'authenticated': True})


def verify_session_token(token: str) -> bool:
    """토큰 검증. True=유효, False=만료/위조."""
    try:
        _serializer.loads(token, max_age=SESSION_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False
"""
간편 비밀번호 게이트 — 세션 쿠키 기반 인증 모듈
itsdangerous URLSafeTimedSerializer 사용
"""
import os
import secrets
import sys
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

# 환경변수 미지정 시에만 32바이트 난수 생성 (한 번 내린 후 계속 유지하지 않음)
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    # 랜덤 키를 생성해 stderr에 한 번 경고하고 사용. 프로덕션에서는 반드시 SECRET_KEY 환경변수를 설정하세요.
    SECRET_KEY = secrets.token_urlsafe(32)
    print('[auth] WARNING: SECRET_KEY 환경변수가 설정되지 않았습니다. 랜덤 키를 임시로 사용합니다.', file=sys.stderr)

DASHBOARD_PASSWORD = os.environ.get('DASHBOARD_PASSWORD', '1234!')
SESSION_MAX_AGE = int(os.environ.get('SESSION_MAX_AGE', '3600'))  # 1시간
COOKIE_NAME = os.environ.get('COOKIE_NAME', 'session_token')
# 외부 HTTPS 배포 시 True로 설정 (SameSite=None + Secure 필요)
COOKIE_SECURE = os.environ.get('COOKIE_SECURE', 'false').lower() in ('1', 'true', 'yes')
COOKIE_SAMESITE = os.environ.get('COOKIE_SAMESITE', 'lax')

_serializer = URLSafeTimedSerializer(SECRET_KEY, salt='budget_dashboard_session')
