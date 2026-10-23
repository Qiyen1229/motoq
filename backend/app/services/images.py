"""圖片處理：移除 EXIF（含 GPS）、HEIC 轉 JPEG、縮圖與壓縮。全部在本機完成。"""

import hashlib
import io
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

try:  # iPhone 的 HEIC
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:  # pragma: no cover
    pass

MAX_BYTES = 15 * 1024 * 1024
MAX_EDGE = 1600
THUMB_EDGE = 320
Image.MAX_IMAGE_PIXELS = 60_000_000


class ImageError(ValueError):
    pass


@dataclass
class Stored:
    file_path: str  # 相對於 uploads 根目錄
    thumb_path: str
    size_bytes: int
    sha256: str


def _to_jpeg(img: Image.Image, edge: int, quality: int) -> bytes:
    img = img.copy()
    img.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    if img.mode not in ("RGB", "L"):
        # 透明背景鋪白，避免轉 JPEG 變黑
        bg = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)  # 不帶 exif
    return buf.getvalue()


def store_image(data: bytes, uploads_root: Path, user_id: int) -> Stored:
    if len(data) > MAX_BYTES:
        raise ImageError("檔案超過 15 MB")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise ImageError("無法辨識的圖片格式（支援 JPEG、PNG、WEBP、HEIC）") from e
    img = ImageOps.exif_transpose(img)  # 先依 EXIF 轉正，再丟棄所有中繼資料

    full = _to_jpeg(img, MAX_EDGE, 80)
    thumb = _to_jpeg(img, THUMB_EDGE, 70)

    folder = uploads_root / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex
    (folder / f"{name}.jpg").write_bytes(full)
    (folder / f"{name}_t.jpg").write_bytes(thumb)
    return Stored(
        file_path=f"{user_id}/{name}.jpg",
        thumb_path=f"{user_id}/{name}_t.jpg",
        size_bytes=len(full),
        sha256=hashlib.sha256(full).hexdigest(),
    )
