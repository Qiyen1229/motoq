from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.models import AppUser, EnergyLog, OdometerAdjustment, Vehicle, utcnow
from app.schemas import AdjustmentIn, AdjustmentOut, VehicleIn, VehicleOut, allowed_sources
from app.services.energy import adjustments_for, vehicle_out

router = APIRouter(tags=["vehicles"])


def get_vehicle_or_404(db: Session, vehicle_id: int, user: AppUser) -> Vehicle:
    """所有車輛相關資料都必須經由這裡驗證擁有者，避免跨使用者存取。"""
    v = db.get(Vehicle, vehicle_id)
    if not v or v.deleted_at or v.user_id != user.id:
        raise HTTPException(404, "找不到車輛")
    return v


def _validate(body: VehicleIn) -> None:
    if body.energy_type == "hybrid" and body.vehicle_type != "car":
        raise HTTPException(422, "油電車僅適用於汽車類")
    if body.default_energy_source and body.default_energy_source not in allowed_sources(body.energy_type):
        raise HTTPException(422, "預設能源來源與車輛能源類型不符")
    if body.energy_type == "gasoline":
        body.battery_kwh = None


@router.get("/vehicles", response_model=list[VehicleOut])
def list_vehicles(user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Vehicle).where(Vehicle.user_id == user.id, Vehicle.deleted_at.is_(None)).order_by(Vehicle.id)
    )
    return [vehicle_out(db, v) for v in rows]


@router.post("/vehicles", response_model=VehicleOut, status_code=201)
def create_vehicle(body: VehicleIn, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    _validate(body)
    v = Vehicle(user_id=user.id, **body.model_dump())
    db.add(v)
    db.commit()
    return vehicle_out(db, v)


@router.get("/vehicles/{vehicle_id}", response_model=VehicleOut)
def get_vehicle(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    return vehicle_out(db, get_vehicle_or_404(db, vehicle_id, user))


@router.put("/vehicles/{vehicle_id}", response_model=VehicleOut)
def update_vehicle(
    vehicle_id: int, body: VehicleIn, user: AppUser = Depends(require_user), db: Session = Depends(get_db)
):
    v = get_vehicle_or_404(db, vehicle_id, user)
    _validate(body)
    if body.energy_type != v.energy_type:
        # 只有「燃油 ↔ 油電」之間、且既有記錄都是燃油時才允許轉換
        used = {u for (u,) in db.execute(select(EnergyLog.unit).where(EnergyLog.vehicle_id == v.id).distinct())}
        incompatible = (body.energy_type == "gasoline" and "kWh" in used) or (
            body.energy_type == "electric" and "L" in used
        )
        if incompatible:
            raise HTTPException(409, "已有不相容的能源記錄，無法變更能源類型")
    for k, val in body.model_dump().items():
        setattr(v, k, val)
    db.commit()
    return vehicle_out(db, v)


@router.delete("/vehicles/{vehicle_id}", status_code=204)
def delete_vehicle(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    v = get_vehicle_or_404(db, vehicle_id, user)
    v.deleted_at = utcnow()
    db.commit()


@router.get("/vehicles/{vehicle_id}/odometer-adjustments", response_model=list[AdjustmentOut])
def list_adjustments(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    get_vehicle_or_404(db, vehicle_id, user)
    return adjustments_for(db, vehicle_id)


@router.post(
    "/vehicles/{vehicle_id}/odometer-adjustments", response_model=AdjustmentOut, status_code=201
)
def add_adjustment(
    vehicle_id: int, body: AdjustmentIn, user: AppUser = Depends(require_user), db: Session = Depends(get_db)
):
    get_vehicle_or_404(db, vehicle_id, user)
    adj = OdometerAdjustment(vehicle_id=vehicle_id, **body.model_dump())
    db.add(adj)
    db.commit()
    return adj


@router.delete("/odometer-adjustments/{adj_id}", status_code=204)
def delete_adjustment(adj_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    adj = db.get(OdometerAdjustment, adj_id)
    if not adj:
        raise HTTPException(404, "找不到記錄")
    get_vehicle_or_404(db, adj.vehicle_id, user)
    db.delete(adj)
    db.commit()
