from datetime import date

import pytest

from app.domain.compliance import evaluate
from app.domain.dates import add_months
from app.domain.maintenance import Baseline, avg_daily_km, evaluate_item
from app.domain.reporting import distance_in_range
from app.domain.templates import template_for

TODAY = date(2026, 6, 1)


def test_add_months_clamps_day():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_avg_daily_km_recent_window_and_fallback():
    pts = [(date(2025, 1, 1), 0), (date(2025, 12, 1), 3000), (date(2026, 4, 2), 3000 + 0), (date(2026, 6, 1), 3600)]
    # 近 90 天：4/2 → 6/1（60 天、600 km）= 10 km/日
    assert avg_daily_km(pts, TODAY) == pytest.approx(10.0)
    # 近 90 天只有一點 → 退回全期
    assert avg_daily_km([(date(2025, 1, 1), 0), (date(2026, 1, 1), 3650)], TODAY) == pytest.approx(10.0)
    assert avg_daily_km([(date(2026, 5, 1), 100)], TODAY) is None
    assert avg_daily_km([(date(2026, 5, 20), 100), (date(2026, 5, 21), 110)], TODAY) is None  # 跨度太短


def test_km_first_when_riding_a_lot():
    # 每 5000 km 或 6 個月；2 個月騎了 4600 km → 里程先到
    last = Baseline(date(2026, 4, 1), 10000)
    s = evaluate_item(5000, 6, last, 14600, TODAY, daily_km=70)
    assert s.basis == "km" and s.state == "soon"  # 剩 400 km ≤ 10%（500 km）
    assert s.remaining_km == 400
    assert s.predicted_date_by_km == date(2026, 6, 7)  # 400/70 = 5.7 → 6 天
    assert s.due_date == date(2026, 6, 7)


def test_time_first_when_barely_riding():
    last = Baseline(date(2025, 12, 15), 10000)
    s = evaluate_item(5000, 6, last, 10300, TODAY, daily_km=2)
    assert s.basis == "time"
    assert s.date_by_time == date(2026, 6, 15)
    assert s.state == "soon"  # 剩 14 天 ≤ 約 18 天（10%）


def test_overdue_by_either_side():
    last = Baseline(date(2025, 1, 1), 0)
    assert evaluate_item(5000, 6, last, 1000, TODAY, 5).state == "overdue"  # 時間逾期
    assert evaluate_item(5000, None, Baseline(date(2026, 5, 1), 0), 5200, TODAY, 5).state == "overdue"  # 里程逾期


def test_ok_and_unknown_and_no_daily_rate():
    last = Baseline(date(2026, 5, 20), 10000)
    s = evaluate_item(5000, 12, last, 10100, TODAY, None)
    assert s.state == "ok" and s.predicted_date_by_km is None
    assert s.basis == "time"  # 只能用時間推算
    assert evaluate_item(5000, 12, None, 10100, TODAY, 5).state == "unknown"
    assert evaluate_item(None, None, last, 10100, TODAY, 5).state == "unknown"


def test_km_only_item_without_rate_has_no_date():
    s = evaluate_item(1000, None, Baseline(date(2026, 5, 1), 0), 400, TODAY, None)
    assert s.state == "ok" and s.due_date is None and s.remaining_km == 600


@pytest.mark.parametrize(
    "days,paid,state,level",
    [(45, None, "ok", 0), (30, None, "due_soon", 1), (7, None, "due_soon", 2), (1, None, "due_soon", 3),
     (0, None, "due_soon", 3), (-1, None, "overdue", 3), (-5, date(2026, 5, 1), "paid", 0)],
)
def test_compliance_levels(days, paid, state, level):
    from datetime import timedelta

    st = evaluate(TODAY + timedelta(days=days), paid, TODAY)
    assert (st.state, st.level) == (state, level)


def test_compliance_custom_lead_days():
    from datetime import timedelta

    st = evaluate(TODAY + timedelta(days=45), None, TODAY, [60, 14])
    assert st.state == "due_soon" and st.level == 1


def test_distance_in_range():
    pts = [(date(2025, 12, 20), 1000), (date(2026, 3, 1), 1500), (date(2026, 12, 20), 3000), (date(2027, 1, 5), 3200)]
    assert distance_in_range(pts, date(2026, 1, 1), date(2026, 12, 31)) == 2000
    # 車輛當年才購入：以區間內第一點為起點
    assert distance_in_range([(date(2026, 2, 1), 10), (date(2026, 9, 1), 410)], date(2026, 1, 1), date(2026, 12, 31)) == 400
    assert distance_in_range([], date(2026, 1, 1), date(2026, 12, 31)) == 0


def test_templates_cover_every_type_combo():
    for vt in ("car", "scooter", "heavy_moto"):
        for et in ("gasoline", "electric", "hybrid"):
            if et == "hybrid" and vt != "car":
                continue
            tpl = template_for(vt, et)
            assert tpl and all(km or mo for _, _, km, mo in tpl)
    names = {n for n, *_ in template_for("car", "electric")}
    assert "機油" not in names  # 電動車沒有機油
