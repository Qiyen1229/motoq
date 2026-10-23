from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth
from app.config import get_settings
from app.db import get_db
from app.models import AppUser
from app.schemas import LoginIn, PasswordChangeIn, RegisterIn
from app.services.settings import get_global

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, token: str, days: int) -> None:
    response.set_cookie(
        auth.COOKIE_NAME, token, max_age=days * 86400, httponly=True,
        samesite="strict", secure=get_settings().cookie_secure, path="/",
    )


def _me(user: AppUser) -> dict:
    return {"username": user.username, "role": user.role, "status": user.status}


@router.get("/registration")
def registration_status(db: Session = Depends(get_db)):
    has_users = (db.scalar(select(func.count()).select_from(AppUser)) or 0) > 0
    mode = get_global(db)["registration_mode"]
    return {
        "has_users": has_users,
        "mode": mode,
        "can_register": (not has_users) or mode in ("open", "approval"),
        "needs_setup_token": (not has_users) and bool(get_settings().setup_token),
    }


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    auth.check_register_limit(request)
    count = db.scalar(select(func.count()).select_from(AppUser)) or 0
    first = count == 0
    mode = get_global(db)["registration_mode"]

    if first:
        token = get_settings().setup_token
        if token and not (body.setup_token and secrets_equal(body.setup_token, token)):
            auth.log_event(db, "register", request, success=False, username=body.username, detail="bad setup token")
            raise HTTPException(403, "初始設定碼不正確")
    elif mode == "closed":
        raise HTTPException(403, "目前未開放註冊")

    if db.scalar(select(AppUser).where(func.lower(AppUser.username) == body.username.lower())):
        raise HTTPException(409, "此帳號已被使用")

    status = "active" if first or mode == "open" else "pending"
    user = AppUser(
        username=body.username, password_hash=auth.hash_password(body.password),
        role="admin" if first else "user", status=status,
    )
    db.add(user)
    db.commit()
    auth.log_event(db, "register", request, username=user.username, user_id=user.id,
                   detail="first user → admin" if first else f"status={status}")
    if status == "active":
        token, days = auth.create_session(db, user, request)
        _set_cookie(response, token, days)
    return {**_me(user), "pending": status == "pending"}


def secrets_equal(a: str, b: str) -> bool:
    import secrets

    return secrets.compare_digest(a.encode(), b.encode())


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    key = auth.check_login_limit(request, db)
    user = db.scalar(select(AppUser).where(func.lower(AppUser.username) == body.username.strip().lower()))
    if not user or not auth.verify_password(user.password_hash, body.password):
        auth.record_login_failure(key)
        auth.log_event(db, "login", request, success=False, username=body.username, detail="bad credentials")
        raise HTTPException(401, "帳號或密碼錯誤")
    if user.status == "pending":
        raise HTTPException(403, "帳號待管理員核准")
    if user.status == "disabled":
        auth.log_event(db, "login", request, success=False, username=user.username, user_id=user.id, detail="disabled")
        raise HTTPException(403, "帳號已停用")
    auth.clear_login_failures(key)
    auth.purge_expired_sessions(db)
    token, days = auth.create_session(db, user, request)
    _set_cookie(response, token, days)
    auth.log_event(db, "login", request, username=user.username, user_id=user.id)
    return _me(user)


@router.post("/logout")
def logout(
    response: Response, motoq_session: str | None = Cookie(default=None), db: Session = Depends(get_db)
):
    if motoq_session:
        auth.revoke_session(db, motoq_session)
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: AppUser = Depends(auth.require_user)):
    return _me(user)


@router.post("/change-password")
def change_password(
    body: PasswordChangeIn, request: Request,
    user: AppUser = Depends(auth.require_user),
    motoq_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    if not auth.verify_password(user.password_hash, body.current_password):
        raise HTTPException(400, "目前密碼不正確")
    user.password_hash = auth.hash_password(body.new_password)
    db.commit()
    auth.revoke_user_sessions(db, user.id, except_token=motoq_session)  # 其他裝置需重新登入
    auth.log_event(db, "password_change", request, username=user.username, user_id=user.id)
    return {"ok": True}
