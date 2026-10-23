from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.efficiency import LogPoint, Segment, compute_segments
from app.models import EnergyLog, OdometerAdjustment, ServiceVisit, Vehicle
from app.schemas import EnergyLogOut, VehicleOut


def adjustments_for(db: Session, vehicle_id: int) -> list[OdometerAdjustment]:
    return list(
        db.scalars(
            select(OdometerAdjustment)
            .where(OdometerAdjustment.vehicle_id == vehicle_id)
            .order_by(OdometerAdjustment.effective_date)
        )
    )


def total_km(reading: int, log_date: date, adjustments: list[OdometerAdjustment]) -> int:
    return reading + sum(a.offset_km for a in adjustments if a.effective_date <= log_date)


def active_logs(db: Session, vehicle_id: int) -> list[EnergyLog]:
    return list(
        db.scalars(
            select(EnergyLog)
            .where(EnergyLog.vehicle_id == vehicle_id, EnergyLog.deleted_at.is_(None))
            .order_by(EnergyLog.log_date, EnergyLog.odometer_km, EnergyLog.id)
        )
    )


def to_point(log: EnergyLog, adjustments: list[OdometerAdjustment]) -> LogPoint:
    return LogPoint(
        id=log.id,
        log_date=log.log_date,
        odometer=total_km(log.odometer_km, log.log_date, adjustments),
        quantity=log.quantity,
        unit_price=log.unit_price,
        total_amount=log.total_amount,
        is_full=log.is_full,
        missed_before=log.missed_before,
        start_soc=log.start_soc,
        end_soc=log.end_soc,
    )


def segments_for(vehicle: Vehicle, logs: list[EnergyLog], points: list[LogPoint]) -> list[Segment]:
    """油耗以「燃油」記錄計算；電動車用電量記錄；油電車的充電不納入 km/L。"""
    want_unit = "kWh" if vehicle.energy_type == "electric" else "L"
    kept = [p for l, p in zip(logs, points) if l.unit == want_unit]
    return compute_segments(kept, vehicle.energy_type, vehicle.battery_kwh)


@dataclass
class VehicleState:
    logs: list[EnergyLog]
    adjustments: list[OdometerAdjustment]
    points: list[LogPoint]
    segments: list[Segment]
    odo_points: list[tuple[date, int]]  # (日期, 總里程)，含加油與進廠
    current_km: int


def load_state(db: Session, vehicle: Vehicle) -> VehicleState:
    adjustments = adjustments_for(db, vehicle.id)
    logs = active_logs(db, vehicle.id)
    points = [to_point(l, adjustments) for l in logs]
    segments = segments_for(vehicle, logs, points)
    odo_points = [(p.log_date, p.odometer) for p in points]
    for v in db.scalars(select(ServiceVisit).where(ServiceVisit.vehicle_id == vehicle.id)):
        odo_points.append((v.visit_date, total_km(v.odometer_km, v.visit_date, adjustments)))
    if vehicle.purchase_date:
        odo_points.append((vehicle.purchase_date, vehicle.initial_odometer_km))
    current = max([vehicle.initial_odometer_km, *(o for _, o in odo_points)])
    return VehicleState(logs, adjustments, points, segments, sorted(set(odo_points)), current)


def analyze(db: Session, vehicle: Vehicle):
    st = load_state(db, vehicle)
    return st.logs, st.adjustments, st.points, st.segments


def log_out(log: EnergyLog, adjustments, seg_by_end: dict[int, Segment] | None = None) -> EnergyLogOut:
    seg = (seg_by_end or {}).get(log.id)
    return EnergyLogOut(
        id=log.id,
        vehicle_id=log.vehicle_id,
        log_date=log.log_date,
        odometer_km=log.odometer_km,
        total_km=total_km(log.odometer_km, log.log_date, adjustments),
        quantity=log.quantity,
        unit=log.unit,
        unit_price=log.unit_price,
        total_amount=log.total_amount,
        is_full=log.is_full,
        missed_before=log.missed_before,
        energy_source=log.energy_source,
        station=log.station,
        start_soc=log.start_soc,
        end_soc=log.end_soc,
        note=log.note,
        efficiency=round(seg.efficiency, 2) if seg else None,
        cost_per_km=round(seg.cost_per_km, 2) if seg else None,
        distance_km=seg.distance_km if seg else None,
    )


def vehicle_out(db: Session, vehicle: Vehicle) -> VehicleOut:
    out = VehicleOut.model_validate(vehicle)
    out.current_odometer_km = load_state(db, vehicle).current_km
    return out
