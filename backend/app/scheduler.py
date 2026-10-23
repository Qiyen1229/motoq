"""進程內排程（APScheduler）。務必以單一 worker 執行，否則工作會重複觸發。"""

import logging
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app import auth
from app.db import _session_factory
from app.models import AnnualReport, Vehicle
from app.services import fuel
from app.services.reports import annual_report

log = logging.getLogger("motoq.scheduler")
TZ = "Asia/Taipei"


def generate_annual_reports(year: int | None = None) -> int:
    year = year or date.today().year
    created = 0
    with _session_factory()() as db:
        vehicles = db.scalars(select(Vehicle).where(Vehicle.deleted_at.is_(None))).all()
        for v in vehicles:
            exists = db.scalar(
                select(AnnualReport.id).where(
                    AnnualReport.vehicle_id == v.id, AnnualReport.year == year, AnnualReport.trigger == "auto"
                )
            )
            if exists:
                continue
            snap = annual_report(db, v, year)
            import json

            db.add(AnnualReport(vehicle_id=v.id, year=year, trigger="auto", snapshot=json.loads(json.dumps(snap, default=str))))
            created += 1
        db.commit()
    log.info("annual reports generated: %s", created)
    return created


def refresh_fuel_prices() -> None:
    try:
        with _session_factory()() as db:
            n = fuel.refresh(db)
        log.info("fuel prices updated: %s", n)
    except Exception as e:  # 外部來源不穩定，只記錄
        log.warning("fuel price refresh failed: %s", e.__class__.__name__)


def check_parking_fees() -> None:
    from app.routers.parking import run_auto_checks

    try:
        with _session_factory()() as db:
            n = run_auto_checks(db)
        log.info("parking auto checks: %s", n)
    except Exception as e:  # 外部服務不穩定，只記錄
        log.warning("parking auto check failed: %s", e.__class__.__name__)


def purge_sessions() -> None:
    with _session_factory()() as db:
        auth.purge_expired_sessions(db)


def build_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=TZ)
    sched.add_job(generate_annual_reports, CronTrigger(month=12, day=31, hour=23, minute=50, timezone=TZ),
                  id="annual_reports", replace_existing=True)
    sched.add_job(refresh_fuel_prices, CronTrigger(hour="*/3", minute=5, timezone=TZ), id="fuel_prices", replace_existing=True)
    # 官方系統每天 05:15–06:15 更新資料，避開該時段
    sched.add_job(check_parking_fees, CronTrigger(hour=7, minute=30, timezone=TZ), id="parking_checks", replace_existing=True)
    sched.add_job(purge_sessions, CronTrigger(hour=4, minute=0, timezone=TZ), id="purge_sessions", replace_existing=True)
    return sched
