"""使用者資料匯出／匯入（JSON 與 CSV）。

匯入採「取代目前使用者的全部資料」，主鍵一律重新配發並重建關聯，不會碰到其他使用者的資料。
附件圖片檔案不在 JSON 內，請以備份指令一併備份 uploads 目錄。
"""

import csv
import io
import zipfile
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Date, DateTime, delete, select
from sqlalchemy.orm import Session

from app.models import (
    Attachment, ComplianceItem, EnergyLog, EtagEntry, Expense, Fine, MaintenanceItem,
    OdometerAdjustment, ServiceLine, ServiceVisit, UserSetting, Vehicle, utcnow,
)

FORMAT_VERSION = 2
ACCEPTED_VERSIONS = {1, 2}

# (名稱, Model, {外鍵欄位: 父表名稱})；依相依順序排列
SPEC: list[tuple[str, type, dict[str, str]]] = [
    ("vehicles", Vehicle, {}),
    ("odometer_adjustments", OdometerAdjustment, {"vehicle_id": "vehicles"}),
    ("energy_logs", EnergyLog, {"vehicle_id": "vehicles"}),
    ("maintenance_items", MaintenanceItem, {"vehicle_id": "vehicles"}),
    ("service_visits", ServiceVisit, {"vehicle_id": "vehicles"}),
    ("service_lines", ServiceLine, {"visit_id": "service_visits", "item_id": "maintenance_items"}),
    ("compliance_items", ComplianceItem, {"vehicle_id": "vehicles"}),
    ("fines", Fine, {"vehicle_id": "vehicles"}),
    ("expenses", Expense, {"vehicle_id": "vehicles"}),
    ("etag_entries", EtagEntry, {"vehicle_id": "vehicles"}),
]
SKIP_COLUMNS = {"deleted_at", "user_id"}
USER_SETTING_KEYS = {"anomaly_drop_pct", "lead_days"}


def _columns(model) -> list[str]:
    return [c.name for c in model.__table__.columns if c.name not in SKIP_COLUMNS]


def _serialize(obj, cols: list[str]) -> dict:
    out = {}
    for c in cols:
        v = getattr(obj, c)
        out[c] = v.isoformat() if isinstance(v, (date, datetime)) else v
    return out


def export_json(db: Session, user_id: int) -> dict:
    data: dict = {"app": "motoq", "version": FORMAT_VERSION, "exported_at": utcnow().isoformat()}
    vehicles = db.scalars(
        select(Vehicle).where(Vehicle.user_id == user_id, Vehicle.deleted_at.is_(None)).order_by(Vehicle.id)
    ).all()
    vehicle_ids = {v.id for v in vehicles}
    ids: dict[str, set[int]] = {"vehicles": vehicle_ids}
    for name, model, fks in SPEC:
        if model is Vehicle:
            rows = vehicles
        else:
            q = select(model).order_by(model.id)
            if "vehicle_id" in fks:
                q = q.where(model.vehicle_id.in_(vehicle_ids))
            else:  # service_lines
                q = q.where(model.visit_id.in_(ids["service_visits"]))
            if hasattr(model, "deleted_at"):
                q = q.where(model.deleted_at.is_(None))
            rows = db.scalars(q).all()
        ids[name] = {r.id for r in rows}
        data[name] = [_serialize(r, _columns(model)) for r in rows]
    data["settings"] = {
        s.key: s.value
        for s in db.scalars(select(UserSetting).where(UserSetting.user_id == user_id))
        if s.key in USER_SETTING_KEYS
    }
    return data


def export_csv_zip(db: Session, user_id: int) -> bytes:
    data = export_json(db, user_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, model, _ in SPEC:
            s = io.StringIO()
            writer = csv.DictWriter(s, fieldnames=_columns(model))
            writer.writeheader()
            writer.writerows(data[name])
            zf.writestr(f"{name}.csv", "﻿" + s.getvalue())  # BOM：Excel 開啟中文不亂碼
    return buf.getvalue()


def _coerce(model, row: dict) -> dict:
    cols = {c.name: c for c in model.__table__.columns}
    out = {}
    for k, v in row.items():
        if k not in cols or k in SKIP_COLUMNS:
            continue
        if v is not None:
            if isinstance(cols[k].type, DateTime):
                v = datetime.fromisoformat(v)
            elif isinstance(cols[k].type, Date):
                v = date.fromisoformat(v)
        out[k] = v
    return out


def validate_payload(payload: dict) -> dict[str, int]:
    if not isinstance(payload, dict) or payload.get("app") != "motoq":
        raise ValueError("不是 MotoQ 匯出檔")
    if payload.get("version") not in ACCEPTED_VERSIONS:
        raise ValueError(f"不支援的格式版本：{payload.get('version')}")
    counts: dict[str, int] = {}
    known: dict[str, set] = {}
    for name, model, fks in SPEC:
        rows = payload.get(name, [])
        if not isinstance(rows, list):
            raise ValueError(f"{name} 格式錯誤")
        known[name] = set()
        for r in rows:
            if not isinstance(r, dict) or "id" not in r:
                raise ValueError(f"{name} 含有格式錯誤的資料列")
            _coerce(model, r)  # 觸發日期格式錯誤
            for col, parent in fks.items():
                ref = r.get(col)
                if ref is None and col == "item_id":
                    continue
                if ref not in known[parent]:
                    raise ValueError(f"{name} 含有不存在的關聯（{col}={ref}）")
            known[name].add(r["id"])
        counts[name] = len(rows)
    return counts


def snapshot_db(db: Session, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"pre-import-{utcnow():%Y%m%d-%H%M%S}.db"
    conn = db.get_bind().connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        conn.exec_driver_sql("VACUUM INTO ?", (str(target),))
    finally:
        conn.close()
    return target


def replace_user_data(db: Session, user_id: int, payload: dict, uploads_root: Path) -> dict[str, int]:
    counts = validate_payload(payload)

    # 既有資料（含軟刪除）與其附件一併移除
    for att in db.scalars(select(Attachment).where(Attachment.user_id == user_id)):
        for rel in (att.file_path, att.thumb_path):
            (uploads_root / rel).unlink(missing_ok=True)
    db.execute(delete(Attachment).where(Attachment.user_id == user_id))
    for v in db.scalars(select(Vehicle).where(Vehicle.user_id == user_id)):
        db.delete(v)  # ORM 刪除 + 外鍵 CASCADE
    db.flush()

    id_map: dict[str, dict[int, int]] = {}
    for name, model, fks in SPEC:
        id_map[name] = {}
        for r in payload.get(name, []):
            values = _coerce(model, r)
            old_id = values.pop("id")
            for col, parent in fks.items():
                if values.get(col) is not None:
                    values[col] = id_map[parent][values[col]]
            if model is Vehicle:
                values["user_id"] = user_id
            obj = model(**values)
            db.add(obj)
            db.flush()
            id_map[name][old_id] = obj.id

    db.execute(delete(UserSetting).where(UserSetting.user_id == user_id))
    for k, v in (payload.get("settings") or {}).items():
        if k in USER_SETTING_KEYS:
            db.add(UserSetting(user_id=user_id, key=k, value=v))
    db.commit()
    return counts
