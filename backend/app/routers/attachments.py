from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.config import get_settings
from app.db import get_db
from app.models import AppUser, Attachment, ComplianceItem, EnergyLog, Expense, Fine, ServiceVisit
from app.routers.vehicles import get_vehicle_or_404
from app.services.images import ImageError, store_image

router = APIRouter(tags=["attachments"])

OWNER_MODELS = {
    "energy_log": EnergyLog,
    "service_visit": ServiceVisit,
    "compliance_item": ComplianceItem,
    "fine": Fine,
    "expense": Expense,
}


def _uploads_root() -> Path:
    return get_settings().data_dir / "uploads"


def _check_owner(db: Session, owner_type: str, owner_id: int, user: AppUser) -> None:
    model = OWNER_MODELS.get(owner_type)
    if not model:
        raise HTTPException(422, "不支援的附件對象")
    row = db.get(model, owner_id)
    if not row:
        raise HTTPException(404, "找不到附件所屬的記錄")
    get_vehicle_or_404(db, row.vehicle_id, user)


def _out(a: Attachment) -> dict:
    return {
        "id": a.id, "owner_type": a.owner_type, "owner_id": a.owner_id, "original_name": a.original_name,
        "size_bytes": a.size_bytes, "created_at": a.created_at,
        "url": f"/api/v1/attachments/{a.id}/file", "thumb_url": f"/api/v1/attachments/{a.id}/thumb",
    }


def _owned(db: Session, att_id: int, user: AppUser) -> Attachment:
    a = db.get(Attachment, att_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "找不到附件")
    return a


@router.get("/attachments")
def list_attachments(
    owner_type: str, owner_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)
):
    _check_owner(db, owner_type, owner_id, user)
    rows = db.scalars(
        select(Attachment).where(
            Attachment.user_id == user.id, Attachment.owner_type == owner_type, Attachment.owner_id == owner_id
        ).order_by(Attachment.id)
    )
    return [_out(a) for a in rows]


@router.post("/attachments", status_code=201)
async def upload(
    file: UploadFile,
    owner_type: str = Form(),
    owner_id: int = Form(),
    user: AppUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    _check_owner(db, owner_type, owner_id, user)
    data = await file.read(15 * 1024 * 1024 + 1)
    try:
        stored = store_image(data, _uploads_root(), user.id)
    except ImageError as e:
        raise HTTPException(422, str(e)) from e
    att = Attachment(
        user_id=user.id, owner_type=owner_type, owner_id=owner_id,
        file_path=stored.file_path, thumb_path=stored.thumb_path,
        original_name=(file.filename or "")[:120], size_bytes=stored.size_bytes, sha256=stored.sha256,
    )
    db.add(att)
    db.commit()
    return _out(att)


def _serve(att: Attachment, rel: str) -> FileResponse:
    root = _uploads_root().resolve()
    path = (root / rel).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "檔案不存在")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/attachments/{att_id}/file")
def get_file(att_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    a = _owned(db, att_id, user)
    return _serve(a, a.file_path)


@router.get("/attachments/{att_id}/thumb")
def get_thumb(att_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    a = _owned(db, att_id, user)
    return _serve(a, a.thumb_path)


@router.delete("/attachments/{att_id}", status_code=204)
def delete_attachment(att_id: int, user: AppUser = Depends(require_user), db: Session = Depends(get_db)):
    a = _owned(db, att_id, user)
    root = _uploads_root().resolve()
    for rel in (a.file_path, a.thumb_path):
        p = (root / rel).resolve()
        if root in p.parents:
            p.unlink(missing_ok=True)
    db.delete(a)
    db.commit()
