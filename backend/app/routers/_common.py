from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import AppUser
from app.routers.vehicles import get_vehicle_or_404


def owned_row(db: Session, model, row_id: int, user: AppUser, label: str = "記錄"):
    """取得帶有 vehicle_id 的資料列，並確認其車輛屬於目前使用者。"""
    row = db.get(model, row_id)
    if not row:
        raise HTTPException(404, f"找不到{label}")
    get_vehicle_or_404(db, row.vehicle_id, user)
    return row
