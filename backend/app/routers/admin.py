import shutil
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth
from app.config import get_settings
from app.db import get_db
from app.models import (
    AppUser, Attachment, AuthSession, EnergyLog, SecurityEvent, Vehicle, utcnow,
)
from app.schemas import GlobalSettingsIn
from app.services.settings import get_global, set_global

router = APIRouter(prefix="/admin", tags=["admin"])


class UserPatch(BaseModel):
    role: Literal["admin", "user"] | None = None
    status: Literal["active", "pending", "disabled"] | None = None


class ResetPassword(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


def _active_admin_count(db: Session, exclude_id: int | None = None) -> int:
    q = select(func.count()).select_from(AppUser).where(AppUser.role == "admin", AppUser.status == "active")
    if exclude_id is not None:
        q = q.where(AppUser.id != exclude_id)
    return db.scalar(q) or 0


def _dir_size(path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0


@router.get("/overview")
def overview(admin: AppUser = Depends(auth.require_admin), db: Session = Depends(get_db)):
    s = get_settings()
    by_status = dict(db.execute(select(AppUser.status, func.count()).group_by(AppUser.status)).all())
    since = utcnow() - timedelta(hours=24)
    failed = db.scalar(
        select(func.count()).select_from(SecurityEvent).where(
            SecurityEvent.kind == "login", SecurityEvent.success.is_(False), SecurityEvent.created_at >= since
        )
    )
    return {
        "version": "1.0.0",
        "users": {"total": sum(by_status.values()), **by_status},
        "vehicles": db.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.deleted_at.is_(None))),
        "energy_logs": db.scalar(select(func.count()).select_from(EnergyLog).where(EnergyLog.deleted_at.is_(None))),
        "attachments": db.scalar(select(func.count()).select_from(Attachment)),
        "active_sessions": db.scalar(select(func.count()).select_from(AuthSession).where(AuthSession.expires_at > utcnow())),
        "failed_logins_24h": failed,
        "db_bytes": s.db_path.stat().st_size if s.db_path.exists() else 0,
        "uploads_bytes": _dir_size(s.data_dir / "uploads"),
        "cookie_secure": s.cookie_secure,
        "setup_token_configured": bool(s.setup_token),
        "settings": get_global(db),
    }


@router.get("/users")
def users(admin: AppUser = Depends(auth.require_admin), db: Session = Depends(get_db)):
    vehicle_counts = dict(
        db.execute(select(Vehicle.user_id, func.count()).where(Vehicle.deleted_at.is_(None)).group_by(Vehicle.user_id)).all()
    )
    session_counts = dict(
        db.execute(
            select(AuthSession.user_id, func.count()).where(AuthSession.expires_at > utcnow()).group_by(AuthSession.user_id)
        ).all()
    )
    rows = db.scalars(select(AppUser).order_by(AppUser.id))
    return [
        {
            "id": u.id, "username": u.username, "role": u.role, "status": u.status,
            "created_at": u.created_at, "last_login_at": u.last_login_at,
            "vehicle_count": vehicle_counts.get(u.id, 0), "session_count": session_counts.get(u.id, 0),
        }
        for u in rows
    ]


@router.patch("/users/{user_id}")
def patch_user(
    user_id: int, body: UserPatch, request: Request,
    admin: AppUser = Depends(auth.require_admin), db: Session = Depends(get_db),
):
    user = db.get(AppUser, user_id)
    if not user:
        raise HTTPException(404, "找不到使用者")
    new_role = body.role or user.role
    new_status = body.status or user.status
    if user.id == admin.id and (new_role != "admin" or new_status != "active"):
        raise HTTPException(400, "不能降級或停用自己的帳號")
    losing_admin = user.role == "admin" and user.status == "active" and (new_role != "admin" or new_status != "active")
    if losing_admin and _active_admin_count(db, exclude_id=user.id) == 0:
        raise HTTPException(400, "至少需保留一位啟用中的管理員")
    changes = []
    if new_role != user.role:
        changes.append(f"role {user.role}→{new_role}")
    if new_status != user.status:
        changes.append(f"status {user.status}→{new_status}")
    user.role, user.status = new_role, new_status
    db.commit()
    if new_status != "active":
        auth.revoke_user_sessions(db, user.id)
    auth.log_event(db, "admin_user_update", request, username=admin.username, user_id=admin.id,
                   detail=f"{user.username}: {', '.join(changes) or '無變更'}")
    return {"id": user.id, "role": user.role, "status": user.status}


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: int, body: ResetPassword, request: Request,
    admin: AppUser = Depends(auth.require_admin), db: Session = Depends(get_db),
):
    user = db.get(AppUser, user_id)
    if not user:
        raise HTTPException(404, "找不到使用者")
    user.password_hash = auth.hash_password(body.new_password)
    db.commit()
    auth.revoke_user_sessions(db, user.id)
    auth.log_event(db, "admin_reset_password", request, username=admin.username, user_id=admin.id, detail=user.username)
    return {"ok": True}


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int, request: Request,
    admin: AppUser = Depends(auth.require_admin), db: Session = Depends(get_db),
):
    user = db.get(AppUser, user_id)
    if not user:
        raise HTTPException(404, "找不到使用者")
    if user.id == admin.id:
        raise HTTPException(400, "不能刪除自己的帳號")
    if user.role == "admin" and user.status == "active" and _active_admin_count(db, exclude_id=user.id) == 0:
        raise HTTPException(400, "至少需保留一位啟用中的管理員")
    name = user.username
    db.delete(user)  # 外鍵 CASCADE：車輛與所有紀錄一併刪除
    db.commit()
    shutil.rmtree(get_settings().data_dir / "uploads" / str(user_id), ignore_errors=True)
    auth.log_event(db, "admin_delete_user", request, username=admin.username, user_id=admin.id, detail=name)


@router.get("/events")
def events(
    kind: str | None = None, limit: int = Query(100, ge=1, le=500),
    admin: AppUser = Depends(auth.require_admin), db: Session = Depends(get_db),
):
    q = select(SecurityEvent).order_by(SecurityEvent.id.desc()).limit(limit)
    if kind:
        q = q.where(SecurityEvent.kind == kind)
    return [
        {
            "id": e.id, "kind": e.kind, "success": e.success, "username": e.username,
            "ip": e.ip, "user_agent": e.user_agent, "detail": e.detail, "created_at": e.created_at,
        }
        for e in db.scalars(q)
    ]


@router.get("/sessions")
def sessions(admin: AppUser = Depends(auth.require_admin), db: Session = Depends(get_db)):
    rows = db.execute(
        select(AuthSession, AppUser.username)
        .join(AppUser, AppUser.id == AuthSession.user_id)
        .where(AuthSession.expires_at > utcnow())
        .order_by(AuthSession.last_seen_at.desc())
    ).all()
    return [
        {
            "id": s.id, "username": name, "ip": s.ip, "user_agent": s.user_agent,
            "created_at": s.created_at, "last_seen_at": s.last_seen_at, "expires_at": s.expires_at,
        }
        for s, name in rows
    ]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke(
    session_id: int, request: Request,
    admin: AppUser = Depends(auth.require_admin), db: Session = Depends(get_db),
):
    row = db.get(AuthSession, session_id)
    if not row:
        raise HTTPException(404, "找不到工作階段")
    db.delete(row)
    db.commit()
    auth.log_event(db, "admin_revoke_session", request, username=admin.username, user_id=admin.id, detail=f"session {session_id}")


@router.get("/settings")
def get_settings_(admin: AppUser = Depends(auth.require_admin), db: Session = Depends(get_db)):
    return get_global(db)


@router.put("/settings")
def put_settings(
    body: GlobalSettingsIn, request: Request,
    admin: AppUser = Depends(auth.require_admin), db: Session = Depends(get_db),
):
    values = body.model_dump(exclude_none=True)
    result = set_global(db, values)
    auth.log_event(db, "admin_settings", request, username=admin.username, user_id=admin.id, detail=str(values))
    return result
