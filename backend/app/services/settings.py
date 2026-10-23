from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting, UserSetting

USER_DEFAULTS: dict = {
    "anomaly_drop_pct": 15.0,
    "lead_days": [30, 7, 1],
    "parking_cities": ["TPE"],  # 每日自動檢查停車費欠費的縣市
    "parking_auto_check": False,  # 預設關閉：自動檢查會把你的車牌送到各縣市政府的查詢服務
    "etag_low_balance": 200,  # etag 餘額低於此金額時列入待辦（0 = 不提醒）
}


def global_defaults() -> dict:
    s = get_settings()
    return {
        "registration_mode": "closed",
        "session_days": s.session_days,
        "login_max_failures": s.login_max_failures,
        "login_window_seconds": s.login_window_seconds,
    }


def get_global(db: Session) -> dict:
    merged = global_defaults()
    for row in db.scalars(select(AppSetting)):
        if row.key in merged:
            merged[row.key] = row.value
    return merged


def set_global(db: Session, values: dict) -> dict:
    for key, value in values.items():
        row = db.get(AppSetting, key)
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=key, value=value))
    db.commit()
    return get_global(db)


def get_user_settings(db: Session, user_id: int) -> dict:
    merged = dict(USER_DEFAULTS)
    for row in db.scalars(select(UserSetting).where(UserSetting.user_id == user_id)):
        if row.key in merged:
            merged[row.key] = row.value
    return merged


def set_user_settings(db: Session, user_id: int, values: dict) -> dict:
    for key, value in values.items():
        row = db.get(UserSetting, (user_id, key))
        if row:
            row.value = value
        else:
            db.add(UserSetting(user_id=user_id, key=key, value=value))
    db.commit()
    return get_user_settings(db, user_id)
