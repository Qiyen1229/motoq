from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.domain.amounts import resolve_amounts
from app.domain.efficiency import summarize
from app.models import AppUser, EnergyLog, Vehicle, utcnow
from app.routers.vehicles import get_vehicle_or_404
from app.schemas import EnergyLogIn, EnergyLogOut, allowed_sources, unit_for
from app.models import Vehicle as _Vehicle
from app.services import fuel as fuel_service
from app.services.energy import adjustments_for, analyze, log_out, total_km
from app.services.settings import get_user_settings

router = APIRouter(tags=["energy"])


def _apply(db: Session, vehicle: Vehicle, body: EnergyLogIn, log: EnergyLog, force: bool) -> None:
    if body.energy_source not in allowed_sources(vehicle.energy_type):
        raise HTTPException(422, "能源來源與車輛能源類型不符")
    try:
        qty, price, total = resolve_amounts(body.quantity, body.unit_price, body.total_amount)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    adjustments = adjustments_for(db, vehicle.id)
    new_total = total_km(body.odometer_km, body.log_date, adjustments)
    if not force:
        _, _, points, _ = analyze(db, vehicle)
        earlier = [p for p in points if p.log_date <= body.log_date and p.id != log.id]
        if earlier:
            prev = max(earlier, key=lambda p: (p.log_date, p.odometer))
            if new_total < prev.odometer:
                raise HTTPException(
                    409,
                    detail={
                        "code": "odometer_decrease",
                        "message": f"里程 {new_total} km 小於先前記錄的 {prev.odometer} km",
                        "previous_km": prev.odometer,
                    },
                )

    log.vehicle_id = vehicle.id
    log.log_date = body.log_date
    log.odometer_km = body.odometer_km
    log.quantity, log.unit_price, log.total_amount = qty, price, total
    log.unit = unit_for(body.energy_source)
    log.energy_source = body.energy_source
    log.is_full = body.is_full
    log.missed_before = body.missed_before
    log.station = body.station
    log.start_soc = body.start_soc
    log.end_soc = body.end_soc
    log.note = body.note


def _out_for(db: Session, vehicle: Vehicle, log_id: int) -> EnergyLogOut:
    logs, adjustments, _, segments = analyze(db, vehicle)
    seg_by_end = {s.end_log_id: s for s in segments}
    return log_out(next(l for l in logs if l.id == log_id), adjustments, seg_by_end)


def _owned_log(db: Session, log_id: int, user: AppUser) -> tuple[EnergyLog, Vehicle]:
    log = db.get(EnergyLog, log_id)
    if not log or log.deleted_at:
        raise HTTPException(404, "找不到記錄")
    return log, get_vehicle_or_404(db, log.vehicle_id, user)


@router.get("/vehicles/{vehicle_id}/energy-logs", response_model=list[EnergyLogOut])
def list_logs(
    vehicle_id: int, limit: int | None = Query(None, ge=1, le=1000),
    user: AppUser = Depends(require_user), db: Session = Depends(get_db),
):
    vehicle = get_vehicle_or_404(db, vehicle_id, user)
    logs, adjustments, _, segments = analyze(db, vehicle)
    seg_by_end = {s.end_log_id: s for s in segments}
    out = [log_out(l, adjustments, seg_by_end) for l in reversed(logs)]
    return out[:limit] if limit else out


@router.get("/vehicles/{vehicle_id}/energy-logs/defaults")
def defaults(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    """快速輸入預填：上次的能源來源、單價、站點與里程。"""
    vehicle = get_vehicle_or_404(db, vehicle_id, user)
    logs = analyze(db, vehicle)[0]
    last = logs[-1] if logs else None
    fallback = vehicle.default_energy_source or ("home" if vehicle.energy_type == "electric" else "gas_95")
    return {
        "energy_type": vehicle.energy_type,
        "energy_source": last.energy_source if last else fallback,
        "unit_price": last.unit_price if last else None,
        "station": last.station if last else "",
        "last_odometer_km": last.odometer_km if last else vehicle.initial_odometer_km,
        "last_log_date": last.log_date if last else None,
        "battery_kwh": vehicle.battery_kwh,
    }


@router.get("/vehicles/{vehicle_id}/energy-logs/price-suggestion")
def price_suggestion(
    vehicle_id: int, energy_source: str, station: str = "",
    user: AppUser = Depends(require_user), db: Session = Depends(get_db),
):
    """依油品與加油站建議單價：中油用最新牌價；其他品牌優先用你牌價生效後在該站的實付價。"""
    vehicle = get_vehicle_or_404(db, vehicle_id, user)
    if energy_source not in allowed_sources(vehicle.energy_type):
        raise HTTPException(422, "能源來源與車輛能源類型不符")
    fuel_service.ensure_fresh(db)
    ids = [i for (i,) in db.execute(select(_Vehicle.id).where(_Vehicle.user_id == user.id))]
    return fuel_service.suggest_price(db, ids, energy_source, station)


@router.post("/vehicles/{vehicle_id}/energy-logs", response_model=EnergyLogOut, status_code=201)
def create_log(
    vehicle_id: int, body: EnergyLogIn, force: bool = False,
    user: AppUser = Depends(require_user), db: Session = Depends(get_db),
):
    vehicle = get_vehicle_or_404(db, vehicle_id, user)
    log = EnergyLog()
    _apply(db, vehicle, body, log, force)
    db.add(log)
    db.commit()
    return _out_for(db, vehicle, log.id)


@router.put("/energy-logs/{log_id}", response_model=EnergyLogOut)
def update_log(
    log_id: int, body: EnergyLogIn, force: bool = False,
    user: AppUser = Depends(require_user), db: Session = Depends(get_db),
):
    log, vehicle = _owned_log(db, log_id, user)
    _apply(db, vehicle, body, log, force)
    db.commit()
    return _out_for(db, vehicle, log.id)


@router.delete("/energy-logs/{log_id}", status_code=204)
def delete_log(log_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    log, _ = _owned_log(db, log_id, user)
    log.deleted_at = utcnow()
    db.commit()


def _in_range(d: date, start: date | None, end: date | None) -> bool:
    return (start is None or d >= start) and (end is None or d <= end)


@router.get("/vehicles/{vehicle_id}/efficiency/trend")
def trend(
    vehicle_id: int, from_: date | None = Query(None, alias="from"), to: date | None = None,
    user: AppUser = Depends(require_user), db: Session = Depends(get_db),
):
    vehicle = get_vehicle_or_404(db, vehicle_id, user)
    _, _, _, segments = analyze(db, vehicle)
    return [
        {
            "end_date": s.end_date, "start_date": s.start_date, "distance_km": s.distance_km,
            "energy": s.energy, "cost": round(s.cost), "efficiency": round(s.efficiency, 2),
            "cost_per_km": round(s.cost_per_km, 2), "method": s.method,
        }
        for s in segments
        if _in_range(s.end_date, from_, to)
    ]


@router.get("/vehicles/{vehicle_id}/efficiency/stats")
def stats(
    vehicle_id: int, from_: date | None = Query(None, alias="from"), to: date | None = None,
    user: AppUser = Depends(require_user), db: Session = Depends(get_db),
):
    vehicle = get_vehicle_or_404(db, vehicle_id, user)
    _, _, _, segments = analyze(db, vehicle)
    segments = [s for s in segments if _in_range(s.end_date, from_, to)]
    threshold = get_user_settings(db, user.id)["anomaly_drop_pct"] / 100
    s = summarize(segments, drop_threshold=threshold)
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in s.__dict__.items()}
