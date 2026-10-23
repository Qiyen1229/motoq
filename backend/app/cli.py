"""管理指令：
  uv run python -m app.cli create-user --username me [--admin]   # 互動輸入密碼；第一位使用者自動為管理員
  uv run python -m app.cli reset-password --username me
  uv run python -m app.cli backup --out ./backups --keep 14
  uv run python -m app.cli seed-demo                              # 建立示範資料與 demo 帳號
"""

import argparse
import getpass
import secrets
import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func, select

from app import auth
from app.config import get_settings
from app.db import _session_factory
from app.main import run_migrations
from app.models import (
    AppUser, ComplianceItem, EnergyLog, EtagEntry, Expense, Fine, MaintenanceItem,
    ServiceLine, ServiceVisit, Vehicle,
)
from app.domain.templates import template_for
from app.services.backup import make_backup


def _prompt_password() -> str:
    password = getpass.getpass("密碼（至少 8 碼）: ")
    if len(password) < 8:
        sys.exit("密碼至少 8 碼")
    if password != getpass.getpass("再輸入一次: "):
        sys.exit("兩次密碼不一致")
    return password


def create_user(args) -> None:
    run_migrations()
    with _session_factory()() as db:
        first = (db.scalar(select(func.count()).select_from(AppUser)) or 0) == 0
        if db.scalar(select(AppUser).where(AppUser.username == args.username)):
            sys.exit("帳號已存在；要重設密碼請用 reset-password")
        user = AppUser(
            username=args.username, password_hash=auth.hash_password(_prompt_password()),
            role="admin" if (first or args.admin) else "user", status="active",
        )
        db.add(user)
        db.commit()
        print(f"已建立 {user.role} 使用者 {user.username}")


def reset_password(args) -> None:
    run_migrations()
    with _session_factory()() as db:
        user = db.scalar(select(AppUser).where(AppUser.username == args.username))
        if not user:
            sys.exit("找不到使用者")
        user.password_hash = auth.hash_password(_prompt_password())
        db.commit()
        auth.revoke_user_sessions(db, user.id)
        print("密碼已更新，所有裝置需重新登入")


def backup(args) -> None:
    target = make_backup(get_settings().data_dir, Path(args.out), keep=args.keep)
    print(target)


def seed_demo(_args) -> None:
    """示範資料：一台機車（油耗末段刻意下降）與一台油電汽車，含保養、稅費、罰單等。"""
    run_migrations()
    settings = get_settings()
    today = date.today()
    password = secrets.token_urlsafe(12)
    with _session_factory()() as db:
        if db.scalar(select(func.count()).select_from(AppUser)):
            print("已有使用者資料，略過示範資料")
            return
        user = AppUser(username="demo", password_hash=auth.hash_password(password), role="admin", status="active")
        db.add(user)
        db.flush()

        # ── 機車（燃油）──
        moto = Vehicle(
            user_id=user.id, vehicle_type="scooter", energy_type="gasoline", brand="示範", model="125cc 機車",
            plate="ABC-1234", displacement_cc=125, default_energy_source="gas_95",
            purchase_date=today - timedelta(days=400), purchase_price=78000, initial_odometer_km=3200,
        )
        db.add(moto)
        db.flush()
        effs = [41, 42, 40, 43, 41, 42, 41, 40, 42, 41, 36, 34, 33]
        odo, day, price = 3200, today - timedelta(days=13 * 12 + 4), 30.2
        db.add(EnergyLog(vehicle_id=moto.id, log_date=day, odometer_km=odo, quantity=3.1, unit="L",
                         unit_price=price, total_amount=round(3.1 * price), is_full=True,
                         energy_source="gas_95", station="中油"))
        for i, eff in enumerate(effs):
            liters = 3.0 + (i % 3) * 0.2
            odo += round(liters * eff)
            day += timedelta(days=12)
            price += 0.1 * (i % 4 - 1)
            db.add(EnergyLog(vehicle_id=moto.id, log_date=day, odometer_km=odo, quantity=liters, unit="L",
                             unit_price=round(price, 1), total_amount=round(liters * price), is_full=True,
                             energy_source="gas_95", station="中油"))
        db.flush()

        items = {}
        for name, cat, km, months in template_for("scooter", "gasoline"):
            it = MaintenanceItem(vehicle_id=moto.id, name=name, category=cat, interval_km=km, interval_months=months,
                                 baseline_date=today - timedelta(days=380), baseline_km=3200)
            db.add(it)
            items[name] = it
        db.flush()
        visit = ServiceVisit(vehicle_id=moto.id, visit_date=today - timedelta(days=70), odometer_km=odo - 900,
                             shop="示範車行", total_cost=650, technician_note="換機油並檢查皮帶，狀況良好")
        db.add(visit)
        db.flush()
        db.add(ServiceLine(visit_id=visit.id, item_id=items["機油"].id, description="更換機油", part_name="0.8L 機油", cost=350))
        db.add(ServiceLine(visit_id=visit.id, item_id=items["齒輪油"].id, description="更換齒輪油", part_name="120ml", cost=300))

        db.add(ComplianceItem(vehicle_id=moto.id, kind="license_tax", due_date=today + timedelta(days=5), amount=1620,
                              recurrence_months=12))
        db.add(ComplianceItem(vehicle_id=moto.id, kind="compulsory_ins", due_date=today + timedelta(days=40), amount=1000,
                              provider="示範產險", recurrence_months=12))
        db.add(ComplianceItem(vehicle_id=moto.id, kind="emission_test", due_date=today + timedelta(days=200), amount=0,
                              recurrence_months=12))
        db.add(ComplianceItem(vehicle_id=moto.id, kind="license_tax", due_date=today - timedelta(days=360), amount=1620,
                              paid_date=today - timedelta(days=370), recurrence_months=12))
        db.add(Fine(vehicle_id=moto.id, fine_no="DEMO-A001", violation_date=today - timedelta(days=20),
                    violation="未依規定停車（示範）", location="示範路", amount=300, due_date=today + timedelta(days=25)))
        db.add(Expense(vehicle_id=moto.id, expense_date=today - timedelta(days=9), category="parking", amount=60, note="停車費"))
        db.add(EtagEntry(vehicle_id=moto.id, entry_date=today - timedelta(days=30), kind="topup", amount=500))
        db.add(EtagEntry(vehicle_id=moto.id, entry_date=today - timedelta(days=12), kind="toll", amount=40))

        # ── 油電汽車 ──
        car = Vehicle(
            user_id=user.id, vehicle_type="car", energy_type="hybrid", brand="示範", model="油電房車",
            plate="XYZ-5678", displacement_cc=1798, default_energy_source="gas_95",
            purchase_date=today - timedelta(days=900), purchase_price=860000, initial_odometer_km=12000,
        )
        db.add(car)
        db.flush()
        odo, day = 12000, today - timedelta(days=150)
        for i in range(6):
            liters = 28 + (i % 2) * 2
            odo += round(liters * 22)
            day += timedelta(days=24)
            db.add(EnergyLog(vehicle_id=car.id, log_date=day, odometer_km=odo, quantity=liters, unit="L",
                             unit_price=30.4, total_amount=round(liters * 30.4), is_full=True,
                             energy_source="gas_95", station="台塑"))
        for name, cat, km, months in template_for("car", "hybrid"):
            db.add(MaintenanceItem(vehicle_id=car.id, name=name, category=cat, interval_km=km, interval_months=months,
                                   baseline_date=today - timedelta(days=200), baseline_km=12000))
        db.add(ComplianceItem(vehicle_id=car.id, kind="voluntary_ins", due_date=today + timedelta(days=95), amount=14500,
                              provider="示範產險", recurrence_months=12))
        db.commit()

    cred = settings.data_dir / "DEMO_LOGIN.txt"
    cred.write_text(f"username: demo\npassword: {password}\n")
    cred.chmod(0o600)
    print(f"示範資料已建立；登入資訊寫在 {cred}")


def init_admin(_args) -> None:
    """依設定初始化預設最高權限管理員"""
    run_migrations()
    from app.main import ensure_default_admin

    ensure_default_admin()
    settings = get_settings()
    print(f"預設最高權限管理員 ({settings.default_admin_username}) 已確認存在並處於啟用狀態")


def main() -> None:
    parser = argparse.ArgumentParser(prog="motoq")
    sub = parser.add_subparsers(required=True)
    p = sub.add_parser("create-user")
    p.add_argument("--username", required=True)
    p.add_argument("--admin", action="store_true", help="指定為管理員（第一位使用者一律為管理員）")
    p.set_defaults(func=create_user)
    p = sub.add_parser("reset-password")
    p.add_argument("--username", required=True)
    p.set_defaults(func=reset_password)
    p = sub.add_parser("backup")
    p.add_argument("--out", default="./backups")
    p.add_argument("--keep", type=int, default=14)
    p.set_defaults(func=backup)
    p = sub.add_parser("seed-demo")
    p.set_defaults(func=seed_demo)
    p = sub.add_parser("init-admin")
    p.set_defaults(func=init_admin)
    args = parser.parse_args()
    args.func(args)



if __name__ == "__main__":
    main()
