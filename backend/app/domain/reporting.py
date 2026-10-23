"""年度持有成本與里程（純函式）。"""

from datetime import date


def distance_in_range(points: list[tuple[date, int]], start: date, end: date) -> int:
    """區間行駛里程：end 以前最後一點 − start 前一天以前最後一點（無則取區間內第一點）。"""
    pts = sorted(points)
    upto_end = [p for p in pts if p[0] <= end]
    if not upto_end:
        return 0
    last = upto_end[-1][1]
    before = [p for p in pts if p[0] < start]
    if before:
        first = before[-1][1]
    else:
        inside = [p for p in pts if start <= p[0] <= end]
        first = inside[0][1] if inside else last
    return max(last - first, 0)


def cost_per_km(total: float, distance: int) -> float | None:
    return round(total / distance, 2) if distance > 0 else None
