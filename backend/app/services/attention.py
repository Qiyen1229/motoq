"""跨車輛的「待辦」彙整：保養、稅費、罰單、油耗異常。"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.compliance import KIND_LABEL, evaluate
from app.domain.efficiency import summarize
from sqlalchemy import func

from app.models import ComplianceItem, EtagEntry, Fine, ParkingCheck, Vehicle
from app.services.energy import load_state
from app.services.maintenance import item_statuses
from app.services.settings import get_user_settings

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def vehicle_label(v: Vehicle) -> str:
    return " ".join(x for x in (v.brand, v.model) if x) or v.plate or f"車輛 {v.id}"


def attention_for_vehicle(db: Session, v: Vehicle, settings: dict, today: date) -> list[dict]:
    items: list[dict] = []
    base = {"vehicle_id": v.id, "vehicle": vehicle_label(v)}
    state = load_state(db, v)

    for m in item_statuses(db, v, state, today):
        if m["state"] == "overdue":
            items.append({**base, "kind": "maintenance", "severity": "critical", "title": f"{m['name']} 已逾期",
                          "detail": _maint_detail(m, today), "link": "/maintenance"})
        elif m["state"] == "soon":
            items.append({**base, "kind": "maintenance", "severity": "warning", "title": f"{m['name']} 即將到期",
                          "detail": _maint_detail(m, today), "link": "/maintenance"})

    leads = settings["lead_days"]
    for c in db.scalars(select(ComplianceItem).where(ComplianceItem.vehicle_id == v.id, ComplianceItem.paid_date.is_(None))):
        st = evaluate(c.due_date, None, today, leads)
        label = KIND_LABEL.get(c.kind, c.kind)
        if st.state == "overdue":
            items.append({**base, "kind": "compliance", "severity": "critical", "title": f"{label} 已逾期 {-st.days_left} 天",
                          "detail": f"到期日 {c.due_date}", "link": "/compliance"})
        elif st.state == "due_soon":
            sev = "critical" if st.level >= len(leads) else "warning"
            items.append({**base, "kind": "compliance", "severity": sev, "title": f"{label} 剩 {st.days_left} 天",
                          "detail": f"到期日 {c.due_date}", "link": "/compliance"})

    for f in db.scalars(select(Fine).where(Fine.vehicle_id == v.id, Fine.paid_date.is_(None))):
        overdue = f.due_date is not None and f.due_date < today
        near = f.due_date is not None and f.due_date <= today + timedelta(days=30)
        sev = "critical" if overdue else "warning" if near else "info"
        when = f"繳費期限 {f.due_date}" if f.due_date else "未設定期限"
        items.append({**base, "kind": "fine", "severity": sev, "title": f"未繳罰單 ${f.amount}",
                      "detail": f"{f.violation or f.fine_no or '罰單'}・{when}", "link": "/expenses"})

    for pc in db.scalars(select(ParkingCheck).where(ParkingCheck.vehicle_id == v.id, ParkingCheck.total_count > 0)):
        payload = pc.payload or {}
        prosecuted = any(m.get("prosecuted") for m in payload.get("reminders", []))
        city = payload.get("city", pc.city)
        items.append({**base, "kind": "parking", "severity": "critical" if prosecuted else "warning",
                      "title": f"{city}停車費欠費 ${pc.total_amount:,.0f}",
                      "detail": f"{pc.total_count} 筆待繳・查詢於 {pc.checked_at:%m/%d %H:%M}"
                                + ("・已有移送強制執行" if prosecuted else ""),
                      "link": "/expenses?tab=parking"})

    threshold = settings.get("etag_low_balance", 0)
    if threshold:
        def _sum(kind: str) -> int:
            return db.scalar(select(func.coalesce(func.sum(EtagEntry.amount), 0)).where(
                EtagEntry.vehicle_id == v.id, EtagEntry.kind == kind)) or 0

        has_entries = db.scalar(select(EtagEntry.id).where(EtagEntry.vehicle_id == v.id).limit(1)) is not None
        balance = _sum("topup") - _sum("toll") + _sum("balance_adjust")
        if has_entries and balance < threshold:
            items.append({**base, "kind": "etag", "severity": "warning", "title": f"etag 餘額偏低 ${balance:,}",
                          "detail": f"低於提醒門檻 ${threshold:,}，記得儲值", "link": "/expenses?tab=etag"})

    summary = summarize(state.segments, drop_threshold=settings["anomaly_drop_pct"] / 100)
    if summary.warning:
        items.append({**base, "kind": "efficiency", "severity": "warning",
                      "title": "油耗異常下降", "detail": f"近 3 次比基準低 {summary.drop_pct:.0f}%，建議檢查保養", "link": "/"})
    return items


def _maint_detail(m: dict, today: date) -> str:
    """說明是哪一邊先到期：已逾期就講逾期的原因，其餘講剩餘量。"""
    parts = []
    km_over = m["remaining_km"] is not None and m["remaining_km"] <= 0
    time_over = m["date_by_time"] is not None and m["date_by_time"] <= today
    if km_over:
        parts.append(f"里程已超過 {-m['remaining_km']:,} km")
    elif m["remaining_km"] is not None:
        parts.append(f"里程剩 {m['remaining_km']:,} km")
    if time_over:
        parts.append(f"已超過時間期限（{m['date_by_time']}）")
    elif m["date_by_time"] is not None:
        parts.append(f"時間到期 {m['date_by_time']}")
    return "・".join(parts)


def build_attention(db: Session, user_id: int, today: date | None = None) -> list[dict]:
    today = today or date.today()
    settings = get_user_settings(db, user_id)
    vehicles = db.scalars(
        select(Vehicle).where(Vehicle.user_id == user_id, Vehicle.deleted_at.is_(None), Vehicle.status == "active")
    )
    out: list[dict] = []
    for v in vehicles:
        out.extend(attention_for_vehicle(db, v, settings, today))
    out.sort(key=lambda a: SEVERITY_ORDER[a["severity"]])
    return out
