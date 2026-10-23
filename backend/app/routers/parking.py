import time
from collections import defaultdict, deque
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.auth import require_user
from app.db import get_db
from app.models import AppUser, ParkingCheck, Vehicle, utcnow
from app.routers.vehicles import get_vehicle_or_404
from app.services import parking

router = APIRouter(tags=["parking"])

PER_USER_LIMIT = 60  # 每位使用者每小時（查詢全台 21 個縣市約用掉 21 次）
_attempts: dict[int, deque[float]] = defaultdict(deque)


class Lookup(BaseModel):
    plate: str = Field(min_length=2, max_length=12)
    car_type: str = "M"
    city: str = "TPE"
    vehicle_id: int | None = None  # 指定時，結果會存為該車輛的最近一次查詢（供待辦使用）


def _mask(plate: str) -> str:
    return plate[:-2] + "**" if len(plate) > 3 else "***"


def save_check(db: Session, vehicle_id: int, result: dict, source: str) -> None:
    row = db.scalar(
        select(ParkingCheck).where(ParkingCheck.vehicle_id == vehicle_id, ParkingCheck.city == result["city_code"])
    )
    if not row:
        row = ParkingCheck(vehicle_id=vehicle_id, city=result["city_code"])
        db.add(row)
    row.checked_at = utcnow()
    row.total_count = result["total_count"]
    row.total_amount = float(result["total_amount"] or 0)
    row.payload = {k: v for k, v in result.items() if k != "cached"}
    row.source = source
    db.commit()


@router.get("/parking/cities")
def cities(user: AppUser = Depends(require_user)):
    return [
        {"code": c.code, "name": c.name, "insecure": c.insecure, "pay_url": c.pay_url}
        for c in parking.CITIES.values()
    ]


@router.post("/parking/lookup")
def lookup(
    body: Lookup, request: Request,
    user: AppUser = Depends(require_user), db: Session = Depends(get_db),
):
    """查詢指定縣市的路邊停車費欠費（未繳停車單與催繳單）。"""
    vehicle: Vehicle | None = get_vehicle_or_404(db, body.vehicle_id, user) if body.vehicle_id else None

    window = _attempts[user.id]
    now = time.monotonic()
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= PER_USER_LIMIT:
        raise HTTPException(429, f"查詢次數過多，請稍後再試（每小時上限 {PER_USER_LIMIT} 次）")
    window.append(now)

    try:
        result = parking.lookup(body.city, body.plate, body.car_type)
    except parking.ParkingLookupError as e:
        auth.log_event(db, "parking_lookup", request, success=False, username=user.username,
                       user_id=user.id, detail=f"{body.city} {e}")
        raise HTTPException(502 if ("連線" in str(e) or "回應" in str(e)) else 422, str(e)) from e

    if vehicle and parking.normalize_plate(vehicle.plate or "") == result["plate"]:
        save_check(db, vehicle.id, result, "manual")
    # 稽核只記錄遮蔽後的車牌，不記錄查詢結果
    auth.log_event(db, "parking_lookup", request, username=user.username, user_id=user.id,
                   detail=f"{result['city_code']} {_mask(result['plate'])} {result['car_type']}")
    return result


@router.get("/vehicles/{vehicle_id}/parking-checks")
def checks(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    get_vehicle_or_404(db, vehicle_id, user)
    rows = db.scalars(
        select(ParkingCheck).where(ParkingCheck.vehicle_id == vehicle_id).order_by(ParkingCheck.checked_at.desc())
    )
    return [
        {"city_code": r.city, "city": parking.CITIES[r.city].name if r.city in parking.CITIES else r.city,
         "checked_at": r.checked_at, "total_count": r.total_count, "total_amount": r.total_amount,
         "source": r.source, "detail": r.payload}
        for r in rows
    ]


def run_auto_checks(db: Session) -> int:
    """排程用：替已開啟自動檢查的使用者，逐車逐縣市查詢並存檔。回傳查詢次數。"""
    from app.models import UserSetting
    from app.services.settings import get_user_settings

    count = 0
    user_ids = {
        uid for (uid,) in db.execute(
            select(UserSetting.user_id).where(UserSetting.key == "parking_auto_check")
        ) if get_user_settings(db, uid)["parking_auto_check"]
    }
    for uid in user_ids:
        cities = get_user_settings(db, uid)["parking_cities"]
        vehicles = db.scalars(
            select(Vehicle).where(Vehicle.user_id == uid, Vehicle.deleted_at.is_(None),
                                  Vehicle.status == "active", Vehicle.plate != "")
        ).all()
        for v in vehicles:
            for code in cities:
                try:
                    result = parking.lookup(code, v.plate, parking.car_type_for(v.vehicle_type))
                    save_check(db, v.id, result, "auto")
                except parking.ParkingLookupError:
                    pass  # 單一縣市失敗不影響其他
                count += 1
    return count


__all__ = ["router", "run_auto_checks", "date"]
