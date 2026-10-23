from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.efficiency import summarize
from app.domain.reporting import cost_per_km, distance_in_range
from app.models import ComplianceItem, Expense, Fine, ServiceVisit, Vehicle
from app.services.energy import load_state

CATEGORIES = [
    ("energy", "能源"),
    ("maintenance", "保養維修"),
    ("tax", "稅金"),
    ("insurance", "保險"),
    ("inspection", "檢驗規費"),
    ("fines", "罰單"),
    ("other", "停車／其他"),
]
_COMPLIANCE_CATEGORY = {
    "license_tax": "tax", "fuel_fee": "tax",
    "compulsory_ins": "insurance", "voluntary_ins": "insurance",
    "inspection": "inspection", "emission_test": "inspection",
}


def _in(d: date | None, start: date, end: date) -> bool:
    return d is not None and start <= d <= end


def period_report(db: Session, vehicle: Vehicle, start: date, end: date) -> dict:
    st = load_state(db, vehicle)
    totals = {k: 0 for k, _ in CATEGORIES}
    monthly: dict[str, int] = {}

    def add(cat: str, amount: int, d: date) -> None:
        totals[cat] += amount
        key = f"{d.year}-{d.month:02d}"
        monthly[key] = monthly.get(key, 0) + amount

    for l in st.logs:
        if _in(l.log_date, start, end):
            add("energy", l.total_amount, l.log_date)
    for v in db.scalars(select(ServiceVisit).where(ServiceVisit.vehicle_id == vehicle.id)):
        if _in(v.visit_date, start, end):
            add("maintenance", v.total_cost, v.visit_date)
    for c in db.scalars(select(ComplianceItem).where(ComplianceItem.vehicle_id == vehicle.id)):
        if _in(c.paid_date, start, end):  # 以實際繳費日認列
            add(_COMPLIANCE_CATEGORY.get(c.kind, "other"), c.amount, c.paid_date)
    for f in db.scalars(select(Fine).where(Fine.vehicle_id == vehicle.id)):
        if _in(f.violation_date, start, end):
            add("fines", f.amount, f.violation_date)
    for e in db.scalars(select(Expense).where(Expense.vehicle_id == vehicle.id)):
        if _in(e.expense_date, start, end):
            add("energy" if e.category == "energy_subscription" else "other", e.amount, e.expense_date)

    total = sum(totals.values())
    distance = distance_in_range(st.odo_points, start, end)
    segs = [s for s in st.segments if _in(s.end_date, start, end)]
    summary = summarize(segs)
    return {
        "vehicle_id": vehicle.id,
        "start": start, "end": end, "days": (end - start).days + 1,
        "distance_km": distance,
        "total_cost": total,
        "cost_per_km": cost_per_km(total, distance),
        "categories": [{"key": k, "label": label, "amount": totals[k]} for k, label in CATEGORIES],
        "monthly": [{"month": m, "amount": a} for m, a in sorted(monthly.items())],
        "avg_efficiency": round(summary.avg_efficiency, 2) if summary.avg_efficiency else None,
        "efficiency_unit": "km/kWh" if vehicle.energy_type == "electric" else "km/L",
        "energy_cost_per_km": round(totals["energy"] / distance, 2) if distance > 0 else None,
    }


def annual_report(db: Session, vehicle: Vehicle, year: int) -> dict:
    r = period_report(db, vehicle, date(year, 1, 1), date(year, 12, 31))
    r["year"] = year
    return r
