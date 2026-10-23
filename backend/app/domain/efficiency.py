"""油耗／電耗計算（純函式，不碰資料庫）。

方法：充滿到充滿（full-to-full）。兩次「加滿」之間的距離，除以其間（含後者）所有加入的能源量。
區間內有標記「前次漏記」者整段不納入。電動車若沒有足夠的充滿區間，可退回以電量 % 估算。
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class LogPoint:
    id: int
    log_date: date
    odometer: int  # 已套用儀表更換偏移的總里程
    quantity: float
    unit_price: float
    total_amount: int
    is_full: bool
    missed_before: bool = False
    start_soc: int | None = None
    end_soc: int | None = None


@dataclass(frozen=True)
class Segment:
    start_log_id: int
    end_log_id: int
    start_date: date
    end_date: date
    distance_km: int
    energy: float
    cost: float
    efficiency: float  # km / (L|kWh)
    cost_per_km: float
    method: str  # "full" | "soc"


@dataclass(frozen=True)
class Summary:
    segment_count: int
    total_distance_km: int
    total_energy: float
    total_cost: float
    avg_efficiency: float | None
    cost_per_km: float | None
    last_efficiency: float | None
    recent_avg: float | None
    baseline_avg: float | None
    drop_pct: float | None
    warning: bool


def _sorted(points: list[LogPoint]) -> list[LogPoint]:
    return sorted(points, key=lambda p: (p.log_date, p.odometer, p.id))


def full_to_full_segments(points: list[LogPoint]) -> list[Segment]:
    segments: list[Segment] = []
    anchor: LogPoint | None = None
    energy = cost = 0.0
    broken = False
    for p in _sorted(points):
        if anchor is None:
            if p.is_full:
                anchor = p
            continue
        energy += p.quantity
        cost += p.total_amount
        broken = broken or p.missed_before
        if not p.is_full:
            continue
        distance = p.odometer - anchor.odometer
        if not broken and distance > 0 and energy > 0:
            segments.append(
                Segment(
                    start_log_id=anchor.id,
                    end_log_id=p.id,
                    start_date=anchor.log_date,
                    end_date=p.log_date,
                    distance_km=distance,
                    energy=round(energy, 3),
                    cost=cost,
                    efficiency=distance / energy,
                    cost_per_km=cost / distance,
                    method="full",
                )
            )
        anchor, energy, cost, broken = p, 0.0, 0.0, False
    return segments


def soc_segments(points: list[LogPoint], battery_kwh: float) -> list[Segment]:
    """電動車：相鄰兩筆都有電量 %，以 (上次充後 % − 本次充前 %) × 電池容量 估算耗電。"""
    segments: list[Segment] = []
    ordered = _sorted(points)
    for prev, cur in zip(ordered, ordered[1:]):
        if cur.missed_before or prev.end_soc is None or cur.start_soc is None:
            continue
        used_pct = prev.end_soc - cur.start_soc
        distance = cur.odometer - prev.odometer
        if used_pct <= 0 or distance <= 0:
            continue
        energy = used_pct / 100 * battery_kwh
        cost = energy * cur.unit_price
        segments.append(
            Segment(
                start_log_id=prev.id,
                end_log_id=cur.id,
                start_date=prev.log_date,
                end_date=cur.log_date,
                distance_km=distance,
                energy=round(energy, 3),
                cost=cost,
                efficiency=distance / energy,
                cost_per_km=cost / distance,
                method="soc",
            )
        )
    return segments


def compute_segments(
    points: list[LogPoint], energy_type: str = "gasoline", battery_kwh: float | None = None
) -> list[Segment]:
    full = full_to_full_segments(points)
    if energy_type == "electric" and battery_kwh and len(full) < 2:
        estimated = soc_segments(points, battery_kwh)
        if len(estimated) > len(full):
            return estimated
    return full


def summarize(
    segments: list[Segment],
    drop_threshold: float = 0.15,
    recent_n: int = 3,
    baseline_n: int = 10,
    min_baseline: int = 3,
) -> Summary:
    if not segments:
        return Summary(0, 0, 0.0, 0.0, None, None, None, None, None, None, False)
    distance = sum(s.distance_km for s in segments)
    energy = sum(s.energy for s in segments)
    cost = sum(s.cost for s in segments)
    effs = [s.efficiency for s in segments]

    recent_avg = baseline_avg = drop_pct = None
    warning = False
    if len(effs) >= recent_n + min_baseline:
        recent = effs[-recent_n:]
        baseline = effs[-(recent_n + baseline_n) : -recent_n]
        recent_avg = sum(recent) / len(recent)
        baseline_avg = sum(baseline) / len(baseline)
        drop_pct = (baseline_avg - recent_avg) / baseline_avg * 100
        warning = recent_avg < baseline_avg * (1 - drop_threshold)

    return Summary(
        segment_count=len(segments),
        total_distance_km=distance,
        total_energy=round(energy, 3),
        total_cost=cost,
        avg_efficiency=distance / energy if energy else None,
        cost_per_km=cost / distance if distance else None,
        last_efficiency=effs[-1],
        recent_avg=recent_avg,
        baseline_avg=baseline_avg,
        drop_pct=drop_pct,
        warning=warning,
    )
