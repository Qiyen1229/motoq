from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MOTOQ_", env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")
    cookie_secure: bool = False  # 放在 HTTPS 反向代理後面時設為 true
    session_days: int = 30
    frontend_dist: Path | None = None
    login_max_failures: int = 5
    login_window_seconds: int = 600
    setup_token: str | None = None  # 設定後，第一位（管理員）註冊必須提供此 token
    scheduler_enabled: bool = True
    default_admin_username: str | None = None
    default_admin_password: str | None = None  # 請以環境變數 MOTOQ_DEFAULT_ADMIN_PASSWORD 設定

    @property
    def db_path(self) -> Path:
        return self.data_dir / "motoq.db"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
