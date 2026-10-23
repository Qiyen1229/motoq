"""備份：SQLite 一致性快照 + uploads 目錄，打包成單一 tar.gz。"""

import tarfile
import tempfile
from pathlib import Path

from sqlalchemy import create_engine

from app.models import utcnow


def make_backup(data_dir: Path, out_dir: Path, keep: int = 14) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    db_file = data_dir / "motoq.db"
    if not db_file.exists():
        raise FileNotFoundError(f"找不到資料庫：{db_file}")
    target = out_dir / f"motoq-backup-{utcnow():%Y%m%d-%H%M%S-%f}.tar.gz"

    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "motoq.db"
        engine = create_engine(f"sqlite:///{db_file}")
        try:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.exec_driver_sql("VACUUM INTO ?", (str(snap),))
        finally:
            engine.dispose()
        with tarfile.open(target, "w:gz") as tar:
            tar.add(snap, arcname="motoq.db")
            uploads = data_dir / "uploads"
            if uploads.exists():
                tar.add(uploads, arcname="uploads")
    target.chmod(0o600)

    if keep > 0:
        old = sorted(out_dir.glob("motoq-backup-*.tar.gz"))[:-keep]
        for f in old:
            f.unlink(missing_ok=True)
    return target
