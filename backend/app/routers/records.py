from datetime import date

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.domain.compliance import KIND_LABEL, evaluate
from app.domain import license_tax
from app.domain.dates import add_months
from app.models import AppUser, ComplianceItem, EtagEntry, Expense, Fine, Vehicle
from app.routers._common import owned_row
from app.routers.vehicles import get_vehicle_or_404
from app.schemas import ComplianceIn, EtagIn, ExpenseIn, FineIn, PayIn
from app.services import fines as fine_service
from app.services.attention import vehicle_label
from app.services.settings import get_user_settings

router = APIRouter(tags=["records"])


def _row(obj, *cols: str) -> dict:
    return {c: getattr(obj, c) for c in ("id", "vehicle_id", *cols)}


# ───────────── 稅費與到期 ─────────────
def _compliance_out(c: ComplianceItem, today: date, leads: list[int]) -> dict:
    st = evaluate(c.due_date, c.paid_date, today, leads)
    return {
        **_row(c, "kind", "due_date", "amount", "paid_date", "provider", "policy_no", "recurrence_months", "note"),
        "kind_label": KIND_LABEL.get(c.kind, c.kind),
        "state": st.state, "days_left": st.days_left, "level": st.level,
    }


@router.get("/vehicles/{vehicle_id}/compliance")
def list_compliance(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    get_vehicle_or_404(db, vehicle_id, user)
    leads = get_user_settings(db, user.id)["lead_days"]
    rows = db.scalars(
        select(ComplianceItem).where(ComplianceItem.vehicle_id == vehicle_id)
        .order_by(ComplianceItem.paid_date.is_not(None), ComplianceItem.due_date)
    )
    return [_compliance_out(c, date.today(), leads) for c in rows]


@router.get("/vehicles/{vehicle_id}/compliance/estimate")
def compliance_estimate(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    """依排氣量／能源類型估算使用牌照稅，並給出下一個繳納期限（4/30）。"""
    v = get_vehicle_or_404(db, vehicle_id, user)
    est = license_tax.estimate(v.vehicle_type, v.energy_type, v.displacement_cc)
    due = license_tax.next_due_date()
    exists = db.scalar(
        select(ComplianceItem.id).where(
            ComplianceItem.vehicle_id == v.id, ComplianceItem.kind == "license_tax",
            ComplianceItem.due_date == due,
        )
    )
    return {
        "license_tax": {
            "amount": est.amount, "exempt": est.exempt, "note": est.note,
            "due_date": due, "already_created": exists is not None,
        },
        "fuel_fee": {"amount": None, "note": "燃料費（公路養管費）金額依車型與年度公告而異，請以繳款書為準"},
    }


@router.get("/compliance/upcoming")
def upcoming(user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    leads = get_user_settings(db, user.id)["lead_days"]
    rows = db.execute(
        select(ComplianceItem, Vehicle)
        .join(Vehicle, Vehicle.id == ComplianceItem.vehicle_id)
        .where(Vehicle.user_id == user.id, Vehicle.deleted_at.is_(None), ComplianceItem.paid_date.is_(None))
        .order_by(ComplianceItem.due_date)
    ).all()
    return [{**_compliance_out(c, date.today(), leads), "vehicle": vehicle_label(v)} for c, v in rows]


@router.post("/vehicles/{vehicle_id}/compliance", status_code=201)
def create_compliance(
    vehicle_id: int, body: ComplianceIn, user: AppUser = Depends(require_user), db: Session = Depends(get_db)
):
    get_vehicle_or_404(db, vehicle_id, user)
    c = ComplianceItem(vehicle_id=vehicle_id, **body.model_dump())
    db.add(c)
    db.commit()
    return _compliance_out(c, date.today(), get_user_settings(db, user.id)["lead_days"])


@router.put("/compliance/{item_id}")
def update_compliance(
    item_id: int, body: ComplianceIn, user: AppUser = Depends(require_user), db: Session = Depends(get_db)
):
    c = owned_row(db, ComplianceItem, item_id, user, "項目")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return _compliance_out(c, date.today(), get_user_settings(db, user.id)["lead_days"])


@router.delete("/compliance/{item_id}", status_code=204)
def delete_compliance(item_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    db.delete(owned_row(db, ComplianceItem, item_id, user, "項目"))
    db.commit()


@router.post("/compliance/{item_id}/pay")
def pay_compliance(
    item_id: int, body: PayIn, user: AppUser = Depends(require_user), db: Session = Depends(get_db)
):
    c = owned_row(db, ComplianceItem, item_id, user, "項目")
    if c.paid_date:
        raise HTTPException(409, "此項目已繳費")
    c.paid_date = body.paid_date or date.today()
    if body.amount is not None:
        c.amount = body.amount
    next_id = None
    if body.create_next:
        months = c.recurrence_months or 12
        nxt = ComplianceItem(
            vehicle_id=c.vehicle_id, kind=c.kind, due_date=add_months(c.due_date, months),
            amount=c.amount, provider=c.provider, recurrence_months=c.recurrence_months, note="",
        )
        db.add(nxt)
        db.flush()
        next_id = nxt.id
    db.commit()
    return {"paid": item_id, "next_id": next_id}


# ───────────── 罰單 ─────────────
def _fine_out(f: Fine, today: date) -> dict:
    out = _row(f, "fine_no", "violation_date", "violation", "location", "amount", "due_date", "paid_date", "source")
    out["overdue"] = f.paid_date is None and f.due_date is not None and f.due_date < today
    return out


@router.get("/vehicles/{vehicle_id}/fines")
def list_fines(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    get_vehicle_or_404(db, vehicle_id, user)
    rows = db.scalars(select(Fine).where(Fine.vehicle_id == vehicle_id).order_by(Fine.violation_date.desc()))
    return [_fine_out(f, date.today()) for f in rows]


@router.post("/vehicles/{vehicle_id}/fines", status_code=201)
def create_fine(vehicle_id: int, body: FineIn, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    get_vehicle_or_404(db, vehicle_id, user)
    f = Fine(vehicle_id=vehicle_id, source="manual", **body.model_dump())
    db.add(f)
    db.commit()
    return _fine_out(f, date.today())


@router.put("/fines/{fine_id}")
def update_fine(fine_id: int, body: FineIn, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    f = owned_row(db, Fine, fine_id, user, "罰單")
    for k, v in body.model_dump().items():
        setattr(f, k, v)
    db.commit()
    return _fine_out(f, date.today())


@router.delete("/fines/{fine_id}", status_code=204)
def delete_fine(fine_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    db.delete(owned_row(db, Fine, fine_id, user, "罰單"))
    db.commit()


@router.post("/vehicles/{vehicle_id}/fines/import")
async def import_fines(
    vehicle_id: int, file: UploadFile, user: AppUser = Depends(require_user), db: Session = Depends(get_db)
):
    get_vehicle_or_404(db, vehicle_id, user)
    try:
        rows = fine_service.parse_csv(await file.read())
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    existing = {n for (n,) in db.execute(select(Fine.fine_no).where(Fine.vehicle_id == vehicle_id)) if n}
    added = skipped = 0
    for r in rows:
        if r["fine_no"] and r["fine_no"] in existing:
            skipped += 1
            continue
        db.add(Fine(vehicle_id=vehicle_id, source="import", **r))
        existing.add(r["fine_no"])
        added += 1
    db.commit()
    return {"added": added, "skipped": skipped}


@router.post("/vehicles/{vehicle_id}/fines/lookup")
def lookup_fines(
    vehicle_id: int, provider: str = "mock", user: AppUser = Depends(require_user), db: Session = Depends(get_db)
):
    """未繳罰單查詢（預留模組）。目前只有示範提供者，結果不會自動存入。"""
    v = get_vehicle_or_404(db, vehicle_id, user)
    prov = fine_service.PROVIDERS.get(provider)
    if not prov:
        raise HTTPException(404, "未知的查詢來源")
    return {
        "provider": prov.name,
        "demo": prov.name == "mock",
        "results": [r.__dict__ for r in prov.lookup(v.plate)],
    }


# ───────────── 其他支出 ─────────────
@router.get("/vehicles/{vehicle_id}/expenses")
def list_expenses(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    get_vehicle_or_404(db, vehicle_id, user)
    rows = db.scalars(select(Expense).where(Expense.vehicle_id == vehicle_id).order_by(Expense.expense_date.desc(), Expense.id.desc()))
    return [_row(e, "expense_date", "category", "amount", "note") for e in rows]


@router.post("/vehicles/{vehicle_id}/expenses", status_code=201)
def create_expense(
    vehicle_id: int, body: ExpenseIn, user: AppUser = Depends(require_user), db: Session = Depends(get_db)
):
    get_vehicle_or_404(db, vehicle_id, user)
    e = Expense(vehicle_id=vehicle_id, **body.model_dump())
    db.add(e)
    db.commit()
    return _row(e, "expense_date", "category", "amount", "note")


@router.put("/expenses/{expense_id}")
def update_expense(
    expense_id: int, body: ExpenseIn, user: AppUser = Depends(require_user), db: Session = Depends(get_db)
):
    e = owned_row(db, Expense, expense_id, user, "支出")
    for k, v in body.model_dump().items():
        setattr(e, k, v)
    db.commit()
    return _row(e, "expense_date", "category", "amount", "note")


@router.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    db.delete(owned_row(db, Expense, expense_id, user, "支出"))
    db.commit()


# ───────────── etag ─────────────
def _etag_balance(db: Session, vehicle_id: int) -> int:
    def total(kind: str) -> int:
        return db.scalar(
            select(func.coalesce(func.sum(EtagEntry.amount), 0)).where(
                EtagEntry.vehicle_id == vehicle_id, EtagEntry.kind == kind
            )
        ) or 0

    return total("topup") - total("toll") + total("balance_adjust")


@router.get("/vehicles/{vehicle_id}/etag")
def list_etag(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    get_vehicle_or_404(db, vehicle_id, user)
    rows = db.scalars(select(EtagEntry).where(EtagEntry.vehicle_id == vehicle_id).order_by(EtagEntry.entry_date.desc(), EtagEntry.id.desc()))
    return {
        "balance": _etag_balance(db, vehicle_id),
        "entries": [_row(e, "entry_date", "kind", "amount", "note") for e in rows],
    }


@router.post("/vehicles/{vehicle_id}/etag", status_code=201)
def create_etag(vehicle_id: int, body: EtagIn, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    get_vehicle_or_404(db, vehicle_id, user)
    if body.kind != "balance_adjust" and body.amount < 0:
        raise HTTPException(422, "儲值與通行費金額需為正數；校正才可為負")
    e = EtagEntry(vehicle_id=vehicle_id, **body.model_dump())
    db.add(e)
    db.commit()
    return {"balance": _etag_balance(db, vehicle_id), **_row(e, "entry_date", "kind", "amount", "note")}


@router.delete("/etag/{entry_id}", status_code=204)
def delete_etag(entry_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    db.delete(owned_row(db, EtagEntry, entry_id, user, "etag 記錄"))
    db.commit()
