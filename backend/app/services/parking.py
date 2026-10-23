"""全國路邊停車費（欠費）查詢。

使用交通部「全國路邊停車費查詢 API 服務規範」，各縣市政府各自提供端點（TDX 公開、免審核、無驗證碼）：
  GET {base}/Parking/PayBill/CarID/{車牌}/CarType/{C|M|O}
官方限制：每秒單一 IP 不得超過 1 次呼叫。這裡以全域間隔與短時間快取遵守。
"""

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from app.services.http import open_url

_SUFFIX = "/CarID/{car_id}/CarType/{car_type}"
MIN_INTERVAL = 1.2  # 秒，略高於官方每秒 1 次的上限
CACHE_TTL = 300
CAR_TYPES = {"C": "汽車", "M": "機車", "O": "其他（拖車等）"}


@dataclass(frozen=True)
class City:
    code: str
    name: str
    base: str  # 到 /Parking/PayBill 為止（含）
    pay_url: str = ""
    insecure: bool = False  # 官方僅提供未加密（http）連線


def _c(code, name, base, pay_url="", insecure=False):
    return City(code, name, base, pay_url, insecure)


CITIES: dict[str, City] = {c.code: c for c in [
    _c("TPE", "臺北市", "https://trafficapi.pma.gov.taipei/Parking/PayBill", "https://parkingfee.pma.gov.taipei/"),
    _c("NWT", "新北市", "https://trafficapi.traffic.ntpc.gov.tw/Parking/PayBill", "https://parkweb.traffic.ntpc.gov.tw/"),
    _c("TAO", "桃園市", "https://bill-epark.tycg.gov.tw/Parking/PayBill", "https://epark.tycg.gov.tw/"),
    _c("TXG", "臺中市", "http://tcparkingapi.taichung.gov.tw:8081/NationalParkingPayBillInquiry.Api/Parking/PayBill", insecure=True),
    _c("TNN", "臺南市", "https://parkingbill.tainan.gov.tw/Parking/PayBill"),
    _c("KHH", "高雄市", "https://kpp.tbkc.gov.tw/parking/V1/parking/PayBill"),
    _c("KEE", "基隆市", "https://park.klcg.gov.tw/TrafficPayBill/Parking/PayBill"),
    _c("HSZ", "新竹市", "https://his.futek.com.tw:5443/TrafficPayBill/Parking/PayBill"),
    _c("HSQ", "新竹縣", "https://hcpark.hchg.gov.tw/NationalParkingPayBillInquiry/Parking/PayBill"),
    _c("MIA", "苗栗縣", "https://miaoliparking.jotangi.com.tw/TrafficPayBill/Parking/PayBill"),
    _c("CHA", "彰化縣", "https://chpark.chcg.gov.tw/TrafficPayBill/Parking/PayBill"),
    _c("NAN", "南投縣", "https://parking.nantou.gov.tw/TrafficPayBill/Parking/PayBill"),
    _c("YUN", "雲林縣", "https://parking.yunlin.gov.tw/TrafficPayBill/Parking/PayBill"),
    _c("CYQ", "嘉義縣", "https://8voc0wuf1g.execute-api.ap-southeast-1.amazonaws.com/default/chiayi/Parking/PayBill"),
    _c("CYI", "嘉義市", "https://parking.chiayi.gov.tw/cypark/api/Parking/PayBill"),
    _c("PIF", "屏東縣", "https://8voc0wuf1g.execute-api.ap-southeast-1.amazonaws.com/default/pingtung/Parking/PayBill"),
    _c("ILA", "宜蘭縣", "https://billparking.e-land.gov.tw/Parking/PayBill"),
    _c("HUA", "花蓮縣", "https://hl.parchere.com.tw/TrafficPayBill/Parking/PayBill"),
    _c("TTT", "臺東縣", "https://tt.guoyun.com.tw/TrafficPayBill/Parking/PayBill"),
    _c("PEN", "澎湖縣", "https://parking.penghu.gov.tw/TrafficPayBill/Parking/PayBill"),
    _c("KIN", "金門縣", "https://km.guoyun.com.tw/TrafficPayBill/Parking/PayBill"),
]}
DEFAULT_PAY_URL = "https://tdx.transportdata.tw/"

_lock = threading.Lock()
_last_call = 0.0
_cache: dict[tuple[str, str, str], tuple[float, dict]] = {}


class ParkingLookupError(Exception):
    pass


def normalize_plate(plate: str) -> str:
    """去空白、轉大寫；英數交界補上連字號（ABC1234 → ABC-1234），符合官方範例格式。"""
    p = re.sub(r"[\s　]", "", plate).upper()
    if not re.fullmatch(r"[A-Z0-9-]{2,10}", p):
        raise ParkingLookupError("車牌格式不正確，請輸入英數字（可含連字號）")
    if "-" not in p:
        m = re.fullmatch(r"([A-Z]+)(\d+)", p) or re.fullmatch(r"(\d+)([A-Z]+)", p)
        if m:
            p = f"{m.group(1)}-{m.group(2)}"
    return p


def car_type_for(vehicle_type: str) -> str:
    return "C" if vehicle_type == "car" else "M"


def _parse_bill(b: dict) -> dict:
    return {
        "bill_no": b.get("BillNo") or "",
        "parking_date": b.get("ParkingDate") or "",
        "pay_limit_date": b.get("PayLimitDate") or "",
        "status": b.get("BillStatus"),
        "hours": b.get("ParkingHours"),
        "amount": b.get("Amount") or 0,
        "pay_amount": b.get("PayAmount") if b.get("PayAmount") is not None else b.get("Amount") or 0,
    }


def parse_response(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ParkingLookupError("查詢服務回應格式異常")
    if str(data.get("Status", "")).upper() != "SUCCESS":
        raise ParkingLookupError(str(data.get("Message") or "查詢服務回報失敗"))
    r = data.get("Result") or {}
    bills = [_parse_bill(b) for b in (r.get("Bills") or []) if isinstance(b, dict)]
    reminders = []
    for m in r.get("Reminders") or []:
        if not isinstance(m, dict):
            continue
        reminders.append(
            {
                "reminder_no": m.get("ReminderNo") or "",
                "limit_date": m.get("ReminderLimitDate") or "",
                "amount": m.get("Amount") or 0,
                "extra_charge": m.get("ExtraCharge") or 0,
                "pay_amount": m.get("PayAmount") if m.get("PayAmount") is not None else m.get("Amount") or 0,
                "prosecuted": bool(m.get("IsProsecuted")),
                "prosecute_limit_date": m.get("ProsecuteLimitDate") or "",
                "bills": [_parse_bill(b) for b in (m.get("Bills") or []) if isinstance(b, dict)],
            }
        )
    # 催繳單內含的停車單不重複計入總額：優先採官方 TotalAmount
    total = r.get("TotalAmount")
    if total is None:
        total = sum(b["pay_amount"] for b in bills) + sum(m["pay_amount"] for m in reminders)
    return {
        "total_count": r.get("TotalCount") if r.get("TotalCount") is not None else len(bills) + len(reminders),
        "total_amount": total,
        "bills": bills,
        "reminders": reminders,
        "update_time": r.get("UpdateTime") or "",
    }


def lookup(city_code: str, plate: str, car_type: str, timeout: int = 8) -> dict:
    global _last_call
    city = CITIES.get(city_code)
    if not city:
        raise ParkingLookupError("不支援的縣市")
    if car_type not in CAR_TYPES:
        raise ParkingLookupError("車種代碼不正確")
    car_id = normalize_plate(plate)
    key = (city.code, car_id, car_type)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_TTL:
        return {**hit[1], "cached": True}

    with _lock:  # 全域序列化，確保對官方 API 每秒不超過 1 次
        wait = MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        url = city.base + _SUFFIX.format(car_id=urllib.parse.quote(car_id, safe=""), car_type=car_type)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MotoQ", "Accept": "application/json"})
        try:
            with open_url(req, timeout=timeout) as resp:
                raw = resp.read(1_000_000)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ParkingLookupError(f"無法連線到{city.name}的查詢服務，請稍後再試") from e
        finally:
            _last_call = time.monotonic()

    try:
        result = parse_response(json.loads(raw))
    except ValueError as e:
        raise ParkingLookupError(f"{city.name}的查詢服務回應無法解析") from e
    result.update(plate=car_id, car_type=car_type, car_type_label=CAR_TYPES[car_type], city=city.name,
                  city_code=city.code, pay_url=city.pay_url or DEFAULT_PAY_URL, insecure=city.insecure, cached=False)
    _cache[key] = (time.monotonic(), result)
    if len(_cache) > 400:
        _cache.pop(next(iter(_cache)))
    return result
