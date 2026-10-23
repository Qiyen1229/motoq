import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AppUser, AuthSession, SecurityEvent, utcnow
from app.services.settings import get_global

COOKIE_NAME = "motoq_session"
_hasher = PasswordHasher()
_login_failures: dict[str, deque[float]] = defaultdict(deque)
_register_attempts: dict[str, deque[float]] = defaultdict(deque)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(hashed: str, password: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def log_event(
    db: Session, kind: str, request: Request | None, *, success: bool = True,
    username: str = "", user_id: int | None = None, detail: str = "",
) -> None:
    db.add(
        SecurityEvent(
            kind=kind, success=success, username=username[:64], user_id=user_id,
            ip=client_ip(request) if request else "", detail=detail[:255],
            user_agent=(request.headers.get("user-agent", "") if request else "")[:255],
        )
    )
    db.commit()


def create_session(db: Session, user: AppUser, request: Request) -> tuple[str, int]:
    cfg = get_global(db)
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=_digest(token), user_id=user.id,
            expires_at=utcnow() + timedelta(days=cfg["session_days"]),
            ip=client_ip(request), user_agent=request.headers.get("user-agent", "")[:255],
            last_seen_at=utcnow(),
        )
    )
    user.last_login_at = utcnow()
    db.commit()
    return token, cfg["session_days"]


def revoke_session(db: Session, token: str) -> None:
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == _digest(token)))
    if row:
        db.delete(row)
        db.commit()


def revoke_user_sessions(db: Session, user_id: int, except_token: str | None = None) -> None:
    keep = _digest(except_token) if except_token else None
    for row in db.scalars(select(AuthSession).where(AuthSession.user_id == user_id)):
        if row.token_hash != keep:
            db.delete(row)
    db.commit()


def purge_expired_sessions(db: Session) -> None:
    for row in db.scalars(select(AuthSession).where(AuthSession.expires_at < utcnow())):
        db.delete(row)
    db.commit()


def _window(store: dict[str, deque[float]], key: str, seconds: int) -> deque[float]:
    window = store[key]
    now = time.monotonic()
    while window and now - window[0] > seconds:
        window.popleft()
    return window


def check_login_limit(request: Request, db: Session) -> str:
    cfg = get_global(db)
    key = client_ip(request)
    if len(_window(_login_failures, key, cfg["login_window_seconds"])) >= cfg["login_max_failures"]:
        raise HTTPException(429, "登入失敗次數過多，請稍後再試")
    return key


def record_login_failure(key: str) -> None:
    _login_failures[key].append(time.monotonic())


def clear_login_failures(key: str) -> None:
    _login_failures.pop(key, None)


def check_register_limit(request: Request, max_per_hour: int = 10) -> None:
    key = client_ip(request)
    window = _window(_register_attempts, key, 3600)
    if len(window) >= max_per_hour:
        raise HTTPException(429, "註冊嘗試過於頻繁，請稍後再試")
    window.append(time.monotonic())


def reset_limiters() -> None:
    _login_failures.clear()
    _register_attempts.clear()


def require_user(
    motoq_session: str | None = Cookie(default=None), db: Session = Depends(get_db)
) -> AppUser:
    if not motoq_session:
        raise HTTPException(401, "未登入")
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == _digest(motoq_session)))
    now = utcnow()
    if not row or row.expires_at < now:
        raise HTTPException(401, "登入已過期")
    user = db.get(AppUser, row.user_id)
    if not user or user.status != "active":
        raise HTTPException(401, "帳號無法使用")
    if not row.last_seen_at or (now - row.last_seen_at).total_seconds() > 300:
        row.last_seen_at = now
        db.commit()
    return user


def require_admin(user: AppUser = Depends(require_user)) -> AppUser:
    if user.role != "admin":
        raise HTTPException(403, "需要管理員權限")
    return user
