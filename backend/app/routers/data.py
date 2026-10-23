import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app import auth
from app.auth import require_user
from app.config import get_settings
from app.db import get_db
from app.models import AppUser, utcnow
from app.schemas import UserSettingsIn
from app.services import dataio
from app.services.settings import get_user_settings, set_user_settings

router = APIRouter(tags=["data"])

MAX_IMPORT_BYTES = 20 * 1024 * 1024


@router.get("/data/export")
def export(
    format: str = Query("json", pattern="^(json|csv)$"),
    user: AppUser = Depends(require_user), db: Session = Depends(get_db),
):
    stamp = utcnow().strftime("%Y%m%d")
    if format == "json":
        body = json.dumps(dataio.export_json(db, user.id), ensure_ascii=False, indent=2)
        return Response(
            body, media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="motoq-{stamp}.json"'},
        )
    return Response(
        dataio.export_csv_zip(db, user.id), media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="motoq-{stamp}-csv.zip"'},
    )


@router.post("/data/import")
async def import_data(
    request: Request, file: UploadFile, dry_run: bool = True,
    user: AppUser = Depends(require_user), db: Session = Depends(get_db),
):
    raw = await file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "匯入檔過大（上限 20 MB）")
    try:
        payload = json.loads(raw)
        counts = dataio.validate_payload(payload)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(422, f"匯入檔無法解析：{e}") from e
    if dry_run:
        return {"dry_run": True, "counts": counts}
    settings = get_settings()
    snapshot = dataio.snapshot_db(db, settings.data_dir / "snapshots")
    dataio.replace_user_data(db, user.id, payload, settings.data_dir / "uploads")
    auth.log_event(db, "data_import", request, username=user.username, user_id=user.id, detail=str(counts))
    return {"dry_run": False, "counts": counts, "snapshot": snapshot.name}


@router.get("/settings")
def read_settings(user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    return get_user_settings(db, user.id)


@router.put("/settings")
def write_settings(body: UserSettingsIn, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    return set_user_settings(db, user.id, body.model_dump(exclude_none=True))
