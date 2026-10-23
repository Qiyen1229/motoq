from dataclasses import dataclass
from datetime import date

KIND_LABEL = {
    "license_tax": "牌照稅",
    "fuel_fee": "燃料使用費",
    "compulsory_ins": "強制險",
    "voluntary_ins": "任意險",
    "inspection": "定期檢驗（驗車）",
    "emission_test": "排氣檢驗",
    "other": "其他",
}
DEFAULT_LEAD_DAYS = [30, 7, 1]


@dataclass(frozen=True)
class ComplianceStatus:
    state: str  # paid | overdue | due_soon | ok
    days_left: int
    level: int  # 已跨過幾個提前天數門檻（0~len(lead_days)），越大越急迫


def evaluate(due_date: date, paid_date: date | None, today: date, lead_days: list[int] | None = None) -> ComplianceStatus:
    leads = sorted(set(lead_days or DEFAULT_LEAD_DAYS), reverse=True)
    days_left = (due_date - today).days
    if paid_date:
        return ComplianceStatus("paid", days_left, 0)
    level = sum(1 for d in leads if days_left <= d)
    if days_left < 0:
        return ComplianceStatus("overdue", days_left, len(leads))
    return ComplianceStatus("due_soon" if level else "ok", days_left, level)
