from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings
from app.routers import (
    admin, attachments, auth, dashboard, data, energy, fuel, maintenance, parking, records, reports,
    vehicles,
)

import logging

from app.db import _session_factory
from app.models import AppUser

logger = logging.getLogger("motoq")
BACKEND_DIR = Path(__file__).resolve().parent.parent


def run_migrations() -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")


def ensure_default_admin() -> None:
    """若設定了預設管理員帳號密碼，確保系統中存在該管理者且處於啟用狀態。"""
    settings = get_settings()
    if not settings.default_admin_username or not settings.default_admin_password:
        return

    from sqlalchemy import func, select
    from app import auth

    with _session_factory()() as db:
        user = db.scalar(
            select(AppUser).where(func.lower(AppUser.username) == settings.default_admin_username.lower())
        )
        if not user:
            user = AppUser(
                username=settings.default_admin_username,
                password_hash=auth.hash_password(settings.default_admin_password),
                role="admin",
                status="active",
            )
            db.add(user)
            db.commit()
            logger.info("已建立預設管理員帳號: %s", settings.default_admin_username)
        else:
            updated = False
            if user.role != "admin":
                user.role = "admin"
                updated = True
            if user.status != "active":
                user.status = "active"
                updated = True
            if updated:
                db.commit()
                logger.info("已更新管理員帳號 %s 權限為 admin 與 active", settings.default_admin_username)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    run_migrations()
    ensure_default_admin()
    scheduler = None
    if settings.scheduler_enabled:
        from app.scheduler import build_scheduler, refresh_fuel_prices as refresh_fuel_prices_now

        scheduler = build_scheduler()
        scheduler.start()
        scheduler.add_job(refresh_fuel_prices_now, id="fuel_prices_boot", replace_existing=True)  # 啟動後立刻抓一次
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(title="MotoQ", version="1.0.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")

    api = APIRouter(prefix="/api/v1")
    for module in (
        auth, admin, vehicles, energy, maintenance, records, attachments, reports, fuel, parking, dashboard, data,
    ):
        api.include_router(module.router)

    @api.get("/healthz")
    def healthz():
        return {"status": "ok"}

    app.include_router(api)

    dist = get_settings().frontend_dist
    if dist and dist.is_dir():
        root = dist.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404)
            candidate = (root / path).resolve()
            if path and candidate.is_file() and root in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(root / "index.html")

    return app


app = create_app()
