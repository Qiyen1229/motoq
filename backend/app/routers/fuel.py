from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.auth import require_admin, require_user
from app.db import get_db
from app.models import AppUser, FuelPrice
from app.schemas import FuelPriceIn
from app.services import fuel

router = APIRouter(tags=["fuel"])


@router.get("/fuel-prices/history")
def history(product: str = "gas_95", user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(FuelPrice).where(FuelPrice.product == product).order_by(FuelPrice.price_date.desc()).limit(120)
    )
    return [{"date": r.price_date, "price": r.price, "source": r.source} for r in rows]


@router.post("/fuel-prices", status_code=201)
def set_price(
    body: FuelPriceIn, request: Request, admin: AppUser = Depends(require_admin), db: Session = Depends(get_db)
):
    fuel.store_prices(db, {body.product: body.price}, on=body.price_date, source="manual")
    auth.log_event(db, "admin_fuel_price", request, username=admin.username, user_id=admin.id,
                   detail=f"{body.product}={body.price}")
    return {"ok": True}


@router.post("/fuel-prices/refresh")
def refresh_prices(request: Request, admin: AppUser = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        count = fuel.refresh(db)
    except Exception as e:  # 外部服務失敗不應造成 500
        raise HTTPException(502, f"無法取得中油牌價：{e.__class__.__name__}") from e
    if count == 0:
        raise HTTPException(502, "中油回應內容無法解析，請改用手動輸入")
    return {"updated": count}
