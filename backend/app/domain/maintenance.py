"""保養預測（純函式）。

規則：里程與時間各自推算到期點，**先到者為準**。
里程預測日 = 今天 + 剩餘里程 ÷ 平均日行駛里程（以近 90 天里程回歸，資料不足時退回全期）。
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.dates import add_months


@dataclass(frozen=True)
class Baseline:
    date: date
    odometer: int


@dataclass(frozen=True)
class ItemStatus:
    state: str  # ok | soon | overdue | unknown
    basis: str | None  # km | time
    due_date: date | None
    due_km: int | None
    remaining_km: int | None
    remaining_days: int | None
    predicted_date_by_km: date | None
    date_by_time: date | None
    progress: float | None  # 0~1，超過 1 即逾期


def avg_daily_km(
    points: list[tuple[date, int]], today: date, window_days: int = 90, min_span_days: int = 14
) -> float | None:
    """平均日行駛里程。points 為 (日期, 總里程)。"""
    pts = sorted(set(points))
    if len(pts) < 2:
        return None

    def rate(sel: list[tuple[date, int]]) -> float | None:
        if len(sel) < 2:
            return None
        span = (sel[-1][0] - sel[0][0]).days
        gained = sel[-1][1] - sel[0][1]
        if span < min_span_days or gained <= 0:
            return None
        return gained / span

    recent = [p for p in pts if (today - p[0]).days <= window_days]
    return rate(recent) or rate(pts)


def evaluate_item(
    interval_km: int | None,
    interval_months: int | None,
    last: Baseline | None,
    current_km: int,
    today: date,
    daily_km: float | None,
    soon_ratio: float = 0.1,
) -> ItemStatus:
    if last is None or not (interval_km or interval_months):
        return ItemStatus("unknown", None, None, None, None, None, None, None, None)

    due_km = remaining_km = predicted_by_km = date_by_time = None
    progresses: list[float] = []
    soon = overdue = False

    if interval_km:
        due_km = last.odometer + interval_km
        remaining_km = due_km - current_km
        progresses.append((current_km - last.odometer) / interval_km)
        if remaining_km <= 0:
            overdue = True
            predicted_by_km = today
        else:
            soon = soon or remaining_km <= interval_km * soon_ratio
            if daily_km:
                predicted_by_km = today + timedelta(days=math.ceil(remaining_km / daily_km))

    if interval_months:
        date_by_time = add_months(last.date, interval_months)
        total_days = max((date_by_time - last.date).days, 1)
        elapsed = (today - last.date).days
        progresses.append(elapsed / total_days)
        left = (date_by_time - today).days
        if left <= 0:
            overdue = True
        else:
            soon = soon or left <= total_days * soon_ratio

    candidates = [(d, b) for d, b in ((date_by_time, "time"), (predicted_by_km, "km")) if d]
    due_date, basis = (min(candidates, key=lambda c: (c[0], c[1] != "time")) if candidates else (None, None))
    if overdue and basis is None:
        basis = "km"

    return ItemStatus(
        state="overdue" if overdue else "soon" if soon else "ok",
        basis=basis,
        due_date=due_date,
        due_km=due_km,
        remaining_km=remaining_km,
        remaining_days=(due_date - today).days if due_date else None,
        predicted_date_by_km=predicted_by_km,
        date_by_time=date_by_time,
        progress=max(progresses) if progresses else None,
    )
