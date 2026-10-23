from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.db import get_db
from app.models import AnnualReport, AppUser
from app.routers.vehicles import get_vehicle_or_404
from app.services import pdf as pdf_service
from app.services.attention import vehicle_label
from app.services.reports import annual_report, period_report

router = APIRouter(tags=["reports"])


@router.get("/vehicles/{vehicle_id}/reports/annual")
def get_annual(
    vehicle_id: int, year: int = Query(default_factory=lambda: date.today().year, ge=1990, le=2100),
    user: AppUser = Depends(require_user), db: Session = Depends(get_db),
):
    return annual_report(db, get_vehicle_or_404(db, vehicle_id, user), year)


@router.post("/vehicles/{vehicle_id}/reports/annual", status_code=201)
def save_annual(
    vehicle_id: int, year: int = Query(ge=1990, le=2100),
    user: AppUser = Depends(require_user), db: Session = Depends(get_db),
):
    v = get_vehicle_or_404(db, vehicle_id, user)
    snap = annual_report(db, v, year)
    row = AnnualReport(vehicle_id=v.id, year=year, trigger="manual", snapshot=_jsonable(snap))
    db.add(row)
    db.commit()
    return {"id": row.id, "year": year, "generated_at": row.generated_at}


@router.get("/vehicles/{vehicle_id}/reports/annual/saved")
def saved_annual(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    get_vehicle_or_404(db, vehicle_id, user)
    rows = db.scalars(
        select(AnnualReport).where(AnnualReport.vehicle_id == vehicle_id).order_by(AnnualReport.year.desc(), AnnualReport.id.desc())
    )
    return [
        {"id": r.id, "year": r.year, "trigger": r.trigger, "generated_at": r.generated_at, "snapshot": r.snapshot}
        for r in rows
    ]


@router.get("/reports/compare")
def compare(
    vehicle_ids: str = Query(description="以逗號分隔的車輛 id，至少 2 台"),
    from_: date = Query(alias="from"), to: date = Query(),
    user: AppUser = Depends(require_user), db: Session = Depends(get_db),
):
    try:
        ids = [int(x) for x in vehicle_ids.split(",") if x.strip()]
    except ValueError as e:
        raise HTTPException(422, "vehicle_ids 格式錯誤") from e
    if len(set(ids)) < 2 or len(ids) > 6:
        raise HTTPException(422, "請選擇 2–6 台不同的車輛")
    if to < from_:
        raise HTTPException(422, "結束日期不可早於開始日期")
    out = []
    for vid in dict.fromkeys(ids):
        v = get_vehicle_or_404(db, vid, user)
        out.append({"vehicle": vehicle_label(v), "vehicle_type": v.vehicle_type, **period_report(db, v, from_, to)})
    return out


@router.get("/vehicles/{vehicle_id}/reports/service-history.html")
def history_html(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    v = get_vehicle_or_404(db, vehicle_id, user)
    return Response(pdf_service.build_html(db, v), media_type="text/html; charset=utf-8")


@router.get("/vehicles/{vehicle_id}/reports/service-history.pdf")
def history_pdf(vehicle_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    v = get_vehicle_or_404(db, vehicle_id, user)
    try:
        data = pdf_service.render_pdf(pdf_service.build_html(db, v))
    except (ImportError, OSError) as e:
        raise HTTPException(501, "此環境缺少 PDF 轉換所需的系統函式庫，請改用 HTML 版本列印") from e
    return Response(
        data, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="service-history-{v.id}.pdf"'},
    )


def _jsonable(obj):
    import json

    return json.loads(json.dumps(obj, default=str))
