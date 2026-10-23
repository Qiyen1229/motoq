from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.maintenance import Baseline, avg_daily_km, evaluate_item
from app.models import MaintenanceItem, ServiceLine, ServiceVisit, Vehicle
from app.services.energy import VehicleState, load_state, total_km

STATE_ORDER = {"overdue": 0, "soon": 1, "ok": 2, "unknown": 3}


def last_done(db: Session, item: MaintenanceItem, vehicle: Vehicle, adjustments) -> Baseline | None:
    row = db.execute(
        select(ServiceVisit.visit_date, ServiceVisit.odometer_km)
        .join(ServiceLine, ServiceLine.visit_id == ServiceVisit.id)
        .where(ServiceLine.item_id == item.id)
        .order_by(ServiceVisit.visit_date.desc(), ServiceVisit.odometer_km.desc())
        .limit(1)
    ).first()
    if row:
        return Baseline(row[0], total_km(row[1], row[0], adjustments))
    if item.baseline_date:
        km = item.baseline_km if item.baseline_km is not None else vehicle.initial_odometer_km
        return Baseline(item.baseline_date, km)
    return None


def item_statuses(
    db: Session, vehicle: Vehicle, state: VehicleState | None = None, today: date | None = None
) -> list[dict]:
    today = today or date.today()
    state = state or load_state(db, vehicle)
    daily = avg_daily_km(state.odo_points, today)
    items = db.scalars(
        select(MaintenanceItem)
        .where(MaintenanceItem.vehicle_id == vehicle.id, MaintenanceItem.is_active.is_(True))
        .order_by(MaintenanceItem.id)
    )
    out = []
    for item in items:
        last = last_done(db, item, vehicle, state.adjustments)
        st = evaluate_item(item.interval_km, item.interval_months, last, state.current_km, today, daily)
        out.append(
            {
                "item_id": item.id, "name": item.name, "category": item.category,
                "interval_km": item.interval_km, "interval_months": item.interval_months,
                "last_date": last.date if last else None, "last_km": last.odometer if last else None,
                "state": st.state, "basis": st.basis, "due_date": st.due_date, "due_km": st.due_km,
                "remaining_km": st.remaining_km, "remaining_days": st.remaining_days,
                "predicted_date_by_km": st.predicted_date_by_km, "date_by_time": st.date_by_time,
                "progress": round(st.progress, 3) if st.progress is not None else None,
            }
        )
    out.sort(key=lambda r: (STATE_ORDER[r["state"]], r["due_date"] or date.max))
    return out


def maintenance_overview(db: Session, vehicle: Vehicle, state=None, today=None) -> dict:
    statuses = item_statuses(db, vehicle, state, today)
    state_ = state or load_state(db, vehicle)
    today = today or date.today()
    return {
        "daily_km": round(avg_daily_km(state_.odo_points, today) or 0, 1) or None,
        "current_km": state_.current_km,
        "items": statuses,
    }
