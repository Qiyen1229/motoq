"""中油牌價（政府資料開放平臺「中油主產品牌價」JSON）與單價建議。

來源：https://vipmbr.cpc.com.tw/opendata/mainprodlistprice
只取「汽柴油零售／中油自營站」的 92、95、98 與超級柴油。牌價生效日為民國 7 碼（如 1151012）。
"""

import json
import threading
import time
import urllib.request
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EnergyLog, FuelPrice
from app.services.http import open_url

CPC_URL = "https://vipmbr.cpc.com.tw/opendata/mainprodlistprice"
NAME_MAP = {"92無鉛汽油": "gas_92", "95無鉛汽油": "gas_95", "98無鉛汽油": "gas_98", "超級柴油": "diesel"}
PRODUCT_ORDER = ["gas_92", "gas_95", "gas_98", "diesel"]

REFRESH_AFTER_SECONDS = 6 * 3600  # 有人查看時，距上次成功更新超過 6 小時就重新抓
RETRY_AFTER_SECONDS = 15 * 60  # 失敗後至少隔 15 分鐘再試，避免拖慢頁面
_lock = threading.Lock()
_last_success = 0.0
_last_attempt = 0.0


def _roc_to_date(s: str) -> date | None:
    s = s.strip()
    if len(s) != 7 or not s.isdigit():
        return None
    try:
        return date(int(s[:3]) + 1911, int(s[3:5]), int(s[5:7]))
    except ValueError:
        return None


def parse_cpc(payload: str | bytes) -> tuple[dict[str, float], date | None]:
    """回傳 ({產品: 牌價}, 牌價生效日)。內容不是預期格式時回傳空結果。"""
    try:
        rows = json.loads(payload)
    except (ValueError, TypeError):
        return {}, None
    if not isinstance(rows, list):
        return {}, None
    prices: dict[str, float] = {}
    effective: date | None = None
    for r in rows:
        if not isinstance(r, dict):
            continue
        if "汽柴油零售" not in str(r.get("型別名稱", "")) or "中油自營站" not in str(r.get("交貨地點", "")):
            continue
        product = NAME_MAP.get(str(r.get("產品名稱", "")).strip())
        try:
            value = float(r.get("參考牌價_金額"))
        except (TypeError, ValueError):
            continue
        if product and product not in prices and 0 < value < 1000:
            prices[product] = value
            d = _roc_to_date(str(r.get("牌價生效日期", "")))
            if d and (effective is None or d > effective):
                effective = d
    return prices, effective


def fetch_cpc(timeout: int = 10) -> tuple[dict[str, float], date | None]:
    req = urllib.request.Request(CPC_URL, headers={"User-Agent": "Mozilla/5.0 MotoQ", "Accept": "application/json"})
    with open_url(req, timeout=timeout) as resp:
        return parse_cpc(resp.read(2_000_000))


def store_prices(db: Session, prices: dict[str, float], on: date | None = None, source: str = "cpc") -> int:
    on = on or date.today()
    for product, price in prices.items():
        row = db.get(FuelPrice, (on, product))
        if row:
            row.price, row.source = price, source
        else:
            db.add(FuelPrice(price_date=on, product=product, price=price, source=source))
    db.commit()
    return len(prices)


def refresh(db: Session) -> int:
    """立即向中油抓取並存檔；回傳更新的品項數（0 = 來源無法解析）。"""
    global _last_success, _last_attempt
    _last_attempt = time.monotonic()
    prices, effective = fetch_cpc()
    if not prices:
        return 0
    n = store_prices(db, prices, on=effective or date.today())
    _last_success = time.monotonic()
    return n


def ensure_fresh(db: Session) -> None:
    """有人查看油價時順手更新：資料過舊才抓，且失敗不丟例外。"""
    now = time.monotonic()
    has_rows = db.scalar(select(FuelPrice.product).limit(1)) is not None
    stale = (now - _last_success) > REFRESH_AFTER_SECONDS or not has_rows
    if not stale or (now - _last_attempt) < RETRY_AFTER_SECONDS or not _lock.acquire(blocking=False):
        return
    try:
        refresh(db)
    except Exception:  # 外部來源失敗不影響頁面
        pass
    finally:
        _lock.release()


def latest_summary(db: Session) -> list[dict]:
    """每種油品最新牌價，以及與上一次不同價格的差額。"""
    out = []
    for product in PRODUCT_ORDER:
        rows = db.scalars(
            select(FuelPrice).where(FuelPrice.product == product).order_by(FuelPrice.price_date.desc()).limit(60)
        ).all()
        if not rows:
            continue
        latest = rows[0]
        prev = next((r for r in rows[1:] if r.price != latest.price), None)
        out.append(
            {
                "product": product, "price": latest.price, "price_date": latest.price_date,
                "change": round(latest.price - prev.price, 2) if prev else None,
                "source": latest.source,
            }
        )
    return out


def latest_price(db: Session, product: str) -> FuelPrice | None:
    return db.scalar(select(FuelPrice).where(FuelPrice.product == product).order_by(FuelPrice.price_date.desc()).limit(1))


def suggest_price(db: Session, user_vehicle_ids: list[int], source: str, station: str) -> dict:
    """依油品與加油站建議單價。

    - 中油：直接採中油牌價（最新）。
    - 其他品牌：若你在該站、該油品「牌價生效日之後」有加過油，用那次的實付單價；否則以中油牌價為參考。
    - 電力：沿用你上次同來源的單價。
    """
    last_q = (
        select(EnergyLog)
        .where(EnergyLog.vehicle_id.in_(user_vehicle_ids), EnergyLog.deleted_at.is_(None),
               EnergyLog.energy_source == source)
        .order_by(EnergyLog.log_date.desc(), EnergyLog.id.desc())
    )
    if source in NAME_MAP.values():
        ref = latest_price(db, source)
        station = (station or "").strip()
        is_cpc = station in ("", "中油") or station.startswith("中油")
        if not is_cpc:
            mine = db.scalar(last_q.where(EnergyLog.station == station).limit(1))
            if mine and (not ref or mine.log_date >= ref.price_date):
                return {"price": mine.unit_price, "basis": "last_at_station", "as_of": mine.log_date,
                        "note": f"你上次在「{station}」的實付單價"}
        if ref:
            note = f"中油牌價（{ref.price_date} 生效）"
            if not is_cpc:
                note += "，作為參考；實際請依站內價格調整"
            return {"price": ref.price, "basis": "cpc_reference", "as_of": ref.price_date, "note": note}
    mine = db.scalar(last_q.limit(1))
    if mine:
        return {"price": mine.unit_price, "basis": "last_same_source", "as_of": mine.log_date,
                "note": "你上次同類型的單價"}
    return {"price": None, "basis": None, "as_of": None, "note": ""}
