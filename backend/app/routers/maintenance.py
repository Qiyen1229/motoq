from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.domain.templates import template_for
from app.models import AppUser, Attachment, MaintenanceItem, ServiceLine, ServiceVisit
from app.routers._common import owned_row
from app.routers.vehicles import get_vehicle_or_404
from app.schemas import MaintenanceItemIn, ServiceVisitIn
from app.services.maintenance import maintenance_overview

router = APIRouter(tags=["maintenance"])


class ApplyTemplate(BaseModel):
    baseline_date: date | None = None
    baseline_km: int | None = None


def _item_out(i: MaintenanceItem) -> dict:
    return {
        "id": i.id, "vehicle_id": i.vehicle_id, "name": i.name, "category": i.category,
        "interval_km": i.interval_km, "interval_months": i.interval_months,
        "baseline_date": i.baseline_date, "baseline_km": i.baseline_km,
        "is_active": i.is_active, "note": i.note,
    }


@router.get("/vehicles/{vehicle_id}/maintenance/status")
def status(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    return maintenance_overview(db, get_vehicle_or_404(db, vehicle_id, user))


@router.get("/vehicles/{vehicle_id}/maintenance-template")
def template(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    v = get_vehicle_or_404(db, vehicle_id, user)
    return [
        {"name": n, "category": c, "interval_km": km, "interval_months": mo}
        for n, c, km, mo in template_for(v.vehicle_type, v.energy_type)
    ]


@router.post("/vehicles/{vehicle_id}/maintenance-items/apply-template", status_code=201)
def apply_template(
    vehicle_id: int, body: ApplyTemplate, user: AppUser = Depends(require_user), db: Session = Depends(get_db)
):
    v = get_vehicle_or_404(db, vehicle_id, user)
    existing = {n for (n,) in db.execute(select(MaintenanceItem.name).where(MaintenanceItem.vehicle_id == v.id))}
    created = 0
    for name, cat, km, months in template_for(v.vehicle_type, v.energy_type):
        if name in existing:
            continue
        db.add(
            MaintenanceItem(
                vehicle_id=v.id, name=name, category=cat, interval_km=km, interval_months=months,
                baseline_date=body.baseline_date, baseline_km=body.baseline_km,
            )
        )
        created += 1
    db.commit()
    return {"created": created, "skipped": len(existing)}


@router.get("/vehicles/{vehicle_id}/maintenance-items")
def list_items(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    get_vehicle_or_404(db, vehicle_id, user)
    rows = db.scalars(select(MaintenanceItem).where(MaintenanceItem.vehicle_id == vehicle_id).order_by(MaintenanceItem.id))
    return [_item_out(i) for i in rows]


@router.post("/vehicles/{vehicle_id}/maintenance-items", status_code=201)
def create_item(
    vehicle_id: int, body: MaintenanceItemIn, user: AppUser = Depends(require_user), db: Session = Depends(get_db)
):
    get_vehicle_or_404(db, vehicle_id, user)
    if not (body.interval_km or body.interval_months):
        raise HTTPException(422, "請至少設定里程或時間其中一項間隔")
    item = MaintenanceItem(vehicle_id=vehicle_id, **body.model_dump())
    db.add(item)
    db.commit()
    return _item_out(item)


@router.put("/maintenance-items/{item_id}")
def update_item(
    item_id: int, body: MaintenanceItemIn, user: AppUser = Depends(require_user), db: Session = Depends(get_db)
):
    item = owned_row(db, MaintenanceItem, item_id, user, "保養項目")
    if not (body.interval_km or body.interval_months):
        raise HTTPException(422, "請至少設定里程或時間其中一項間隔")
    for k, v in body.model_dump().items():
        setattr(item, k, v)
    db.commit()
    return _item_out(item)


@router.delete("/maintenance-items/{item_id}", status_code=204)
def delete_item(item_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    item = owned_row(db, MaintenanceItem, item_id, user, "保養項目")
    db.delete(item)
    db.commit()


# ───── 進廠／維修履歷 ─────
def _visit_out(db: Session, visit: ServiceVisit) -> dict:
    lines = db.scalars(select(ServiceLine).where(ServiceLine.visit_id == visit.id).order_by(ServiceLine.id)).all()
    names = {i.id: i.name for i in db.scalars(select(MaintenanceItem).where(MaintenanceItem.vehicle_id == visit.vehicle_id))}
    attachments = db.scalar(
        select(func.count()).select_from(Attachment).where(
            Attachment.owner_type == "service_visit", Attachment.owner_id == visit.id
        )
    )
    return {
        "id": visit.id, "vehicle_id": visit.vehicle_id, "visit_date": visit.visit_date,
        "odometer_km": visit.odometer_km, "shop": visit.shop, "total_cost": visit.total_cost,
        "technician_note": visit.technician_note, "attachment_count": attachments,
        "lines": [
            {"id": l.id, "item_id": l.item_id, "item_name": names.get(l.item_id), "description": l.description,
             "part_name": l.part_name, "cost": l.cost}
            for l in lines
        ],
    }


def _write_visit(db: Session, visit: ServiceVisit, body: ServiceVisitIn, vehicle_id: int) -> None:
    valid_items = {i for (i,) in db.execute(select(MaintenanceItem.id).where(MaintenanceItem.vehicle_id == vehicle_id))}
    for line in body.lines:
        if line.item_id is not None and line.item_id not in valid_items:
            raise HTTPException(422, "明細含有不屬於此車輛的保養項目")
        if not (line.item_id or line.description.strip() or line.part_name.strip()):
            raise HTTPException(422, "明細至少需選擇項目或填寫說明")
    visit.visit_date, visit.odometer_km = body.visit_date, body.odometer_km
    visit.shop, visit.technician_note = body.shop, body.technician_note
    visit.total_cost = body.total_cost if body.total_cost is not None else sum(l.cost for l in body.lines)
    db.flush()
    for old in db.scalars(select(ServiceLine).where(ServiceLine.visit_id == visit.id)):
        db.delete(old)
    db.flush()
    for line in body.lines:
        db.add(ServiceLine(visit_id=visit.id, **line.model_dump()))


@router.get("/vehicles/{vehicle_id}/service-visits")
def list_visits(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    get_vehicle_or_404(db, vehicle_id, user)
    rows = db.scalars(
        select(ServiceVisit).where(ServiceVisit.vehicle_id == vehicle_id)
        .order_by(ServiceVisit.visit_date.desc(), ServiceVisit.id.desc())
    )
    return [_visit_out(db, v) for v in rows]


@router.post("/vehicles/{vehicle_id}/service-visits", status_code=201)
def create_visit(
    vehicle_id: int, body: ServiceVisitIn, user: AppUser = Depends(require_user), db: Session = Depends(get_db)
):
    get_vehicle_or_404(db, vehicle_id, user)
    visit = ServiceVisit(vehicle_id=vehicle_id, visit_date=body.visit_date, odometer_km=body.odometer_km)
    db.add(visit)
    _write_visit(db, visit, body, vehicle_id)
    db.commit()
    return _visit_out(db, visit)


@router.put("/service-visits/{visit_id}")
def update_visit(
    visit_id: int, body: ServiceVisitIn, user: AppUser = Depends(require_user), db: Session = Depends(get_db)
):
    visit = owned_row(db, ServiceVisit, visit_id, user, "進廠記錄")
    _write_visit(db, visit, body, visit.vehicle_id)
    db.commit()
    return _visit_out(db, visit)


@router.delete("/service-visits/{visit_id}", status_code=204)
def delete_visit(visit_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    visit = owned_row(db, ServiceVisit, visit_id, user, "進廠記錄")
    db.delete(visit)
    db.commit()
