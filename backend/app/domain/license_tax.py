"""使用牌照稅（自用）估算。

依「使用牌照稅法」自用乘人小客車與機車的稅額級距（臺北市稅捐稽徵處公告表）。
- 完全以電能為動力之電動車：免徵至 2030-12-31（民國 119 年底）。
- 機車 150cc 以下免徵；151–250cc 800 元；251cc 以上與小客車同級距。
- 僅適用「自用」車輛；營業用、貨車等稅額不同，不在估算範圍。
"""

from dataclasses import dataclass
from datetime import date

EV_EXEMPT_UNTIL = date(2030, 12, 31)

# (排氣量上限 cc, 年稅額)；最後一級為 8400cc 以上
_CAR_TABLE: list[tuple[int, int]] = [
    (500, 1620), (600, 2160), (1200, 4320), (1800, 7120), (2400, 11230), (3000, 15210),
    (3600, 28220), (4200, 28220), (4800, 46170), (5400, 46170), (6000, 69690), (6600, 69690),
    (7200, 117000), (7800, 117000), (8400, 151200),
]
_TOP = 151200


@dataclass(frozen=True)
class TaxEstimate:
    amount: int | None
    exempt: bool
    note: str


def _lookup(cc: int) -> int:
    for limit, amount in _CAR_TABLE:
        if cc <= limit:
            return amount
    return _TOP


def estimate(vehicle_type: str, energy_type: str, displacement_cc: int | None, today: date | None = None) -> TaxEstimate:
    today = today or date.today()
    if energy_type == "electric":
        if today <= EV_EXEMPT_UNTIL:
            return TaxEstimate(0, True, "純電動車免徵使用牌照稅（至 2030-12-31）")
        return TaxEstimate(None, False, "電動車免徵期限已過，請依當時公告的馬力級距確認稅額")
    if not displacement_cc:
        return TaxEstimate(None, False, "請先在車輛資料填寫排氣量，才能估算牌照稅")
    if vehicle_type != "car" and displacement_cc <= 150:
        return TaxEstimate(0, True, "機車 150cc 以下免徵使用牌照稅")
    if vehicle_type != "car" and displacement_cc <= 250:
        return TaxEstimate(800, False, "機車 151–250cc：每年 800 元（自用）")
    amount = _lookup(displacement_cc)
    return TaxEstimate(amount, False, f"排氣量 {displacement_cc}cc 的自用稅額（營業用等稅額不同）")


def next_due_date(today: date | None = None) -> date:
    """牌照稅每年 4 月繳納，期限為 4/30；已過則算明年。"""
    today = today or date.today()
    this_year = date(today.year, 4, 30)
    return this_year if today <= this_year else date(today.year + 1, 4, 30)
