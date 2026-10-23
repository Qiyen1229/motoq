from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.domain.efficiency import summarize
from app.models import AppUser, Vehicle
from app.routers.vehicles import get_vehicle_or_404
from app.schemas import VehicleOut
from app.services import fuel
from app.services.attention import build_attention
from app.services.energy import load_state
from app.services.maintenance import item_statuses
from app.services.settings import get_user_settings

router = APIRouter(tags=["dashboard"])


def build_dashboard(db: Session, vehicle: Vehicle, user_settings: dict) -> dict:
    st = load_state(db, vehicle)
    summary = summarize(st.segments, drop_threshold=user_settings["anomaly_drop_pct"] / 100)
    today = date.today()
    month_logs = [l for l in st.logs if l.log_date.year == today.year and l.log_date.month == today.month]
    electric = vehicle.energy_type == "electric"
    veh = VehicleOut.model_validate(vehicle)
    veh.current_odometer_km = st.current_km

    maint = [m for m in item_statuses(db, vehicle, st, today) if m["state"] != "unknown"]
    next_maint = None
    if maint:
        m = maint[0]
        next_maint = {k: m[k] for k in ("name", "state", "basis", "due_date", "remaining_km", "remaining_days")}

    primary_unit = "kWh" if electric else "L"
    return {
        "vehicle": veh,
        "efficiency_unit": "km/kWh" if electric else "km/L",
        "energy_unit": primary_unit,
        "total_km": st.current_km,
        "month_cost": sum(l.total_amount for l in month_logs),
        "month_energy": round(sum(l.quantity for l in month_logs if l.unit == primary_unit), 2),
        "month_log_count": len(month_logs),
        "log_count": len(st.logs),
        "last_log_date": st.logs[-1].log_date if st.logs else None,
        "avg_efficiency": round(summary.avg_efficiency, 2) if summary.avg_efficiency else None,
        "last_efficiency": round(summary.last_efficiency, 2) if summary.last_efficiency else None,
        "cost_per_km": round(summary.cost_per_km, 2) if summary.cost_per_km else None,
        "next_maintenance": next_maint,
        "warning": {
            "active": summary.warning,
            "recent_avg": round(summary.recent_avg, 2) if summary.recent_avg else None,
            "baseline_avg": round(summary.baseline_avg, 2) if summary.baseline_avg else None,
            "drop_pct": round(summary.drop_pct, 1) if summary.drop_pct is not None else None,
        },
    }


@router.get("/vehicles/{vehicle_id}/dashboard")
def vehicle_dashboard(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    v = get_vehicle_or_404(db, vehicle_id, user)
    return build_dashboard(db, v, get_user_settings(db, user.id))


@router.get("/dashboard")
def overview(user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    settings = get_user_settings(db, user.id)
    vehicles = db.scalars(
        select(Vehicle).where(Vehicle.user_id == user.id, Vehicle.deleted_at.is_(None)).order_by(Vehicle.id)
    )
    return [build_dashboard(db, v, settings) for v in vehicles]


@router.get("/attention")
def attention(user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    return build_attention(db, user.id)


@router.get("/fuel-prices/latest")
def fuel_latest(user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    fuel.ensure_fresh(db)  # 資料過舊時順手向中油更新，失敗不影響回應
    return fuel.latest_summary(db)
