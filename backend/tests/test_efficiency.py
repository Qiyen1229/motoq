from datetime import date

import pytest

from app.domain.amounts import resolve_amounts
from app.domain.efficiency import LogPoint, compute_segments, full_to_full_segments, summarize


def P(id, day, odo, qty, full=True, price=30.0, missed=False, s0=None, s1=None):
    return LogPoint(id, date(2026, 1, day), odo, qty, price, round(qty * price), full, missed, s0, s1)


def test_full_to_full_basic():
    pts = [P(1, 1, 1000, 3.0), P(2, 10, 1120, 3.0), P(3, 20, 1250, 3.25)]
    segs = full_to_full_segments(pts)
    assert len(segs) == 2
    assert segs[0].distance_km == 120
    assert segs[0].efficiency == pytest.approx(40.0)
    assert segs[1].efficiency == pytest.approx(130 / 3.25)


def test_partial_fills_accumulate_into_next_full():
    pts = [P(1, 1, 1000, 3.0), P(2, 5, 1050, 1.0, full=False), P(3, 10, 1160, 3.0)]
    (seg,) = full_to_full_segments(pts)
    assert seg.distance_km == 160
    assert seg.energy == pytest.approx(4.0)
    assert seg.efficiency == pytest.approx(40.0)
    assert seg.cost == 120


def test_first_full_is_only_baseline():
    # 沒有前一次加滿，無法計算
    assert full_to_full_segments([P(1, 1, 1000, 3.0)]) == []
    assert full_to_full_segments([P(1, 1, 1000, 2.0, full=False), P(2, 5, 1050, 3.0)]) == []


def test_missed_refuel_excludes_segment_but_next_is_valid():
    pts = [
        P(1, 1, 1000, 3.0),
        P(2, 10, 1200, 3.0, missed=True),  # 中間漏記一次：整段不採計
        P(3, 20, 1320, 3.0),
    ]
    segs = full_to_full_segments(pts)
    assert [s.end_log_id for s in segs] == [3]


def test_unsorted_input_and_non_increasing_odometer():
    pts = [P(3, 20, 1250, 3.25), P(1, 1, 1000, 3.0), P(2, 10, 1000, 3.0)]  # 1→2 里程沒增加
    segs = full_to_full_segments(pts)
    assert [(s.start_log_id, s.end_log_id) for s in segs] == [(2, 3)]  # 無效區間略過，以 2 為新基準


def test_electric_soc_fallback():
    pts = [
        P(1, 1, 1000, 0, s1=100),
        P(2, 5, 1030, 0.9, full=False, price=5.0, s0=60, s1=80),
        P(3, 10, 1050, 0.6, full=False, price=5.0, s0=50, s1=70),
    ]
    segs = compute_segments(pts, "electric", battery_kwh=2.0)
    assert len(segs) == 2 and all(s.method == "soc" for s in segs)
    assert segs[0].energy == pytest.approx(0.8)  # (100-60)% × 2kWh
    assert segs[0].efficiency == pytest.approx(30 / 0.8)


def _effs(values):
    return [
        type("S", (), {"distance_km": 100, "energy": 100 / e, "cost": 100.0, "efficiency": e})()
        for e in values
    ]


def test_summary_warning_triggers_on_drop():
    s = summarize(_effs([40] * 10 + [32, 33, 31]))  # 近 3 次 ≈32，基準 40，下降 20%
    assert s.warning
    assert s.drop_pct == pytest.approx(20.0, abs=0.5)


def test_summary_no_warning_when_stable_or_few_data():
    assert not summarize(_effs([40] * 10 + [38, 39, 37])).warning
    assert not summarize(_effs([40, 30, 30])).warning  # 資料不足 6 筆
    assert summarize([]).avg_efficiency is None


def test_summary_weighted_average_is_distance_over_energy():
    s = summarize(_effs([40, 20]))
    # 200 km / (2.5 + 5) L
    assert s.avg_efficiency == pytest.approx(200 / 7.5)


@pytest.mark.parametrize(
    "q,p,t,expected",
    [(3.0, 30.0, None, (3.0, 30.0, 90)), (None, 30.0, 90, (3.0, 30.0, 90)), (3.0, None, 90, (3.0, 30.0, 90))],
)
def test_resolve_amounts(q, p, t, expected):
    assert resolve_amounts(q, p, t) == expected


def test_resolve_amounts_needs_two():
    with pytest.raises(ValueError):
        resolve_amounts(3.0, None, None)
