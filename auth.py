"""
간편 비밀번호 게이트 — 세션 쿠키 기반 인증 모듈
itsdangerous URLSafeTimedSerializer 사용
"""
import os
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32).hex())
DASHBOARD_PASSWORD = os.environ.get('DASHBOARD_PASSWORD', '1234!')
SESSION_MAX_AGE = 3600  # 1시간
COOKIE_NAME = 'session_token'

_serializer = URLSafeTimedSerializer(SECRET_KEY, salt='session')


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
